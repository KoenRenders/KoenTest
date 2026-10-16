"""Counting the opens and the clicks of a letter without knowing who (CR-37, #2027).

Each mail carries one **code** made while the mail is rendered and stored nowhere: the
letter's id, a random part and a signature (`kernel/signing.py`), so the portal can
recognise its own codes without a list. A pixel counts an open, a redirect counts a
click. An event is a row of letter, code, link and day — no address, no delivery, no IP,
no device, no time of day (`LetterEvent`). Counting the different codes gives *how many
people*; one code counts once however often it is opened or clicked.

The links of a letter are rewritten on the HTML **as rendered**, after the blocks are
built, so the links of an activity block and of a button are counted too and the design
holds when the letter's text moves editor. The destination is read from `letter_links`,
never from the request, so the click route cannot be turned into an open redirect.

A code that does not verify answers like one that does (the pixel) or like a link that
is gone (the click): the address is no oracle. A failed write never blocks the reader.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.newsletter.models import (
    Delivery,
    DeliveryStatus,
    LetterEvent,
    LetterLink,
    Newsletter,
)
from app.kernel.clock import belgian_today

logger = logging.getLogger(__name__)

#: The signing context of a code (`kernel/signing.py`): a code is no unsubscribe link.
CODE_CONTEXT = "newsletter-count"

#: Where a click and a pixel are answered, under the letter's origin.
CLICK_PATH = "/nieuwsbrief/k/"
PIXEL_PATH = "/nieuwsbrief/o/"

#: The one-pixel picture every code answers with: 43 bytes, transparent.
PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

#: A link longer than this is left as it is: it does not fit a unique key, and nobody
#: writes one by hand.
MAX_URL = 2000

#: A letter's own unsubscribe addresses are never counted or changed (CR-05 §3.4).
_NEVER_COUNTED = ("/nieuwsbrief/uitschrijven/",)

_HREF = re.compile(r"""(<a\b[^>]*?\bhref\s*=\s*)("([^"]*)"|'([^']*)')""", re.I)


# ── The code ─────────────────────────────────────────────────────────────────


def make_code(letter_id: int) -> str:
    """A code for one mail of this letter: `<letter id>.<random>.<signature>`."""
    from app.kernel.signing import sign

    random = secrets.token_hex(12)
    return f"{letter_id}.{random}.{sign(CODE_CONTEXT, letter_id, random)}"


def letter_id_of(code: str) -> Optional[int]:
    """The letter a code names, or None for anything the portal did not make."""
    from app.kernel.signing import verify

    number, _dot, rest = (code or "").partition(".")
    random, _dot, signature = rest.partition(".")
    # ASCII digits only and a length no letter id reaches: `int()` raises on a longer run.
    if not (number.isascii() and number.isdigit() and len(number) <= 18):
        return None
    if not random or not signature or len(code) > 80:
        return None
    if not verify(CODE_CONTEXT, int(number), random, signature=signature):
        return None
    return int(number)


# ── Rewriting a letter ───────────────────────────────────────────────────────


def _counted(url: str) -> bool:
    if not url.lower().startswith(("http://", "https://")) or len(url) > MAX_URL:
        return False
    if any(part in url for part in _NEVER_COUNTED):
        return False
    return CLICK_PATH not in url


def _link_row(db: Session, letter_id: int, url: str) -> LetterLink:
    """The row of an address, made if it is not there. Two mails rendered at once may both
    try: the unique key refuses the second, whose savepoint is undone and which then reads
    the first's row."""
    # An explicit savepoint, not a context manager (as `kernel/jobs.py`): the unique key may
    # refuse the row, and only this row is undone.
    savepoint = db.begin_nested()
    try:
        row = LetterLink(newsletter_id=letter_id, url=url)
        db.add(row)
        db.flush()
        savepoint.commit()
        return row
    except IntegrityError:
        savepoint.rollback()
        return db.query(LetterLink).filter_by(newsletter_id=letter_id, url=url).one()


def link_ids(db: Session, letter_id: int, urls: list[str]) -> dict[str, int]:
    """The id of each address in the letter's link store; an address met for the first
    time gets a row (two mails rendered at once make one: the unique key decides)."""
    wanted = sorted(set(urls))
    if not wanted:
        return {}
    found = {
        url: link_id
        for link_id, url in db.query(LetterLink.id, LetterLink.url)
        .filter(LetterLink.newsletter_id == letter_id, LetterLink.url.in_(wanted))
        .all()
    }
    for url in (url for url in wanted if url not in found):
        found[url] = _link_row(db, letter_id, url).id
    return found


def track_links(db: Session, letter: Newsletter, html: str, *, code: str, base: str) -> str:
    """The HTML with every `http` and `https` link sent through the portal's click
    address. `mailto:`, `tel:`, in-page anchors, the unsubscribe link and a link that
    already goes through the portal stay as they are, so rendering twice does not wrap a
    link twice."""
    found = [
        html_lib.unescape(m.group(3) if m.group(3) is not None else m.group(4))
        for m in _HREF.finditer(html)
    ]
    ids = link_ids(db, letter.id, [url for url in found if _counted(url)])
    if not ids:
        return html

    def swap(match: re.Match) -> str:
        raw = match.group(3) if match.group(3) is not None else match.group(4)
        link_id = ids.get(html_lib.unescape(raw))
        if link_id is None:
            return match.group(0)
        target = html_lib.escape(f"{base}{CLICK_PATH}{code}/{link_id}")
        return f'{match.group(1)}"{target}"'

    return _HREF.sub(swap, html)


def pixel_html(code: str, *, base: str) -> str:
    """The one-pixel picture at the end of a letter."""
    src = html_lib.escape(f"{base}{PIXEL_PATH}{code}.gif")
    return f'<img src="{src}" width="1" height="1" alt="" style="display:block;border:0">'


# ── Counting ─────────────────────────────────────────────────────────────────


def _letter_exists(db: Session, letter_id: int) -> bool:
    return db.query(Newsletter.id).filter(Newsletter.id == letter_id).first() is not None


def _write(db: Session, letter_id: int, code: str, link_id: Optional[int]) -> None:
    """One event, once: a second write of the same code and link does nothing. Never
    raises — a count lost is better than a reader stopped."""
    try:
        savepoint = db.begin_nested()
        try:
            db.add(
                LetterEvent(
                    newsletter_id=letter_id, code=code, link_id=link_id, day=belgian_today()
                )
            )
            db.flush()
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            return  # this code already counted: once is the rule
        db.commit()
    except Exception:  # noqa: BLE001 — a failed count must not stop the reader
        db.rollback()
        logger.exception("Count of a newsletter event failed")


def record_open(db: Session, code: str) -> None:
    """Count an open. A code that does not verify, or of a letter this tenant does not
    have, counts nothing."""
    letter_id = letter_id_of(code)
    if letter_id is None or not _letter_exists(db, letter_id):
        return
    _write(db, letter_id, code, None)


def record_click(db: Session, code: str, link_id: int) -> Optional[str]:
    """Count a click and answer the address it goes to; None when the code does not
    verify or the link belongs to another letter (the route answers 404)."""
    letter_id = letter_id_of(code)
    if letter_id is None:
        return None
    link = (
        db.query(LetterLink)
        .filter(LetterLink.id == link_id, LetterLink.newsletter_id == letter_id)
        .first()
    )
    if link is None:
        return None
    url = link.url
    _write(db, letter_id, code, link.id)
    return url


# ── The result ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LinkResult:
    url: str
    clicked: int


@dataclass(frozen=True)
class LetterResult:
    """What was counted for one letter. A percentage is None while nothing was sent."""

    sent: int
    opened: int
    clicked: int
    links: tuple[LinkResult, ...]

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def opened_pct(self) -> Optional[int]:
        return _pct(self.opened, self.sent)

    @property
    def clicked_pct(self) -> Optional[int]:
        return _pct(self.clicked, self.sent)


def _pct(part: int, whole: int) -> Optional[int]:
    """A share in whole percent, never above 100: a resent mail is a second code and
    can make the codes outnumber the mails (a small, accepted overcount)."""
    if not whole:
        return None
    return min(100, round(100 * part / whole))


def results_of(db: Session, letter_ids: list[int]) -> dict[int, LetterResult]:
    """The result of each letter: mails sent, different codes that opened, different codes
    that clicked anything, and per link the different codes that clicked it."""
    if not letter_ids:
        return {}
    sent = dict(
        db.query(Delivery.newsletter_id, func.count())
        .filter(Delivery.newsletter_id.in_(letter_ids), Delivery.status == DeliveryStatus.SENT)
        .group_by(Delivery.newsletter_id)
        .all()
    )
    opened = dict(
        db.query(LetterEvent.newsletter_id, func.count(func.distinct(LetterEvent.code)))
        .filter(LetterEvent.newsletter_id.in_(letter_ids), LetterEvent.link_id.is_(None))
        .group_by(LetterEvent.newsletter_id)
        .all()
    )
    clicked = dict(
        db.query(LetterEvent.newsletter_id, func.count(func.distinct(LetterEvent.code)))
        .filter(LetterEvent.newsletter_id.in_(letter_ids), LetterEvent.link_id.isnot(None))
        .group_by(LetterEvent.newsletter_id)
        .all()
    )
    per_link = dict(
        db.query(LetterEvent.link_id, func.count(func.distinct(LetterEvent.code)))
        .filter(LetterEvent.newsletter_id.in_(letter_ids), LetterEvent.link_id.isnot(None))
        .group_by(LetterEvent.link_id)
        .all()
    )
    links: dict[int, list[LinkResult]] = {}
    for link_id, letter_id, url in (
        db.query(LetterLink.id, LetterLink.newsletter_id, LetterLink.url)
        .filter(LetterLink.newsletter_id.in_(letter_ids))
        .order_by(LetterLink.id)
        .all()
    ):
        links.setdefault(letter_id, []).append(
            LinkResult(url=url, clicked=per_link.get(link_id, 0))
        )
    return {
        letter_id: LetterResult(
            sent=sent.get(letter_id, 0),
            opened=opened.get(letter_id, 0),
            clicked=clicked.get(letter_id, 0),
            links=tuple(links.get(letter_id, ())),
        )
        for letter_id in letter_ids
    }

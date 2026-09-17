"""The newsletter: subscribers, audiences, letters and sending (CR-05, #984).

Everything deterministic lives here. Raakje's drafting is a separate module
(``drafting.py``) that only ever proposes text; it never reaches the functions
that pick recipients or send.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.i18n import _

from app.domains.newsletter.models import (
    AUDIENCE_BOTH,
    AUDIENCE_MEMBERS,
    AUDIENCE_NON_MEMBERS,
    AUDIENCES,
    DELIVERY_FAILED,
    DELIVERY_MEMBER,
    DELIVERY_QUEUED,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    DELIVERY_SUBSCRIBER,
    ERASED_ADDRESS,
    LETTER_DRAFT,
    LETTER_SENDING,
    LETTER_SENT,
    REPLY_TO_ASSOCIATION,
    REPLY_TO_MODES,
    REPLY_TO_SENDER,
    SOURCE_ADMIN,
    SOURCE_IMPORT,
    SOURCE_PUBLIC_FORM,
    SUBSCRIBER_CONFIRMED,
    SUBSCRIBER_PENDING,
    SUBSCRIBER_UNSUBSCRIBED,
    Delivery,
    DraftingMessage,
    Newsletter,
    Subscriber,
)

logger = logging.getLogger(__name__)

SEND_JOB = "newsletter.send"
# How many mails one job run sends before it hands over to the next run. Small,
# so a run never holds the scheduler for minutes and a restart loses little.
BATCH_SIZE = 20
# The brake on the public form: one confirmation mail per address per day, and
# at most this many confirmation mails per day for the whole association. A
# script typing strangers' addresses must not be able to spend the Gmail quota
# that registrations need.
CONFIRMATION_INTERVAL = timedelta(hours=24)
CONFIRMATIONS_PER_DAY = 50
# How far ahead "Kalender invoegen" looks (CR-05 §3.10).
CALENDAR_WEEKS = 9

_EMAIL = re.compile(r"^[^@\s<>()\[\],;:\"]+@[^@\s<>()\[\],;:\"]+\.[a-zA-Z]{2,}$")


class NewsletterError(ValueError):
    """A request the rules refuse. The message is for the screen."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return secrets.token_urlsafe(32)


def normalize_email(raw: Optional[str]) -> Optional[str]:
    """The address as it is stored — trimmed and lower-case — or None if it is
    not an address. Lower-case because the unique constraint has to mean one row
    per person, not one per spelling."""
    value = (raw or "").strip().lower()
    if not value or len(value) > 255 or not _EMAIL.match(value):
        return None
    return value


# ── Subscribers ──────────────────────────────────────────────────────────────

def get_subscriber(db: Session, subscriber_id: int) -> Optional[Subscriber]:
    return db.get(Subscriber, subscriber_id)


def subscriber_by_email(db: Session, email: str) -> Optional[Subscriber]:
    return db.query(Subscriber).filter(Subscriber.email == email).first()


def list_subscribers(db: Session, *, query: str = "", status: str = "") -> list[Subscriber]:
    q = db.query(Subscriber)
    if status:
        q = q.filter(Subscriber.status == status)
    needle = (query or "").strip().lower()
    if needle:
        like = f"%{needle}%"
        q = q.filter((Subscriber.email.ilike(like)) | (Subscriber.first_name.ilike(like)))
    return q.order_by(Subscriber.created_at.desc(), Subscriber.id.desc()).all()


def subscriber_counts(db: Session) -> dict[str, int]:
    rows = db.query(Subscriber.status, func.count(Subscriber.id)).group_by(Subscriber.status)
    counts = {status: 0 for status in (SUBSCRIBER_PENDING, SUBSCRIBER_CONFIRMED,
                                       SUBSCRIBER_UNSUBSCRIBED)}
    for status, amount in rows:
        counts[status] = amount
    return counts


def _confirmations_sent_today(db: Session) -> int:
    since = _now() - timedelta(hours=24)
    return (db.query(func.count(Subscriber.id))
            .filter(Subscriber.confirm_sent_at.isnot(None),
                    Subscriber.confirm_sent_at >= since)
            .scalar() or 0)


def subscribe_public(db: Session, raw_email: str, first_name: str,
                     confirm_url_for) -> None:
    """The public form (CR-05 §3.5): store the request and send the confirmation.

    Always answers the same way, whatever the address's state, so the form
    cannot be used to find out who is on the list. ``confirm_url_for`` builds
    the absolute link from a token; the route knows the host, this module does
    not.

    - A new address becomes ``pending`` and gets a confirmation mail.
    - A pending address gets a new mail, at most once a day.
    - An unsubscribed address asks again of its own accord: it becomes pending
      and must confirm, like a new one.
    - A confirmed address changes nothing and gets no mail.
    """
    from app.domains.mail.api import send_newsletter_confirmation

    email = normalize_email(raw_email)
    if email is None:
        raise NewsletterError(_("Dat is geen geldig e-mailadres."))
    name = (first_name or "").strip()[:100] or None
    now = _now()

    subscriber = subscriber_by_email(db, email)
    if subscriber is not None and subscriber.status == SUBSCRIBER_CONFIRMED:
        return
    if subscriber is None:
        subscriber = Subscriber(email=email, first_name=name, source=SOURCE_PUBLIC_FORM,
                                status=SUBSCRIBER_PENDING, unsubscribe_token=_token())
        db.add(subscriber)
    elif subscriber.status == SUBSCRIBER_UNSUBSCRIBED:
        subscriber.status = SUBSCRIBER_PENDING
        subscriber.source = SOURCE_PUBLIC_FORM
        subscriber.unsubscribed_at = None
    if name:
        subscriber.first_name = name
    subscriber.consented_at = now

    if (subscriber.confirm_sent_at is not None
            and now - subscriber.confirm_sent_at < CONFIRMATION_INTERVAL):
        db.commit()
        return
    if _confirmations_sent_today(db) >= CONFIRMATIONS_PER_DAY:
        logger.warning("Nieuwsbrief: dagelijks maximum aan bevestigingsmails bereikt; "
                       "%s wacht op een volgende poging.", subscriber.id)
        db.commit()
        return
    subscriber.confirm_token = _token()
    subscriber.confirm_sent_at = now
    db.commit()
    send_newsletter_confirmation(email, subscriber.first_name,
                                 confirm_url_for(subscriber.confirm_token))


def subscriber_by_confirm_token(db: Session, token: str) -> Optional[Subscriber]:
    if not token:
        return None
    return db.query(Subscriber).filter(Subscriber.confirm_token == token).first()


def subscriber_by_unsubscribe_token(db: Session, token: str) -> Optional[Subscriber]:
    if not token:
        return None
    return db.query(Subscriber).filter(Subscriber.unsubscribe_token == token).first()


def confirm(db: Session, token: str) -> Optional[Subscriber]:
    """The confirmation button: exactly the row of this token becomes confirmed."""
    subscriber = subscriber_by_confirm_token(db, token)
    if subscriber is None:
        return None
    subscriber.status = SUBSCRIBER_CONFIRMED
    subscriber.confirmed_at = _now()
    subscriber.confirm_token = None
    subscriber.unsubscribed_at = None
    db.commit()
    return subscriber


def unsubscribe(db: Session, token: str) -> Optional[Subscriber]:
    """The unsubscribe link, without a login. Idempotent."""
    subscriber = subscriber_by_unsubscribe_token(db, token)
    if subscriber is None:
        return None
    if subscriber.status != SUBSCRIBER_UNSUBSCRIBED:
        subscriber.status = SUBSCRIBER_UNSUBSCRIBED
        subscriber.unsubscribed_at = _now()
        subscriber.confirm_token = None
        db.commit()
    return subscriber


def resubscribe(db: Session, token: str) -> Optional[Subscriber]:
    """"Toch opnieuw inschrijven" on the unsubscribe page.

    The token came out of this person's own mailbox, so the click is the
    confirmation: no second mail.
    """
    subscriber = subscriber_by_unsubscribe_token(db, token)
    if subscriber is None:
        return None
    subscriber.status = SUBSCRIBER_CONFIRMED
    subscriber.unsubscribed_at = None
    subscriber.confirmed_at = _now()
    subscriber.consented_at = _now()
    db.commit()
    return subscriber


def add_by_admin(db: Session, raw_email: str, first_name: str = "") -> Subscriber:
    """An address added by hand — someone who asked in person (CR-05 §3.6).

    Refused for an address that unsubscribed: that choice is theirs, and a
    board member re-adding it would undo it without anyone noticing.
    """
    email = normalize_email(raw_email)
    if email is None:
        raise NewsletterError(_("Dat is geen geldig e-mailadres."))
    existing = subscriber_by_email(db, email)
    if existing is not None:
        if existing.status == SUBSCRIBER_UNSUBSCRIBED:
            raise NewsletterError(_("Dit adres heeft zich uitgeschreven. Het kan zich "
                                    "alleen zelf opnieuw inschrijven."))
        raise NewsletterError(_("Dit adres staat al op de lijst."))
    now = _now()
    subscriber = Subscriber(email=email, first_name=(first_name or "").strip()[:100] or None,
                            source=SOURCE_ADMIN, status=SUBSCRIBER_CONFIRMED,
                            consented_at=now, confirmed_at=now,
                            unsubscribe_token=_token())
    db.add(subscriber)
    db.commit()
    return subscriber


def unsubscribe_by_admin(db: Session, subscriber_id: int) -> None:
    subscriber = get_subscriber(db, subscriber_id)
    if subscriber is None or subscriber.status == SUBSCRIBER_UNSUBSCRIBED:
        return
    subscriber.status = SUBSCRIBER_UNSUBSCRIBED
    subscriber.unsubscribed_at = _now()
    subscriber.confirm_token = None
    db.commit()


def erase(db: Session, subscriber_id: int) -> None:
    """The right to erasure: the row goes, its deliveries lose the address.

    The deliveries stay so the archive's counts stay true; each gets a
    placeholder that is unique within its letter.
    """
    subscriber = get_subscriber(db, subscriber_id)
    if subscriber is None:
        return
    for delivery in (db.query(Delivery)
                     .filter(Delivery.subscriber_id == subscriber.id).all()):
        delivery.email = f"{ERASED_ADDRESS} {delivery.id}"
        delivery.subscriber_id = None
    db.delete(subscriber)
    db.commit()


# ── Import ───────────────────────────────────────────────────────────────────

@dataclass
class ImportPreview:
    """What an import would do, before it writes anything (CR-05 §3.6)."""

    new: list[str] = field(default_factory=list)
    known: list[str] = field(default_factory=list)
    unsubscribed: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)


def preview_import(db: Session, text: str) -> ImportPreview:
    """One address per line. Blank lines are ignored; a line repeated in the
    file counts once."""
    preview = ImportPreview()
    existing = {s.email: s.status for s in db.query(Subscriber).all()}
    seen: set[str] = set()
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        email = normalize_email(raw)
        if email is None:
            preview.invalid.append(raw[:255])
            continue
        if email in seen:
            continue
        seen.add(email)
        status = existing.get(email)
        if status is None:
            preview.new.append(email)
        elif status == SUBSCRIBER_UNSUBSCRIBED:
            preview.unsubscribed.append(email)
        else:
            preview.known.append(email)
    return preview


def run_import(db: Session, text: str) -> ImportPreview:
    """Add the new addresses as confirmed, with provenance.

    Recomputed from the text rather than trusted from the preview screen, so
    what is written is what the rules allow at this moment. An address that
    unsubscribed is never touched (CR-05 §3.6).
    """
    preview = preview_import(db, text)
    now = _now()
    for email in preview.new:
        db.add(Subscriber(email=email, source=SOURCE_IMPORT,
                          status=SUBSCRIBER_CONFIRMED, imported_at=now,
                          confirmed_at=now, unsubscribe_token=_token()))
    db.commit()
    return preview


# ── Audiences ────────────────────────────────────────────────────────────────

def member_addresses(db: Session, today: Optional[date] = None) -> list[str]:
    """Every address of every person in a household with a membership for the
    current working year (CR-05 §3.3). The rule is the membership domain's."""
    from app.domains.mdm.api import email_addresses_of_members
    from app.domains.membership.api import members_with_membership_for_year

    year = (today or date.today()).year
    return email_addresses_of_members(db, members_with_membership_for_year(db, year))


def confirmed_subscribers(db: Session) -> list[Subscriber]:
    return (db.query(Subscriber)
            .filter(Subscriber.status == SUBSCRIBER_CONFIRMED)
            .order_by(Subscriber.email).all())


@dataclass(frozen=True)
class Recipient:
    email: str
    kind: str
    subscriber_id: Optional[int]


def recipients_for(db: Session, audience: str) -> list[Recipient]:
    """The recipient list of one audience, deduplicated by address.

    In *allebei*, an address that is both a member and a subscriber is sent as
    a member: members cannot unsubscribe (CR-05 §3.4), and this letter is also
    their member letter.
    """
    if audience not in AUDIENCES:
        raise NewsletterError(_("Kies eerst voor wie deze nieuwsbrief is."))
    out: dict[str, Recipient] = {}
    if audience in (AUDIENCE_MEMBERS, AUDIENCE_BOTH):
        for email in member_addresses(db):
            out[email] = Recipient(email, DELIVERY_MEMBER, None)
    if audience in (AUDIENCE_NON_MEMBERS, AUDIENCE_BOTH):
        for subscriber in confirmed_subscribers(db):
            out.setdefault(subscriber.email,
                           Recipient(subscriber.email, DELIVERY_SUBSCRIBER, subscriber.id))
    return [out[email] for email in sorted(out)]


@dataclass(frozen=True)
class AudienceCounts:
    members: int
    non_members: int
    both: int

    @property
    def overlap(self) -> int:
        return self.members + self.non_members - self.both


def audience_counts(db: Session) -> AudienceCounts:
    members = set(member_addresses(db))
    subscribers = {s.email for s in confirmed_subscribers(db)}
    return AudienceCounts(members=len(members), non_members=len(subscribers),
                          both=len(members | subscribers))


# ── Letters ──────────────────────────────────────────────────────────────────

def list_newsletters(db: Session, *, query: str = "") -> list[Newsletter]:
    q = db.query(Newsletter)
    needle = (query or "").strip()
    if needle:
        q = q.filter(Newsletter.subject.ilike(f"%{needle}%"))
    return q.order_by(Newsletter.updated_at.desc(), Newsletter.id.desc()).all()


def get_newsletter(db: Session, newsletter_id: int) -> Optional[Newsletter]:
    return db.get(Newsletter, newsletter_id)


def create_newsletter(db: Session, *, created_by: str) -> Newsletter:
    letter = Newsletter(created_by=created_by, subject="", body_html="",
                        draft_activity_ids=[], draft_meeting_item_ids=[])
    db.add(letter)
    db.commit()
    return letter


def _refuse_unless_draft(letter: Newsletter) -> None:
    if letter.status != LETTER_DRAFT:
        raise NewsletterError(_("Deze nieuwsbrief is al verstuurd. Kopieer hem om "
                                "een nieuwe te maken."))


def _clean_body(body_html: str) -> str:
    from app.domains.cms.api import sanitize_cms_html

    return sanitize_cms_html(body_html or "") or ""


def update_draft(db: Session, letter: Newsletter, *, subject: str, body_html: str,
                 audience: Optional[str]) -> None:
    _refuse_unless_draft(letter)
    if audience and audience not in AUDIENCES:
        raise NewsletterError(_("Onbekende doelgroep."))
    letter.subject = (subject or "").strip()[:500]
    letter.body_html = _clean_body(body_html)
    letter.audience = audience or None
    db.commit()


def set_draft_sources(db: Session, letter: Newsletter, *, activity_ids: list[int],
                      meeting_item_ids: list[int]) -> None:
    """What Raakje writes about: the chosen activities and ticked points."""
    _refuse_unless_draft(letter)
    letter.draft_activity_ids = sorted({int(i) for i in activity_ids})
    letter.draft_meeting_item_ids = sorted({int(i) for i in meeting_item_ids})
    db.commit()


def copy_newsletter(db: Session, letter: Newsletter, *, created_by: str) -> Newsletter:
    """A new draft with the same subject and text — and no audience (CR-05 §3.12)."""
    copy = Newsletter(subject=letter.subject, body_html=letter.body_html,
                      audience=None, created_by=created_by, copied_from_id=letter.id,
                      draft_activity_ids=list(letter.draft_activity_ids or []),
                      draft_meeting_item_ids=list(letter.draft_meeting_item_ids or []))
    db.add(copy)
    db.commit()
    return copy


def delete_draft(db: Session, letter: Newsletter) -> None:
    from app.soft_delete import soft_delete

    _refuse_unless_draft(letter)
    soft_delete(letter)
    db.commit()


# ── Insert helpers ───────────────────────────────────────────────────────────

_WEEKDAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]
_MONTHS = ["", "jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep",
           "okt", "nov", "dec"]
_LONG_WEEKDAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
                  "zaterdag", "zondag"]
_LONG_MONTHS = ["", "januari", "februari", "maart", "april", "mei", "juni", "juli",
                "augustus", "september", "oktober", "november", "december"]


def short_date(day: date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day} {_MONTHS[day.month]}"


def _long_date(day: date) -> str:
    return f"{_LONG_WEEKDAYS[day.weekday()]} {day.day} {_LONG_MONTHS[day.month]}"


def _clock(value) -> str:
    return f"{value.hour}u{value.minute:02d}" if value.minute else f"{value.hour}u"


@dataclass(frozen=True)
class ActivityFacts:
    """The facts of one activity that a letter may state (CR-05 §3.16)."""

    id: int
    name: str
    start: date
    end: date
    start_time: Optional[object]
    location: str
    url: str
    photos_url: Optional[str]
    is_full: bool
    prices: tuple


def _activity_key(activity) -> str:
    return getattr(activity, "slug", None) or str(activity.id)


def _prices_of(activity) -> tuple:
    """Every amount the activity charges: per component and per product, the
    normal and the member price. What a proposal's amounts are checked against."""
    amounts = set()
    for component in getattr(activity, "sub_registrations", []) or []:
        for thing in [component, *(getattr(component, "products", []) or [])]:
            if getattr(thing, "is_free", False):
                continue
            for value in (getattr(thing, "price", None), getattr(thing, "member_price", None)):
                if value is not None and value > 0:
                    amounts.add(value)
    return tuple(sorted(amounts))


def _albums(db: Session) -> set[int]:
    from app.domains.media.api import activity_photo_covers

    try:
        return {row["activity_id"] for row in activity_photo_covers(db)}
    except Exception:  # noqa: BLE001 — a missing album link is not worth an error
        logger.exception("Fotoalbums konden niet gelezen worden")
        return set()


def activity_facts(db: Session, activity_ids, *, base_url: str,
                   today: Optional[date] = None) -> dict[int, ActivityFacts]:
    """The facts of these activities, from the activities domain.

    ``base_url`` makes the links absolute: they end up in a mail.
    """
    from app.domains.activities.api import Activity, activities_from

    wanted = {int(i) for i in (activity_ids or [])}
    if not wanted:
        return {}
    albums = _albums(db)
    since = (today or date.today()) - timedelta(days=400)
    spans = {span.activity.id: span for span in activities_from(db, since)
             if span.activity.id in wanted}
    out: dict[int, ActivityFacts] = {}
    for activity in db.query(Activity).filter(Activity.id.in_(wanted)).all():
        span = spans.get(activity.id)
        dates = sorted(getattr(activity, "dates", []) or [],
                       key=lambda d: (d.start_date, d.start_time or datetime.min.time()))
        first = dates[0] if dates else None
        start = span.start if span else (first.start_date if first else None)
        if start is None:
            continue
        key = _activity_key(activity)
        out[activity.id] = ActivityFacts(
            id=activity.id, name=activity.name, start=start,
            end=span.end if span else start,
            start_time=first.start_time if first else None,
            location=activity.location or "",
            url=f"{base_url}/activiteiten/{key}",
            photos_url=(f"{base_url}/activiteiten/{key}/fotos"
                        if activity.id in albums else None),
            is_full=bool(span and span.capacity and span.registered >= span.capacity),
            prices=_prices_of(activity))
    return out


def activity_line_html(facts: ActivityFacts) -> str:
    """The one line "Activiteit invoegen" writes (CR-05 §3.10).

    The same line the drafting uses for its activity markers, so a date or a
    link in a letter always comes from here and never from a model.
    """
    parts = [_long_date(facts.start)]
    if facts.end and facts.end != facts.start:
        parts[0] = f"{_long_date(facts.start)} tot {_long_date(facts.end)}"
    if facts.start_time:
        parts.append(_clock(facts.start_time))
    if facts.location:
        parts.append(facts.location)
    text = ", ".join(parts)
    esc = html_lib.escape
    link = (f' <a href="{esc(facts.url)}">{esc(_("Schrijf je in"))}</a>'
            if not facts.is_full else f" <em>{esc(_('volzet'))}</em>")
    return f"<strong>{esc(facts.name)}</strong> — {esc(text)}.{link}"


def photos_line_html(facts: ActivityFacts) -> str:
    """The link to an activity's photo album, when it has one."""
    if not facts.photos_url:
        return ""
    esc = html_lib.escape
    return (f'<a href="{esc(facts.photos_url)}">'
            f'{esc(_("Bekijk de foto’s van %(naam)s") % {"naam": facts.name})}</a>')


def calendar_html(db: Session, *, base_url: str, today: Optional[date] = None) -> str:
    """"Kalender invoegen": the activities of the coming weeks as a list."""
    from app.domains.activities.api import activities_from

    start = today or date.today()
    until = start + timedelta(weeks=CALENDAR_WEEKS)
    spans = [s for s in activities_from(db, start) if s.start <= until]
    if not spans:
        return f"<div>{html_lib.escape(_('Er staan de komende weken geen activiteiten gepland.'))}</div>"
    facts = activity_facts(db, [s.activity.id for s in spans], base_url=base_url, today=start)
    esc = html_lib.escape
    lines = []
    for span in spans:
        fact = facts.get(span.activity.id)
        if fact is None:
            continue
        where = f", {esc(fact.location)}" if fact.location else ""
        full = f" · <em>{esc(_('volzet'))}</em>" if fact.is_full else ""
        lines.append(f'<li>{esc(short_date(fact.start))} — '
                     f'<a href="{esc(fact.url)}">{esc(fact.name)}</a>{where}{full}</li>')
    return f"<ul>{''.join(lines)}</ul>"


def insertable_activities(db: Session, *, query: str = "",
                          today: Optional[date] = None) -> list:
    """The picker: every coming activity, soonest first, optionally filtered."""
    from app.domains.activities.api import activities_from

    spans = activities_from(db, today or date.today())
    needle = (query or "").strip().lower()
    if needle:
        spans = [s for s in spans if needle in s.activity.name.lower()]
    return spans[:40]


def save_settings(db: Session, *, house_style: str, daily_cap: Optional[int]) -> None:
    """The house style Raakje writes in, and the daily cap (CR-05 §3.7, §8.3).

    An empty value removes the setting, so the default applies again.
    """
    from app.kernel.tenant_config import set_setting

    if daily_cap is not None and daily_cap < 1:
        raise NewsletterError(_("Het dagplafond is een getal groter dan nul."))
    set_setting(db, "newsletter_house_style", (house_style or "").strip()[:2000] or None)
    set_setting(db, "newsletter_daily_cap", str(daily_cap) if daily_cap else None)
    db.commit()


# ── The mail ─────────────────────────────────────────────────────────────────

def _organisation_footer(db: Session) -> tuple[str, str]:
    """The association's name and address line for the mail footer."""
    from app.domains.mdm.api import organization_address
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
    from app.kernel.tenant_config import tenant_display_name

    name = tenant_display_name(db)
    line = ""
    try:
        # The tenant IS the organisation (#924): its id is the organisation id.
        organisation_id = current_tenant_id.get() or DEFAULT_TENANT_ID
        if organisation_id:
            address = organization_address(db, organisation_id)
            street = " ".join(p for p in (address.get("street"),
                                          address.get("house_number")) if p)
            if address.get("bus_number"):
                street = f"{street} bus {address['bus_number']}"
            line = ", ".join(p for p in (street, address.get("postal_code")) if p)
    except Exception:  # noqa: BLE001 — a missing address must not stop a letter
        logger.exception("Adres van de vereniging niet leesbaar voor de nieuwsbrief")
    return name, line


def closing_html(db: Session) -> str:
    """The closing of every letter: no personal names (CR-05 §3.10)."""
    from app.kernel.tenant_config import tenant_display_name

    esc = html_lib.escape
    return (f"<div>{esc(_('Tot binnenkort!'))}<br>"
            f"{esc(_('Het bestuur van %(naam)s') % {'naam': tenant_display_name(db)})}</div>")


def render_mail(db: Session, letter: Newsletter, *, kind: str,
                unsubscribe_url: Optional[str], logo_url: Optional[str] = None) -> str:
    """The letter as it arrives: a simple frame around the text.

    Inline styles only — many mail clients ignore a style block. A member mail
    has no unsubscribe line (CR-05 §3.4); a subscriber mail always has one.
    """
    esc = html_lib.escape
    name, address = _organisation_footer(db)
    header = (f'<img src="{esc(logo_url)}" alt="{esc(name)}" style="max-height:56px">'
              if logo_url else
              f'<span style="font-size:24px;font-weight:700;color:#0051a4">{esc(name)}</span>')
    footer = [esc(name)]
    if address:
        footer[0] = f"{esc(name)} · {esc(address)}"
    if kind == DELIVERY_SUBSCRIBER and unsubscribe_url:
        footer.append(esc(_("Je krijgt deze mail omdat je op de mailinglijst van "
                            "%(naam)s staat.") % {"naam": name}))
        footer.append(f'<a href="{esc(unsubscribe_url)}" style="color:#52607a">'
                      f'{esc(_("Uitschrijven"))}</a>')
    return (
        '<div style="background:#eef3f9;padding:20px 10px;font-family:Arial,Helvetica,sans-serif">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:10px;'
        'padding:22px 26px;font-size:15px;line-height:1.6;color:#14171c">'
        f'<div style="border-bottom:3px solid #ffce00;padding-bottom:10px;margin-bottom:16px">{header}</div>'
        f'{letter.body_html or ""}'
        '</div>'
        '<div style="max-width:640px;margin:0 auto;text-align:center;font-size:12px;'
        f'color:#52607a;padding:14px 10px 0;line-height:1.6">{"<br>".join(footer)}</div>'
        '</div>'
    )


def _logo_url(db: Session, base_url: str) -> Optional[str]:
    """The association logo as an absolute URL — the same asset the site header
    and the meeting PDF use — or None."""
    from app.domains.media.api import tenant_logo

    try:
        asset = tenant_logo(db)
    except Exception:  # noqa: BLE001 — a letter without logo is still a letter
        return None
    return f"{base_url}/api/v1/media/{asset.id}" if asset is not None else None


def reply_address(mode: str, sender_email: str) -> Optional[str]:
    """Where replies go (CR-05 §3.8).

    *De vereniging* means the sender address from the tenant configuration —
    the address the mail comes from — so no Reply-To header is needed. *Mezelf*
    sets the admin who sends.
    """
    if mode == REPLY_TO_SENDER:
        return sender_email
    return None


def send_test(db: Session, letter: Newsletter, *, to_email: str, base_url: str) -> str:
    """"Testmail naar mezelf": the real mail, to the signed-in admin only.

    Shown as a non-member would see it when non-members are among the
    audience, so the unsubscribe line can be checked too. Changes nothing
    about the letter.
    """
    from app.domains.mail.api import send_campaign_mail

    if not (letter.subject or "").strip():
        raise NewsletterError(_("Geef de nieuwsbrief eerst een onderwerp."))
    kind = (DELIVERY_SUBSCRIBER if letter.audience in (AUDIENCE_NON_MEMBERS, AUDIENCE_BOTH)
            else DELIVERY_MEMBER)
    unsubscribe_url = f"{base_url}/nieuwsbrief/uitschrijven/test" if kind == DELIVERY_SUBSCRIBER else None
    body = render_mail(db, letter, kind=kind, unsubscribe_url=unsubscribe_url,
                       logo_url=_logo_url(db, base_url))
    return send_campaign_mail(to_email, f"[{_('TEST')}] {letter.subject}", body,
                              email_type="newsletter")


# ── Sending ──────────────────────────────────────────────────────────────────

def start_sending(db: Session, letter: Newsletter, *, sent_by: str, reply_to_mode: str,
                  base_url: str) -> int:
    """Fix the recipient list and hand the letter to the queue (CR-05 §3.7).

    Returns the number of recipients. Everything that can be refused is
    refused here, before a single row is written.
    """
    from app.kernel.jobs import enqueue
    from app.kernel.tenancy import current_tenant_id

    _refuse_unless_draft(letter)
    if not letter.audience:
        raise NewsletterError(_("Kies eerst voor wie deze nieuwsbrief is."))
    if not (letter.subject or "").strip():
        raise NewsletterError(_("Geef de nieuwsbrief eerst een onderwerp."))
    if not re.sub(r"<[^>]+>|\s|&nbsp;", "", letter.body_html or ""):
        raise NewsletterError(_("De nieuwsbrief heeft nog geen inhoud."))
    if reply_to_mode not in REPLY_TO_MODES:
        raise NewsletterError(_("Kies waar antwoorden naartoe gaan."))
    recipients = recipients_for(db, letter.audience)
    if not recipients:
        raise NewsletterError(_("Er is niemand om deze nieuwsbrief naar te sturen."))

    for recipient in recipients:
        db.add(Delivery(newsletter_id=letter.id, email=recipient.email,
                        kind=recipient.kind, subscriber_id=recipient.subscriber_id,
                        status=DELIVERY_QUEUED))
    letter.status = LETTER_SENDING
    letter.sent_by = sent_by
    letter.reply_to_mode = reply_to_mode
    letter.reply_to_address = reply_address(reply_to_mode, sent_by)
    letter.link_base = base_url.rstrip("/")
    letter.send_started_at = _now()
    # The conversation with Raakje ends here: the letter is the record now.
    for message in list(letter.messages):
        db.delete(message)
    enqueue(db, SEND_JOB, {"newsletter_id": letter.id,
                           "tenant_id": current_tenant_id.get()})
    db.commit()
    return len(recipients)


def sent_in_last_day(db: Session) -> int:
    since = _now() - timedelta(hours=24)
    return (db.query(func.count(Delivery.id))
            .filter(Delivery.status == DELIVERY_SENT, Delivery.sent_at >= since)
            .scalar() or 0)


def _next_free_moment(db: Session) -> datetime:
    """When the oldest send of the last 24 hours drops out of the window."""
    since = _now() - timedelta(hours=24)
    oldest = (db.query(func.min(Delivery.sent_at))
              .filter(Delivery.status == DELIVERY_SENT, Delivery.sent_at >= since)
              .scalar())
    return (oldest + timedelta(hours=24, minutes=1)) if oldest else _now() + timedelta(minutes=5)


def _pause(db: Session, letter: Newsletter, until: datetime) -> None:
    from app.kernel.jobs import enqueue
    from app.kernel.tenancy import current_tenant_id

    letter.paused_until = until
    enqueue(db, SEND_JOB, {"newsletter_id": letter.id,
                           "tenant_id": current_tenant_id.get()}, run_at=until)
    db.commit()


def send_batch(db: Session, newsletter_id: int, *, batch_size: int = BATCH_SIZE) -> str:
    """Send the next few queued mails of one letter. Returns what happened:
    ``done``, ``paused``, ``continue`` or ``nothing``.

    Each delivery is committed right after its mail left, so a restart resumes
    with the next address and never mails anyone twice — except for the one
    mail that was on its way at the exact moment of a crash.
    """
    from app.domains.mail.api import SendingQuotaReached, send_campaign_mail
    from app.kernel.jobs import enqueue
    from app.kernel.tenancy import current_tenant_id
    from app.kernel.tenant_config import tenant_newsletter_daily_cap

    letter = db.get(Newsletter, newsletter_id)
    if letter is None or letter.status != LETTER_SENDING:
        return "nothing"
    now = _now()
    if letter.paused_until and letter.paused_until > now:
        return "nothing"
    letter.paused_until = None

    room = tenant_newsletter_daily_cap(db) - sent_in_last_day(db)
    if room <= 0:
        _pause(db, letter, _next_free_moment(db))
        return "paused"

    queued = (db.query(Delivery)
              .filter(Delivery.newsletter_id == letter.id,
                      Delivery.status == DELIVERY_QUEUED)
              .order_by(Delivery.id)
              .limit(min(room, batch_size)).all())
    logo_url = _logo_url(db, letter.link_base or "")
    for delivery in queued:
        unsubscribe_url = None
        if delivery.kind == DELIVERY_SUBSCRIBER:
            subscriber = (db.get(Subscriber, delivery.subscriber_id)
                          if delivery.subscriber_id else None)
            if subscriber is None or subscriber.status != SUBSCRIBER_CONFIRMED:
                delivery.status = DELIVERY_SKIPPED
                delivery.error = _("uitgeschreven tijdens het versturen")
                db.commit()
                continue
            unsubscribe_url = (f"{letter.link_base}/nieuwsbrief/uitschrijven/"
                               f"{subscriber.unsubscribe_token}")
        body = render_mail(db, letter, kind=delivery.kind,
                           unsubscribe_url=unsubscribe_url, logo_url=logo_url)
        try:
            outcome = send_campaign_mail(delivery.email, letter.subject, body,
                                         email_type="newsletter",
                                         reply_to=letter.reply_to_address,
                                         unsubscribe_url=unsubscribe_url)
        except SendingQuotaReached:
            _pause(db, letter, _now() + timedelta(hours=24))
            return "paused"
        if outcome in ("sent", "logged"):
            delivery.status = DELIVERY_SENT
            delivery.sent_at = _now()
            delivery.error = None
        elif outcome == "skipped":
            delivery.status = DELIVERY_FAILED
            delivery.error = _("geen mailaccount ingesteld")
        else:
            delivery.status = DELIVERY_FAILED
            delivery.error = _("de mailserver weigerde deze mail")
        db.commit()

    left = (db.query(func.count(Delivery.id))
            .filter(Delivery.newsletter_id == letter.id,
                    Delivery.status == DELIVERY_QUEUED).scalar() or 0)
    if left == 0:
        letter.status = LETTER_SENT
        letter.send_finished_at = _now()
        db.commit()
        return "done"
    enqueue(db, SEND_JOB, {"newsletter_id": letter.id,
                           "tenant_id": current_tenant_id.get()},
            run_at=_now() + timedelta(seconds=5))
    db.commit()
    return "continue"


@dataclass(frozen=True)
class Progress:
    total: int
    sent: int
    failed: int
    skipped: int
    queued: int
    expected_finish: Optional[datetime]


def progress_of(db: Session, letter: Newsletter) -> Progress:
    from app.kernel.tenant_config import tenant_newsletter_daily_cap

    rows = dict(db.query(Delivery.status, func.count(Delivery.id))
                .filter(Delivery.newsletter_id == letter.id)
                .group_by(Delivery.status).all())
    queued = rows.get(DELIVERY_QUEUED, 0)
    expected = None
    if letter.status == LETTER_SENDING and queued:
        days = expected_days(db, queued) - 1
        start = letter.paused_until or _now()
        expected = start + timedelta(days=days)
    return Progress(total=sum(rows.values()), sent=rows.get(DELIVERY_SENT, 0),
                    failed=rows.get(DELIVERY_FAILED, 0),
                    skipped=rows.get(DELIVERY_SKIPPED, 0), queued=queued,
                    expected_finish=expected)


def expected_days(db: Session, count: int) -> int:
    """How many days a send of ``count`` mails takes under today's cap."""
    from app.kernel.tenant_config import tenant_newsletter_daily_cap

    cap = tenant_newsletter_daily_cap(db)
    room_today = max(0, cap - sent_in_last_day(db))
    if count <= room_today:
        return 1
    return 1 + -(-(count - room_today) // cap)


def deliveries_of(db: Session, letter: Newsletter, *, status: str = "",
                  query: str = "") -> list[Delivery]:
    q = db.query(Delivery).filter(Delivery.newsletter_id == letter.id)
    if status:
        q = q.filter(Delivery.status == status)
    needle = (query or "").strip().lower()
    if needle:
        q = q.filter(Delivery.email.ilike(f"%{needle}%"))
    return q.order_by(Delivery.id).limit(500).all()


def messages_of(db: Session, letter: Newsletter) -> list[DraftingMessage]:
    return (db.query(DraftingMessage)
            .filter(DraftingMessage.newsletter_id == letter.id)
            .order_by(DraftingMessage.id).all())

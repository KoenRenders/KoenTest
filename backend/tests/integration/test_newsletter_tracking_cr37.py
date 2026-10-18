"""CR-37 (#2027): the opens and the clicks of a letter, counted without knowing who.

Proven red (16 October 2026), each by an additive or reversing edit:
- `track_links` left out of `render_mail` → T1 fails (a real mail carries no rewritten link);
- the `kind` of the unsubscribe path removed from `_NEVER_COUNTED` and a body link to it added →
  the unsubscribe test fails;
- the link of the code not compared with the letter in `record_click` → T4 fails;
- the signature not checked in `letter_id_of` → T5 fails (a forged code counts);
- `UNIQUE NULLS NOT DISTINCT` taken from the model → T6's direct second insert is accepted.
"""

import re
from datetime import timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.domains.newsletter import service as nb
from app.domains.newsletter import tracking
from app.domains.newsletter.models import (
    Audience,
    DeliveryKind,
    LetterEvent,
    LetterLink,
    Newsletter,
)
from app.kernel.clock import belgian_today
from tests._newsletter_world import Mailbox, subscriber

pytestmark = pytest.mark.ui_serverrendered

BASE = "https://raak.example"
OUTSIDE = "https://extern.example/pagina?a=1&b=2"


@pytest.fixture
def mailbox(monkeypatch):
    box = Mailbox()
    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", box)
    return box


def _letter(db, body=None) -> Newsletter:
    letter = nb.create_newsletter(db, created_by="secretaris@example.org")
    nb.update_draft(
        db,
        letter,
        subject="Het najaar",
        body_html=body
        or (
            f'<div>Lees <a href="{OUTSIDE.replace("&", "&amp;")}">dit</a>, '
            '<a href="mailto:bestuur@example.org">schrijf ons</a> of ga '
            '<a href="#onder">naar onder</a>.</div>'
        ),
        audience=Audience.NON_MEMBERS,
    )
    return letter


def _send_all(db, letter) -> None:
    nb.start_sending(
        db, letter, sent_by="secretaris@example.org", reply_to_mode="association", base_url=BASE
    )
    for _ in range(20):
        if nb.send_batch(db, letter.id) in ("done", "paused", "nothing"):
            break


def _mail_of(db, mailbox, letter, address="een@example.org") -> dict:
    subscriber(db, address)
    _send_all(db, letter)
    return next(m for m in mailbox.sent if m["to"] == address)


def _code_of(mail: dict) -> str:
    return re.search(r"/nieuwsbrief/o/([^\"]+)\.gif", mail["body"]).group(1)


def _click_ids(mail: dict) -> list[int]:
    return [int(i) for i in re.findall(r"/nieuwsbrief/k/[^/\"]+/(\d+)", mail["body"])]


# ── The mail ─────────────────────────────────────────────────────────────────


def test_a_real_mail_carries_the_pixel_the_rewritten_links_and_the_line(db_session, mailbox):
    """T1, T10, T13."""
    letter = _letter(db_session)
    mail = _mail_of(db_session, mailbox, letter)
    body, plain = mail["body"], mail["body_text"]
    code = _code_of(mail)
    assert f'src="{BASE}/nieuwsbrief/o/{code}.gif"' in body
    # (the inbox's hidden preview line quotes the text of the letter, address included: no link)
    assert 'href="https://extern.example' not in body, "the outside address goes through the portal"
    assert len(_click_ids(mail)) == 1
    assert 'href="mailto:bestuur@example.org"' in body and 'href="#onder"' in body
    line = "Wij tellen anoniem hoeveel brieven geopend en hoeveel links aangeklikt worden."
    assert line in body and line in plain
    assert "(https://extern.example" not in plain and f"/nieuwsbrief/k/{code}/" in plain
    stored = db_session.query(LetterLink).filter_by(newsletter_id=letter.id).one()
    assert stored.url == OUTSIDE, "the store holds the address as the reader would have met it"


def test_the_unsubscribe_link_is_never_counted_or_changed(db_session, mailbox):
    letter = _letter(db_session)
    mail = _mail_of(db_session, mailbox, letter)
    assert mail["unsubscribe_url"].startswith(f"{BASE}/nieuwsbrief/uitschrijven/")
    assert f'href="{mail["unsubscribe_url"]}"' in mail["body"]
    own = f"{BASE}/nieuwsbrief/uitschrijven/abc"
    body = f'<div><a href="{own}">weg</a></div>'
    letter = _letter(db_session, body=body)
    html = tracking.track_links(
        db_session, letter, body, code=tracking.make_code(letter.id), base=BASE
    )
    assert html == body, "a body link to the unsubscribe page stays as it is"


def test_rendering_twice_wraps_nothing_twice(db_session):
    letter = _letter(db_session)
    code = tracking.make_code(letter.id)
    once = tracking.track_links(
        db_session, letter, f'<a href="{OUTSIDE}">x</a>', code=code, base=BASE
    )
    assert tracking.track_links(db_session, letter, once, code=code, base=BASE) == once


def test_the_test_mail_and_the_preview_carry_no_code(db_session):
    """T8: no code passed, nothing rewritten, no pixel, no line."""
    letter = _letter(db_session)
    mail = nb.render_mail(
        db_session, letter, kind=DeliveryKind.SUBSCRIBER, unsubscribe_url=None, base_url=BASE
    )
    assert "extern.example" in mail
    assert "/nieuwsbrief/o/" not in mail and "/nieuwsbrief/k/" not in mail
    assert "Wij tellen anoniem" not in mail
    assert db_session.query(LetterLink).filter_by(newsletter_id=letter.id).count() == 0


def test_every_external_link_of_a_letter_with_blocks_goes_through_the_portal(db_session):
    """T2 and the gate of C7: an activity block (title, registration link), the calendar
    and a button, and the body — each outside address is in the store, none is left."""
    from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration

    activity = Activity(name="Quiz", slug="quiz", location="Dorpsplein")
    db_session.add(activity)
    db_session.flush()
    db_session.add(
        ActivityDate(activity_id=activity.id, start_date=belgian_today() + timedelta(days=10))
    )
    db_session.add(
        ActivitySubRegistration(
            activity_id=activity.id,
            name="Deelname",
            external_register_url="https://inschrijven.example/quiz",
        )
    )
    db_session.flush()
    letter = _letter(
        db_session,
        body=(
            f'<div>Zie <a href="{OUTSIDE.replace("&", "&amp;")}">dit</a></div>'
            f"<div>[[activiteit:{activity.id}]]</div><div>[[kalender]]</div>"
        ),
    )
    code = tracking.make_code(letter.id)
    mail = nb.render_mail(
        db_session,
        letter,
        kind=DeliveryKind.SUBSCRIBER,
        unsubscribe_url=f"{BASE}/nieuwsbrief/uitschrijven/t",
        base_url=BASE,
        code=code,
    )
    hrefs = [
        h
        for h in re.findall(r'href="([^"]+)"', mail)
        if h.startswith("http") and "/nieuwsbrief/uitschrijven/" not in h
    ]
    assert hrefs, "the gate looked at links"
    outside = [h for h in hrefs if f"{BASE}/nieuwsbrief/k/{code}/" not in h]
    assert not outside, f"links that bypass the portal: {outside}"
    stored = {u for (u,) in db_session.query(LetterLink.url).filter_by(newsletter_id=letter.id)}
    assert len(stored) >= 2, "the body link and at least one link of a block were stored"
    assert not any("/nieuwsbrief/k/" in u for u in stored)


def test_a_link_met_for_the_first_time_in_a_later_mail_gets_a_row(db_session, mailbox):
    """T15."""
    letter = _letter(db_session)
    first = tracking.link_ids(db_session, letter.id, [OUTSIDE])
    later = tracking.link_ids(db_session, letter.id, [OUTSIDE, "https://nieuw.example/x"])
    assert later[OUTSIDE] == first[OUTSIDE] and len(set(later.values())) == 2


# ── Counting ─────────────────────────────────────────────────────────────────


def test_a_click_forwards_to_the_stored_address_and_counts_once(client, db_session, mailbox):
    """T3."""
    letter = _letter(db_session)
    mail = _mail_of(db_session, mailbox, letter)
    db_session.commit()
    path = re.search(r'href="https://raak.example(/nieuwsbrief/k/[^"]+)"', mail["body"]).group(1)
    for _ in range(2):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == OUTSIDE
    events = db_session.query(LetterEvent).filter_by(newsletter_id=letter.id).all()
    assert len(events) == 1 and events[0].link_id is not None


def test_a_link_or_code_of_another_letter_is_a_404_and_counts_nothing(client, db_session, mailbox):
    """T4."""
    letter = _letter(db_session)
    other = _letter(db_session)
    link = tracking.link_ids(db_session, other.id, [OUTSIDE])[OUTSIDE]
    db_session.commit()
    code = tracking.make_code(letter.id)
    assert client.get(f"/nieuwsbrief/k/{code}/{link}", follow_redirects=False).status_code == 404
    assert client.get(f"/nieuwsbrief/k/{code}/999999", follow_redirects=False).status_code == 404
    assert db_session.query(LetterEvent).count() == 0


def test_a_forged_code_gets_the_picture_and_counts_nothing(client, db_session):
    """T5, and walkthrough 10: a changed character in the code still loads the picture."""
    letter = _letter(db_session)
    db_session.commit()
    code = tracking.make_code(letter.id)
    forged = code[:-1] + ("0" if code[-1] != "0" else "1")
    for name in (forged, "abc", f"{letter.id}.zz.{'0' * 32}", "9" * 5000):
        response = client.get(f"/nieuwsbrief/o/{name}.gif")
        assert response.status_code == 200 and response.content == tracking.PIXEL_GIF
        assert response.headers["content-type"] == "image/gif"
        assert "no-store" in response.headers["cache-control"]
    assert db_session.query(LetterEvent).count() == 0
    assert client.get(f"/nieuwsbrief/k/{forged}/1", follow_redirects=False).status_code == 404
    assert client.get(f"/nieuwsbrief/k/{'9' * 5000}/1", follow_redirects=False).status_code == 404


def test_one_code_opening_twice_counts_one_and_two_codes_count_two(client, db_session):
    """T6: the second write of one code is refused by the database itself, not only by
    the service."""
    letter = _letter(db_session)
    db_session.commit()
    first, second = tracking.make_code(letter.id), tracking.make_code(letter.id)
    for code in (first, first, second):
        assert client.get(f"/nieuwsbrief/o/{code}.gif").status_code == 200
    assert db_session.query(LetterEvent).filter_by(newsletter_id=letter.id).count() == 2
    assert tracking.results_of(db_session, [letter.id])[letter.id].opened == 2
    db_session.add(
        LetterEvent(newsletter_id=letter.id, code=first, link_id=None, day=belgian_today())
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_failing_write_still_redirects(client, db_session, monkeypatch):
    """T9."""
    letter = _letter(db_session)
    link = tracking.link_ids(db_session, letter.id, [OUTSIDE])[OUTSIDE]
    db_session.commit()
    monkeypatch.setattr(
        "app.domains.newsletter.tracking.belgian_today", lambda: (_ for _ in ()).throw(OSError())
    )
    code = tracking.make_code(letter.id)
    response = client.get(f"/nieuwsbrief/k/{code}/{link}", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == OUTSIDE


def test_fifty_pixels_of_different_codes_from_one_address_are_all_recorded(client, db_session):
    """T14: no per-address limit — a mail proxy fetches hundreds from a few addresses."""
    letter = _letter(db_session)
    db_session.commit()
    for _ in range(50):
        client.get(f"/nieuwsbrief/o/{tracking.make_code(letter.id)}.gif")
    assert db_session.query(LetterEvent).filter_by(newsletter_id=letter.id).count() == 50


# ── What is kept ─────────────────────────────────────────────────────────────


def test_the_event_table_has_no_column_that_can_name_a_person():
    """T7, the gate of C7: only the letter, the code, the link and the day. A column for an
    address, a delivery, an IP or a time of day is the end of the promise made in the
    letter's footer. Proven red by adding a column `email` to the model."""
    from app.database import Base

    table = Base.metadata.tables["newsletter.letter_events"]
    assert {c.name for c in table.columns} == {
        "id",
        "tenant_id",
        "newsletter_id",
        "code",
        "link_id",
        "day",
    }
    assert str(table.c.day.type) == "DATE", "a day, not a moment"


def test_a_code_stands_nowhere_but_in_the_mail(db_session, mailbox):
    """The portal's own tables hold no link between a code and a person: after a send the
    deliveries carry no code, and the events table is empty until a reader acts."""
    letter = _letter(db_session)
    mail = _mail_of(db_session, mailbox, letter)
    code = _code_of(mail)
    found = db_session.execute(
        text("SELECT count(*) FROM newsletter.deliveries d WHERE d::text LIKE :c"),
        {"c": f"%{code}%"},
    ).scalar()
    assert found == 0
    assert db_session.query(LetterEvent).count() == 0
    assert "letter_events" in inspect(db_session.get_bind()).get_table_names(schema="newsletter")


def test_the_log_is_kept_for_ninety_days():
    """The e-mail log ties a code to a recipient for as long as it is kept (B9, 15 October
    2026: 90 days, not 365)."""
    from app.config import settings

    assert settings.email_log_retention_days == 90


# ── The privacy statement (Q5) ───────────────────────────────────────────────


def _migration():
    import importlib.util
    from pathlib import Path

    path = next(
        (Path(__file__).resolve().parents[2] / "alembic" / "versions").glob("214_2026_10_16_*.py")
    )
    spec = importlib.util.spec_from_file_location("cr37_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_privacy_page_has_the_newsletter_section_once_and_a_restore_keeps_it(
    client, db_session
):
    """T11: asserted on the rendered page, not on `content`; a second run adds nothing; the
    latest history version carries the section, so restoring it keeps the section."""
    from app.domains.cms.models import CmsPage, CmsPageHistory

    page = client.get("/privacy")
    assert page.status_code == 200
    assert "Nieuwsbrief" in page.text and "tellen we hoeveel brieven geopend" in page.text
    assert "niet bij wie een brief las" in page.text
    migration = _migration()
    before = db_session.query(CmsPageHistory).count()
    done = migration.add_privacy_section(db_session.connection())
    assert done["documents"] == 0 and done["html"] == 0 and done["left alone"] >= 1
    assert db_session.query(CmsPageHistory).count() == before
    privacy = db_session.query(CmsPage).filter(CmsPage.slug == "privacy").first()
    latest = (
        db_session.query(CmsPageHistory)
        .filter(CmsPageHistory.page_id == privacy.id)
        .order_by(CmsPageHistory.id.desc())
        .first()
    )
    assert "tellen we hoeveel brieven geopend" in str(latest.document)


def test_a_page_that_has_no_section_gets_it_in_its_document_or_its_html(db_session):
    """The migration's two paths, on pages made without it."""
    from app.domains.cms.models import CmsPage, CmsPageHistory, CmsPageTranslation

    migration = _migration()
    privacy = db_session.query(CmsPage).filter(CmsPage.slug == "privacy").first()
    translation = (
        db_session.query(CmsPageTranslation)
        .filter(CmsPageTranslation.page_id == privacy.id, CmsPageTranslation.language == "nl")
        .one()
    )
    plain = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Wie zijn we?"}],
            }
        ],
    }
    translation.draft_json = plain
    translation.published_json = plain
    db_session.flush()
    history = db_session.query(CmsPageHistory).count()
    done = migration.add_privacy_section(db_session.connection())
    db_session.refresh(translation)
    assert done["documents"] >= 1
    for document in (translation.draft_json, translation.published_json):
        assert document["content"][-2]["attrs"]["level"] == 2, "the page's own heading level"
        assert document["content"][-1]["content"][0]["text"].startswith("Bij de nieuwsbrief")
    assert db_session.query(CmsPageHistory).count() == history + done["documents"]
    # A page that kept its HTML.
    db_session.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == privacy.id).delete()
    privacy.content = "<h3>Wie zijn we?</h3>"
    db_session.flush()
    assert migration.add_privacy_section(db_session.connection())["html"] >= 1
    db_session.refresh(privacy)
    assert "tellen we hoeveel brieven geopend" in privacy.content


# ── The result (phase 1) ─────────────────────────────────────────────────────


def _admin(client) -> None:
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _counted_letter(client, db_session, mailbox):
    """A letter sent to four made-up readers: two open (one of them twice), one clicks."""
    letter = _letter(db_session)
    for n in range(4):
        subscriber(db_session, f"lezer{n}@example.org")
    _send_all(db_session, letter)
    db_session.commit()
    mails = {m["to"]: m for m in mailbox.sent}
    for who in ("lezer0@example.org", "lezer0@example.org", "lezer1@example.org"):
        client.get(f"/nieuwsbrief/o/{_code_of(mails[who])}.gif")
    path = re.search(
        r'href="https://raak.example(/nieuwsbrief/k/[^"]+)"', mails["lezer0@example.org"]["body"]
    )
    client.get(path.group(1), follow_redirects=False)
    return letter


def test_the_archive_shows_the_result_of_a_sent_letter_and_names_nobody(
    client, db_session, mailbox
):
    """Walkthrough 7 and 8, AC1, AC2, AC7: opened 2 of 4, clicked 1 of 4, the link with 1,
    each labelled as an indication; no address, name or time of day on the block."""
    letter = _counted_letter(client, db_session, mailbox)
    _admin(client)
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert page.status_code == 200
    block = page.text.split("data-letter-result", 1)[1].split("De tekst zoals hij vertrok")[0]
    assert "Geopend (indicatie)" in block and "50&nbsp;%" in block and "2 mensen" in block
    assert "Geklikt (indicatie)" in block and "25&nbsp;%" in block and "1 persoon" in block
    assert OUTSIDE.replace("&", "&amp;") in block
    assert "example.org" not in block, "the result names nobody"
    assert "lezer" not in block


def test_the_archive_list_percentages_equal_the_counts_of_the_events(client, db_session, mailbox):
    """T16."""
    letter = _counted_letter(client, db_session, mailbox)
    result = tracking.results_of(db_session, [letter.id])[letter.id]
    assert (result.sent, result.opened, result.clicked, result.link_count) == (4, 2, 1, 1)
    assert (result.opened_pct, result.clicked_pct) == (50, 25)
    _admin(client)
    page = client.get("/admin/nieuwsbrieven")
    # #2123: the kit's table shows the two shares in a column of their own ("Geopend ·
    # geklikt"); the link count stays on the letter's own result block.
    line = page.text.split("data-letter-result", 1)[1].split("</span>", 1)[0]
    assert "50\u00a0% · 25\u00a0%" in line.replace("&nbsp;", "\u00a0")


def test_a_letter_that_was_not_sent_shows_no_result(client, db_session):
    _letter(db_session)
    db_session.commit()
    _admin(client)
    assert "data-letter-result" not in client.get("/admin/nieuwsbrieven").text


def test_a_resent_mail_cannot_push_a_share_over_one_hundred():
    assert tracking._pct(5, 4) == 100
    assert tracking._pct(1, 0) is None

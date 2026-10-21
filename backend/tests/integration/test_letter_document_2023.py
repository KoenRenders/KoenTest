"""CR-17 phase 7b (#2023, C6 10): the letter is a document of the page editor, the
mail is built from its blocks, and migration 212 moves every letter onto it.

Broken on purpose (15 October 2026), each red for its own reason: the marker
splitter not cutting a paragraph at the marker → the mid-paragraph test fails; the
`closing` block taken out of `mail_blocks` → the blocks test fails; the schema not
asked at the save → the refusal test fails; the migration keeping a sent letter's
text out of the conversion → the migration test fails.
"""

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.cms.api import render_document
from app.domains.newsletter import service as nb
from app.domains.newsletter.letter_markup import (
    document_to_markup,
    markup_to_document,
)
from app.domains.newsletter.models import Audience, DeliveryKind
from app.kernel.clock import belgian_today
from tests._letter import letter_doc

pytestmark = pytest.mark.ui_serverrendered

BASE = "https://raak.example"
VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"
MIGRATION = next(VERSIONS.glob("212_*document_of_*.py"))
FREEZE = next(VERSIONS.glob("320_*freeze_the_sent_letters*.py"))


def _activity(db, name="Zomerfeest", days=10):
    from app.domains.activities.api import Activity, ActivityDate

    activity = Activity(name=name, location="Dorpsplein", slug=name.lower())
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=belgian_today() + timedelta(days=days)))
    db.flush()
    return activity


def _letter(db, body):
    letter = nb.create_newsletter(db, created_by="s@example.org")
    nb.update_draft(db, letter, subject="Najaar", body=body, audience=Audience.MEMBERS)
    return letter


def _mail(db, letter):
    return nb.render_mail(db, letter, kind=DeliveryKind.MEMBER, unsubscribe_url=None, base_url=BASE)


def _doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def _par(words):
    return {"type": "paragraph", "content": [{"type": "text", "text": words}]}


# ── The markers become blocks, and back ──────────────────────────────────────


def test_a_marker_on_its_own_line_is_a_block_and_the_text_around_it_stays():
    document = markup_to_document(
        "<div>Beste,</div><div>[[activiteit:7|Zomerfeest]]</div><div>[[kalender]]</div>"
        "<div>Tot dan.</div><div>[[afsluiting]]</div>"
    )
    assert [b["type"] for b in document["content"]] == [
        "paragraph",
        "activity",
        "calendar",
        "paragraph",
        "closing",
    ]
    assert document["content"][1]["attrs"] == {"activity_id": 7}


def test_a_marker_in_the_middle_of_a_paragraph_cuts_it():
    """Broken on purpose: `_split` returning the paragraph whole → the marker stays
    text and this test fails."""
    document = markup_to_document("<div>Kom naar [[activiteit:7]] want het is leuk.</div>")
    assert [b["type"] for b in document["content"]] == ["paragraph", "activity", "paragraph"]
    assert document["content"][0]["content"][0]["text"].strip() == "Kom naar"
    assert document["content"][2]["content"][0]["text"].strip() == "want het is leuk."


def test_a_blank_line_is_no_paragraph():
    """The `<div><br></div>` Trix wrote as space: the mail gives its own space."""
    document = markup_to_document("<div>Een</div><div><br></div><div>Twee</div>")
    assert [b["type"] for b in document["content"]] == ["paragraph", "paragraph"]


def test_the_text_with_markers_round_trips_through_the_document():
    markup = (
        "<p>Beste,</p><div>[[activiteit:7]]</div><div>[[kalender]]</div><div>[[afsluiting]]</div>"
    )
    assert document_to_markup(markup_to_document(markup)) == markup


# ── The mail is built from the blocks ────────────────────────────────────────


def test_every_block_of_the_letter_is_built_for_the_mail(db_session):
    activity = _activity(db_session)
    activity.description = "Een avond over vaderschap."
    db_session.flush()  # the seed is the test's own write, before the app commits (#1885 gate 2)
    letter = _letter(
        db_session,
        _doc(
            _par("Beste,"),
            {"type": "activity", "attrs": {"activity_id": activity.id}},
            {"type": "calendar"},
            {"type": "closing"},
        ),
    )
    mail = _mail(db_session, letter)
    assert "Zomerfeest" in mail and "Een avond over vaderschap." in mail
    assert "Tot binnenkort!" in mail, "the closing"
    assert 'class="nb-blok-titel" style="font-size:20px' in mail, "styles inline, at the send"
    assert "[[" not in mail
    assert '<p style="margin:0 0 12px">Beste,</p>' in mail


def test_an_activity_that_is_gone_leaves_nothing_behind(db_session):
    letter = _letter(
        db_session, _doc(_par("Hoi"), {"type": "activity", "attrs": {"activity_id": 99999}})
    )
    assert "99999" not in _mail(db_session, letter)


def test_a_picture_and_a_button_are_built_for_a_mail(db_session):
    """Absolute addresses, inline styles and a table for the button: a mail client
    has no stylesheet. Broken on purpose: the `button` entry of `mail_blocks` removed
    → the site's `prose-button` class stands in the mail and this test fails."""
    from app.domains.media.models import MediaAsset

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    asset = MediaAsset(
        kind="page_image",
        title="Foto",
        data=png,
        content_type="image/png",
        thumbnail=png,
        thumb_content_type="image/png",
        width=64,
        height=48,
        byte_size=len(png),
        sort_order=0,
        is_active=True,
    )
    db_session.add(asset)
    db_session.flush()
    letter = _letter(
        db_session,
        _doc(
            {
                "type": "figure",
                "attrs": {"media_id": asset.id, "alt": "Een foto", "caption": "Onderschrift"},
            },
            {
                "type": "button",
                "attrs": {
                    "label": "Lees meer",
                    "variant": "primary",
                    "href": "https://voorbeeld.example/meer",
                },
            },
        ),
    )
    mail = _mail(db_session, letter)
    assert f'src="{BASE}/' in mail and 'alt="Een foto"' in mail and "Onderschrift" in mail
    assert "prose-button" not in mail and "prose-figure" not in mail
    assert 'href="https://voorbeeld.example/meer"' in mail and "<table" in mail
    assert "background:#0051a4" in mail, "the primary button has its colour in the mail"


def test_a_page_renders_the_letters_blocks_as_nothing():
    document = _doc(_par("Tekst"), {"type": "calendar"}, {"type": "closing"})
    html = render_document(document)
    assert html == "<p>Tekst</p>"


def test_the_text_part_reads_the_blocks_too(db_session):
    activity = _activity(db_session)
    letter = _letter(
        db_session,
        _doc(_par("Beste,"), {"type": "activity", "attrs": {"activity_id": activity.id}}),
    )
    body = nb.render_text(db_session, letter, unsubscribe_url=None, base_url=BASE)
    assert "Zomerfeest" in body and "[[" not in body and "<" not in body.split("---")[0]


def test_a_letter_with_only_a_block_is_not_blank_and_an_empty_one_is(db_session):
    only_block = _letter(db_session, _doc({"type": "calendar"}))
    empty = _letter(db_session, _doc({"type": "paragraph"}))
    assert not nb.letter_is_blank(only_block)
    assert nb.letter_is_blank(empty)


# ── The schema is the border ─────────────────────────────────────────────────


def test_a_document_the_schema_refuses_is_refused_by_name_and_nothing_is_stored(db_session):
    letter = _letter(db_session, _doc(_par("Goed")))
    with pytest.raises(nb.NewsletterError, match="Onbekend blok"):
        nb.update_draft(
            db_session,
            letter,
            subject="x",
            body=_doc({"type": "scriptje"}),
            audience=Audience.MEMBERS,
        )
    with pytest.raises(nb.NewsletterError):
        nb.update_draft(db_session, letter, subject="x", body="{niet-json", audience=None)
    assert letter.body_document == _doc(_par("Goed")), "nothing stored"


# ── Migration 212 ────────────────────────────────────────────────────────────


def test_the_migration_converts_every_letter_the_sent_ones_too_and_drops_the_html(db_session):
    """Koen, 15 October 2026: convert everything, the sent letters too, and drop the
    old column in the same change. Broken on purpose: a sent letter left out of the
    loop → its document stays empty and the last assertion fails."""
    sent = _letter(db_session, _doc(_par("x")))
    draft = _letter(db_session, _doc(_par("y")))
    sent_id, draft_id = sent.id, draft.id
    spec = importlib.util.spec_from_file_location("letters_210", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The state before the migration: the HTML column back, the document column gone.
    db_session.execute(
        text("ALTER TABLE newsletter.newsletters DROP CONSTRAINT ck_newsletter_sent_has_body")
    )
    db_session.execute(text("ALTER TABLE newsletter.newsletters DROP COLUMN body_document"))
    db_session.execute(
        text("ALTER TABLE newsletter.newsletters ADD COLUMN body_html TEXT NOT NULL DEFAULT ''")
    )
    db_session.execute(
        text("UPDATE newsletter.newsletters SET body_html = :b, status = 'sent' WHERE id = :i"),
        {"b": "<div>Beste,</div><div>[[activiteit:7|Zomerfeest]]</div>", "i": sent_id},
    )
    db_session.execute(
        text("UPDATE newsletter.newsletters SET body_html = :b WHERE id = :i"),
        {"b": "<div>Een concept.</div>", "i": draft_id},
    )
    assert module.convert_letters(db_session.connection()) >= 2
    rows = dict(
        db_session.execute(
            text(
                "SELECT id, body_document FROM newsletter.newsletters WHERE id IN :ids"
            ).bindparams(ids=(sent_id, draft_id))
        ).fetchall()
    )
    assert [b["type"] for b in rows[sent_id]["content"]] == ["paragraph", "activity"]
    assert rows[draft_id]["content"][0]["content"][0]["text"] == "Een concept."
    columns = {
        r[0]
        for r in db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'newsletter' AND table_name = 'newsletters'"
            )
        )
    }
    assert "body_html" not in columns and "body_document" in columns
    assert module.convert_letters(db_session.connection()) == 0, "a second run changes nothing"
    assert json.loads(json.dumps(rows[sent_id]))["type"] == "doc"


def test_the_helper_makes_the_document_of_a_text():
    assert letter_doc("<div>Hoi</div>")["content"][0]["type"] == "paragraph"


# ── The letter as it went (Koen, 16 October 2026: "a") ───────────────────────


def _send(db, letter):
    from app.domains.newsletter.models import Subscriber, SubscriberStatus

    db.add(
        Subscriber(
            email="lezer@example.org",
            status=SubscriberStatus.CONFIRMED,
            source="admin",
            unsubscribe_token="frozen-1",
        )
    )
    letter.audience = Audience.NON_MEMBERS
    db.flush()
    nb.start_sending(
        db, letter, sent_by="s@example.org", reply_to_mode="association", base_url=BASE
    )


def test_a_sent_letter_keeps_the_body_it_went_with(db_session):
    """The activity moves after the send: the archive and every later mail still read
    the body of the moment. Broken on purpose: `start_sending` not writing the column →
    the archive shows the new place and this test fails."""
    activity = _activity(db_session)
    letter = _letter(
        db_session,
        _doc(_par("Beste,"), {"type": "activity", "attrs": {"activity_id": activity.id}}),
    )
    assert letter.sent_body_html is None, "a draft is built from today's data"
    _send(db_session, letter)
    assert "Dorpsplein" in letter.sent_body_html
    activity.location = "Kerkplein"
    db_session.flush()
    assert "Dorpsplein" in nb.render_body(db_session, letter, base_url=BASE)
    assert "Kerkplein" not in _mail(db_session, letter)


def test_a_sent_letter_without_its_body_is_refused_by_the_database(db_session):
    """Broken on purpose: the CHECK left out → the flush succeeds and this fails."""
    from sqlalchemy.exc import IntegrityError

    letter = _letter(db_session, _doc(_par("Hoi")))
    letter.status = nb.LetterStatus.SENT
    with pytest.raises(IntegrityError, match="ck_newsletter_sent_has_body"):
        db_session.flush()
    db_session.rollback()


def _freeze_module():
    spec = importlib.util.spec_from_file_location("letters_320", FREEZE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unfrozen(db, body):
    """A letter as the migration finds it: sent, with no frozen body and no CHECK yet."""
    letter = _letter(db, body)
    letter.link_base = BASE
    db.execute(
        text(
            "ALTER TABLE newsletter.newsletters DROP CONSTRAINT IF EXISTS ck_newsletter_sent_has_body"
        )
    )
    letter.status = nb.LetterStatus.SENT
    db.flush()
    return letter


def test_the_migration_freezes_the_sent_letters_and_leaves_a_draft(db_session):
    activity = _activity(db_session)
    body = _doc(_par("Hoi"), {"type": "activity", "attrs": {"activity_id": activity.id}})
    sent = _unfrozen(db_session, body)
    draft = _letter(db_session, body)
    module = _freeze_module()
    assert module.freeze_sent_letters(db_session.connection()) == 1
    db_session.expire_all()
    assert "Zomerfeest" in sent.sent_body_html and "Hoi" in sent.sent_body_html
    assert draft.sent_body_html is None
    assert module.freeze_sent_letters(db_session.connection()) == 0, "a second run changes nothing"


@pytest.mark.parametrize(
    "block",
    [
        _par("Beste leden,"),
        {
            "type": "paragraph",
            "content": [{"type": "value", "attrs": {"code": "membership_valid_until"}}],
        },
    ],
    ids=["prose", "value-node"],
)
def test_the_migration_freezes_a_sent_letter_outside_any_tenant(db_session, monkeypatch, block):
    """#2195: a migration runs outside any tenant, and rendering prose asks the clock for a
    day (`membership_valid_until`). PROD's v2.17.0 deploy died here on a sent letter with prose.
    The migration renders each letter in its own tenant, and leaves no tenant behind.

    Broken on purpose (21 October 2026): the `current_tenant_id.set` taken out of
    `freeze_sent_letters` → `NoTenantContext`, both cases red."""
    from app.domains.payment.api import membership_valid_period
    from app.kernel import clock
    from app.kernel.tenancy import current_tenant_id

    year = str(membership_valid_period()[1].year)
    sent = _unfrozen(db_session, _doc(block))
    module = _freeze_module()
    # Only now: building the letter is a call inside a tenant, the migration is not.
    monkeypatch.setattr(clock, "tenant_of_the_call", current_tenant_id.get)
    assert current_tenant_id.get() is None, "the test must run outside any tenant"
    assert module.freeze_sent_letters(db_session.connection()) == 1
    assert current_tenant_id.get() is None, "the migration leaves no tenant behind"
    db_session.expire_all()
    if block["content"][0]["type"] == "value":
        assert year in sent.sent_body_html
    else:
        assert "Beste leden," in sent.sent_body_html

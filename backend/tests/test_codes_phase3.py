"""What phase 3 of CR-12 must prove: the constants domains (§B8).

Nineteen lists — eight in `newsletter`, three in `meetings` on top of the
phase-0 pilot, seven in `designstudio`. The largest phase in number of lists
and the smallest in risk: no money, no roles, no stored value changes.

So the test that carries this phase is **§B8.5 / AC3: the same Dutch words as
before**. Nothing about the behaviour of these screens should move; what moves
is where the word comes from. :data:`LABELS_BEFORE_CR12` is that snapshot,
copied literally out of the module constants as they stood on this branch
before they were deleted, and every entry is checked against the label table.

The second thing worth proving is what did **not** become a list. The brand
assets of the design studio have a payload — an SVG path, two house-style
colours, a file-name fragment — and §B4.10 keeps them out. A phase that
converts nineteen lists is exactly when the twentieth gets converted by
reflex, so there is a test against it.

## Proof that these can go red

The method of the css gate (#652): make one real violation, run the test, put
it back. Measured on 26 September 2026, each on its own:

| Test | Violation | Fired |
|---|---|---|
| The same Dutch words | the `beeld` seed back to the shorter wording an earlier draft had | yes — names the list, the code and both words |
| The database refuses a non-code | the `preset` list removed from migration 157, so the column keeps no key | yes — *DID NOT RAISE* |
| The dropped checks are gone | `ck_design_preset` left out of 157's `CHECKS` | yes — names the constraint |
| The two kept checks stay | `ck_design_focus` added to 157's `CHECKS` | yes |
| A column stores the code | `EnumColumn` on `designs.status` swapped for `sa.Enum(DesignStatus)` | yes |
| The screen shows a word | the badge back to `{{ s.status.value }}` in `_nb_abonnees.html` | yes — after a correction, see below |
| The brand assets stay out | a `CodeList` named `duo` registered in `designstudio/codes.py` | yes |
| The attendance button turns green | the view boundary back to `attendance_of(...)` straight through | yes — no `bg-green-50`, and `value="Attendance.PRESENT"` |

**Two of the eight are worth a sentence.**

The `sa.Enum` swap fired, but not on the assertion it was written for: the
foreign key refused the write, because `sa.Enum` stored the member *name*
`FINAL` and there is no such code. That is the corruption of §B4.1 being
caught one layer lower than expected — the assertion would have caught it
too, had the key not been there first.

The badge measurement had to be redone, and it is the same trap as everywhere
in this repository. The first version asserted `"Bevestigd" in page.text`.
With the badge rendering the raw code that assertion **still passed**, because
the filter dropdown on the same page carries the word. Asserting the presence
of a word proves nothing about *where* it is; the test now looks at rendered
text — `>confirmed<` — which is what a code on a screen actually looks like.
"""
import re

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.designstudio.api import (
    DesignStatus,
    DrawingStyle,
    GenerationStatus,
    InsetCorner,
    Layout,
    Preset,
    RenderVariant,
)
from app.domains.meetings.api import Attendance, FilePurpose, SectionKind
from app.domains.newsletter.api import (
    Audience,
    DeliveryKind,
    DeliveryStatus,
    LetterStatus,
    MessageRole,
    ReplyToMode,
    SubscriberSource,
    SubscriberStatus,
)
from app.kernel.codes import code_label, code_of, registry, reset_label_cache
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.test_designstudio_service import activity, design  # noqa: F401 - fixtures

#: The Dutch words these nineteen screens showed before CR-12, taken literally
#: from the module constants as they stood on 26 September 2026:
#: `newsletter/admin_ui.py` (`LETTER_STATUS_LABELS`, `AUDIENCE_LABELS`,
#: `DELIVERY_LABELS`, `SUBSCRIBER_LABELS`, `SOURCE_LABELS`),
#: `meetings/service.py` (`SECTION_LABELS`), `designstudio/service.py`
#: (`PRESET_LABELS`, `STATUS_LABELS`, `LAYOUT_LABELS`),
#: `designstudio/admin_ui.py` (`CORNER_LABELS`, `GENERATION_LABELS`) and
#: `designstudio/imaging.py` (`STYLE_LABELS`).
#:
#: A list with no dictionary before it is absent here on purpose: there is no
#: "same word" to keep, and inventing one would turn this snapshot into a
#: second place where the words live.
LABELS_BEFORE_CR12 = {
    "letter_status": {"draft": "Concept", "sending": "Wordt verstuurd",
                      "sent": "Verstuurd"},
    "audience": {"members": "Leden", "non_members": "Niet-leden",
                 "both": "Allebei"},
    "delivery_status": {"queued": "In de wachtrij", "sent": "Verstuurd",
                        "failed": "Mislukt", "skipped": "Overgeslagen"},
    "subscriber_status": {"confirmed": "Bevestigd",
                          "pending": "Wacht op bevestiging",
                          "unsubscribed": "Uitgeschreven"},
    "section_kind": {"EVALUATION": "Evaluatie voorbije activiteiten",
                     "UPCOMING": "Volgende activiteiten",
                     "MEMBERS": "Leden",
                     "IDEAS": "Programma-ideeën",
                     "MISC": "Varia"},
    "design_status": {"draft": "Ontwerp", "final": "Definitief"},
    "layout": {"print_a": "Print (A3/A4)", "feed_portrait": "Instagram (4:5)"},
    "preset": {
        "eenvoudig": "Eenvoudig — één grote foto en de tekst van de activiteit "
                     "over de volle breedte",
        "beeld": "Met beeld — foto of tekening rechts, kernpunten links, "
                 "omschrijving eronder",
        "tekst": "Tekst — geen beeld, kernpunten links, omschrijving rechts"},
    "inset_corner": {"top_left": "Linksboven", "top_right": "Rechtsboven",
                     "bottom_left": "Linksonder", "bottom_right": "Rechtsonder"},
    "generation_status": {"requested": "Bezig…", "fetched": "Klaar",
                          "picked": "Gekozen", "discarded": "Niet gekozen",
                          "refused": "Geweigerd (moderatie)", "failed": "Mislukt"},
    "drawing_style": {"lijn": "Lijntekening (zwart-wit)",
                      "lijnkleur": "Lijntekening met kleuraccenten",
                      "kleur": "Kleurtekening (vlakke kleuren)"},
}

#: The nineteen lists of this phase, with the enum that belongs to each.
PHASE_3_LISTS = {
    "subscriber_status": SubscriberStatus, "subscriber_source": SubscriberSource,
    "audience": Audience, "letter_status": LetterStatus,
    "reply_to_mode": ReplyToMode, "delivery_kind": DeliveryKind,
    "delivery_status": DeliveryStatus, "message_role": MessageRole,
    "meeting_status": None,  # the phase-0 pilot; counted, not rebuilt here
    "section_kind": SectionKind, "attendance": Attendance,
    "file_purpose": FilePurpose,
    "design_status": DesignStatus, "layout": Layout,
    "render_variant": RenderVariant, "generation_status": GenerationStatus,
    "preset": Preset, "inset_corner": InsetCorner,
    "drawing_style": DrawingStyle,
}


@pytest.fixture(autouse=True)
def _clean_label_cache():
    reset_label_cache()
    yield
    reset_label_cache()


# ── §B8.5 / AC3 The same Dutch words as before ───────────────────────────────

@pytest.mark.parametrize("code_list", sorted(LABELS_BEFORE_CR12))
def test_every_screen_shows_the_same_dutch_word_as_before(db_session, code_list):
    """AC3, and the point of this phase: the source of the word changed, the
    word did not.

    A conversion that quietly rewords a status is the kind of change nobody
    reports and everybody notices. This compares the label table against the
    dictionaries that stood in the modules on the day they were deleted.
    """
    for code, before in LABELS_BEFORE_CR12[code_list].items():
        assert code_label(code_list, code, language="nl", db=db_session) == before, (
            f"`{code_list}` code {code!r} used to read {before!r}")


@pytest.mark.parametrize("code_list", sorted(PHASE_3_LISTS))
def test_every_list_of_this_phase_is_registered_with_both_languages(db_session, code_list):
    entry = registry()[code_list]
    for language in ("nl", "en"):
        rows = db_session.execute(
            text(f"SELECT count(*) FROM {entry.labels_table} WHERE language = :l"),
            {"l": language}).scalar_one()
        codes = db_session.execute(
            text(f"SELECT count(*) FROM {entry.codes_table}")).scalar_one()
        assert rows == codes, f"`{code_list}` has {codes} codes but {rows} `{language}` labels"


@pytest.mark.parametrize("code_list, enum_cls",
                         sorted((k, v) for k, v in PHASE_3_LISTS.items() if v is not None))
def test_the_enum_of_every_list_covers_exactly_its_codes(db_session, code_list, enum_cls):
    codes = {row[0] for row in db_session.execute(
        text(f"SELECT code FROM {registry()[code_list].codes_table}")).all()}
    assert {m.value for m in enum_cls} == codes


# ── §B8.2 / AC1 The database refuses what is not a code ──────────────────────

def _rows_for_the_refusal_test(db, design):
    """One real row per table, so the `UPDATE` below can only fail on the
    foreign key.

    An `INSERT` with just the one column would also raise `IntegrityError` —
    on a `NOT NULL` somewhere else — and the test would be green with the key
    removed. That is the shape `CLAUDE.md` warns about: it tests the failure
    and not the reason.
    """
    from datetime import date

    from app.domains.meetings.api import create_meeting, sections_of
    from app.domains.newsletter.api import add_by_admin, create_newsletter

    meeting = create_meeting(db, meeting_date=date(2026, 11, 3))
    letter = create_newsletter(db, created_by="bestuur@example.com")
    # `ck_newsletter_sent_has_audience` refuses a non-draft status without an
    # audience. Choosing one here leaves the foreign key as the only thing
    # that can refuse the status below.
    letter.audience = Audience.MEMBERS
    subscriber = add_by_admin(db, "ongeldig@example.com")
    db.flush()
    return {
        "designstudio.designs": design.id,
        "meetings.meeting_sections": sections_of(db, meeting)[0].id,
        "newsletter.newsletters": letter.id,
        "newsletter.subscribers": subscriber.id,
    }


#: `(table, column, a value that is not a code)`.
NOT_A_CODE = [
    ("designstudio.designs", "preset", "illustratie"),
    ("designstudio.designs", "status", "definitief"),
    ("designstudio.designs", "inset_corner", "midden"),
    ("meetings.meeting_sections", "kind", "VARIA"),
    ("newsletter.newsletters", "audience", "iedereen"),
    ("newsletter.newsletters", "status", "concept"),
    ("newsletter.subscribers", "status", "bevestigd"),
    ("newsletter.subscribers", "source", "formulier"),
]


@pytest.mark.parametrize("table, column, value", NOT_A_CODE)
def test_a_value_that_is_not_a_code_never_reaches_the_column(
        db_session, design, table, column, value):  # noqa: F811
    """AC1 per domain: the value does not get in, not even by raw SQL.

    And it fails **for the right reason**: SQLSTATE 23503 is a foreign-key
    violation. Without that assertion a `NOT NULL` elsewhere in the row would
    keep this test green after the key was dropped.
    """
    ids = _rows_for_the_refusal_test(db_session, design)
    with pytest.raises(IntegrityError) as caught:
        db_session.execute(
            text(f"UPDATE {table} SET {column} = :v WHERE id = :i"),
            {"v": value, "i": ids[table]})
    assert caught.value.orig.pgcode == "23503", (
        f"{table}.{column} refused {value!r} with SQLSTATE "
        f"{caught.value.orig.pgcode}, not with a foreign key (23503)")
    db_session.rollback()


# ── §B8.3 The check constraints the foreign keys replace ─────────────────────

DROPPED_CHECKS = [
    ("newsletter", "subscribers", "ck_newsletter_subscriber_status"),
    ("newsletter", "subscribers", "ck_newsletter_subscriber_source"),
    ("newsletter", "newsletters", "ck_newsletter_audience"),
    ("newsletter", "newsletters", "ck_newsletter_status"),
    ("newsletter", "deliveries", "ck_newsletter_delivery_kind"),
    ("newsletter", "deliveries", "ck_newsletter_delivery_status"),
    ("newsletter", "drafting_messages", "ck_newsletter_message_role"),
    ("meetings", "meeting_attendances", "ck_meeting_attendances_status"),
    ("meetings", "meeting_files", "ck_meeting_files_purpose"),
    ("meetings", "meeting_sections", "ck_meeting_sections_kind"),
    ("designstudio", "designs", "ck_design_status"),
    ("designstudio", "designs", "ck_design_preset"),
    ("designstudio", "designs", "ck_design_inset_corner"),
    ("designstudio", "design_renditions", "ck_design_rendition_layout"),
    ("designstudio", "design_renditions", "ck_design_rendition_variant"),
    ("designstudio", "image_generations", "ck_image_generation_status"),
]


@pytest.mark.parametrize("schema, table, constraint", DROPPED_CHECKS)
def test_a_check_that_says_what_the_foreign_key_says_is_gone(db_session, schema, table, constraint):
    """Two guards on one value is how they drift: a new code gets a row and
    the check still refuses it, months later, from a migration nobody reads."""
    names = {c["name"] for c in inspect(db_session.bind).get_check_constraints(
        table, schema=schema)}
    assert constraint not in names


@pytest.mark.parametrize("table, constraint", [
    ("designs", "ck_design_focus"),
    ("design_renditions", "ck_design_rendition_owner"),
    ("newsletters", "ck_newsletter_sent_has_audience"),
])
def test_a_check_that_spans_two_columns_stays(db_session, table, constraint):
    """A foreign key says "this value is in that list". These say something a
    list cannot: that two numbers are within bounds, that a variant matches
    whether there is a version, that an audience is chosen before sending.
    """
    schema = "designstudio" if table != "newsletters" else "newsletter"
    names = {c["name"] for c in inspect(db_session.bind).get_check_constraints(
        table, schema=schema)}
    assert constraint in names


# ── §B8.4 The column stores the code, never the member name ──────────────────

def test_the_columns_of_this_phase_store_the_code(db_session, design):
    """The reason `EnumColumn` exists. `sa.Enum(SomeEnum)` would write `DRAFT`
    where every export, report and query expects `draft`, and nothing raises.
    """
    design.status = DesignStatus.FINAL
    design.preset = Preset.TEXT
    design.inset_corner = InsetCorner.TOP_LEFT
    db_session.flush()
    row = db_session.execute(text(
        "SELECT status, preset, inset_corner FROM designstudio.designs WHERE id = :i"),
        {"i": design.id}).one()
    assert tuple(row) == ("final", "tekst", "top_left")
    db_session.expire(design)
    assert design.status is DesignStatus.FINAL
    assert design.preset is Preset.TEXT


def test_a_code_assigned_as_a_string_becomes_the_member_at_once(db_session, design):
    """A form hands over a string. Without the coercion listener the object
    holds a `str` until the next flush, and `design.preset is Preset.TEXT`
    is false in between — a difference that only shows up in the one branch
    that runs before the commit.
    """
    design.preset = "tekst"
    assert design.preset is Preset.TEXT


# ── §B8.6 The screen shows a word, not a code ────────────────────────────────

def test_the_subscriber_screen_shows_words_and_the_filter_carries_codes(client, db_session):
    """AC2: nothing on the screen reads like a database value.

    The filter is the half that broke silently in this phase: its options used
    to be keyed by an enum member, which Jinja renders as
    `SubscriberStatus.CONFIRMED` into a `value=` attribute. The option value
    must be the code, and the text next to it the word.
    """
    from app.domains.newsletter.api import add_by_admin

    add_by_admin(db_session, "abonnee@example.com", first_name="Iemand")
    db_session.commit()
    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    page = client.get("/admin/nieuwsbrieven/abonnees")
    assert page.status_code == 200
    assert 'value="confirmed"' in page.text          # the filter carries the code
    assert "SubscriberStatus." not in page.text      # never a member
    # The badge itself. `"Bevestigd" in page.text` is not enough: the filter
    # option carries that word too, so the badge could render the raw code
    # and the assertion would still pass. This one looks at rendered text —
    # `>confirmed<` — and that is what a code on the screen looks like.
    assert not re.search(r">\s*confirmed\s*<", page.text), (
        "the subscriber badge renders the code instead of the word")
    assert re.search(r">\s*Bevestigd\s*<", page.text), (
        "the subscriber badge should read `Bevestigd`")


def test_the_design_list_shows_the_preset_and_the_status_in_words(client, db_session, design):
    db_session.commit()
    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    page = client.get("/admin/ontwerpen")
    assert page.status_code == 200
    assert "Ontwerp" in page.text
    assert "Preset." not in page.text and "DesignStatus." not in page.text


def test_the_attendance_button_comes_back_green_after_one_click(client, db_session):
    """A code that reaches a template attribute must be a code, not a member.

    This one was found by the e2e golden flow and **not** by this suite, which
    is why it is written down here. `attendance_of` returns members since this
    phase; the meeting document puts the value in
    `<input name="current" value="{{ state }}">` and compares it to
    `'present'` for the colour. A member renders as `Attendance.PRESENT` in
    that attribute and equals no literal, so every click stayed grey and the
    next click restarted the cycle. The conversion now happens on the view
    boundary.

    Asserting on the rendered fragment and not on `attendance_of`: the stored
    state was right the whole time. The screen was not.
    """
    from datetime import date

    from app.domains.meetings.api import create_meeting
    from tests.test_vergadering_routes import _kringlid

    person = _kringlid(db_session, voornaam="Aanwezig", achternaam="Persoon",
                       email="aanwezig@example.org")
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 10))
    db_session.commit()

    sess = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, sess)
    response = client.post(
        f"/admin/vergaderingen/{meeting.id}/aanwezigheid",
        headers={"X-CSRF-Token": csrf_token_for(sess)},
        data={"person_id": str(person.id), "current": ""})
    assert response.status_code == 200
    assert 'name="current" value="present"' in response.text, (
        "the form must send back the CODE, not the member")
    assert "Attendance." not in response.text
    assert "bg-green-50" in response.text, (
        "the button should come back green after one click")


# ── §B4.10 What deliberately did NOT become a code list ──────────────────────

def test_the_brand_assets_of_the_design_studio_stay_out_of_the_pattern():
    """Icons, colour duos, paper sizes and template keys have a payload — an
    SVG path, two house-style colours, a file-name fragment — and change with
    the brand guide, not with a translator (§B4.10).

    This test exists because a phase that converts nineteen lists is exactly
    when the twentieth gets converted by reflex.
    """
    from app.domains.designstudio import brand, icons, service

    assert not ({"duo", "icon", "paper_size", "template_key", "size"}
                & set(registry())), "a brand asset became a code list"
    assert icons.ICONS and brand.DUOS, "the assets moved out of their modules"
    assert service.FILE_SIZE_LABELS["feed"] == "portrait", (
        "the file-name fragment is not a translation")


def test_the_preset_reaches_the_renderer_as_a_member(db_session, design):
    """`PosterContent` is the boundary between the service and the renderer.

    The block layout branches on the preset, so the renderer gets the member
    and never a string — whichever of the two its caller happened to hold.
    """
    from app.domains.designstudio.content import PosterContent
    from app.domains.designstudio.service import content_for

    assert PosterContent(duo_code=design.duo_code, preset="eenvoudig").preset is Preset.SIMPLE
    assert content_for(db_session, design).preset is Preset.PICTURE


def test_the_section_heading_comes_from_the_label_table(db_session):
    """`section_label` was a dictionary in the service; the words are the same
    and a custom section still uses its own title."""
    from app.domains.meetings.api import MeetingSection, section_label

    standard = MeetingSection(kind=SectionKind.IDEAS, position=10)
    assert section_label(standard) == "Programma-ideeën"
    own = MeetingSection(kind=SectionKind.CUSTOM, title="Rondvraag", position=20)
    assert section_label(own) == "Rondvraag"


def test_code_of_gives_the_stored_value_for_every_enum_of_this_phase():
    """History tables and file names take the code, not the member (§F4)."""
    for code_list, enum_cls in PHASE_3_LISTS.items():
        if enum_cls is None:
            continue
        for member in enum_cls:
            assert code_of(member) == member.value, f"{code_list}: {member!r}"

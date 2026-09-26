"""What phase 0 of CR-12 must prove before the money domain is touched (§B8).

The pilot list is `meetings.meeting_status`: three codes, one screen, one
badge. Small enough that a mistake is visible, real enough to show the four
things every later phase leans on.

**The most important test here is the round trip**, and the reason is in §B10:
`sa.Enum` stores the **member name** by default. A column declared against
`PaymentStatus` would then hold `PAID` where every query, export and report
expects `paid` — and nothing breaks, not on write and not on read. The mistake
ends up in the data, which is the expensive kind. `EnumColumn` exists to rule
exactly that out, and this test is the proof that it does.
"""
from datetime import date

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import MEETING_STATUS, MeetingStatus, create_meeting
from app.i18n import current_locale
from app.kernel.codes import (
    CodeSeed,
    code_label,
    code_labels,
    registry,
    reset_label_cache,
    tone,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

#: The Dutch words the screens showed before CR-12, taken literally from
#: `meetings/admin_ui.py:STATUS_LABELS` as it stood on 25 September 2026.
#: §B8.5: later phases assert against this that the screens show the same
#: words. If one of these changes, that is a decision and not a detail.
LABELS_BEFORE_CR12 = {"agenda": "Agenda", "report": "Verslag (bezig)",
                      "sent": "Verslag verstuurd"}

#: The tones as they were, for the same reason.
TONES_BEFORE_CR12 = {"agenda": "blue", "report": "yellow", "sent": "green"}


@pytest.fixture(autouse=True)
def _clean_label_cache():
    """The cache lives per process; tests may not inherit each other's language."""
    reset_label_cache()
    yield
    reset_label_cache()


# ── §B8.3 The round trip ─────────────────────────────────────────────────────

def test_an_enum_member_lands_in_the_column_as_its_code(db_session):
    """Read raw, the column holds `sent` — not `SENT`, not `MeetingStatus.SENT`.

    This is the test that covers the silent data-corruption risk. Had the
    column been declared against `sa.Enum(MeetingStatus)`, this would read
    `SENT` and nothing in the application would complain about it.
    """
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 3))
    meeting.status = MeetingStatus.SENT
    db_session.flush()

    raw = db_session.execute(
        text("SELECT status FROM meetings.meetings WHERE id = :id"),
        {"id": meeting.id}).scalar_one()
    assert raw == "sent"
    assert raw != "SENT", "the member name got stored — EnumColumn is not doing its job"
    assert "MeetingStatus" not in raw


def test_a_code_in_the_column_reads_back_as_the_member(db_session):
    """The other direction: what was already there comes back as a member."""
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 4))
    db_session.execute(
        text("UPDATE meetings.meetings SET status = 'report' WHERE id = :id"),
        {"id": meeting.id})
    db_session.expire(meeting)

    assert meeting.status is MeetingStatus.REPORT
    assert meeting.status != "report", (
        "a plain Enum must NOT equal its string — if it does, it is a `str, Enum` "
        "and every loose comparison stays quietly true")


def test_a_value_outside_the_list_is_caught_on_read(db_session):
    """Corrupt data raises with the list and the value, not a bare string.

    A bare string would be unequal to *every* member — the same silent failure
    one layer up. Such a row can only be created by a writer outside the
    application, because the foreign key refuses it; that is why this is an
    exception and not a rendering case. The test has to drop that key first to
    create the case at all, which also shows the key really is the first line.
    The fixture's SAVEPOINT puts it back afterwards.
    """
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 5))
    db_session.execute(text(
        "ALTER TABLE meetings.meetings DROP CONSTRAINT fk_meetings_status_code"))
    db_session.execute(
        text("UPDATE meetings.meetings SET status = 'kwijt' WHERE id = :id"),
        {"id": meeting.id})
    db_session.expire(meeting)

    with pytest.raises(ValueError) as error:
        _ = meeting.status
    assert "kwijt" in str(error.value)
    assert "MeetingStatus" in str(error.value)


# ── §B8.2 and AC1 The foreign key holds ──────────────────────────────────────

def test_the_database_refuses_a_status_that_does_not_exist(db_session):
    """AC1 on the pilot list: an unknown code does not get in, not even by raw SQL."""
    from sqlalchemy.exc import IntegrityError

    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 6))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE meetings.meetings SET status = 'verzonden' WHERE id = :id"),
            {"id": meeting.id})


# ── §B8.4 One label per code per language ────────────────────────────────────

def test_every_active_code_of_every_list_has_nl_and_en(db_session):
    """Exactly one non-empty text per language, for every list in the registry.

    **Not "the label differs from the code".** That was the first version of
    this test and it was wrong: gender `X` is labelled `X`, and so are
    `Facebook`, `TikTok` and `Mollie`. A label that happens to equal its code is
    a real label. What has to hold is that the row exists — otherwise
    `code_label()` falls back to the code and the screen looks fine while the
    translation is missing.
    """
    from sqlalchemy import text as sql

    for lst in registry().values():
        for code, _label in code_labels(lst.name, language="nl"):
            for language in ("nl", "en"):
                rows = db_session.execute(sql(
                    f"SELECT value FROM {lst.labels_table} "
                    f"WHERE code = :c AND language = :l"),
                    {"c": code, "l": language}).scalars().all()
                assert rows and rows[0], (
                    f"`{lst.name}`.`{code}` has no {language} label row")
                assert code_label(lst.name, code, language=language) == rows[0]


def test_the_pilot_list_shows_the_same_dutch_words_as_before_cr12(db_session):
    """§B8.5: the screen may notice nothing of this move."""
    for code, expected in LABELS_BEFORE_CR12.items():
        assert code_label("meeting_status", code, language="nl") == expected


def test_the_english_labels_are_seeded(db_session):
    assert code_label("meeting_status", MeetingStatus.SENT, language="en") == \
        "Report sent"


def test_the_select_list_comes_in_sort_order(db_session):
    """`sort_order` is the last place where a Python list decided the order.

    All three codes are active here, so this test shows the ordering and not the
    `is_active` filter; that one is checked where something *is* retired, in the
    retirement test below.
    """
    assert [code for code, _ in code_labels("meeting_status", language="nl")] == \
        ["agenda", "report", "sent"]


def test_a_member_may_go_straight_into_the_label_function(db_session):
    assert code_label("meeting_status", MeetingStatus.REPORT, language="nl") == \
        "Verslag (bezig)"


# ── §B4.4 The fallbacks ──────────────────────────────────────────────────────

def test_an_unknown_language_falls_back_to_dutch(db_session):
    assert code_label("meeting_status", "sent", language="de") == "Verslag verstuurd"


def test_an_unknown_code_shows_itself_and_is_logged_once(db_session, caplog):
    """Under `StrictUndefined`, rendering blank is worse than showing the code.

    One warning per (list, code) and not per render: a list screen with forty
    rows would otherwise put forty identical lines in the log, and then nobody
    reads the log any more.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="app.kernel.codes"):
        assert code_label("meeting_status", "bestaat-niet") == "bestaat-niet"
        assert code_label("meeting_status", "bestaat-niet") == "bestaat-niet"
    lines = [r for r in caplog.records if "bestaat-niet" in r.getMessage()]
    assert len(lines) == 1, f"{len(lines)} warnings instead of one"


def test_the_active_language_comes_from_the_locale(db_session):
    """`nl_BE` → `nl`: the setting is a locale, the label key a language (§F8)."""
    token = current_locale.set("en_GB")
    try:
        assert code_label("meeting_status", "sent") == "Report sent"
    finally:
        current_locale.reset(token)


# ── §B4.5 The tones ──────────────────────────────────────────────────────────

def test_the_tones_are_the_ones_from_before_cr12():
    import app.main  # noqa: F401  — loads the UI module that registers them

    for code, expected in TONES_BEFORE_CR12.items():
        assert tone("meeting_status", code) == expected


# ── §B8.6 The screen renders text ────────────────────────────────────────────

def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_the_meeting_screen_shows_the_label_and_not_the_code(client, db_session):
    """Through the real view-model, in the `StrictUndefined` environment.

    Before CR-12 the badge came out of a dictionary in `admin_ui.py`; now out of
    the label table through the Jinja filter. The screen must read identically —
    which is exactly what Koen validates on HDEV.
    """
    create_meeting(db_session, meeting_date=date(2026, 11, 7))
    db_session.commit()
    _login(client)

    response = client.get("/admin/vergaderingen")
    assert response.status_code == 200
    body = response.text
    assert "Agenda" in body
    assert "MeetingStatus" not in body, "the member name leaks onto the screen"


# ── The migration helper ─────────────────────────────────────────────────────

def test_the_helper_refuses_an_fk_on_data_that_does_not_fit(db_session):
    """The guard before the foreign key names the value *and* the count.

    Proven by violation: one row with a value outside the list, and the helper
    must abort before it adds the key — with the number in the message, so the
    reader knows whether it is one row or fifteen. That is the shape phase 1
    leans on (§B4.6), so it is measured here and not there.
    """
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.kernel.codes import create_code_list

    db_session.execute(text(
        "CREATE TABLE meetings.proef (id serial PRIMARY KEY, soort_code varchar(10))"))
    db_session.execute(text(
        "INSERT INTO meetings.proef (soort_code) VALUES ('een'), ('kwijt'), ('kwijt')"))
    op = Operations(MigrationContext.configure(db_session.connection()))

    with pytest.raises(RuntimeError) as error:
        create_code_list(op, schema="meetings", name="proef_soort",
                         codes=(CodeSeed(code="een", nl="Een", en="One"),),
                         fk_from=("meetings.proef.soort_code",), code_length=10)
    message = str(error.value)
    assert "'kwijt'×2" in message
    assert "meetings.proef.soort_code" in message


def test_retiring_deletes_nothing_and_keeps_the_fk_valid(db_session):
    """`retire_code` clears `is_active` — a delete would break history.

    Phase 2 retires gender `U`/`O`, and phase 2 is not the place to discover
    that this helper never ran. The invariants: the row survives (the foreign
    key of existing rows stays valid), it no longer counts as active, the member
    stays in the enum and the label stays readable — otherwise an old meeting
    could suddenly not show its status.

    **What this test deliberately does NOT measure through `code_labels()`.**
    The label cache reads through a session the kernel opens itself (§B2.4), so
    a retirement that sits in the test transaction and is not committed yet is
    invisible to it. That is not a shortcoming of the helper but the design of
    the cache: labels only change by migration, and that is committed before
    anything renders. The `is_active` filter is therefore checked on the table.
    """
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.kernel.codes import retire_code

    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 8))
    meeting.status = MeetingStatus.SENT
    db_session.flush()
    op = Operations(MigrationContext.configure(db_session.connection()))

    retire_code(op, schema="meetings", name="meeting_status", code="sent",
                used_by=("meetings.meetings.status",))

    row = db_session.execute(text(
        "SELECT is_active FROM meetings.meeting_status_codes WHERE code = 'sent'"
    )).all()
    assert row == [(False,)], "a retired code may not disappear, only switch off"
    assert db_session.execute(text(
        "SELECT code FROM meetings.meeting_status_codes WHERE is_active "
        "ORDER BY sort_order")).scalars().all() == ["agenda", "report"]
    assert db_session.execute(text(
        "SELECT value FROM meetings.meeting_status_labels "
        "WHERE code = 'sent' AND language = 'nl'")).scalar_one() == \
        "Verslag verstuurd"
    assert MeetingStatus.SENT in list(MeetingStatus), (
        "the member stays, otherwise this row reads back as a bare string")
    db_session.expire(meeting)
    assert meeting.status is MeetingStatus.SENT


def test_the_pilot_list_is_in_the_registry():
    assert registry()["meeting_status"] is MEETING_STATUS
    assert MEETING_STATUS.enum is MeetingStatus
    assert MEETING_STATUS.codes_table == "meetings.meeting_status_codes"

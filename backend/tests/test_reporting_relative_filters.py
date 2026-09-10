"""Relative filter values: "vandaag", "dit jaar", "ik" (#847).

A saved report stores its filter values literally, which means a report about "this
year" is a report about 2026 forever. In January it answers a question nobody asked
while looking exactly as trustworthy as it did in December — and that is worse than
having no saved report, because nothing about it looks wrong.

Three values fix that by being stored as a **reference** and resolved when the
report runs. The first two change *what* a report shows; `ik` changes *for whom it
shows something else*, which is the point and also where it could go wrong.

**The clock is an argument, never a call to `date.today()` in a test.** A test that
can only turn red next January is not a test, so both moments are passed in.

**Where identity enters is itself under test.** `build_query` still takes a
selection and a tenant and nothing else; resolution happens one layer up. That
keeps `ik` a filter value and stops it becoming a role fence — a different
question, still open (CR-06 §5.1).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.reporting.api import (
    SYMBOLIC_ME, SYMBOLIC_THIS_YEAR, SYMBOLIC_TODAY, Filter, Operator, Selection,
    SelectionError, is_personal, resolve_selection, run_validated,
    selection_from_dict, selection_to_dict,
)
from tests._reporting_seed import TENANT_A, seed


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _members_this_year() -> Selection:
    """"How many members do we have this year", saved as a relative report."""
    return Selection(
        object_keys=("membership_year", "membership_households"),
        filters=(Filter("membership_year", Operator.EQ, (), SYMBOLIC_THIS_YEAR),))


# ── The reason this issue exists (#847 test 1) ───────────────────────────────

def test_the_same_saved_report_moves_with_the_year(db_session, situation):
    """Two "now" moments, two answers, one stored report."""
    _y0, y1, y2, _y3 = situation["years"]

    vorig = run_validated(db_session, _members_this_year(), tenant_id=TENANT_A,
                          today=date(y1, 6, 1))
    dit = run_validated(db_session, _members_this_year(), tenant_id=TENANT_A,
                        today=date(y2, 6, 1))

    assert [r["membership_year"] for r in vorig.rows] == [y1]
    assert [r["membership_year"] for r in dit.rows] == [y2]
    assert vorig.rows[0]["membership_households"] != dit.rows[0]["membership_households"], (
        "de seed heeft 1 gezin in het ene jaar en 2 in het andere — het getal "
        "beweegt mee, niet alleen het label")


def test_a_literal_value_does_not_move(db_session, situation):
    """The counter-proof. Without it, "everything moves" and "the right thing
    moves" look the same from the green side."""
    _y0, y1, y2, _y3 = situation["years"]
    vast = Selection(
        object_keys=("membership_year", "membership_households"),
        filters=(Filter("membership_year", Operator.EQ, (str(y1),)),))

    vroeg = run_validated(db_session, vast, tenant_id=TENANT_A,
                          today=date(y1, 6, 1))
    laat = run_validated(db_session, vast, tenant_id=TENANT_A,
                         today=date(y2, 6, 1))
    assert [r["membership_year"] for r in vroeg.rows] == [y1]
    assert [r["membership_year"] for r in laat.rows] == [y1], (
        "een hardgezette waarde blijft staan waar ze stond")


def test_today_resolves_to_the_day_it_runs(db_session, situation):
    selectie = Selection(
        object_keys=("date_day", "payment_amount"),
        filters=(Filter("date_day", Operator.LTE, (), SYMBOLIC_TODAY),))
    opgelost = resolve_selection(selectie, today=date(2026, 3, 4))
    assert opgelost.filters[0].values == ("2026-03-04",)
    # And it still runs against the database.
    assert run_validated(db_session, selectie, tenant_id=TENANT_A,
                         today=date(2026, 3, 4)) is not None


# ── `ik` (#847 test 3) ───────────────────────────────────────────────────────

def _closed_task(db, *, by: str, days_ago: int = 3):
    from app.domains.workflow.api import WorkflowTask

    nu = datetime.now(timezone.utc)
    taak = WorkflowTask(
        tenant_id=TENANT_A, kind="kernel.job_gefaald", title="Klaar",
        subject_type="kernel_job", subject_id=f"s{days_ago}", status="done",
        required_role="ADMIN", created_at=nu - timedelta(days=days_ago + 2),
        done_at=nu - timedelta(days=days_ago), done_by=by)
    db.add(taak)
    db.commit()
    return taak


def test_the_same_report_shows_each_person_their_own_rows(db_session, situation):
    """#847 test 3. One saved report, two people, two outcomes.

    "Tasks I closed" is the case the mechanism is proved on: a task carries who
    closed it, so `ik` has a real column to compare against.
    """
    _closed_task(db_session, by="anna@example.com", days_ago=3)
    _closed_task(db_session, by="bram@example.com", days_ago=5)
    _closed_task(db_session, by="bram@example.com", days_ago=7)

    mijn_taken = Selection(
        object_keys=("task_done_by", "task_count"),
        filters=(Filter("task_done_by", Operator.EQ, (), SYMBOLIC_ME),))

    anna = run_validated(db_session, mijn_taken, tenant_id=TENANT_A,
                         viewer="anna@example.com")
    bram = run_validated(db_session, mijn_taken, tenant_id=TENANT_A,
                         viewer="bram@example.com")

    assert [r["task_done_by"] for r in anna.rows] == ["anna@example.com"]
    assert anna.rows[0]["task_count"] == 1
    assert [r["task_done_by"] for r in bram.rows] == ["bram@example.com"]
    assert bram.rows[0]["task_count"] == 2, "elk ziet alleen zijn eigen rijen"


def test_a_personal_report_without_anybody_signed_in_says_so(db_session, situation):
    """Falling back to "everybody" would be the worst possible default."""
    mijn_taken = Selection(
        object_keys=("task_done_by", "task_count"),
        filters=(Filter("task_done_by", Operator.EQ, (), SYMBOLIC_ME),))
    with pytest.raises(SelectionError) as exc:
        run_validated(db_session, mijn_taken, tenant_id=TENANT_A, viewer="")
    assert "aangemelde gebruiker" in str(exc.value)


def test_a_personal_report_is_marked_as_personal():
    """#847 point 2: somebody shares a link and the receiver has to understand."""
    assert is_personal(Selection(
        object_keys=("task_done_by", "task_count"),
        filters=(Filter("task_done_by", Operator.EQ, (), SYMBOLIC_ME),)))
    assert not is_personal(_members_this_year())


def test_the_panel_offers_the_relative_values_and_marks_the_report(client,
                                                                   db_session,
                                                                   situation):
    """A user has to be able to BUILD such a report, not only open a seeded one.

    Which is why this asserts three things at once: the option is offered where it
    means something, choosing it produces a relative filter, and the panel then
    says the report is personal.
    """
    from tests.test_reporting_panel_ui import login

    login(client, db_session, "anna@example.com", ("ADMIN",))
    _closed_task(db_session, by="anna@example.com", days_ago=3)
    _closed_task(db_session, by="bram@example.com", days_ago=5)

    fragment = client.get(
        "/admin/rapporten/paneel?object=task_done_by&object=task_count"
        "&filter=task_done_by&op_task_done_by=eq&v_task_done_by=@ik")
    assert fragment.status_code == 200
    assert 'value="@ik"' in fragment.text, "de keuze staat in de lijst"
    assert "toont jouw eigen gegevens" in fragment.text, (
        "en het scherm zegt dat het rapport per persoon verschilt")
    # On the TABLE and not on the whole fragment: the filter dropdown lists every
    # value the dimension has, which is what a dropdown is for and what CR-06 §7.3
    # allows an admin to see. What must be personal is the result.
    tabel = fragment.text[fragment.text.index("<tbody"):
                          fragment.text.index("</tbody>")]
    assert "anna@example.com" in tabel
    assert "bram@example.com" not in tabel, "anna ziet alleen haar eigen taak"


def test_a_year_filter_offers_this_year_and_a_municipality_does_not(client,
                                                                    db_session,
                                                                    situation):
    """Offering all three everywhere would let somebody filter a gemeente on today."""
    from tests.test_reporting_panel_ui import login

    login(client, db_session)
    jaar = client.get(
        "/admin/rapporten/paneel?object=membership_year"
        "&object=membership_households&filter=membership_year")
    assert 'value="@dit_jaar"' in jaar.text
    assert 'value="@vandaag"' not in jaar.text

    gemeente = client.get(
        "/admin/rapporten/paneel?object=member_municipality"
        "&object=membership_households&filter=member_municipality")
    assert "@dit_jaar" not in gemeente.text and "@vandaag" not in gemeente.text


# ── Where identity may and may not enter (#847 tests 4 and 5) ────────────────

def test_the_engine_still_knows_no_identity_and_no_clock():
    """The signature test of #832, restated because #847 brings identity back.

    `ik` resolves one layer up, in `service.resolve_selection`. If it were to move
    into `build_query`, the engine would hold identity — and the step from "a
    filter value" to "which objects may you see" is short enough that the only
    safe place to refuse it is the signature.
    """
    import inspect

    from app.domains.reporting.api import build_query, resolve_selection

    assert set(inspect.signature(build_query).parameters) == {"selection", "tenant_id"}
    resolutie = set(inspect.signature(resolve_selection).parameters)
    assert resolutie == {"selection", "today", "viewer"}, (
        "identiteit en de klok komen hier binnen, en alleen hier")


def test_resolving_does_not_touch_what_was_saved(db_session, situation):
    """Opening a report once must not freeze it."""
    bewaard = _members_this_year()
    resolve_selection(bewaard, today=date(2026, 1, 1))
    assert bewaard.filters[0].values == (), "de bewaarde selectie blijft relatief"
    assert bewaard.filters[0].symbolic == SYMBOLIC_THIS_YEAR


def test_resolving_twice_changes_nothing(db_session, situation):
    """The panel resolves before it dispatches and the service resolves again."""
    eerst = resolve_selection(_members_this_year(), today=date(2026, 1, 1))
    nogmaals = resolve_selection(eerst, today=date(2026, 1, 1))
    assert eerst.filters[0].values == nogmaals.filters[0].values == ("2026",)


def test_resolving_ik_twice_does_not_lose_the_viewer(db_session, situation):
    """The second pass may not throw the first one's answer away.

    This is not hypothetical: the panel resolves with the signed-in user and then
    calls the service, which resolves again with whatever it was given. When that
    second pass raised "there is nobody signed in", the panel rendered no table
    and no error — just an empty result area, which is the hardest kind of bug to
    read.
    """
    mijn = Selection(
        object_keys=("task_done_by", "task_count"),
        filters=(Filter("task_done_by", Operator.EQ, (), SYMBOLIC_ME),))

    eerst = resolve_selection(mijn, viewer="anna@example.com")
    assert eerst.filters[0].values == ("anna@example.com",)

    nogmaals = resolve_selection(eerst, viewer="")
    assert nogmaals.filters[0].values == ("anna@example.com",)

    # But an unresolved one with nobody signed in still refuses, loudly.
    with pytest.raises(SelectionError):
        resolve_selection(mijn, viewer="")


def test_a_relative_value_survives_being_saved_and_read_back():
    heen = selection_to_dict(_members_this_year())
    assert heen["filters"][0]["symbolic"] == SYMBOLIC_THIS_YEAR
    terug = selection_from_dict(heen)
    assert terug.filters[0].symbolic == SYMBOLIC_THIS_YEAR
    assert terug.filters[0].values == ()


def test_an_unknown_relative_value_is_refused_by_name():
    with pytest.raises(SelectionError) as exc:
        selection_from_dict({
            "objects": ["membership_year", "membership_households"],
            "filters": [{"object": "membership_year", "operator": "eq",
                         "values": [], "symbolic": "vorige_maand"}],
        })
    assert "'vorige_maand'" in str(exc.value)


def test_a_report_saved_before_this_change_still_reads_literally():
    """Every filter saved before #847 has no `symbolic` key, and must not gain one."""
    oud = selection_from_dict({
        "objects": ["membership_year", "membership_households"],
        "filters": [{"object": "membership_year", "operator": "eq",
                     "values": ["2026"]}],
    })
    assert oud.filters[0].symbolic == ""
    assert resolve_selection(oud, today=date(2030, 1, 1)).filters[0].values == ("2026",)


def test_the_export_header_says_both_what_it_means_and_what_it_was(db_session,
                                                                   situation):
    """A sheet that says only "dit jaar" cannot be checked a year later; one that
    says only "2026" hides that it moves."""
    from app.domains.reporting.api import filter_summary

    opgelost = resolve_selection(_members_this_year(), today=date(2026, 6, 1))
    regels = filter_summary(opgelost)
    assert regels == ["Lidmaatschapsjaar is dit jaar (2026)"]

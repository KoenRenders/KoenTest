"""An address group without a main member is not loaded, and the import says so (#1832).

Koen, 9 October 2026, in writing, to the master CLI's question "Kies je a of b?"
— a being: the group is not loaded and the detail says so, the same rule as for
two main members: *"a"*.

Until then the import made a household of such a group — a partner and a child,
say — WITHOUT a main member and without an address (the address hangs on the
main member's row), created the year's membership, and said nothing. And for a
household that was loaded before and whose main member the report no longer
lists, it took the main member away and left the others without one.

Now none of the group's rows is added, changed or removed, it counts under
"overgeslagen", and one sentence in the detail names the rows and says what to
change in the report. The preview says the same as the run.

Red proofs, one replacement each, the tree as before afterwards — the counts
stand in the pull request.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.domains.mdm.api import Address, Member, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from app.domains.membership.api import Membership
from tests._snapshot import compare
from tests.conftest import seed_postal_code

SNAPSHOTS = Path(__file__).parent / "snapshots" / "import_1832"
BEFORE = "what the import does with an address group without a main member (#1832)"
NO_MAIN = "op een adres zonder lid"


def _row(lidnr, voornaam, naam, relatie, huisnummer):
    return {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": "Voorbeeldstraat",
        "huisnummer": huisnummer,
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": f"{voornaam.lower()}@example.com" if relatie == "HOOFDLID" else None,
        "telefoon": None,
        "gsm": "0470000000" if relatie == "HOOFDLID" else None,
        "geboortedatum": date(1980, 5, 1),
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": relatie,
    }


def _load(db, families, *, apply=True):
    return upsert_families(
        db, [[dict(row) for row in fam] for fam in families], {}, [], apply=apply
    )


def _stored(db) -> list[str]:
    """Per household: who is in it with which relation, how many addresses its
    members have and how many memberships it has — sorted, so two runs compare."""
    db.expire_all()
    told = []
    for member in db.query(Member):
        links = db.query(MemberPerson).filter_by(member_id=member.id).all()
        people = sorted((mp.person.first_name, mp.relation_type.value) for mp in links)
        addresses = sum(1 for mp in links if mp.person.address)
        memberships = db.query(Membership).filter_by(member_id=member.id).count()
        told.append(f"household: {people} addresses {addresses} memberships {memberships}")
    return sorted(told) or ["no household"]


def _counts(db) -> tuple:
    return tuple(db.query(model).count() for model in (Member, Person, MemberPerson, Address))


def _good():
    return [
        _row("100", "Jan", "Janssens", "HOOFDLID", "1"),
        _row("101", "An", "Janssens", "PARTNER", "1"),
    ]


def _without_main():
    return [_row("400", "Sam", "Thys", "PARTNER", "5"), _row("401", "Lou", "Thys", "KIND", "5")]


def _detail(db, report) -> str:
    counts = (
        f"new {report.new_families} · changed {report.updated_families} · "
        f"unchanged {report.unchanged_families} · persons added {report.persons_added} · "
        f"removed {report.persons_removed} · skipped {report.skipped}"
    )
    # A household's own number in its header is a sequence value: masked.
    lines = [re.sub(r"gezin \(#\d+\)", "gezin (#N)", line) for line in report.lines]
    parts = [counts, "-- warnings", *report.warnings, "-- lines", *lines, "-- stored", *_stored(db)]
    return "\n".join(parts) + "\n"


def test_the_detail_of_a_report_with_a_group_without_a_main_member(db_session):
    """Recorded on the code before the rule and again after it: a good household and
    a group of a partner and a child — the preview, the run, the second upload."""
    seed_postal_code(db_session)
    rows = [_good(), _without_main()]

    compare(
        SNAPSHOTS,
        "no_main_preview",
        _detail(db_session, _load(db_session, rows, apply=False)),
        BEFORE,
    )
    compare(SNAPSHOTS, "no_main_run", _detail(db_session, _load(db_session, rows)), BEFORE)
    compare(SNAPSHOTS, "no_main_second_run", _detail(db_session, _load(db_session, rows)), BEFORE)


def test_the_detail_when_a_loaded_household_loses_its_main_member_in_the_report(db_session):
    """The other road to the same state: Jan and An were loaded; the next report
    lists An alone, as partner, on that address."""
    seed_postal_code(db_session)
    _load(db_session, [_good()])
    rows = [[_row("101", "An", "Janssens", "PARTNER", "1")]]

    compare(
        SNAPSHOTS,
        "main_gone_preview",
        _detail(db_session, _load(db_session, rows, apply=False)),
        BEFORE,
    )
    compare(SNAPSHOTS, "main_gone_run", _detail(db_session, _load(db_session, rows)), BEFORE)


# ── the rule ─────────────────────────────────────────────────────────────────


def test_a_group_without_a_main_member_is_not_loaded(db_session):
    seed_postal_code(db_session)
    before = _counts(db_session)

    report = _load(db_session, [_without_main()])

    assert _counts(db_session) == before, "a row of the refused address was written"
    assert db_session.query(Membership).count() == 0
    assert report.skipped == 1
    assert report.new_families == 0 and report.persons_added == 0
    assert not report.lines, "the refused address has lines in the detail of what is written"
    (sentence,) = report.warnings
    assert NO_MAIN in sentence
    # Every row by name and member number, so the report can be corrected.
    assert "Sam Thys (#400) en Lou Thys (#401) staan" in sentence
    assert "(2 rijen)" in sentence
    assert "één adres is dezelfde straat, huisnummer, bus en postcode" in sentence
    assert "zet op dit adres één persoon als lid" in sentence


def test_one_row_without_a_main_member_is_said_in_the_singular(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, [[_row("400", "Sam", "Thys", "PARTNER", "5")]])

    (sentence,) = report.warnings
    assert "Sam Thys (#400) staat op een adres zonder lid" in sentence
    assert "(1 rij)" in sentence and "geef deze persoon het adres" in sentence


def test_the_other_households_of_the_report_are_loaded(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, [_without_main(), _good()])

    assert report.new_families == 1 and report.persons_added == 2 and report.skipped == 1
    assert {p.first_name for p in db_session.query(Person)} == {"Jan", "An"}


def test_the_preview_says_the_same_as_the_run(db_session):
    seed_postal_code(db_session)
    rows = [_good(), _without_main()]

    preview = _load(db_session, rows, apply=False)
    assert _counts(db_session) == (0, 0, 0, 0), "the preview wrote"
    run = _load(db_session, rows)

    assert preview.warnings == run.warnings and len(run.warnings) == 1
    assert preview.lines == run.lines
    assert preview.skipped == run.skipped == 1


def test_a_loaded_household_keeps_its_main_member_when_the_report_drops_him(db_session):
    """The report lists An alone, as partner. Before the rule Jan was taken out of
    the household and An stayed behind without a main member and without an
    address. Now nothing of that address is touched: the household waits for a
    report that names a main member on it."""
    seed_postal_code(db_session)
    _load(db_session, [_good()])
    before = (_counts(db_session), _stored(db_session))

    report = _load(db_session, [[_row("101", "An", "Janssens", "PARTNER", "1")]])

    assert (_counts(db_session), _stored(db_session)) == before
    assert report.persons_removed == 0 and report.updated_families == 0
    assert any(NO_MAIN in sentence for sentence in report.warnings)
    db_session.flush()
    db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def test_a_group_that_gets_its_main_member_in_a_later_report_is_loaded_then(db_session):
    """What the sentence asks for works: one of them as "lid", and the address loads."""
    seed_postal_code(db_session)
    _load(db_session, [_without_main()])

    report = _load(
        db_session,
        [[_row("400", "Sam", "Thys", "HOOFDLID", "5"), _row("401", "Lou", "Thys", "KIND", "5")]],
    )

    assert report.new_families == 1 and report.skipped == 0 and not report.warnings
    assert _stored(db_session) == [
        "household: [('Lou', 'KIND'), ('Sam', 'HOOFDLID')] addresses 1 memberships 1"
    ]

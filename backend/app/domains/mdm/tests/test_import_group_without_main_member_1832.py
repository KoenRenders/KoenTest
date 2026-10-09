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

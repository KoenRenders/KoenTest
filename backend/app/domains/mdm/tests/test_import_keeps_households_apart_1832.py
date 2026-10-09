"""The member import does not make one household of two (#1832).

Found when the database got its net for "one main member per household": the
import itself could store two. An address group whose main member the import
does not know yet is looked up through its other members — and a member who
MOVED in with that main member led the group to the household he left. If that
household is in the same report with its own main member, both groups wrote to
it: two main members, two addresses, one household.

The lookups through another member and through identity pass over a household
that another address group of the report claims through its own main member.
The group is a new household then, and the member moves into it.

Red proofs, one replacement each, the tree as before afterwards — the counts
stand in the pull request.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.domains.mdm.api import Address, Member, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from tests._snapshot import compare
from tests.conftest import seed_postal_code

SNAPSHOTS = Path(__file__).parent / "snapshots" / "import_1832"
BEFORE = "what the import does when a member moves in with a new main member (#1832)"


def _row(lidnr, voornaam, naam, relatie, huisnummer, *, born=date(1980, 5, 1)):
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
        "geboortedatum": born,
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": relatie,
    }


def _load(db, families, *, apply=True):
    return upsert_families(
        db, [[dict(row) for row in fam] for fam in families], {}, [], apply=apply
    )


def _households(db) -> list[dict]:
    """Per household: who is in it with which relation, and the addresses of its
    members — sorted, so two runs compare."""
    db.expire_all()
    found = []
    for member in db.query(Member):
        links = db.query(MemberPerson).filter_by(member_id=member.id).all()
        found.append(
            {
                "members": sorted((mp.person.first_name, mp.relation_type.value) for mp in links),
                "addresses": sorted(
                    mp.person.address.house_number for mp in links if mp.person.address
                ),
            }
        )
    return sorted(found, key=lambda h: h["members"])


def _end_of_transaction(db) -> None:
    """What a commit checks, asked now: one main member per household."""
    db.flush()
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def _first():
    return [
        [
            _row("100", "Jan", "Janssens", "HOOFDLID", "1"),
            _row("101", "An", "Janssens", "PARTNER", "1"),
        ]
    ]


def _moved():
    """An moves in with Bob, a main member the import does not know yet."""
    return [
        [_row("100", "Jan", "Janssens", "HOOFDLID", "1")],
        [
            _row("200", "Bob", "Bakker", "HOOFDLID", "99"),
            _row("101", "An", "Janssens", "KIND", "99"),
        ],
    ]


def test_a_member_who_moves_in_with_a_new_main_member_makes_a_new_household(db_session):
    seed_postal_code(db_session)
    _load(db_session, _first())

    report = _load(db_session, _moved())

    assert _households(db_session) == [
        {"members": [("An", "KIND"), ("Bob", "HOOFDLID")], "addresses": ["99"]},
        {"members": [("Jan", "HOOFDLID")], "addresses": ["1"]},
    ]
    # The household An left has no line of its own: her move is said under the new one.
    assert report.new_families == 1 and report.unchanged_families == 1
    assert any("~ verhuisd #101" in line for line in report.lines)
    assert db_session.query(Person).count() == 3, "a person was made twice"
    assert db_session.query(Address).count() == 2
    _end_of_transaction(db_session)


def test_the_second_upload_of_that_report_changes_nothing(db_session):
    seed_postal_code(db_session)
    _load(db_session, _first())
    _load(db_session, _moved())
    after_first = _households(db_session)

    report = _load(db_session, _moved())

    assert _households(db_session) == after_first
    assert not report.lines and not report.warnings
    assert report.unchanged_families == 2


def test_the_preview_of_the_move_says_what_the_run_does(db_session):
    seed_postal_code(db_session)
    _load(db_session, _first())
    before = _households(db_session)

    preview = _load(db_session, _moved(), apply=False)
    assert _households(db_session) == before, "the preview wrote"
    run = _load(db_session, _moved())

    assert preview.lines == run.lines
    assert preview.warnings == run.warnings
    assert (preview.new_families, preview.unchanged_families) == (1, 1)


def test_an_orphaned_main_member_is_still_found_through_his_household(db_session):
    """The lookup through another member stays for what it was made for: the
    report gives a household a main member the import does not know, and nobody
    else in the report claims that household."""
    seed_postal_code(db_session)
    _load(db_session, _first())

    report = _load(
        db_session,
        [
            [
                _row("300", "Rik", "Janssens", "HOOFDLID", "1"),
                _row("101", "An", "Janssens", "PARTNER", "1"),
            ]
        ],
    )

    assert db_session.query(Member).count() == 1
    assert any("gekoppeld via bestaand gezinslid #101" in w for w in report.warnings)
    assert _households(db_session)[0]["members"] == [("An", "PARTNER"), ("Rik", "HOOFDLID")]
    _end_of_transaction(db_session)


def test_a_self_registered_member_is_still_joined_by_identity(db_session):
    """The lookup by identity stays as well: Ivo registered himself (no member
    number, main member of his own household); the report makes him the partner
    of a new main member. One household — and on the way there it holds two
    main members, which is why the database checks at the end."""
    seed_postal_code(db_session)
    ivo = Person(
        first_name="Ivo", last_name="Jansen", date_of_birth=date(1975, 3, 3), gender_code="M"
    )
    household = Member()
    db_session.add_all([ivo, household])
    db_session.flush()
    db_session.add(MemberPerson(member_id=household.id, person_id=ivo.id, relation_type="HOOFDLID"))
    db_session.flush()

    _load(
        db_session,
        [
            [
                _row("600", "Jo", "Faes", "HOOFDLID", "6"),
                _row("601", "Ivo", "Jansen", "PARTNER", "6", born=date(1975, 3, 3)),
            ]
        ],
    )

    assert _households(db_session) == [
        {"members": [("Ivo", "PARTNER"), ("Jo", "HOOFDLID")], "addresses": ["6"]}
    ]
    _end_of_transaction(db_session)


def test_a_member_without_a_number_who_moves_does_not_merge_two_households(db_session):
    """The same through the identity lookup: Ivo has no member number yet and
    lives with Jan; the report gives him one, at Bob's address. Jan's household
    is Jan's — his own row claims it — so Bob's group is a new household."""
    seed_postal_code(db_session)
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID", "1")]])
    jans = db_session.query(Member).one()
    ivo = Person(
        first_name="Ivo", last_name="Jansen", date_of_birth=date(1975, 3, 3), gender_code="M"
    )
    db_session.add(ivo)
    db_session.flush()
    db_session.add(MemberPerson(member_id=jans.id, person_id=ivo.id, relation_type="PARTNER"))
    db_session.flush()

    _load(
        db_session,
        [
            # Bob's group first: Ivo is still in Jan's household when it is looked up.
            [
                _row("200", "Bob", "Bakker", "HOOFDLID", "99"),
                _row("601", "Ivo", "Jansen", "KIND", "99", born=date(1975, 3, 3)),
            ],
            [_row("100", "Jan", "Janssens", "HOOFDLID", "1")],
        ],
    )

    assert [h["members"] for h in _households(db_session)] == [
        [("Bob", "HOOFDLID"), ("Ivo", "KIND")],
        [("Jan", "HOOFDLID")],
    ]
    assert db_session.query(Person).count() == 3, "Ivo was made twice"
    _end_of_transaction(db_session)


def test_the_old_main_member_moves_out_in_a_later_address_group(db_session):
    """The other order that passes through two main members: An becomes the main
    member of the household before Jan, in a later group, has left it."""
    seed_postal_code(db_session)
    _load(db_session, _first())

    _load(
        db_session,
        [
            [_row("101", "An", "Janssens", "HOOFDLID", "1")],
            [
                _row("200", "Bob", "Bakker", "HOOFDLID", "99"),
                _row("100", "Jan", "Janssens", "KIND", "99"),
            ],
        ],
    )

    assert [h["members"] for h in _households(db_session)] == [
        [("An", "HOOFDLID")],
        [("Bob", "HOOFDLID"), ("Jan", "KIND")],
    ]
    _end_of_transaction(db_session)


def _detail(db, report) -> str:
    counts = (
        f"new {report.new_families} · changed {report.updated_families} · "
        f"unchanged {report.unchanged_families} · persons added {report.persons_added} · "
        f"removed {report.persons_removed} · skipped {report.skipped}"
    )
    stored = [f"household: {h['members']} addresses {h['addresses']}" for h in _households(db)]
    return (
        "\n".join(
            [
                counts,
                "-- warnings",
                *report.warnings,
                "-- lines",
                *report.lines,
                "-- stored",
                *stored,
            ]
        )
        + "\n"
    )


def test_the_detail_of_the_move_in_preview_and_run(db_session):
    """What the board reads for the report in which An moved in with Bob, and
    what is stored after each step."""
    seed_postal_code(db_session)
    _load(db_session, _first())

    preview = _load(db_session, _moved(), apply=False)
    compare(SNAPSHOTS, "move_preview", _detail(db_session, preview), BEFORE)
    run = _load(db_session, _moved())
    compare(SNAPSHOTS, "move_run", _detail(db_session, run), BEFORE)

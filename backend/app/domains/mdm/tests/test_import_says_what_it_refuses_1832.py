"""The member import says what it does with an address that is not whole, and
does not load an address group with two main members (#1832).

Two decisions of Koen (9 October 2026), each on a question the issue put to him:

- a row whose address lacks a street or a house number — "dat is in orde, wel in
  de detail van de dry run die getoond wordt tonen ajb (als dat nog niet het geval
  is)": the import reads it in as before and says so, with what it writes;
- two rows "lid" on one address — "dat mag niet kunnen, ik stel voor ze beiden
  niet op te laden en dat in detail zo te zeggen, dan moet er aan de aangeleverde
  file iets aangepast worden": nobody of that address is loaded, and the detail
  says which four fields make one address.

Both are said in the preview and in the run with the same words: the preview is
what the board reads before it presses the button.

Red proofs, one replacement each, the tree as before afterwards — written with
the count of failures in the pull request.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.domains.mdm.api import Address, Member, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from tests._snapshot import compare
from tests.conftest import seed_postal_code

SNAPSHOTS = Path(__file__).parent / "snapshots" / "import_1832"
BEFORE = "the import's detail for an incomplete address and for two main members (#1832)"

TWO_MAIN_MEMBERS = "staan allebei als lid op hetzelfde adres"
ONE_ADDRESS = "één adres is dezelfde straat, huisnummer, bus en postcode"


def _row(
    lidnr, voornaam, naam, relatie, *, straat="Voorbeeldstraat", huisnummer="40", busnummer=""
):
    """One row as `read_ledenrapport` + `group_families` hand it over."""
    return {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": straat,
        "huisnummer": huisnummer,
        "busnummer": busnummer,
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
    """Fresh rows per call: the service writes `_person_id` on them."""
    return upsert_families(
        db, [[dict(row) for row in fam] for fam in families], {}, [], apply=apply
    )


def _counts(db):
    return tuple(db.query(model).count() for model in (Member, Person, MemberPerson, Address))


def _pair(huisnummer="12"):
    return [
        _row("200", "Piet", "Peeters", "HOOFDLID", huisnummer=huisnummer),
        _row("201", "Mia", "Maes", "HOOFDLID", huisnummer=huisnummer),
        _row("202", "Kim", "Peeters", "KIND", huisnummer=huisnummer),
    ]


def _good():
    return [_row("100", "Jan", "Janssens", "HOOFDLID"), _row("101", "An", "Janssens", "PARTNER")]


# ── two main members on one address ──────────────────────────────────────────


def test_two_main_members_on_one_address_are_not_loaded(db_session):
    seed_postal_code(db_session)
    before = _counts(db_session)

    report = _load(db_session, [_pair()])

    assert _counts(db_session) == before, "a row of the refused address was written"
    assert report.skipped == 1
    assert report.new_families == 0 and report.persons_added == 0
    assert not report.lines, "the refused address has lines in the detail of what is written"
    (sentence,) = report.warnings
    assert TWO_MAIN_MEMBERS in sentence
    # Both rows by name and member number, so the file can be corrected.
    assert "Piet Peeters (#200)" in sentence and "Mia Maes (#201)" in sentence
    # The child is neither a main member nor loaded: the sentence says how many rows wait.
    assert "(3 rijen)" in sentence
    assert ONE_ADDRESS in sentence


def test_the_other_households_of_the_report_are_loaded(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, [_pair(), _good()])

    assert report.new_families == 1 and report.persons_added == 2
    assert report.skipped == 1
    assert db_session.query(Member).count() == 1
    assert {p.first_name for p in db_session.query(Person)} == {"Jan", "An"}


def test_the_preview_says_the_same_as_the_run(db_session):
    seed_postal_code(db_session)
    report_rows = [_pair(), [_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="")]]

    preview = _load(db_session, report_rows, apply=False)
    assert _counts(db_session) == (0, 0, 0, 0), "the preview wrote"
    run = _load(db_session, report_rows)

    assert len(preview.warnings) == 2
    assert preview.warnings == run.warnings
    assert preview.skipped == run.skipped == 1


def test_a_household_that_gets_a_second_main_member_stays_as_it_is(db_session):
    """The address was loaded with one main member; the next report gives it two.
    Nothing of it is changed or removed — a person the report still names is nobody
    the import takes away, also when his address group waits."""
    seed_postal_code(db_session)
    first = [_row("200", "Piet", "Peeters", "HOOFDLID", huisnummer="12")]
    _load(db_session, [first, _good()])
    before = _counts(db_session)

    report = _load(db_session, [_pair(), _good()])

    assert _counts(db_session) == before
    assert report.persons_removed == 0 and report.persons_added == 0
    assert report.updated_families == 0
    piet = db_session.query(Person).filter_by(first_name="Piet").one()
    assert piet.deleted_at is None
    assert any(TWO_MAIN_MEMBERS in sentence for sentence in report.warnings)


def test_a_deleted_person_of_a_refused_address_is_not_brought_back(db_session):
    """Not loaded is not revived either. The import brings a softly deleted person
    back when a report names his member number again (#227); in an address group
    that waits, he stays deleted."""
    seed_postal_code(db_session)
    piet = _row("200", "Piet", "Peeters", "HOOFDLID", huisnummer="12")
    kim = _row("202", "Kim", "Peeters", "KIND", huisnummer="12")
    _load(db_session, [[piet, kim]])
    person = db_session.query(Person).filter_by(first_name="Kim").one()
    person.deleted_at = datetime.now(timezone.utc)
    db_session.flush()

    report = _load(db_session, [_pair()])

    assert report.persons_revived == 0
    assert not report.lines
    db_session.refresh(person)
    assert person.deleted_at is not None


def test_two_main_members_on_two_bus_numbers_are_two_households(db_session):
    """What the sentence tells the board to do works: another bus is another address."""
    seed_postal_code(db_session)
    one = [_row("200", "Piet", "Peeters", "HOOFDLID", huisnummer="12", busnummer="1")]
    two = [_row("201", "Mia", "Maes", "HOOFDLID", huisnummer="12", busnummer="2")]

    report = _load(db_session, [one, two])

    assert report.new_families == 2 and report.skipped == 0
    assert not any(TWO_MAIN_MEMBERS in sentence for sentence in report.warnings)


# ── an address that is not whole ─────────────────────────────────────────────


def _incomplete(report):
    return [s for s in report.warnings if "het adres in het rapport heeft geen" in s]


def test_a_new_household_without_a_house_number_is_read_in_and_said(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, [[_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="")]])

    assert report.new_families == 1 and report.skipped == 0
    assert db_session.query(Address).one().house_number == ""
    (sentence,) = _incomplete(report)
    assert sentence.startswith("Tom Thys: het adres in het rapport heeft geen huisnummer")
    assert "het adres wordt ingelezen zonder huisnummer" in sentence


def test_street_and_house_number_are_named_together(db_session):
    seed_postal_code(db_session)

    report = _load(
        db_session, [[_row("300", "Tom", "Thys", "HOOFDLID", straat="", huisnummer=" ")]]
    )

    (sentence,) = _incomplete(report)
    assert "heeft geen straat en huisnummer" in sentence


def test_an_address_that_loses_its_house_number_says_what_it_was(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="7")]])

    report = _load(db_session, [[_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="")]])

    assert db_session.query(Address).one().house_number == ""
    (sentence,) = _incomplete(report)
    assert "verliest zijn huisnummer (was: Voorbeeldstraat 7" in sentence


def test_an_address_that_stays_incomplete_is_said_at_every_run(db_session):
    seed_postal_code(db_session)
    rows = [[_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="")]]
    _load(db_session, rows)

    report = _load(db_session, rows)

    (sentence,) = _incomplete(report)
    assert "het adres blijft zoals het is, onvolledig" in sentence


def test_a_whole_address_gets_no_sentence(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, [_good()])

    assert not _incomplete(report)
    assert not report.warnings


# ── the recording: preview, run, second run ──────────────────────────────────


def _detail(report) -> str:
    counts = (
        f"new {report.new_families} · changed {report.updated_families} · "
        f"unchanged {report.unchanged_families} · persons added {report.persons_added} · "
        f"removed {report.persons_removed} · skipped {report.skipped}"
    )
    return "\n".join([counts, "-- warnings", *report.warnings, "-- lines", *report.lines]) + "\n"


def test_the_detail_of_preview_run_and_second_run(db_session):
    """One report with a good household, one address without a house number and one
    pair of main members: what the board reads before the run, after it, and at the
    next upload of the same file."""
    seed_postal_code(db_session)
    rows = [_good(), [_row("300", "Tom", "Thys", "HOOFDLID", huisnummer="")], _pair()]

    compare(SNAPSHOTS, "preview", _detail(_load(db_session, rows, apply=False)), BEFORE)
    compare(SNAPSHOTS, "run", _detail(_load(db_session, rows)), BEFORE)
    compare(SNAPSHOTS, "second_run", _detail(_load(db_session, rows)), BEFORE)

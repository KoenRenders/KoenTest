"""#1314 — every write of the member import has a line, in the preview and the run.

Koen, 29 September 2026: *"voor de import moet alles getoond worden wat geüpdate of
geïnsert gaat worden."* A household's board member changed without a line, and the
preview did not show it at all; before #1308 a new person's address and contacts,
and every address or contact change, went the same silent way.

Every line now names the writes it stands for (`ImportReport.writes`, per table).
This test runs one report that makes every kind of write the import knows —
insert, update, soft delete and revival of persons, households, household links,
addresses, contacts, member numbers, memberships, board members and admin
accounts — and holds that tally against what the run really adds:

- a row in a history table for every write that is audited (`person_history`,
  `member_history`, `member_person_history`, `address_history`,
  `contact_detail_history`, `membership_history`);
- for the writes that leave no history row, the table itself:
  - `external_numbers` — a number inserted or revived has no history table;
  - `member_persons` — a household link revived with its person (#227) is not
    audited, so its count comes from the active rows;
  - `users` and `user_roles` — an admin account is not audited here.

A write without a line fails it, including one added later. And the preview must
list the same lines, standing for the same writes.

Found by it while building: a person who moves from one household to another later
in the report was removed from the first (`- verwijderd`) and then removed again by
the move — two history rows for one delete, and SQLAlchemy's "expected to delete 1
row(s); 0 were matched". Someone the report lists elsewhere is now moving, not
leaving.

Proven red (29 September 2026):
- additively, a second `snapshot_member(...)` after the board member's in
  `_link_board_members` — a write without a line → "member: 4 history rows, 3
  declared";
- against master `5ab8d76b`, the board member test fails in the preview: no
  `~ bestuurslid` line at all (the run had none either). The two accounting tests
  cannot run there: the report did not name its writes.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.auth.api import User, UserRole
from app.domains.mdm.api import (
    AddressHistory,
    ContactDetailHistory,
    ExternalNumber,
    Member,
    MemberHistory,
    MemberPerson,
    MemberPersonHistory,
    Person,
    PersonHistory,
)
from app.domains.mdm.import_service import upsert_families
from app.domains.membership.api import MembershipHistory
from app.soft_delete import soft_delete
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

HISTORY = {
    "person": PersonHistory,
    "member": MemberHistory,
    "member_person": MemberPersonHistory,
    "address": AddressHistory,
    "contact_detail": ContactDetailHistory,
    "membership": MembershipHistory,
}


def _row(
    lidnr,
    voornaam,
    naam,
    relatie,
    *,
    huisnummer="1",
    email=None,
    gsm=None,
    geboortedatum=date(1980, 5, 1),
    bestuurslid=None,
):
    return {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": "milostraat",
        "huisnummer": huisnummer,
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": email,
        "telefoon": None,
        "gsm": gsm,
        "geboortedatum": geboortedatum,
        "geslacht": "M",
        "bestuurslid": bestuurslid,
        "_relatie": relatie,
    }


def _first_report():
    return [
        [
            _row("100", "An", "Aerts", "HOOFDLID", email="an@example.com"),
            _row("101", "Bo", "Aerts", "PARTNER"),
        ],
        [
            _row("200", "Cas", "Boons", "HOOFDLID", huisnummer="2"),
            _row("201", "Dirk", "Boons", "KIND", huisnummer="2"),
        ],
        [
            _row("300", "Els", "Claes", "HOOFDLID", huisnummer="3"),
            _row("301", "Fien", "Claes", "PARTNER", huisnummer="3"),
        ],
        [_row("400", "Gust", "Dewit", "HOOFDLID", huisnummer="4")],
    ]


def _second_report():
    """Every kind of write, on top of the first report."""
    return [
        # A: field, relation, address and contact changes; a board member.
        [
            _row(
                "100",
                "An",
                "Aerts",
                "HOOFDLID",
                huisnummer="1A",
                email="an2@example.com",
                geboortedatum=date(1981, 5, 1),
                bestuurslid="Evers Hanne",
            ),
            _row("101", "Bo", "Aerts", "KIND", huisnummer="1A"),
        ],
        # B: loses Dirk, who moves to C.
        [_row("200", "Cas", "Boons", "HOOFDLID", huisnummer="2")],
        # C: Fien leaves the report (removed from the household), Dirk arrives.
        [
            _row("300", "Els", "Claes", "HOOFDLID", huisnummer="3"),
            _row("201", "Dirk", "Boons", "KIND", huisnummer="3"),
        ],
        # D: Gust was soft-deleted with his household, and comes back.
        [_row("400", "Gust", "Dewit", "HOOFDLID", huisnummer="4")],
        # F: a new household; Ivo, registered without a member number, is attached
        # by identity and moves in.
        [
            _row(
                "600",
                "Jo",
                "Faes",
                "HOOFDLID",
                huisnummer="6",
                email="jo@example.com",
                gsm="0470000006",
            ),
            _row("601", "Ivo", "Jansen", "PARTNER", huisnummer="6", geboortedatum=date(1975, 3, 3)),
        ],
        # E: the board member, new, with an address that makes an admin account.
        [_row("500", "Hanne", "Evers", "HOOFDLID", huisnummer="5", email="hanne@example.com")],
    ]


def _board(families):
    """The board index as the upload builds it, from the same rows."""
    from app.domains.mdm.ledenrapport import all_board_member_names, build_bestuurslid_index

    rows = [r for fam in families for r in fam]
    return build_bestuurslid_index(rows), all_board_member_names(rows)


def _counts(db) -> dict[str, int]:
    out = {table: db.query(model).count() for table, model in HISTORY.items()}
    out["external_number"] = db.query(ExternalNumber).count()
    out["member_persons"] = db.query(MemberPerson).count()
    out["mp_inserts"] = db.query(MemberPersonHistory).filter_by(operation="insert").count()
    out["mp_deletes"] = db.query(MemberPersonHistory).filter_by(operation="delete").count()
    out["user"] = db.query(User).count()
    out["user_role"] = db.query(UserRole).count()
    return out


@pytest.fixture
def before_second_import(db_session):
    seed_postal_code(db_session)
    upsert_families(db_session, _first_report(), {}, [], apply=True)
    # Ivo registered himself: a person without a member number, in his own household.
    ivo = Person(
        first_name="Ivo", last_name="Jansen", date_of_birth=date(1975, 3, 3), gender_code="M"
    )
    household = Member()
    db_session.add_all([ivo, household])
    db_session.flush()
    db_session.add(MemberPerson(member_id=household.id, person_id=ivo.id, relation_type="HOOFDLID"))
    # Gust leaves: person, member number, household link and household soft-deleted.
    gust = db_session.query(ExternalNumber).filter_by(external_id="400").one()
    link = db_session.query(MemberPerson).filter_by(person_id=gust.person_id).one()
    for obj in (
        db_session.get(Person, gust.person_id),
        gust,
        link,
        db_session.get(Member, link.member_id),
    ):
        soft_delete(obj)
    db_session.commit()


def test_every_write_of_the_run_has_a_line(db_session, before_second_import):
    families = _second_report()
    start = _counts(db_session)
    report = upsert_families(db_session, families, *_board(families), apply=True)
    db_session.flush()
    end = _counts(db_session)
    delta = {key: end[key] - start[key] for key in end}
    declared = report.writes

    for table in HISTORY:
        assert delta[table] == declared[table], (
            f"{table}: {delta[table]} history rows, {declared[table]} declared\n"
            + "\n".join(report.lines)
        )
    assert delta["external_number"] == declared["external_number"], report.lines
    assert delta["member_persons"] == (
        delta["mp_inserts"] - delta["mp_deletes"] + declared["member_person_revive"]
    ), report.lines
    assert delta["user"] == declared["user"] and delta["user_role"] == declared["user_role"]

    # Every kind happened, or the test proves nothing about it.
    kinds = [
        "person",
        "member",
        "member_person",
        "address",
        "contact_detail",
        "membership",
        "external_number",
        "member_person_revive",
        "user",
        "user_role",
    ]
    assert all(declared[k] > 0 for k in kinds), {k: declared[k] for k in kinds}
    assert any("~ bestuurslid:" in line for line in report.lines), report.lines


def test_the_preview_lists_the_same_lines_and_writes(db_session, before_second_import):
    families = _second_report()
    savepoint = db_session.begin_nested()  # the preview revives in-session; discard it
    preview = upsert_families(db_session, families, *_board(families), apply=False)
    savepoint.rollback()
    # Preview and run are two requests with two sessions in the app; start this one
    # from the database, not from the preview's identity map.
    db_session.expunge_all()

    families = _second_report()
    run = upsert_families(db_session, families, *_board(families), apply=True)

    assert preview.lines == run.lines
    assert preview.writes == run.writes
    assert (preview.updated_families, preview.unchanged_families, preview.new_families) == (
        run.updated_families,
        run.unchanged_families,
        run.new_families,
    )


def test_an_unchanged_board_member_gives_no_line(db_session, before_second_import):
    families = _second_report()
    upsert_families(db_session, families, *_board(families), apply=True)
    db_session.flush()

    again = _second_report()
    report = upsert_families(db_session, again, *_board(again), apply=False)

    assert not [line for line in report.lines if "bestuurslid" in line], report.lines


def test_a_board_member_change_has_its_line_in_preview_and_run(db_session, before_second_import):
    """The issue's own case, on the lines alone: the household's board member
    changes, and preview and run both say so under that household."""
    families = _second_report()
    savepoint = db_session.begin_nested()
    preview = upsert_families(db_session, families, *_board(families), apply=False)
    savepoint.rollback()
    db_session.expunge_all()
    families = _second_report()
    run = upsert_families(db_session, families, *_board(families), apply=True)

    for label, report in (("preview", preview), ("run", run)):
        lines = report.lines
        line = next((line for line in lines if "~ bestuurslid:" in line), None)
        assert line == "  ~ bestuurslid: — → Hanne Evers", f"{label}: {lines}"
        header = max(i for i, x in enumerate(lines[: lines.index(line)]) if not x.startswith(" "))
        assert lines[header].startswith("UPDATE gezin (#") and "milostraat 1A" in lines[header]

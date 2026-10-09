"""A national member number that goes shows in *Wijzigingen* — with its person (#1855).

The board works from the screen *Wijzigingen* and its export when it changes the
national association's own system by hand. Measured for #1855, and held here:

- A national member number (`ExternalNumber`) has no history of its own and no
  door edits or removes one on a living person. It comes with the import and it
  **leaves only together with its person**: the delete of a person (Personen, or
  the household record) and the delete of a whole household.
- Each of those three writes the person's own history row, and the list shows it
  as "Persoon · Verwijderd". The export carries that line WITH the number, in
  the person's number column — the number is soft-deleted by then, and the line
  still names it because the list reads deleted numbers too. The screen shows
  the line (who, when, "Verwijderd") and no number: it has no number column for
  any line, the number is the export's.
- Two things that look like a removal are none: an import in which the person no
  longer stands, and a merge of two persons. The number stays on its person.

Red proof (run, put back): in `reporting/changes.py`, `_ext_of` made to read
living numbers only (`self.db.query(ExternalNumber)` for `self._q(...)`) → the
three removing doors are red, "the export's delete line lost the number"; the two
that do not remove stay green.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from odf.opendocument import load
from odf.table import TableCell, TableRow
from odf.teletype import extractText

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import (
    ExternalNumber,
    Person,
    PersonHistory,
    delete_household,
    delete_household_person,
    delete_person,
    merge_persons,
)
from app.domains.mdm.import_service import upsert_families
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

BOARD = SimpleNamespace(email="board@example.org")
NUMBER = "880101"


def _row(number, first_name, relation, born):
    """One row as the member report's reader hands it to the import."""
    return {
        "lidnr": number,
        "voornaam": first_name,
        "naam": "Voorbeeld",
        "straat": "milostraat",
        "huisnummer": "40",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": None,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": born,
        "geslacht": None,
        "bestuurslid": None,
        "_relatie": relation,
    }


def _household(db) -> SimpleNamespace:
    """A household of two, each with a national number, as the import makes it."""
    seed_postal_code(db)
    head = _row("880100", "An", "HOOFDLID", "1980-01-01")
    partner = _row(NUMBER, "Bert", "PARTNER", "1981-02-02")
    upsert_families(db, [[dict(head), dict(partner)]], {}, [], apply=True)
    db.flush()
    numbers = {n.external_id: n for n in db.query(ExternalNumber).all()}
    partner_id = numbers[NUMBER].person_id
    link = next(m for m in db.get(Person, partner_id).member_persons)
    return SimpleNamespace(
        head_id=numbers["880100"].person_id,
        partner_id=partner_id,
        member_id=link.member_id,
        head_row=head,
    )


def _number(db, person_id) -> ExternalNumber:
    db.flush()
    db.expire_all()
    return (
        db.query(ExternalNumber)
        .execution_options(include_deleted=True)
        .filter(ExternalNumber.person_id == person_id)
        .one()
    )


def _board(client) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _export_lines(client) -> list[dict[str, str]]:
    """The export, downloaded through its route and read back as a file."""
    answer = client.get(f"/admin/ledenwijzigingen/export?since={date.today().isoformat()}")
    assert answer.status_code == 200, answer.text
    rows = load(BytesIO(answer.content)).spreadsheet.getElementsByType(TableRow)
    cells = [[extractText(c) for c in r.getElementsByType(TableCell)] for r in rows]
    headers = cells[0]
    assert "Externe ID persoon" in headers, f"the export has no number column: {headers}"
    return [dict(zip(headers, line)) for line in cells[1:]]


def _person_lines(client, person_id) -> list[dict[str, str]]:
    lines = _export_lines(client)
    assert lines, "the export is empty — is this test still looking?"
    return [line for line in lines if line["Type"] == "Persoon" and line["ID"] == str(person_id)]


def _screen(client) -> str:
    answer = client.get(f"/admin/ledenwijzigingen?since={date.today().isoformat()}&per_page=100")
    assert answer.status_code == 200, answer.text
    return answer.text


DOORS = {
    "the delete of a person": (
        lambda db, w: delete_person(db, db.get(Person, w.partner_id), actor=BOARD.email),
        "person_deleted",
    ),
    "the delete from the household record": (
        lambda db, w: delete_household_person(db, w.partner_id, admin=BOARD),
        "person_deleted",
    ),
    "the delete of the whole household": (
        lambda db, w: delete_household(db, w.member_id, admin=BOARD),
        "family_deleted",
    ),
}


@pytest.mark.parametrize("door", DOORS)
def test_a_number_that_goes_with_its_person_shows_on_the_delete_line(client, db_session, door):
    db = db_session
    world = _household(db)
    _board(client)
    remove, action = DOORS[door]

    remove(db, world)

    assert _number(db, world.partner_id).deleted_at is not None, f"{door} left the number alive"
    written = [
        (h.operation, h.action)
        for h in db.query(PersonHistory).filter(PersonHistory.person_id == world.partner_id)
    ]
    assert ("delete", action) in written, f"{door} wrote no delete row for the person: {written}"

    deleted = [line for line in _person_lines(client, world.partner_id) if line["Actie"] == action]
    assert len(deleted) == 1, f"{door}: {len(deleted)} delete lines in the export"
    line = deleted[0]
    assert (line["Wat"], line["Naam persoon"]) == ("Verwijderd", "Bert Voorbeeld")
    assert line["Externe ID persoon"] == NUMBER, "the export's delete line lost the number"

    screen = _screen(client)
    assert "Verwijderd" in screen and "Bert Voorbeeld" in screen, f"{door}: no line on the screen"


def test_an_import_without_the_person_takes_no_number_away(client, db_session):
    db = db_session
    world = _household(db)
    _board(client)

    upsert_families(db, [[dict(world.head_row)]], {}, [], apply=True)

    assert _number(db, world.partner_id).deleted_at is None
    lines = _person_lines(client, world.partner_id)
    assert [line["Wat"] for line in lines] == ["Toegevoegd"], "the person was not deleted"
    assert lines[0]["Externe ID persoon"] == NUMBER


def test_a_merge_takes_no_number_away(client, db_session):
    db = db_session
    world = _household(db)
    _board(client)

    merge_persons(db, world.partner_id, world.head_id, actor=BOARD.email)

    assert _number(db, world.partner_id).deleted_at is None
    lines = _person_lines(client, world.partner_id)
    assert sorted(line["Wat"] for line in lines) == ["Gewijzigd", "Toegevoegd"]
    assert {line["Externe ID persoon"] for line in lines} == {NUMBER}

"""#1174 — een lid beheert zijn eigen e-mailadressen, en de export toont wát er veranderde.

Koen, 27 september 2026: *"Wat mij betreft kan een lid dat zelfs in het publieke
deel bepalen, dan zien we dat ook in de wijzigingen."*

Die tweede helft is geen bijzin. De lus is: portaal → auditlogboek → de
.ods-export van de ledenwijzigingen → met de hand overtypen in het Raak
Nationaal-programma. Het hoofdadres is precies wat dát programma bijhoudt, dus
een lid dat een ander adres aanduidt moet in die export **herkenbaar** zijn als
"dit is nu het hoofdadres" — niet als een algemeen "contactgegeven gewijzigd".
Anders ziet degene die overtypt wél dat er iets veranderde, maar niet wát, en
staat de lus open zonder dat iemand het merkt.

Gemeten vóór de reparatie: de exportregel was `EMAIL: <waarde>` met het label
"Gewijzigd", en bij een verandering van alleen de markering is die waarde
identiek aan de vorige. Onzichtbaar dus.

Since #1590 a member has no door per e-mail row any more: the rows are part of
the one form of "Mijn gezin" and are written by its one "Opslaan"
(`POST /leden/gezin`). Every test here therefore reads the form from the edit
page (`household_fields`), changes the rows it is about and posts the whole
form — the address added is a new row, the main address is the row the form
marks, a row the form no longer has is gone.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from tests.conftest import create_test_family, household_fields

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
TWEEDE = "tweede@example.com"


@pytest.fixture
def lid(db_session):
    member, person = create_test_family(db_session, email=HOOFD, mobile="0470 00 00 01")
    db_session.commit()
    return member, person


def _aanmelden(client, adres: str) -> str:
    waarde = make_session_value(adres)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _adressen(db, person) -> dict[str, bool]:
    db.expire_all()
    person = db.query(Person).filter(Person.id == person.id).one()
    return {
        c.value: bool(c.is_primary)
        for c in person.contact_details
        if c.contact_type_code == "EMAIL"
    }


def _rij_id(db, person, waarde: str) -> int:
    person = db.query(Person).filter(Person.id == person.id).one()
    return next(
        c.id for c in person.contact_details if c.contact_type_code == "EMAIL" and c.value == waarde
    )


def _confirm(db, value: str) -> None:
    """Enter the code of this waiting address (CR-22 R15, #1711): through the
    link of its mail, the door a member uses."""
    from app.domains.auth.api import LoginToken, consume_link

    token = db.query(LoginToken).filter_by(email=value, used=False).one()
    consumed = consume_link(db, token.token)
    assert consumed is not None and consumed.refusal is None, consumed
    db.expire_all()


def _save(client, csrf, fields):
    return client.post("/leden/gezin", data=fields, headers={"X-CSRF-Token": csrf})


def _add_row(fields: dict, person, key: str, value: str) -> dict:
    """One more e-mail row on this person, as "+ E-mailadres" adds it."""
    fields[f"e_order.{person.id}"] = [*fields.get(f"e_order.{person.id}", []), key]
    fields[f"e.{key}.value"] = value
    return fields


# ── Het lid zelf ────────────────────────────────────────────────────────────


def test_een_lid_zet_er_zelf_een_adres_bij(client, db_session, lid):
    _member, person = lid
    csrf = _aanmelden(client, HOOFD)

    respons = _save(client, csrf, _add_row(household_fields(client), person, "nx1", TWEEDE))

    assert respons.status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}
    # CR-22 R15 (#1711): it waits for its code, and signs nobody in before.
    from app.domains.auth.api import login_person_for_email

    assert login_person_for_email(db_session, TWEEDE) is None


def test_een_lid_duidt_zelf_zijn_hoofdadres_aan(client, db_session, lid):
    """En meldt zich daarna aan met dát adres — de reden dat dit bestaat.

    The mark is one field of the form (`e_primary.<person>`): the page the
    member gets back after adding the address carries the stored row's id, and
    marking that row moves the main address."""
    from app.domains.auth.api import login_person_for_email

    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    _save(client, csrf, _add_row(household_fields(client), person, "nx1", TWEEDE))
    # Since #1711 the address has to be confirmed before it can be marked.
    _confirm(db_session, TWEEDE)
    second_id = _rij_id(db_session, person, TWEEDE)

    fields = household_fields(client)
    assert str(second_id) in fields[f"e_order.{person.id}"], "the page does not show the new row"
    assert fields[f"e_primary.{person.id}"] != str(second_id), "the new row is already marked"
    fields[f"e_primary.{person.id}"] = str(second_id)
    respons = _save(client, csrf, fields)

    assert respons.status_code == 200
    assert _adressen(db_session, person) == {HOOFD: False, TWEEDE: True}
    found = login_person_for_email(db_session, TWEEDE)
    assert getattr(found, "id", found) == person.id


def test_a_member_marks_a_new_row_as_main_in_the_same_save(client, db_session, lid):
    """New with #1590: adding an address and making it the main one is one save.

    Since CR-22 R15 (#1711) the new address waits for its code, and the mark
    waits with it: the old address stays the main one until then. Red when
    the wish is not carried along with the code: the address is confirmed
    and stays an ordinary one."""
    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    fields = _add_row(household_fields(client), person, "nx1", TWEEDE)
    fields[f"e_primary.{person.id}"] = "nx1"

    assert _save(client, csrf, fields).status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}
    _confirm(db_session, TWEEDE)
    assert _adressen(db_session, person) == {HOOFD: False, TWEEDE: True}


def test_a_row_the_form_no_longer_has_is_removed(client, db_session, lid):
    """ "Verwijderen" in a row's menu takes the row out of the form; the save
    removes it. The other row stays, so it is this row that went."""
    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    _save(client, csrf, _add_row(household_fields(client), person, "nx1", TWEEDE))
    second_id = _rij_id(db_session, person, TWEEDE)

    fields = household_fields(client)
    fields[f"e_order.{person.id}"].remove(str(second_id))
    del fields[f"e.{second_id}.value"]

    assert _save(client, csrf, fields).status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True}


def test_een_lid_raakt_niet_aan_de_adressen_van_een_ander_gezin(client, db_session, lid):
    """De gezinsgrens, en ze is het hele verschil tussen een portaal en een lek.

    Wie is aangemeld mag met de id van een vreemde — de persoon of een van diens
    e-mailrijen — niets aan diens adressen veranderen: anders zet hij zijn eigen
    adres bij iemand anders en meldt zich daarmee aan.

    Two ways in, both shut. The stranger as a person row of the form: the save
    is refused as that row and writes nothing. The stranger's e-mail ROW under
    the member's own person: the save only writes rows that are this person's,
    so the stranger's row keeps its value — while the member's own new address
    in the same form IS stored, which shows the save ran.
    """
    _member, person = lid
    _vreemd_member, vreemde = create_test_family(db_session, email="vreemd@example.com")
    db_session.commit()
    strangers_row = _rij_id(db_session, vreemde, "vreemd@example.com")
    csrf = _aanmelden(client, HOOFD)

    as_person = household_fields(client)
    as_person["h_order"] = [*as_person["h_order"], str(vreemde.id)]
    as_person.update(
        {
            f"h.{vreemde.id}.first_name": vreemde.first_name,
            f"h.{vreemde.id}.last_name": vreemde.last_name,
            f"h.{vreemde.id}.date_of_birth": vreemde.date_of_birth.isoformat(),
            f"h.{vreemde.id}.gender_code": vreemde.gender_code,
        }
    )
    _add_row(as_person, vreemde, "nx1", "ingebroken@example.com")
    respons = _save(client, csrf, as_person)

    assert respons.status_code == 422
    assert f'data-error-for="h.{vreemde.id}"' in respons.text
    assert _adressen(db_session, vreemde) == {"vreemd@example.com": True}

    as_row = _add_row(household_fields(client), person, str(strangers_row), "gekaapt@example.com")
    _add_row(as_row, person, "nx2", TWEEDE)
    respons = _save(client, csrf, as_row)

    assert respons.status_code == 200
    assert _adressen(db_session, vreemde) == {"vreemd@example.com": True}
    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}


# ── De lus naar Raak Nationaal ──────────────────────────────────────────────


def test_de_export_zegt_dat_het_hoofdadres_verplaatst_is(client, db_session, lid):
    """De eis die de lus sluit.

    Deze regels worden met de hand overgetypt. De waarde verandert hier NIET —
    alleen de markering — dus zonder deze zin staat er tweemaal hetzelfde adres
    met het label "Gewijzigd" en weet niemand wat er te doen valt.

    Tegenproef: de markering-tak uit `changes.py` → de samenvatting is dan
    `EMAIL: tweede@example.com` en deze test faalt op de ontbrekende zin.
    """
    from datetime import date, timedelta

    from app.domains.reporting.api import member_changes_since

    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    _save(client, csrf, _add_row(household_fields(client), person, "nx1", TWEEDE))
    _confirm(db_session, TWEEDE)
    fields = household_fields(client)
    fields[f"e_primary.{person.id}"] = str(_rij_id(db_session, person, TWEEDE))
    assert _save(client, csrf, fields).status_code == 200

    regels = member_changes_since(db_session, date.today() - timedelta(days=1))
    samenvattingen = [r["summary"] for r in regels if r["entity"] == "Contact"]

    assert any("is nu het hoofdadres" in s and TWEEDE in s for s in samenvattingen), (
        f"de export zegt niet dát dit het nieuwe hoofdadres is: {samenvattingen}"
    )
    assert any("is niet meer het hoofdadres" in s and HOOFD in s for s in samenvattingen), (
        f"de export zegt niet dat het oude adres het niet meer is: {samenvattingen}"
    )


def test_een_gewone_adreswijziging_blijft_lezen_zoals_ze_was(db_session):
    """De markering mag de bestaande regel niet overschrijven.

    Verandert de WAARDE, dan hoort er nog altijd "oud → nieuw" te staan. Zonder
    deze test zou een markering die altijd meekomt ook groen staan.
    """
    from datetime import date, timedelta

    from app.domains.mdm.api import upsert_primary_contact
    from app.domains.reporting.api import member_changes_since

    # Eerst het adres langs een geauditeerd pad zetten: zonder een vorige
    # snapshot van dezelfde rij kan "oud → nieuw" niet bestaan, en dan zou deze
    # test een gebrek meten dat er niet is. (Zo werkte het al vóór #1174.)
    _member, person = create_test_family(db_session, email="start@example.com")
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.commit()
    upsert_primary_contact(
        db_session, person, "EMAIL", HOOFD, action="contacts_updated", source="admin_update"
    )
    db_session.commit()
    upsert_primary_contact(
        db_session, person, "EMAIL", TWEEDE, action="contacts_updated", source="admin_update"
    )
    db_session.commit()

    regels = member_changes_since(db_session, date.today() - timedelta(days=1))
    samenvattingen = [r["summary"] for r in regels if r["entity"] == "Contact"]
    assert any(f"{HOOFD} → {TWEEDE}" in s for s in samenvattingen), (
        f"de oud → nieuw-regel is verdwenen: {samenvattingen}"
    )

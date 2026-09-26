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
"""
from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
TWEEDE = "tweede@example.com"


@pytest.fixture
def lid(db_session):
    member, person = create_test_family(db_session, email=HOOFD)
    db_session.commit()
    return member, person


def _aanmelden(client, adres: str) -> str:
    waarde = make_session_value(adres)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _adressen(db, person) -> dict[str, bool]:
    db.expire_all()
    person = db.query(Person).filter(Person.id == person.id).one()
    return {c.value: bool(c.is_primary) for c in person.contact_details
            if c.contact_type_code == "EMAIL"}


def _rij_id(db, person, waarde: str) -> int:
    person = db.query(Person).filter(Person.id == person.id).one()
    return next(c.id for c in person.contact_details
                if c.contact_type_code == "EMAIL" and c.value == waarde)


def _post(client, csrf, pad, **data):
    return client.post(pad, data=data, headers={"X-CSRF-Token": csrf})


# ── Het lid zelf ────────────────────────────────────────────────────────────

def test_een_lid_zet_er_zelf_een_adres_bij(client, db_session, lid):
    _member, person = lid
    csrf = _aanmelden(client, HOOFD)

    respons = _post(client, csrf, f"/leden/gezin/personen/{person.id}/email",
                    extra_email=TWEEDE)

    assert respons.status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True, TWEEDE: False}


def test_een_lid_duidt_zelf_zijn_hoofdadres_aan(client, db_session, lid):
    """En meldt zich daarna aan met dát adres — de reden dat dit bestaat."""
    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    _post(client, csrf, f"/leden/gezin/personen/{person.id}/email", extra_email=TWEEDE)
    tweede_id = _rij_id(db_session, person, TWEEDE)

    _post(client, csrf,
          f"/leden/gezin/personen/{person.id}/email/{tweede_id}/hoofd")

    assert _adressen(db_session, person) == {HOOFD: False, TWEEDE: True}


def test_een_lid_raakt_niet_aan_de_adressen_van_een_ander_gezin(client, db_session, lid):
    """De gezinsgrens, en ze is het hele verschil tussen een portaal en een lek.

    Zonder `_assert_in_household` kan wie is aangemeld met een persoon-id van een
    vreemde diens adressen beheren — en dus zijn eigen adres bij iemand anders
    zetten en daarmee aanmelden.

    Tegenproef: de controle uit de drie routes → deze test faalt met 200 in
    plaats van 403, en het adres staat bij de vreemde.
    """
    _member, person = lid
    _vreemd_member, vreemde = create_test_family(db_session, email="vreemd@example.com")
    db_session.commit()
    csrf = _aanmelden(client, HOOFD)

    respons = _post(client, csrf, f"/leden/gezin/personen/{vreemde.id}/email",
                    extra_email="ingebroken@example.com")

    assert respons.status_code == 403
    assert "ingebroken@example.com" not in _adressen(db_session, vreemde)


# ── De lus naar Raak Nationaal ──────────────────────────────────────────────

def test_de_export_zegt_dat_het_hoofdadres_verplaatst_is(client, db_session, lid):
    """De eis die de lus sluit.

    Deze regels worden met de hand overgetypt. De waarde verandert hier NIET —
    alleen de markering — dus zonder deze zin staat er tweemaal hetzelfde adres
    met het label "Gewijzigd" en weet niemand wat er te doen valt.

    Tegenproef: de markering-tak uit `changes.py` → de samenvatting is dan
    `EMAIL: tweede@example.com` en deze test faalt op de ontbrekende zin.
    """
    from app.domains.audit.api import member_changes_since
    from datetime import date, timedelta

    _member, person = lid
    csrf = _aanmelden(client, HOOFD)
    _post(client, csrf, f"/leden/gezin/personen/{person.id}/email", extra_email=TWEEDE)
    tweede_id = _rij_id(db_session, person, TWEEDE)
    _post(client, csrf, f"/leden/gezin/personen/{person.id}/email/{tweede_id}/hoofd")

    regels = member_changes_since(db_session, date.today() - timedelta(days=1))
    samenvattingen = [r["summary"] for r in regels if r["entity"] == "Contact"]

    assert any("is nu het hoofdadres" in s and TWEEDE in s for s in samenvattingen), (
        f"de export zegt niet dát dit het nieuwe hoofdadres is: {samenvattingen}")
    assert any("is niet meer het hoofdadres" in s and HOOFD in s
               for s in samenvattingen), (
        f"de export zegt niet dat het oude adres het niet meer is: {samenvattingen}")


def test_een_gewone_adreswijziging_blijft_lezen_zoals_ze_was(db_session):
    """De markering mag de bestaande regel niet overschrijven.

    Verandert de WAARDE, dan hoort er nog altijd "oud → nieuw" te staan. Zonder
    deze test zou een markering die altijd meekomt ook groen staan.
    """
    from datetime import date, timedelta

    from app.domains.audit.api import member_changes_since
    from app.domains.mdm.api import upsert_primary_contact

    # Eerst het adres langs een geauditeerd pad zetten: zonder een vorige
    # snapshot van dezelfde rij kan "oud → nieuw" niet bestaan, en dan zou deze
    # test een gebrek meten dat er niet is. (Zo werkte het al vóór #1174.)
    _member, person = create_test_family(db_session, email="start@example.com")
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.commit()
    upsert_primary_contact(db_session, person, "EMAIL", HOOFD,
                           action="contacts_updated", source="admin_update")
    db_session.commit()
    upsert_primary_contact(db_session, person, "EMAIL", TWEEDE,
                           action="contacts_updated", source="admin_update")
    db_session.commit()

    regels = member_changes_since(db_session, date.today() - timedelta(days=1))
    samenvattingen = [r["summary"] for r in regels if r["entity"] == "Contact"]
    assert any(f"{HOOFD} → {TWEEDE}" in s for s in samenvattingen), (
        f"de oud → nieuw-regel is verdwenen: {samenvattingen}")

"""#1219 — e-mailadressen als rijen in het ledenformulier.

Koen vroeg hoe je een tikfout in een niet-hoofdadres corrigeert. Het antwoord
was: *dat kan niet* — er waren drie acties (toevoegen, hoofdadres maken,
verwijderen) en bewerken zat er niet bij, dus corrigeren was weggooien en
opnieuw toevoegen. Nu zijn de adressen rijen in het formulier, zoals de
gezinsleden dat al zijn (#1110): één formulier, één opslaan, één transactie.

Hybride, zo beslist: **tekst** gaat mee met Opslaan; **verwijderen** en
**hoofdadres aanduiden** blijven eigen knoppen, want dat zijn losse
beslissingen met een eigen betekenis in het auditspoor.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Person
from tests._sites import at_tenant
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, record_fields, save_record

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
TIKFOUT = "twede@example.com"
JUIST = "tweede@example.com"


@pytest.fixture
def gezin(db_session):
    member, person = create_test_family(db_session, email=HOOFD)
    at_tenant(db_session, member)  # CR-26 F9
    db_session.add(
        ContactDetail(
            person_id=person.id, contact_type_code="EMAIL", value=TIKFOUT, is_primary=False
        )
    )
    db_session.commit()
    return member, person


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
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


def _opslaan(client, member, person, rijen=None, nieuw=(), hoofd=None, **velden):
    """De ene save van het gezinsrecord (#1899), met wat de test wijzigt: de tekst
    van bestaande adresrijen (`rijen`), nieuwe rijen (`nieuw`), een rij als
    hoofdadres (`hoofd`) of een veld van de persoon. Tot #1899 had de kaart van
    een persoon haar eigen route, met eigen veldnamen."""
    data = record_fields(client, member.id)
    sleutel = f"e_order.{person.id}"
    for rij_id, tekst in (rijen or {}).items():
        data[f"e.{rij_id}.value"] = tekst
    for nummer, tekst in enumerate(nieuw):
        if not data.get(sleutel):
            # the first row added to an empty list is the chosen one, as the page does
            data[f"e_primary.{person.id}"] = f"n{nummer}"
        data[sleutel] = [*data.get(sleutel, []), f"n{nummer}"]
        data[f"e.n{nummer}.value"] = tekst
    if hoofd is not None:
        data[f"e_primary.{person.id}"] = str(hoofd)
    for naam, waarde in velden.items():
        data[f"h.{person.id}.{naam}"] = waarde
    return save_record(client, member.id, data)


# ── 1. Het gemelde geval ────────────────────────────────────────────────────


def test_een_tikfout_corrigeer_je_door_te_typen(client, db_session, gezin):
    """De vraag waar dit issue mee begon.

    Tegenproef: het invoerveld voor een bestaand adres weghalen (terug naar
    alleen knoppen) → er is niets om in te typen, het veld ontbreekt in het
    formulier en het adres blijft de tikfout houden.
    """
    member, person = gezin
    _login(client)
    rij_id = _rij_id(db_session, person, TIKFOUT)

    respons = _opslaan(client, member, person, rijen={rij_id: JUIST})

    assert respons.status_code == 200
    assert _adressen(db_session, person) == {HOOFD: True, JUIST: False}, (
        "het gecorrigeerde adres hoort de tikfout te vervangen, met dezelfde rol"
    )


def test_het_veld_staat_echt_op_het_scherm(client, db_session, gezin):
    """Zonder veld is er niets te typen — dit is de andere helft van punt 1.

    Een test die alleen de POST toetst zou groen blijven als het scherm dat veld
    nooit rendert; dan werkt de reparatie wel en kan niemand erbij. Het veld
    staat in de bewerkmodus van het record (#1899).
    """
    member, person = gezin
    _login(client)
    rij_id = _rij_id(db_session, person, TIKFOUT)

    html = client.get(f"/admin/leden/gezin/{member.id}?bewerken=1").text

    veld = re.search(rf'<input[^>]*name="e\.{rij_id}\.value"[^>]*>', html)
    assert veld, "er staat geen invoerveld voor het bestaande adres in het formulier"
    assert f'value="{TIKFOUT}"' in veld.group(0)


# ── 2. Een rij die nog niet bestaat ─────────────────────────────────────────


def test_een_nieuwe_rij_draagt_geen_knop_die_een_id_nodig_heeft(client, db_session, gezin):
    """De val: tot het gezin opgeslagen is, heeft die rij geen id.

    Sinds #1899 komt een nieuwe rij uit het sjabloon van de lijst in de pagina
    zelf (geen verzoek), en doet geen enkele rij nog een verzoek van haar eigen:
    hoofdadres aanwijzen en verwijderen reizen mee met de ene save. Het sjabloon
    draagt dus een veld en geen `hx-post`.
    """
    member, person = gezin
    _login(client)

    html = client.get(f"/admin/leden/gezin/{member.id}?bewerken=1").text

    groep = html[html.index(f'data-repeating-group="e_order.{person.id}"') :]
    sjabloon = groep[groep.index("<template data-group-template>") : groep.index("</template>")]
    assert 'name="e.__E__.value"' in sjabloon, f"geen veld in de lege rij: {sjabloon[:300]}"
    assert "hx-post" not in sjabloon, "een nog niet opgeslagen rij stuurt een verzoek"
    lijst = groep[: groep.index("<template data-group-template>")]
    assert "hx-post" not in lijst, "een adresrij stuurt een verzoek van haar eigen"


def test_een_nieuwe_rij_wordt_bij_opslaan_een_adres(client, db_session, gezin):
    member, person = gezin
    _login(client)

    _opslaan(client, member, person, nieuw=["derde@example.com"])

    assert _adressen(db_session, person) == {
        HOOFD: True,
        TIKFOUT: False,
        "derde@example.com": False,
    }


def test_een_lege_nieuwe_rij_levert_niets_op(client, db_session, gezin):
    """Wie op + klikt en niets typt, hoort geen leeg adres te krijgen."""
    member, person = gezin
    _login(client)

    _opslaan(client, member, person, nieuw=["", "   "])

    assert _adressen(db_session, person) == {HOOFD: True, TIKFOUT: False}


# ── 3. De markering is een herkomst, geen positie ───────────────────────────


def test_het_eerste_adres_van_een_mens_wordt_het_hoofdadres(client, db_session):
    """Koen, 26 september 2026: *"Als je maar 1 adres invoert is dat het hoofdadres."*

    Wie het intypt zegt iets — dít is het adres — en er is niets anders dat het
    kan zijn. De IMPORT promoveert daarentegen nooit: daar zou het iets beweren
    over wat Raak Nationaal heeft. Twee herkomsten, twee regels.

    Tegenproef: `is_primary=False` hard zetten voor een nieuwe rij → het eerste
    adres krijgt de markering niet en deze test faalt.
    """
    member, person = create_test_family(db_session, email=HOOFD)
    at_tenant(db_session, member)  # CR-26 F9
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.commit()
    _login(client)

    _opslaan(client, member, person, nieuw=["eerste@example.com"])
    assert _adressen(db_session, person) == {"eerste@example.com": True}

    # En een tweede krijgt hem niet.
    _opslaan(client, member, person, nieuw=["tweede@example.com"])
    assert _adressen(db_session, person) == {
        "eerste@example.com": True,
        "tweede@example.com": False,
    }


def test_de_markering_volgt_de_volgorde_niet(client, db_session, gezin):
    """Staat het hoofdadres op de tweede rij, dan blijft het daar.

    *"Het eerste adres wordt hoofdadres"* geldt bij INVOEREN, niet bij weergeven.
    Zonder deze test zou een scherm dat bij elke opslag de eerste rij markeert
    ook groen staan — en dan is de markering een positie geworden in plaats van
    een herkomst.
    """
    member, person = gezin
    _login(client)
    tweede_id = _rij_id(db_session, person, TIKFOUT)
    _opslaan(client, member, person, hoofd=tweede_id)
    assert _adressen(db_session, person) == {HOOFD: False, TIKFOUT: True}

    _opslaan(client, member, person, rijen={tweede_id: TIKFOUT})

    assert _adressen(db_session, person) == {HOOFD: False, TIKFOUT: True}, (
        "het opslaan heeft de markering verplaatst naar de eerste rij"
    )


# ── 4. Wat niet mag veranderen ──────────────────────────────────────────────


def test_opslaan_zonder_e_mailveld_wist_het_hoofdadres_niet(client, db_session, gezin):
    """De val bij het weghalen van het losse e-mailveld uit de veldenset.

    `update_person_contacts` leest een ontbrekende `email` als "verwijder het
    hoofdadres". Sinds het veld weg is, draagt élk opslaan die lege waarde — dus
    zonder de `model_fields_set`-grens wist elke opslag het hoofdadres.

    Tegenproef: die grens eruit → deze test faalt, en het gezin is zijn
    hoofdadres kwijt na een gewone naamswijziging.
    """
    member, person = gezin
    _login(client)

    _opslaan(client, member, person, first_name="Gewijzigd")

    assert _adressen(db_session, person) == {HOOFD: True, TIKFOUT: False}

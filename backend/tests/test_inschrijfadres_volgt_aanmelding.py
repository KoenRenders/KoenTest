"""#1174 — het inschrijfformulier vult het AANMELDADRES in, niet "het eerste".

Koen, 26 september 2026: de bevestiging van een inschrijving gaat naar het adres
dat op dat formulier staat, en bij een aangemeld lid staat daar het adres
*"waarmee men ingelogd is, ook al is dat niet hoofdadres"*.

Zolang iedereen één adres had, was "het eerste e-mailadres van deze persoon"
hetzelfde antwoord. Met twee adressen is het een willekeurige keuze — en de kans
is even groot dat het formulier het adres invult dat de bezoeker juist NIET
gebruikt. Hij ziet dat, corrigeert het misschien niet, en de bevestiging landt in
een mailbox die hij niet leest.
"""
from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail
from tests.conftest import create_test_family, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
TWEEDE = "tweede@example.com"


def _veld(html: str, veld_id: str) -> str:
    treffer = re.search(rf'<input[^>]*id="{veld_id}"[^>]*>', html)
    assert treffer, f"geen veld {veld_id!r} in het formulier"
    return treffer.group(0)


@pytest.fixture
def lid_met_twee_adressen(db_session):
    """Een lid met een hoofdadres en een tweede adres, in die volgorde."""
    _member, person = create_test_family(db_session, email=HOOFD)
    db_session.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                                 value=TWEEDE, is_primary=False))
    db_session.commit()
    return person


def _formulier(client, activity, component, *, aangemeld_met: str | None):
    client.cookies.clear()
    if aangemeld_met:
        client.cookies.set(SESSION_COOKIE, make_session_value(aangemeld_met))
    respons = client.get(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}")
    assert respons.status_code == 200
    return respons.text


def test_wie_met_zijn_tweede_adres_aanmeldt_ziet_dat_adres_staan(
        client, db_session, lid_met_twee_adressen):
    """Het gemelde geval, en het geval dat vroeger fout ging.

    Tegenproef: de voorvulling terug uit `person.contact_details` laten komen —
    dan staat `hoofd@example.com` in het veld terwijl de bezoeker met
    `tweede@example.com` aangemeld is, en faalt deze test op die waarde.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="0", is_free=True)

    html = _formulier(client, activity, component, aangemeld_met=TWEEDE)
    assert f'value="{TWEEDE}"' in _veld(html, "contact_email"), (
        "het formulier vult niet het adres in waarmee de bezoeker aangemeld is")


def test_wie_met_zijn_hoofdadres_aanmeldt_ziet_dat_staan(
        client, db_session, lid_met_twee_adressen):
    """De tegenhanger — anders zou "vul altijd het tweede adres in" ook slagen.

    Dit is het gewone geval en het mag niet stukgaan doordat we het andere geval
    repareren.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="0", is_free=True)

    html = _formulier(client, activity, component, aangemeld_met=HOOFD)
    assert f'value="{HOOFD}"' in _veld(html, "contact_email")


def test_een_bezoeker_zonder_sessie_krijgt_een_leeg_veld(client, db_session):
    """Zonder aanmelding is er geen adres om in te vullen, en dat hoort leeg.

    Zonder deze test zou een voorvulling die het laatst gebruikte adres onthoudt —
    of erger, een willekeurig adres uit de databank — ook groen staan.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="0", is_free=True)

    html = _formulier(client, activity, component, aangemeld_met=None)
    assert "value=" not in _veld(html, "contact_email") or \
        'value=""' in _veld(html, "contact_email"), (
        f"het veld hoort leeg te zijn: {_veld(html, 'contact_email')}")


def test_het_mobiele_nummer_blijft_uit_de_contactgegevens_komen(
        client, db_session, lid_met_twee_adressen):
    """Alleen het e-mailadres verhuist naar de sessie; het gsm-nummer niet.

    De sessie draagt een adres en geen telefoonnummer, dus dat blijft van de
    persoon komen. Deze test pint vast dat de wijziging het nummer niet
    meegesleept heeft — een tuple dat halveert is makkelijk te ver door te voeren.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="0", is_free=True)
    db_session.add(ContactDetail(person_id=lid_met_twee_adressen.id,
                                 contact_type_code="MOBILE", value="0470112233",
                                 is_primary=True))
    db_session.commit()

    html = _formulier(client, activity, component, aangemeld_met=TWEEDE)
    assert 'value="0470112233"' in _veld(html, "phone")

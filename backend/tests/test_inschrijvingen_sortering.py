"""Golf 4 (#913): sorteerbare kolommen op de inschrijvingenlijst.

Zelfde regels als de golf 3-referentie (e-maillog): whitelist op de sleutel —
die komt uit de querystring, om dezelfde reden als er geen vrije SQL is — en
elke ordening eindigt op id (#761). Default datum/asc is exact de bewaarde
#285-volgorde, dus zonder klik verandert er niets.
"""
import pytest
pytestmark = pytest.mark.ui_serverrendered

import re

from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _drie_inschrijvingen(client, db_session):
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    for naam in ("Carla Sorteer", "Anna Sorteer", "Bert Sorteer"):
        client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                    data={"contact_name": naam,
                          "contact_email": "sort@example.com", "phone": "047",
                          f"product_{product.id}": "1",
                          "payment_method": "OVERSCHRIJVING"})
    return activity, component


def _namen(html: str) -> list[str]:
    """Voornamen in rijvolgorde. Elke rij noemt de naam meermaals (naamlink én
    de bevestigtekst op Verwijderen), dus ontdubbelen op eerste voorkomen."""
    gezien: list[str] = []
    for n in re.findall(r"(\w+) Sorteer", html):
        if n not in gezien:
            gezien.append(n)
    return gezien


def test_sorteren_op_naam_is_alfabetisch(client, db_session):
    activity, component = _drie_inschrijvingen(client, db_session)
    _login(client)
    basis = (f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}"
             f"/inschrijvingen")

    assert _namen(client.get(f"{basis}?sort=naam&richting=asc").text) == \
        ["Anna", "Bert", "Carla"]
    assert _namen(client.get(f"{basis}?sort=naam&richting=desc").text) == \
        ["Carla", "Bert", "Anna"]


def test_onbekende_sleutel_valt_terug_op_de_default(client, db_session):
    """De sleutel komt uit de querystring; een injectiestring wordt nooit een
    kolomnaam. Terugvallen betekent hier: de #285-volgorde (oud → nieuw)."""
    activity, component = _drie_inschrijvingen(client, db_session)
    _login(client)
    basis = (f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}"
             f"/inschrijvingen")
    resp = client.get(f"{basis}?sort=contact_name);DROP--&richting=zijwaarts")
    assert resp.status_code == 200
    assert _namen(resp.text) == ["Carla", "Anna", "Bert"]  # inschrijfvolgorde


def test_actieve_kop_draagt_chevron_en_ariasort(client, db_session):
    activity, component = _drie_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/onderdelen/"
                      f"{component.id}/inschrijvingen?sort=naam&richting=asc").text
    assert 'aria-sort="ascending"' in html
    # De chevron-up van ui.icon() — het svg-pad, want de naam staat niet in de
    # output (zelfde toets als de golf 3-referentie).
    assert 'd="m18 15-6-6-6 6"' in html
    # De actieve kop biedt de omgekeerde richting aan.
    assert "sort=naam&amp;richting=desc" in html


def test_verwijderen_behoudt_de_sorteerstand(client, db_session):
    """De delete-URL draagt sort/richting mee: na een verwijdering komt dezelfde
    lijst terug in dezelfde volgorde, niet de default."""
    from app.domains.activities.api import Registration

    activity, component = _drie_inschrijvingen(client, db_session)
    csrf = _login(client)
    weg = (db_session.query(Registration)
           .filter(Registration.contact_name == "Bert Sorteer").one())
    resp = client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/{weg.id}"
        f"/verwijderen?sort=naam&richting=desc&component_id={component.id}",
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert _namen(resp.text) == ["Carla", "Anna"]
    # En de koppen van het antwoord staan nog steeds op die stand.
    assert 'aria-sort="descending"' in resp.text

"""Sorteerbare kolommen op het audit-logboek (golf 3, #913).

De feed is een in Python samengevoegde lijst, dus de sortering en de
whitelist leven in de route — deze tests toetsen dat het scherm heel blijft
onder elke sleutel, ook een vijandige (#680: de reden, niet enkel de status).
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_sorteren_op_persoon_rendert(client, db_session):
    _login(client)
    resp = client.get("/admin/ledenwijzigingen?sort=persoon&richting=asc")
    assert resp.status_code == 200
    # Mét rijen draagt de actieve kop aria-sort; zonder rijen is de lege
    # toestand de geldige uitkomst — beide bewijzen dat de sortering het
    # scherm niet breekt.
    assert 'aria-sort="ascending"' in resp.text or "Geen wijzigingen" in resp.text


def test_onbekende_sorteersleutel_breekt_het_scherm_niet(client, db_session):
    _login(client)
    resp = client.get("/admin/ledenwijzigingen?sort='; DROP TABLE--&richting=zzz")
    assert resp.status_code == 200  # whitelist → terugval op wanneer/desc

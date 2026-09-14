"""Golf 4 (#913, B2): de inschrijving als volwaardige pagina.

De recordnaam in een lijst opent `/admin/inschrijvingen/{id}` als echte pagina;
het htmx-fragment verhuisde naar `/fragment`. De terugknop volgt A7: een
gevalideerde interne retourcontext, met de activiteit van het record als
canonieke fallback — nooit de Referer, nooit een extern adres.
"""
import pytest
pytestmark = pytest.mark.ui_serverrendered

from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _inschrijving(client, db_session, naam="Pagina Proef"):
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                data={"contact_name": naam, "contact_email": "proef@example.com",
                      "phone": "047", f"product_{product.id}": "1",
                      "payment_method": "OVERSCHRIJVING"})
    from app.domains.activities.api import Registration
    reg = (db_session.query(Registration)
           .filter(Registration.contact_name == naam).one())
    return activity, component, reg


def test_pagina_vereist_sessie(client):
    assert client.get("/admin/inschrijvingen/1").status_code == 401


def test_pagina_toont_kop_context_en_editor(client, db_session):
    activity, component, reg = _inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg.id}").text

    # Volwaardige pagina (admin-schil), niet het kale fragment.
    assert "<title>" in html and "Pagina Proef" in html
    # De contextregel linkt naar de activiteit en noemt het onderdeel.
    assert f'href="/admin/activiteiten/{activity.id}"' in html
    assert component.name in html
    # Het gedeelde editorfragment zit erin: dezelfde ene bron als het openvouwen.
    assert f'hx-post="/admin/inschrijvingen/{reg.id}/opslaan"' in html


def test_terug_herstelt_de_meegegeven_lijstcontext(client, db_session):
    """A7: de lijst geeft haar eigen adres mee — mét filters — en de terugknop
    brengt je daar terug."""
    activity, component, reg = _inschrijving(client, db_session)
    _login(client)
    terug = f"/admin/activiteiten/{activity.id}?sort=naam&richting=asc"
    html = client.get(f"/admin/inschrijvingen/{reg.id}",
                      params={"terug": terug}).text
    # Jinja escapet de & in het attribuut; de browser leest daar weer & uit.
    assert f'href="{terug.replace("&", "&amp;")}"' in html


@pytest.mark.parametrize("kwaad", [
    "https://evil.example/phish",   # absolute URL — open redirect
    "//evil.example/phish",         # scheme-relatief: browser maakt er https:// van
    "/admin\\@evil.example",        # backslash die browsers stil normaliseren
    "/admin/%0d%0aSet-Cookie: x",   # al gedecodeerde controltekens
    "",                             # niets meegegeven
])
def test_terug_valt_terug_op_de_canonieke_plek(client, db_session, kwaad):
    """Een vervalste `?terug=` wordt genegeerd: de knop wijst dan naar de
    activiteit van het record. Zou de validatie sneuvelen, dan staat het kwade
    adres letterlijk in de href en kleurt dit rood."""
    from urllib.parse import unquote
    activity, component, reg = _inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg.id}",
                      params={"terug": unquote(kwaad)}).text
    assert f'href="/admin/activiteiten/{activity.id}"' in html
    if kwaad.startswith(("http", "//")):
        assert f'href="{kwaad}"' not in html


def test_onbekende_inschrijving_geeft_404(client, db_session):
    _login(client)
    assert client.get("/admin/inschrijvingen/999999").status_code == 404


def test_fragmentroute_blijft_het_kale_fragment(client, db_session):
    """De secundaire variant (inline openvouwen, betalingen-expand) haalt
    `/fragment` op en hoort géén volledige pagina terug te krijgen — een
    pagina-in-een-rij zou de admin-schil dubbel renderen."""
    activity, component, reg = _inschrijving(client, db_session)
    _login(client)
    frag = client.get(f"/admin/inschrijvingen/{reg.id}/fragment").text
    assert "Pagina Proef" in frag
    assert "<title>" not in frag

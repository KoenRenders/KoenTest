"""#689 — de deellink kopiëren met één klik.

Er bestond nergens in de app een kopieer-naar-klembord-patroon, dus dit is een
kitcomponent (`ui.copy_button`) en geen losse knop in het formulierenscherm.

Drie dingen waar deze tests op letten, omdat ze alle drie stil kunnen wegvallen:

1. **De volledige URL.** Wat je plakt moet aanklikbaar zijn. De knop draagt het
   pad; `raakKopieer()` maakt er een absolute URL van met `location.origin` —
   zo hoeft het beheerscherm geen domein te kennen.
2. **De terugval.** `navigator.clipboard` bestaat alleen in een secure context.
   Zonder terugval doet de knop op een intern http-adres stil niets, en dat is het
   ergste wat een knop kan doen.
3. **Geldige HTML in de kaartenlijst.** Een `<button>` in een `<a>` mag niet. De
   kaart blijft één grote link via het uitgerekte-link-patroon.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests import forms_door
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _formulier(client):
    r = forms_door.create_form(client, {"title": "Deelbaar", "status": "open", "fields": []})
    assert r.status_code == 200, r.text
    return r.json()


# ── De knop staat op beide schermen ──────────────────────────────────────────


def test_de_kaartenlijst_heeft_een_kopieerknop(client):
    form = _formulier(client)
    _login(client)

    html = client.get("/admin/formulieren").text
    assert f'data-copy="/formulier/{form["share_token"]}"' in html


def test_het_bouwscherm_heeft_een_kopieerknop(client):
    form = _formulier(client)
    _login(client)

    html = client.get(f"/admin/formulieren/{form['id']}").text
    assert f'data-copy="/formulier/{form["share_token"]}"' in html


# ── Wat de knop kopieert ─────────────────────────────────────────────────────


def test_de_helper_maakt_er_een_volledige_url_van(client):
    """Een bronregel: JavaScript draait hier niet, maar het verschil tussen een pad
    en een volledige URL is precies wat het issue vroeg. Zonder deze assertie kan
    de origin-prefix verdwijnen zonder dat iets rood wordt."""
    _login(client)
    html = client.get("/admin/formulieren").text

    assert "raakKopieer" in html, "de helper wordt niet meegeleverd"
    assert "new URL(waarde, location.origin)" in html, (
        "de knop kopieert het pad in plaats van de volledige URL"
    )


def test_er_is_een_terugval_zonder_secure_context(client):
    _login(client)
    html = client.get("/admin/formulieren").text

    assert "isSecureContext" in html, "er wordt niet gecontroleerd op secure context"
    assert "execCommand" in html, "geen terugval als het klembord niet beschikbaar is"
    assert "data-copy-bron" in html, (
        "geen laatste redmiddel: de zichtbare tekst hoort geselecteerd te worden"
    )


def test_de_knop_liegt_niet_bij_een_mislukte_kopie(client):
    """`raakKopieer` geeft false terug bij mislukking, en de bevestiging ("Gekopieerd")
    hangt aan die uitkomst. Een item dat altijd bevestigt is erger dan een item dat niets
    doet: dan denk je dat de link op je klembord staat."""
    _formulier(client)
    _login(client)
    html = client.get("/admin/formulieren").text

    assert "ok = await raakKopieer" in html, (
        "de bevestiging hangt niet aan de uitkomst van de kopieerpoging"
    )
    assert "Gekopieerd" in html


# ── Toegankelijkheid en geldige opmaak ───────────────────────────────────────


def test_het_item_draagt_zijn_label(client):
    """#2123: "Deellink kopiëren" is een item van het rijmenu en heeft dus tekst (geen
    icoonknop met een aria-label): de tekst is het label."""
    _formulier(client)
    _login(client)

    html = client.get("/admin/formulieren").text
    start = html.index('data-copy="/formulier/')
    item = html[html.rindex("<button", 0, start) : html.index("</button>", start)]
    assert 'role="menuitem"' in item and "Deellink kopiëren" in item, item


def test_het_item_staat_niet_in_de_rijlink(client):
    """Een `<button>` in een `<a>` is ongeldige HTML. De rij is een tabelrij en haar link
    (`ui.row_link`) staat in de eerste cel; het menu staat in de laatste."""
    form = _formulier(client)
    _login(client)
    html = client.get("/admin/formulieren").text

    anchor = html.index(f'href="/admin/formulieren/{form["id"]}"')
    knop = html.index('data-copy="/formulier/')
    assert anchor < knop, "onverwachte volgorde; de check hieronder klopt dan niet"
    assert "</a>" in html[anchor:knop], "het kopieeritem staat binnen de rijlink — ongeldige HTML"

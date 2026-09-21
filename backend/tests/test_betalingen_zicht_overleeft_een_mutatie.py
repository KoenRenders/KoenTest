"""Het gekozen tabblad overleeft een bevestiging (Koen, 21 september 2026).

Zijn melding: *"ik ga naar de openstaande betalingen (tab), ik klik op bevestig en
bevestig de popup, ik ga dan terug naar allen terwijl ik van openstaand vertrok."*

**De oorzaak zat niet in de mutatie maar in de tab.** De filterbalk merkt haar
verzoeken met `X-Raak-Filter`, waarop de middleware het PAGINA-adres mét filter in
de adresbalk zet; htmx stuurt dat daarna bij élk verzoek mee als `HX-Current-URL`.
De statustabs deden dat niet. Het gekozen zicht leefde dus alleen in het geswapte
fragment — en een mutatie post naar haar eigen endpoint zónder formuliervelden, dus
die vond niets en viel terug op *Alle*.

Dat een filterstand een mutatie moet overleven, staat al met zoveel woorden in de
docstring van die middleware (#671). De tabs deden alleen niet mee.

**Deze test neemt de weg die Koen neemt**, en dat is het hele punt: mijn eerste
meting stuurde `HX-Current-URL` mét `zicht=openstaand` mee en zag niets fout. Maar
zó komt die URL er nooit te staan — een tabklik pushte hem niet. Wie het zicht in
de URL zet, meet een scherm dat niet bestaat.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): het
`hx-headers`-attribuut van de tabs weghalen → **alle vier** vallen om, met
*"na de bevestiging staat 'alle' actief in plaats van 'openstaand'"*.

**Die tegenproef is de eerste keer mislukt, en dat hoort hier te staan.** Mijn
eerste versie zette `X-Raak-Filter` met de hand in de testkoppen. Toen ik het
attribuut uit het sjabloon haalde, bleven alle tests groen — ze toetsten mijn
simulatie en niet de knop. Een test die het onderwerp omzeilt, overleeft het
verwijderen ervan. Daarom leest `_tabknop` de `hx-get` én de `hx-headers` nu uit
de gerenderde opmaak; wat de browser zou versturen, komt uit het scherm en niet
uit dit bestand.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

ZICHTEN = ("openstaand", "betaald", "terugbetaald")


def _finance(db):
    from app.domains.auth.models import User, UserRole

    gebruiker = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in gebruiker.roles):
        db.add(UserRole(user_id=gebruiker.id, role_code="FINANCE"))
        db.flush()


def _login(client, db):
    _finance(db)
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def _tabknop(html: str, zicht: str) -> tuple[str, dict]:
    """Wat de browser zou doen als je dít tabblad aanklikt.

    De `hx-get` én de `hx-headers` komen uit de GERENDERDE opmaak, niet uit deze
    test. Dat is het verschil tussen een simulatie en een aanname: zet ik de kop
    zelf, dan blijft de test groen terwijl de knop hem niet draagt — en dat is
    precies wat er bij de eerste versie van dit bestand gebeurde.
    """
    import json

    tag = re.search(rf'<a[^>]*hx-get="[^"]*zicht={zicht}[^"]*"[^>]*>', html)
    assert tag, f"geen tabknop gevonden voor zicht={zicht}"
    tekst = tag.group(0).replace("&amp;", "&")
    url = re.search(r'hx-get="([^"]+)"', tekst).group(1)
    koppen = re.search(r"hx-headers='([^']+)'", tekst)
    return url, (json.loads(koppen.group(1)) if koppen else {})


def _actief_tabblad(html: str) -> str | None:
    """Welk tabblad draagt de actieve opmaak? Eén per antwoord."""
    actief = [z for z, klasse in
              re.findall(r'zicht=(\w+)[^>]*class="([^"]*)"', html)
              if "font-semibold" in klasse]
    return actief[0] if actief else None


@pytest.fixture
def openstaande_betaling(db_session):
    rij = PaymentRecord(payable_type="registration", payable_id=4242,
                        amount=Decimal("20.00"), method="transfer",
                        status="pending", type="charge")
    db_session.add(rij)
    db_session.commit()
    return rij


def test_de_tab_zet_zijn_zicht_in_de_adresbalk(client, db_session,
                                                openstaande_betaling):
    """De reparatie zelf: een tabklik pusht het pagina-adres mét zicht.

    Zonder deze kop weet het volgende verzoek niet waar je stond — en dat
    'volgende verzoek' is elke bevestiging, elke terugbetaling, elke wijziging.
    """
    _login(client, db_session)
    pagina = client.get("/admin/betalingen").text
    url, koppen = _tabknop(pagina, "openstaand")

    antwoord = client.get(url, headers={**koppen, "HX-Request": "true",
                                        "HX-Current-URL":
                                        "http://testserver/admin/betalingen"})

    assert antwoord.headers.get("HX-Push-Url") == "/admin/betalingen?zicht=openstaand", (
        "de tabknop draagt geen X-Raak-Filter, dus de middleware duwt niets — en "
        f"dan weet het volgende verzoek niet waar je stond. Koppen: {koppen}")


@pytest.mark.parametrize("zicht", ZICHTEN)
def test_een_bevestiging_laat_je_op_hetzelfde_tabblad(client, db_session,
                                                       openstaande_betaling,
                                                       zicht):
    """Koens melding, voor elk tabblad — hij vroeg expliciet om de andere ook.

    De volgorde is de zijne: pagina laden, tabblad kiezen, bevestigen. De URL
    die de mutatie meestuurt is die welke de TAB pushte, niet één die wij
    verzinnen.
    """
    kop = _login(client, db_session)
    pagina = client.get("/admin/betalingen").text
    url, koppen = _tabknop(pagina, zicht)

    tabklik = client.get(url, headers={**koppen, "HX-Request": "true",
                                       "HX-Current-URL":
                                       "http://testserver/admin/betalingen"})
    # Wat de browser hierna in de adresbalk heeft staan — en dus meestuurt.
    geduwd = tabklik.headers.get("HX-Push-Url", "/admin/betalingen")

    na = client.post(f"/admin/betalingen/{openstaande_betaling.id}/bevestigen",
                     headers={**kop, "HX-Request": "true",
                              "HX-Current-URL": f"http://testserver{geduwd}"})

    assert na.status_code == 200, na.text[:300]
    assert _actief_tabblad(na.text) == zicht, (
        f"na de bevestiging staat '{_actief_tabblad(na.text)}' actief in plaats "
        f"van '{zicht}'")

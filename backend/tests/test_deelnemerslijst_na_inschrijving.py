"""#1159: wie zich net inschreef, staat meteen bij "Wie doet er mee?".

De deelnemerslijst hangt op de activiteitkaart en staat dus BUITEN het swap-doel
van het inschrijfformulier (`hx-target="closest .inschrijf-card"`). Ze bleef
daardoor staan zoals ze bij het laden van de pagina was. Het betaalde pad
verborg dat half — Mollie dwingt een volledige herlaadbeurt af — dus het gat zat
bij een gratis inschrijving en bij betalen ter plaatse.

Dezelfde vorm als §8.4 van het design system, en hetzelfde antwoord: het
antwoord op de inschrijving draagt de bijgewerkte lijst out-of-band mee.

**Het aantal is hier belangrijker dan de naam.** De kop telt hoeveelheden op, dus
wie zich voor drie personen inschrijft hoort N met drie te zien stijgen. Een test
die alleen op de naam let, staat groen bij een kapotte telling.
"""
from __future__ import annotations

import re

import pytest

from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

OOB = re.compile(r'<div hx-swap-oob="innerHTML:#deelnemers-(\d+)-(\d+)">(.*)',
                 re.S)


def _oob(respons, activity_id: int, component_id: int) -> str:
    """Het out-of-band-blok uit het antwoord, of een lege string.

    Bewust op de ECHTE doel-id: een blok dat naar een andere div wijst landt
    nergens, en dat is precies de fout die je anders niet ziet — htmx meldt een
    OOB-swap zonder doel niet.
    """
    treffer = OOB.search(respons.text)
    if treffer is None:
        return ""
    assert (int(treffer.group(1)), int(treffer.group(2))) == (activity_id, component_id), (
        f"het OOB-blok wijst naar #deelnemers-{treffer.group(1)}-{treffer.group(2)} "
        f"maar de kaart draagt #deelnemers-{activity_id}-{component_id}")
    return treffer.group(3)


def _schrijf_in(client, activity, component, product, naam: str, aantal: int):
    return client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={"contact_name": naam, "contact_email": f"{naam.lower()}@example.com",
              "phone": "0470000000", f"product_{product.id}": str(aantal)})


# ── 1. Het gemelde geval ────────────────────────────────────────────────────

def test_a_free_registration_carries_the_updated_list_along(client, db_session):
    """Het scherm dat Koen beschreef: bevestiging in het paneel, lijst ernaast
    nog op de oude stand.

    Tegenproef: het OOB-blok uit `_inschrijf_klaar.html` gehaald → deze test
    faalt op *"geen out-of-band-blok in het antwoord"*, want `_oob` geeft dan
    een lege string terug. Een test die alleen `"Bedankt, Fien" in resp.text`
    controleert blijft daarbij groen — dat is hoe dit zo lang kon blijven staan.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="0", is_free=True)

    resp = _schrijf_in(client, activity, component, product, "Fien", 1)
    assert resp.status_code == 200 and "HX-Redirect" not in resp.headers

    blok = _oob(resp, activity.id, component.id)
    assert blok, "geen out-of-band-blok in het antwoord"
    assert "Fien" in blok, (
        f"de verse inschrijving staat niet in de meegestuurde lijst: {blok!r}")
    assert "1 ingeschreven" in blok


def test_the_count_adds_up_the_quantities(client, db_session):
    """De assertie waar dit issue om vraagt: N telt hoeveelheden, geen rijen.

    Drie personen in één inschrijving horen N met DRIE te laten stijgen. Zonder
    deze test slaagt de vorige ook wanneer de kop rijen telt — bij één rij is
    het verschil onzichtbaar, en dat is precies het geval dat je eerst bouwt.

    Tegenproef: `sum(attribute="quantity")` in `_deelnemers.html` vervangen door
    `| length` → deze test faalt op "3 ingeschreven", de vorige blijft groen.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="0", is_free=True)

    blok = _oob(_schrijf_in(client, activity, component, product, "Ward", 3),
                activity.id, component.id)
    assert "3 ingeschreven" in blok, (
        f"drie personen in één inschrijving, maar de kop telt anders: {blok!r}")

    # En de tweede inschrijving telt bij de eerste op, niet eroverheen.
    blok2 = _oob(_schrijf_in(client, activity, component, product, "Lore", 2),
                 activity.id, component.id)
    assert "5 ingeschreven" in blok2, f"3 + 2 verwacht, gekregen: {blok2!r}"
    assert "Ward" in blok2 and "Lore" in blok2


def test_the_list_is_right_for_someone_who_never_opened_it(client, db_session):
    """Het tweede geval uit het issue: eerst inschrijven, dán pas openklappen.

    Die klik haalt de lijst via de gewone route op (`hx-trigger="click once"`),
    dus dit toetst de gegevenskant los van het OOB-blok. Beide wegen moeten
    hetzelfde zeggen, anders ziet de bezoeker zijn naam verschijnen en bij de
    volgende klik weer verdwijnen.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="0", is_free=True)
    _schrijf_in(client, activity, component, product, "Mira", 2)

    lijst = client.get(f"/activiteiten/{activity.id}/deelnemers/{component.id}")
    assert lijst.status_code == 200
    assert "Mira" in lijst.text and "2 ingeschreven" in lijst.text


# ── 2. Wat niet mag veranderen ──────────────────────────────────────────────

def test_the_paid_path_still_redirects_to_mollie(client, db_session, mock_mollie):
    """Het betaalde pad blijft een harde redirect, zonder OOB-blok ernaast.

    Vaste UI-beslissing (CLAUDE.md): bij een `checkout_url` gaat de browser écht
    naar Mollie via `HX-Redirect`. Een OOB-blok zou daar nergens landen — de
    pagina wordt verlaten — dus het wordt op dat pad niet meegestuurd. Deze test
    legt die keuze vast: verschijnt het blok hier ooit tóch, dan is dat een
    wijziging die iemand bewust moet maken.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="12.50", is_free=False)

    resp = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={"contact_name": "Roos", "contact_email": "roos@example.com",
              "phone": "0470000001", f"product_{product.id}": "1",
              "payment_method": "ONLINE"})

    assert resp.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")
    assert "hx-swap-oob" not in resp.text, (
        "het betaalde pad verlaat de pagina; een OOB-blok hoort daar niet bij")


def test_the_oob_block_leaves_the_alpine_wrapper_alone(client, db_session):
    """De omhullende div blijft van Alpine, de inhoud van htmx.

    `#deelnemers-…` draagt `x-show="open"`, `x-cloak` en een inline `style`.
    Swapt het antwoord de hele div (`outerHTML`), dan wist htmx' settle die
    style en klapt het paneel open terwijl het dicht hoorde te staan — de fout
    die #737/§2.9b beschrijft. `innerHTML:` raakt de omhullende niet aan.

    Getoetst op de vorm van het attribuut, want het gedrag erachter zit in htmx
    en niet in onze code: een `outerHTML`-swap zou hier onopgemerkt binnensluipen.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="0", is_free=True)

    tekst = _schrijf_in(client, activity, component, product, "Jo", 1).text
    assert f'hx-swap-oob="innerHTML:#deelnemers-{activity.id}-{component.id}"' in tekst
    assert "outerHTML:#deelnemers" not in tekst

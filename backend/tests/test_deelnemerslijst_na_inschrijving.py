"""#1159: wie zich net inschreef, staat meteen bij "Wie doet er mee?".

De deelnemerslijst hangt op de activiteitkaart. Tot CR-14 stond ze BUITEN het
swap-doel van de inschrijfmodal, en droeg het antwoord de bijgewerkte lijst
out-of-band mee.

**Since CR-14 phase 1 (#1332, P10 of B4.9) the registration is a page**, and the
out-of-band block went with the modal. The rule stays and has a new mechanism: the
thank-you page's link back opens the list of that component, which loads fresh from
its route (`?deelnemers=<component>`; `app/domains/activities/tests/test_registration_page.py`
holds the opening). The tests below hold what the visitor then reads.

**Het aantal is hier belangrijker dan de naam.** De kop telt hoeveelheden op, dus
wie zich voor drie personen inschrijft hoort N met drie te zien stijgen. Een test
die alleen op de naam let, staat groen bij een kapotte telling.

The test of the out-of-band swap's form (`innerHTML:` and not `outerHTML:`) went:
there is no swap left whose form it could guard.
"""

from __future__ import annotations

import pytest

from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _lijst(client, activity, component) -> str:
    """What the list shows — the route the page loads it from on the way back."""
    return client.get(f"/activiteiten/{activity.id}/deelnemers/{component.id}").text


def _schrijf_in(client, activity, component, product, naam: str, aantal: int):
    return client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": naam,
            "contact_email": f"{naam.lower()}@example.com",
            "phone": "0470000000",
            f"product_{product.id}": str(aantal),
        },
    )


# ── 1. Het gemelde geval ────────────────────────────────────────────────────


def test_a_free_registration_leads_back_to_a_list_with_the_new_name(client, db_session):
    """Het scherm dat Koen beschreef (#1159): bevestiging, en een lijst die de verse
    inschrijving al toont. Since CR-14 the thank-you page links back with the list
    of this component open; the list it then loads names the new registration."""
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)

    resp = _schrijf_in(client, activity, component, product, "Fien", 1)
    assert resp.status_code == 200 and "HX-Redirect" not in resp.headers
    assert f"?deelnemers={component.id}" in resp.text, "no way back to an open list"

    lijst = _lijst(client, activity, component)
    assert "Fien" in lijst, f"de verse inschrijving staat niet in de lijst: {lijst!r}"
    assert "1 ingeschreven" in lijst


def test_the_count_adds_up_the_quantities(client, db_session):
    """De assertie waar dit issue om vraagt: N telt hoeveelheden, geen rijen.

    Drie personen in één inschrijving horen N met DRIE te laten stijgen. Zonder
    deze test slaagt de vorige ook wanneer de kop rijen telt — bij één rij is
    het verschil onzichtbaar, en dat is precies het geval dat je eerst bouwt.

    Tegenproef: `sum(attribute="quantity")` in `_deelnemers.html` vervangen door
    `| length` → deze test faalt op "3 ingeschreven", de vorige blijft groen.
    """
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)

    _schrijf_in(client, activity, component, product, "Ward", 3)
    blok = _lijst(client, activity, component)
    assert "3 ingeschreven" in blok, (
        f"drie personen in één inschrijving, maar de kop telt anders: {blok!r}"
    )

    # En de tweede inschrijving telt bij de eerste op, niet eroverheen.
    _schrijf_in(client, activity, component, product, "Lore", 2)
    blok2 = _lijst(client, activity, component)
    assert "5 ingeschreven" in blok2, f"3 + 2 verwacht, gekregen: {blok2!r}"
    assert "Ward" in blok2 and "Lore" in blok2


def test_the_list_is_right_for_someone_who_never_opened_it(client, db_session):
    """Het tweede geval uit het issue: eerst inschrijven, dán pas openklappen.

    Die klik haalt de lijst via de gewone route op (`hx-trigger="click once"`),
    dus dit toetst de gegevenskant los van het OOB-blok. Beide wegen moeten
    hetzelfde zeggen, anders ziet de bezoeker zijn naam verschijnen en bij de
    volgende klik weer verdwijnen.
    """
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
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
        db_session, price="12.50", is_free=False
    )

    resp = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Roos",
            "contact_email": "roos@example.com",
            "phone": "0470000001",
            f"product_{product.id}": "1",
            "payment_method": "online",
        },
    )

    assert resp.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")
    assert "hx-swap-oob" not in resp.text, (
        "het betaalde pad verlaat de pagina; een OOB-blok hoort daar niet bij"
    )

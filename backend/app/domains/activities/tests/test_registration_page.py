"""CR-14 phase 1 (#1332): the registration is a page — and the card and the activity
page share one block of component actions.

What the page must do beyond the form's content (which the characterisation
snapshots hold, `tests/integration/test_registration_screens_characterisation.py`):

- the card and the activity page link to the page — no modal, no `hx-get` of a form;
- the page stands in the site shell with the activity, its date, the component
  switch (P14) and a way back;
- a refusal re-renders the page with the values kept and the reason on top (P7);
- a free or transfer registration lands on a thank-you page whose link back opens
  the participant list of that component (P8, P10);
- a component whose deadline passed says "closed" on the card AND on the activity
  page, and the other component keeps its button — the page used to look at the
  activity as a whole (#1053 is right: the deadline belongs to the component).

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `c.registration_closed` replaced by `a.registration_closed` in
`_onderdeel_acties.html` (the page's old rule) → the closed-per-component test,
on the card and on the page; `"klaar_url": terug,` added after the `klaar_url`
line in `_page_ctx` (additive) → the thank-you test alone.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.activities.api import ActivityProduct, ActivitySubRegistration
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def two_components(db_session):
    """An activity with two components, each with a paid product: "Onderdeel" (open)
    and "Vroeg" (its deadline passed yesterday)."""
    activity, open_one, product = seed_activity_with_product(db_session, price="7.00")
    closed = ActivitySubRegistration(
        activity_id=activity.id,
        name="Vroeg",
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        is_free=True,
        registration_closes_on=date.today() - timedelta(days=1),
        sort_order=1,
    )
    db_session.add(closed)
    db_session.flush()
    db_session.add(ActivityProduct(component_id=closed.id, name="Vroegproduct", price=Decimal("4")))
    db_session.commit()
    return activity, open_one, closed, product


def _component_block(html: str, component_name: str) -> str:
    """The action block of one component: from its name to the next block."""
    name = html.index(f">{component_name}</span>")
    start = html.rindex('<div class="pt-2"', 0, name)
    rest = html[start:]
    end = rest.find('<div class="pt-2"', 1)
    return rest if end < 0 else rest[:end]


@pytest.mark.parametrize("path", ["/activiteiten", "/activiteiten/{id}"])
def test_card_and_page_link_to_the_page_and_close_per_component(client, two_components, path):
    activity, open_one, closed, _product = two_components
    html = client.get(path.format(id=activity.id)).text

    open_block = _component_block(html, "Onderdeel")
    closed_block = _component_block(html, "Vroeg")
    assert f'href="/activiteiten/{activity.id}/inschrijven/{open_one.id}"' in open_block
    # #1375: the closed state is the disabled "Afgesloten" button.
    assert ">Afgesloten</button>" not in open_block
    assert ">Afgesloten</button>" in closed_block
    assert f"/inschrijven/{closed.id}" not in closed_block
    assert 'hx-get="/activiteiten/' + str(activity.id) + "/inschrijven" not in html, (
        "a component still opens the form as a modal"
    )


def test_the_page_stands_in_the_site_shell(client, two_components):
    activity, open_one, closed, _product = two_components
    response = client.get(f"/activiteiten/{activity.id}/inschrijven/{open_one.id}")
    assert response.status_code == 200
    html = response.text
    assert "<main" in html and 'id="inschrijf-pagina"' in html
    assert f">{activity.name}</h1>" in html
    assert f'href="/activiteiten/{activity.id}"' in html, "no way back to the activity"
    # P14: the switch lists the other component as a link, the chosen one not.
    assert f'href="/activiteiten/{activity.id}/inschrijven/{closed.id}"' in html


def test_a_refusal_keeps_the_page_the_values_and_the_reason(client, two_components):
    activity, open_one, _closed, product = two_components
    response = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{open_one.id}",
        data={
            "contact_name": "Zonder Gsm",
            "contact_email": "zonder@example.com",
            "phone": "",
            f"product_{product.id}": "2",
            "payment_method": "transfer",
        },
    )
    # #1589 (§3.18): the refusal is the banner alone, for the form's message
    # line — the page is not redrawn, so the values stay where they were typed.
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#inschrijf-melding"
    assert response.headers["HX-Reswap"] == "innerHTML"
    html = response.text
    assert 'id="inschrijf-pagina"' not in html and "<input" not in html
    assert 'data-error-for="phone"' in html and ">Vul je mobiel nummer in.<" in html
    assert "Verzenden kan nog niet: controleer 1 veld." in html


def test_the_registration_page_has_no_link_to_who_takes_part(client, two_components):
    """#1642 (Koen, 5 October 2026): the link "Wie doet er mee?" under the total
    is gone from the registration page; the list stays on the activity's page,
    where the visitor came from. Red against master: the link stands in the
    form, to `?deelnemers=<component>`."""
    activity, open_one, _closed, _product = two_components
    form = client.get(f"/activiteiten/{activity.id}/inschrijven/{open_one.id}")
    assert form.status_code == 200
    main = form.text[form.text.index("<main") : form.text.index("</main>")]
    assert "Wie doet er mee?" not in main and "?deelnemers=" not in main
    # The activity's own page still offers the list.
    assert "Wie doet er mee?" in client.get(f"/activiteiten/{activity.id}").text


def test_the_thank_you_page_leads_back_to_an_open_list(client, two_components):
    activity, open_one, _closed, product = two_components
    response = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{open_one.id}",
        data={
            "contact_name": "Terug Tine",
            "contact_email": "terug@example.com",
            "phone": "0470000000",
            f"product_{product.id}": "1",
            "payment_method": "transfer",
        },
    )
    assert response.status_code == 200
    html = response.text
    assert ">Je inschrijving is ontvangen</h1>" in html
    # #1589: what is still to pay is said as such.
    assert "Betaling nog af te ronden" in html
    back = re.search(r'href="([^"]*\?deelnemers=\d+)"', html)
    assert back, "the thank-you page has no way back that opens the list"
    assert back.group(1) == f"/activiteiten/{activity.id}?deelnemers={open_one.id}"

    page = client.get(back.group(1)).text
    block = _component_block(page, "Onderdeel")
    assert 'x-data="{ open: true }"' in block
    assert (
        f'hx-get="/activiteiten/{activity.id}/deelnemers/{open_one.id}" hx-trigger="load"' in block
    )

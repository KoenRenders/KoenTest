"""The promises of `ui.field` that a test walks, because the gate's static walk cannot (#2118).

The walk of the rules gate follows `required`, `pattern` and `min` on a kit field to the
column or the validator that refuses the same on the server (#2110 started it for six pages,
#2118 for every screen). Where it cannot follow — the field is no column, the form's target
is a variable, the route reads the form as a whole — the field's line names the test that
walks it (`{# promise walked by: … #}`). Those tests stand here when no test of the screen
already posted the field empty; the ones that already existed are named in the templates.

Each test posts to the real route the value the browser would refuse and says what the
visitor gets back.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    form_guard_fields,
    seed_activity_with_product,
)


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


_ACCOUNT_REASON = {
    "first_name": "Vul je voornaam in.",
    "last_name": "Vul je achternaam in.",
    "email": "Vul een geldig e-mailadres in.",
    "mobile": "Vul je mobiel nummer in.",
}


@pytest.mark.parametrize("empty", ["first_name", "last_name", "email", "mobile"])
def test_the_account_form_refuses_each_empty_field(client, db_session, empty):
    """Form: "Account aanmaken" (`auth/_create_account_form.html`), route
    `POST /account-aanmaken`. Posts the four fields, one of them empty. The visitor gets
    the form back (200, it swaps into itself) with the reason under that field, marked
    invalid, and no person exists."""
    data = {
        "first_name": "Nora",
        "last_name": "Nieuw",
        "email": "nora-2118@example.org",
        "mobile": "0470 00 21 18",
    }
    data[empty] = ""
    before = db_session.query(Person).count()
    answer = client.post("/account-aanmaken", data=data)
    assert answer.status_code == 200, answer.text[:300]
    start = answer.text.index(f'data-field="{empty}"')
    field = answer.text[start : answer.text.find('data-field="', start + 1)]
    assert _ACCOUNT_REASON[empty] in field and 'aria-invalid="true"' in field
    assert db_session.query(Person).count() == before


@pytest.mark.parametrize("empty", ["contact_name", "contact_email", "phone", "team_name"])
def test_a_registration_refuses_each_empty_contact_field(client, db_session, empty):
    """Form: the registration (`activities/_inschrijf_velden.html`), route
    `POST /activiteiten/{id}/inschrijven/{component}`, for a component that asks a team
    name. Posts the contact fields and the team name, one of them empty. The visitor gets
    the reason under that field (422), and no registration is made."""
    from app.domains.activities.api import Registration

    activity, component, product = seed_activity_with_product(db_session)
    component.team_name_required = True
    db_session.commit()
    data = {
        **form_guard_fields(),
        "contact_name": "An",
        "contact_email": "an@example.org",
        "phone": "0470 00 21 18",
        "team_name": "De Stappers",
        f"product_{product.id}": "1",
        "products": str(product.id),
    }
    data[empty] = ""
    before = db_session.query(Registration).count()
    answer = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}", data=data)
    assert answer.status_code == 422, answer.text[:300]
    assert f'data-error-for="{empty}"' in answer.text
    assert db_session.query(Registration).count() == before


def test_a_subscriber_is_not_added_without_an_address(client, db_session):
    """Form: "+ Adres" (`newsletter/admin_abonnee_nieuw.html`), route
    `POST /admin/nieuwsbrieven/abonnees`. Posts `"subscriber_email"` empty. The server
    answers with the reason for the form's own message line (422) and adds nobody."""
    from app.domains.newsletter.api import Subscriber

    headers = _board(client)
    before = db_session.query(Subscriber).count()
    answer = client.post(
        "/admin/nieuwsbrieven/abonnees", headers=headers, data={"subscriber_email": ""}
    )
    assert answer.status_code == 422, answer.text[:300]
    assert answer.headers["HX-Retarget"] == "#abonnee-melding"
    assert db_session.query(Subscriber).count() == before


def test_a_price_is_refused_with_a_negative_member_price(client, db_session, every_module_on):
    """Form: the price form (`pricing/admin_prijs.html`), route `POST /admin/prijzen/{id}`.
    Posts `"member_amount"` below the `min` of its input. The server answers with the
    reason for the form's message line (422) and sets no price."""
    from app.domains.pricing.api import prices_of
    from app.domains.product.api import create_product
    from tests.integration.test_pricing_screen import _operator

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    answer = client.post(
        f"/admin/prijzen/{product.id}",
        data={"valid_from": "2026-11-01", "variant_id": "", "amount": "17", "member_amount": "-3"},
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422, answer.text[:300]
    assert prices_of(db_session, product.id) == []


def test_the_own_organisation_is_not_saved_without_a_name(client, db_session):
    """Form: the organisation screen (`ui/admin_organisatie.html`), route
    `POST /admin/organisatie`. Posts `"name"` empty. The server refuses (422) and the
    name stays."""
    from app.domains.mdm.api import Organization
    from tests.integration.test_organisatiescherm import _post_own

    before = {o.id: o.name for o in db_session.query(Organization).all()}
    answer = _post_own(client, db_session, name="")
    assert answer.status_code == 422, answer.text[:300]
    db_session.expire_all()
    assert {o.id: o.name for o in db_session.query(Organization).all()} == before


@pytest.mark.parametrize("direction", ["", "sideways"])
def test_a_correction_without_a_direction_is_refused(
    client, db_session, every_module_on, direction
):
    """Form: the correction (`stock/admin_correctie.html`), route
    `POST /admin/voorraad/correctie`. Posts `"direction"` empty, or a word nobody offered.
    The server refuses (422) with "Kies een richting." at the field, and the stock stays;
    it used to book the correction upwards (#2118, the rule is the service's)."""
    from app.domains.product.api import add_variant, create_product
    from app.domains.stock.api import on_hand, receive
    from tests.integration.test_stock_screen import _operator

    headers = _operator(client, db_session, every_module_on)
    variant = add_variant(db_session, create_product(db_session, "T-shirt Raak").id, "M")
    receive(db_session, variant.id, quantity=10)
    answer = client.post(
        "/admin/voorraad/correctie",
        data={
            "variant_id": str(variant.id),
            "quantity": "2",
            "direction": direction,
            "note": "telling",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422, answer.text[:300]
    assert 'data-error-for="direction"' in answer.text and "Kies een richting." in answer.text
    assert on_hand(db_session, variant.id) == 10


def test_a_sale_adds_no_line_without_a_size(client, db_session, every_module_on):
    """Form: "Verkoop nieuw" (`sales/_verkoop_maten.html`), route
    `POST /admin/verkoop/nieuw` with the action "add". Posts `"new_variant_id"` empty
    next to a quantity. The server draws the form again with the lines it had, and no
    line is added: a size is what makes a line."""
    from tests.integration.test_order_placing import (
        _as,
        _board_user,
        _variant_with_price_and_stock,
    )

    shirt = _variant_with_price_and_stock(
        db_session, name="T-shirt", size="M", amount="15.00", stock=5
    )
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))
    answer = client.post(
        "/admin/verkoop/nieuw",
        data={"action": "add", "new_variant_id": "", "new_quantity": "2", "email": ""},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text[:300]
    assert 'name="variant_id"' not in answer.text, "a line was added without a size"
    kept = client.post(
        "/admin/verkoop/nieuw",
        data={"action": "add", "new_variant_id": str(shirt.id), "new_quantity": "2", "email": ""},
        headers=headers,
    )
    assert f'name="variant_id" value="{shirt.id}"' in kept.text, "with a size the line is added"


def test_the_basket_page_holds_no_line_without_a_size(client, db_session, every_module_on):
    """Form: the article page (`sales/webshop_product.html`), whose button is made in
    JavaScript and whose basket is posted to `POST /webshop/mandje`. Posts no
    `"variant_id"`. The server answers the empty basket, no line and no order."""
    answer = client.post("/webshop/mandje", data={}, follow_redirects=False)
    assert answer.status_code == 200
    assert "Je mandje is leeg" in answer.text
    assert 'name="variant_id"' not in answer.text

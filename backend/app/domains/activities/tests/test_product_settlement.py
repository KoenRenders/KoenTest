"""How a product is settled is ONE choice on the fiche (#1608; end state §3.3, CR-11 Q64).

K5 drew the model's two flags as two switches, "Gratis" and "Ter plaatse
betalen", which the screen could both switch on — a state the service refuses.
Koen, 5 October 2026: one choice of three, as it was before. The model keeps its
flags; `activities.settlement` translates.

Proven red, each by one exact replacement:
- `settlement_of` reading the flags the wrong way round → the three-cases test;
- the reader ignoring `settlement` → the save test (a free product stays paid);
- the reader treating an absent price as 0 → "the price a product had is kept";
- the segment taken out of the row → "one segment per product, no switch";
- read mode without the word, the old sentence under the poster, "Extra vragen"
  back on the field → each its own test.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from starlette.datastructures import FormData

from app.domains.activities.api import ActivityProduct
from app.domains.activities.fiche_form import fiche_from_form
from app.domains.activities.settlement import (
    FREE,
    ON_SITE,
    PAID,
    flags_of,
    settlement_of,
    settlement_options,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests._fiche import Fiche
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _page(client, activity_id: int, edit: bool = False) -> str:
    return client.get(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else "")).text


# ── The translation ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("choice", "is_free", "pay_on_site"),
    [(PAID, False, False), (FREE, True, False), (ON_SITE, False, True)],
)
def test_the_three_choices_are_the_models_two_flags_both_ways(choice, is_free, pay_on_site):
    assert flags_of(choice) == (is_free, pay_on_site)
    assert settlement_of(is_free, pay_on_site) == choice


def test_what_is_no_choice_is_refused_and_the_words_are_whole():
    with pytest.raises(ValueError):
        flags_of("both")
    assert settlement_options() == [(PAID, "Betalend"), (FREE, "Gratis"), (ON_SITE, "Ter plaatse")]


def _product(pairs: list[tuple[str, str]]):
    form = FormData(
        [
            ("fiche_groups", "components"),
            ("c_order", "7"),
            ("c.7.name", "Onderdeel"),
            ("p_order.7", "n1"),
            *pairs,
        ]
    )
    fiche, _files = fiche_from_form(form)
    return fiche.components[0].products[0], [(e.field, e.message) for e in fiche.errors]


def test_the_reader_makes_the_flags_from_the_one_choice():
    row, errors = _product([("p.n1.name", "Soep"), ("p.n1.settlement", ON_SITE)])
    assert (row.is_free, row.pay_on_site, errors) == (False, True, [])
    assert row.prices_sent is False, "no price field came with it"

    row, errors = _product([("p.n1.name", "Soep"), ("p.n1.settlement", PAID), ("p.n1.price", "5")])
    assert (row.is_free, row.pay_on_site, row.price, row.prices_sent) == (
        False,
        False,
        Decimal("5"),
        True,
    )


def test_a_choice_that_is_none_of_the_three_is_refused_at_its_field():
    _row, errors = _product([("p.n1.name", "Soep"), ("p.n1.settlement", "both")])
    assert errors == [("p.n1.settlement", "Kies hoe het product afgerekend wordt.")]


def test_a_caller_that_sends_the_two_flags_is_read_as_before():
    """The JSON API's shape, and how the service's own refusal stays reachable:
    both flags arrive as both flags."""
    row, errors = _product(
        [("p.n1.name", "Soep"), ("p.n1.is_free", "1"), ("p.n1.pay_on_site", "1")]
    )
    assert (row.is_free, row.pay_on_site, row.prices_sent, errors) == (True, True, True, [])


# ── The page ─────────────────────────────────────────────────────────────────


def _world(db):
    """One component with three products: one per choice."""
    activity, component, paid = seed_activity_with_product(db, price="10.00", is_free=False)
    free = ActivityProduct(
        component_id=component.id, name="Koffie", price=3, is_free=True, sort_order=1
    )
    on_site = ActivityProduct(
        component_id=component.id,
        name="Taart",
        price=4,
        is_free=False,
        pay_on_site=True,
        sort_order=2,
    )
    db.add_all([free, on_site])
    db.commit()
    return activity, component, paid, free, on_site


def test_one_segment_per_product_and_no_switch_and_each_on_its_choice(client, db_session):
    """Red on master: no segment at all, and two switches per product."""
    activity, _c, paid, free, on_site = _world(db_session)
    _login(client)
    html = _page(client, activity.id, edit=True)
    for product, choice in ((paid, PAID), (free, FREE), (on_site, ON_SITE)):
        radios = re.findall(
            rf'<input type="radio" name="p\.{product.id}\.settlement" value="(\w+)"[^>]*>', html
        )
        assert radios == [PAID, FREE, ON_SITE], f"{product.name}: {radios}"
        checked = re.findall(
            rf'<input type="radio" name="p\.{product.id}\.settlement" value="(\w+)"[^>]*checked',
            html,
        )
        assert checked == [choice], f"{product.name} stands on {checked}"
        assert f'name="p.{product.id}.is_free"' not in html
        assert f'name="p.{product.id}.pay_on_site"' not in html
    # the row a new product is made from starts as a paid product (the page holds
    # that row once per component, and once in the row a new component is made from)
    templates = re.findall(r'name="p\.__P__\.settlement" value="(\w+)"[^>]*checked', html)
    assert templates and set(templates) == {PAID}, templates


def test_read_mode_says_the_choice_in_one_word(client, db_session):
    activity, *_rest = _world(db_session)
    _login(client)
    html = _page(client, activity.id)
    assert re.findall(r"data-product-settlement[^>]*>([^<]+)<", html) == [
        "Betalend",
        "Gratis",
        "Ter plaatse",
    ]
    assert "Ter plaatse betalen:" not in html and "Gratis: " not in html


def test_the_choice_is_saved_as_the_flags_and_the_price_a_product_had_is_kept(client, db_session):
    """Measured before the change: with the two switches, switching to "Gratis"
    left the price field enabled, so the price was sent and stayed stored. The
    price fields are now switched off for a free or on-the-spot product and are
    not sent — and not sent is "leave it": the stored price stays, as it did."""
    activity, component, paid, free, on_site = _world(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    # as the screen sends it after choosing "Gratis" for the paid product:
    # the choice, and no price field
    fiche.set("p", paid.id, settlement=FREE)
    del fiche.data[f"p.{paid.id}.price"], fiche.data[f"p.{paid.id}.member_price"]
    # and "Betalend" for the free one, with a price typed
    fiche.set("p", free.id, settlement=PAID, price="3,50", member_price="")
    response = fiche.post(client, headers)
    assert response.status_code == 200, response.text[:300]
    db_session.expire_all()
    was_paid, was_free, still = (
        db_session.get(ActivityProduct, p.id) for p in (paid, free, on_site)
    )
    assert (was_paid.is_free, was_paid.pay_on_site) == (True, False)
    assert was_paid.price == Decimal("10.00"), "the price was wiped by switching to Gratis"
    assert (was_free.is_free, was_free.pay_on_site, was_free.price) == (
        False,
        False,
        Decimal("3.50"),
    )
    assert (still.is_free, still.pay_on_site, still.price) == (False, True, Decimal("4"))


def test_a_new_product_that_is_free_starts_without_a_price(client, db_session):
    activity, component, *_rest = _world(db_session)
    headers = _login(client)
    fiche = Fiche(db_session, activity.id)
    fiche.add("p", parent=component.id, name="Water", settlement=FREE)
    response = fiche.post(client, headers)
    assert response.status_code == 200, response.text[:300]
    water = db_session.query(ActivityProduct).filter_by(name="Water").one()
    assert (water.is_free, water.pay_on_site, water.price) == (True, False, Decimal("0"))


# ── The words (#1608, second and third point) ────────────────────────────────

POSTER_HELP = (
    "Je kan de affiche ontwerpen in de Design Studio, een bestand uploaden, of hier het "
    "adres van een bestaande affiche invullen."
)


def test_the_posters_help_is_one_sentence_on_its_three_pages(client, db_session):
    """Koen, 5 October 2026 (Q65): three ways to a poster, none "the old way".
    One macro (`ui.poster_help`), three callers."""
    activity, *_rest = _world(db_session)
    _login(client)
    for page in (
        f"/admin/activiteiten/{activity.id}?bewerken=1",
        "/admin/activiteiten/nieuw",
        "/admin/design-system",
    ):
        html = client.get(page).text
        assert POSTER_HELP in html, page
        assert "de oude weg" not in html, page


def test_a_components_question_form_is_called_formulier_on_the_boards_page(client, db_session):
    """Koen, 5 October 2026 (Q66): "Formulier", "Geen", and what it does. Edit
    and read mode; the public page keeps its own word, "Vragen"."""
    activity, component, *_rest = _world(db_session)
    _login(client)
    edit = _page(client, activity.id, edit=True)
    field = edit[edit.index(f'data-field="c.{component.id}.form_id"') :][:1500]
    assert re.search(r"<label[^>]*>\s*Formulier\s*<", field)
    assert '<option value="" selected>Geen</option>' in field or ">Geen</option>" in field
    assert "De vragen van dit formulier staan op de inschrijfpagina." in field
    assert "Extra vragen" not in edit and "Geen extra vragen" not in edit

    read = _page(client, activity.id)
    field = read[read.index(f'data-field="c.{component.id}.form_id"') :][:400]
    assert ">Formulier<" in field
    assert "Extra vragen" not in read

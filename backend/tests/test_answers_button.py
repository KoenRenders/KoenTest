""" "Boek" is "Antwoorden" (#1382).

The printable view of a component's answers was called "Boek" after the Sint's book
(CR-14 R14); for any other activity the word said nothing, and the view also serves
to read the answers and copy them. Koen, 30 September 2026: "Antwoorden".

- The registrations overview shows a button "Antwoorden" next to "Export", no "Boek".
- The view's title says "antwoorden".
- The path a person sees follows the word (CLAUDE.md, URL paths): `/…/antwoorden`,
  and the old `/…/boek` sends a saved or shared link there permanently.
  The code keeps its names (`boek_href`, `onderdeel_boek.html`, `component_book`).

Red against master `08a3ffbd` (30 September 2026): the button read "Boek", the
title "boek", and `/…/antwoorden` did not exist.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    ask_questions,
    register_at_the_door,
    seed_activity_with_product,
    seed_question_form,
)

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def asks(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    ask_questions(db_session, component, form.id)
    body = {
        "contact_name": "Knop Proef",
        "contact_email": "knop@example.com",
        "phone": "0470000000",
        "component_id": component.id,
        "items": [{"product_id": product.id, "quantity": 1}],
    }
    assert register_at_the_door(client, activity.id, json=body).is_success
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    return activity, component


def test_the_overview_offers_answers_not_a_book(client, asks):
    activity, component = asks
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text
    link = f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/antwoorden"
    button = re.search(rf'<a[^>]*href="{re.escape(link)}"[^>]*>(.*?)</a>', html, re.S)
    assert button, "no link to the answers view"
    assert re.sub(r"<[^>]+>", "", button.group(1)).strip() == "Antwoorden"
    assert ">Boek<" not in html


def test_the_view_says_answers_and_the_old_path_leads_there(client, asks):
    activity, component = asks
    base = f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}"
    page = client.get(f"{base}/antwoorden")
    assert page.status_code == 200
    title = re.search(r"<title>(.*?)</title>", page.text, re.S).group(1)
    assert title.rstrip().endswith("antwoorden"), title

    old = client.get(f"{base}/boek", follow_redirects=False)
    assert old.status_code == 301
    assert old.headers["location"] == f"{base}/antwoorden"

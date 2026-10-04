"""A scoped payments list keeps its scope after a mutation (#1247).

Koen, on UAT: *"indien ik via een activiteit naar betalingen ga staan daar de
betalingen van die activiteit, als ik echt iets bewerk, een vordering maak,…
worden op het tabblad van de activiteit alle betalingen getoond."*

Every mutation (confirm, refund, update, edit, refresh, status, delete) goes
through `_uitvoeren`, which rebuilt the list with `_view(request, …)` and no
scope. The scope of a record tab (activity, family, registration) is forced by
its route, not carried in the page URL, and a POST carries no `?activiteit=`
either — so the list that came back held every payment of the association.

These tests take the browser's path: the page is rendered, and the mutation is
posted with exactly what that markup sends — the `hx-post` of the button and the
`hx-headers` of the list it sits in, read from the rendered HTML, not written
here. Then they **count the records** in the answer, because "a list came back"
is true for both outcomes.

The one scoped case that was never broken is the list at `?activiteit=<id>`: its
scope is in the page URL, and htmx sends that along as `HX-Current-URL`. Koen's
report came from the activity's own tab, where the route forces the scope.

Broken on purpose to check that these tests can go red: the `hx-headers` taken
off `#betalingen-lijst` in `_betalingen_scherm.html` → the three record tabs and
the other-mutations test fall over, with records of another scope in the answer;
`_uitvoeren` back to `_view(request, db, email)` without the scope → the same
four. The `?activiteit=` list and the unscoped list stay green both times, as
they should.
"""

from __future__ import annotations

import json
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.auth.models import User, UserRole
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

FAMILY_EMAIL = "gezin-1247@example.org"


def _login(client, db) -> dict:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code.value == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _register(client, activity, component, product, name, email):
    client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": name,
            "contact_email": email,
            "phone": "047",
            f"product_{product.id}": "1",
            "payment_method": "transfer",
        },
    )


@pytest.fixture
def world(client, db_session):
    """Activity A with two registrations (one by a family member), activity B with one."""
    family, _person = create_test_family(db_session, email=FAMILY_EMAIL)
    a, a_comp, a_prod = seed_activity_with_product(db_session, price="10.00", is_free=False)
    b, b_comp, b_prod = seed_activity_with_product(db_session, price="12.00", is_free=False)
    _register(client, a, a_comp, a_prod, "Rec Anna", FAMILY_EMAIL)
    _register(client, a, a_comp, a_prod, "Rec Bert", "bert-1247@example.org")
    _register(client, b, b_comp, b_prod, "Ander Feest", "ander-1247@example.org")
    db_session.commit()

    from app.domains.activities.api import Registration

    anna = db_session.query(Registration).filter(Registration.contact_name == "Rec Anna").one()
    ander = db_session.query(Registration).filter(Registration.contact_name == "Ander Feest").one()
    b_records = {
        str(r.id)
        for r in db_session.query(PaymentRecord).filter(PaymentRecord.payable_id == ander.id).all()
    }
    assert b_records, "activity B has no payment record — is the setup still right?"
    return {"a": a.id, "b": b.id, "family": family.id, "anna": anna.id, "b_records": b_records}


def _record_ids(html: str) -> set[str]:
    """The records a list shows: every row has its own edit panel."""
    # K2 (#1556): a row is its link to the booking's page (the unfold, whose
    # Alpine expression carried the id, is gone).
    return set(
        re.findall(r'href="/admin/betalingen/([0-9a-f-]{36})\?terug=[^"]*" data-row-link', html)
    )


def _list_headers(html: str) -> dict:
    """What the browser adds to every request from inside the list."""
    tag = re.search(r'<div id="betalingen-lijst"[^>]*>', html, re.S)
    assert tag, "no #betalingen-lijst on the page — is this test still looking?"
    headers = re.search(r"hx-headers='([^']+)'", tag.group(0))
    return json.loads(headers.group(1).replace("&#34;", '"')) if headers else {}


def _confirm_url(html: str) -> str:
    url = re.search(r'hx-post="(/admin/betalingen/[^/"]+/bevestigen)"', html)
    assert url, "no Bevestig button on the page"
    return url.group(1)


def _mutate_from(client, csrf, page: str) -> tuple[set[str], set[str]]:
    html = client.get(page).text
    before = _record_ids(html)
    answer = client.post(
        _confirm_url(html),
        data={"note": ""},
        headers={
            **csrf,
            **_list_headers(html),
            "HX-Request": "true",
            "HX-Current-URL": f"http://testserver{page}",
        },
    )
    assert answer.status_code == 200, answer.text[:300]
    return before, _record_ids(answer.text)


SCOPED_PAGES = {
    "activity list": lambda w: f"/admin/betalingen?activiteit={w['a']}",
    "activity tab": lambda w: f"/admin/activiteiten/{w['a']}/betalingen",
    "family tab": lambda w: f"/admin/leden/gezin/{w['family']}/betalingen",
    "registration tab": lambda w: f"/admin/inschrijvingen/{w['anna']}/betalingen",
}


@pytest.mark.parametrize("scope", sorted(SCOPED_PAGES))
def test_a_confirmation_keeps_the_list_in_its_scope(client, db_session, world, scope):
    csrf = _login(client, db_session)

    before, after = _mutate_from(client, csrf, SCOPED_PAGES[scope](world))

    assert before, f"{scope}: the page shows no records — is the setup still right?"
    assert after == before, (
        f"{scope}: {len(before)} record(s) before the confirmation, {len(after)} after; "
        f"extra: {sorted(after - before)}"
    )


def test_without_a_scope_the_list_stays_complete(client, db_session, world):
    csrf = _login(client, db_session)

    before, after = _mutate_from(client, csrf, "/admin/betalingen")

    assert len(before) >= 3
    assert after == before


def test_the_other_mutations_keep_the_scope_too(client, db_session, world):
    """Update, edit and refund share the helper; one scoped page, all three.

    A refund adds a record of its own to this activity, so the check is the
    other way round: nothing of activity B may come back.
    """
    csrf = _login(client, db_session)
    page = f"/admin/activiteiten/{world['a']}/betalingen"
    html = client.get(page).text
    headers = {
        **csrf,
        **_list_headers(html),
        "HX-Request": "true",
        "HX-Current-URL": f"http://testserver{page}",
    }
    record = sorted(_record_ids(html))[0]

    for route, data in (
        ("bijwerken", {"amount_paid": "10.00", "note": ""}),
        ("bewerken", {"status": "paid", "amount_paid": "10.00", "note": ""}),
        ("refund", {"amount": "1.00", "note": "proef"}),
    ):
        answer = client.post(f"/admin/betalingen/{record}/{route}", data=data, headers=headers)
        assert answer.status_code == 200, (route, answer.text[:300])
        shown = _record_ids(answer.text)
        assert shown, f"{route}: the answer shows no records"
        assert not shown & world["b_records"], (
            f"{route}: the record of activity B came back — the scope was lost"
        )

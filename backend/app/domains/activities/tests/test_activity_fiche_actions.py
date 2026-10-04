"""The activity fiche: one save that ends the edit state, and cancelling as an action (#1558).

CR-11 block 6. "Geannuleerd" was a checkbox in the activity form; it is the
record action "Activiteit annuleren" in the head's menu, and "Annulering
intrekken" takes it back. A save writes the three sections and the closed last
one, returns the fiche to its read state, and never touches the cancellation.
"""

import re

import pytest

from app.domains.activities.models import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _activity(db) -> Activity:
    activity, _component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    db.commit()
    return activity


def _save(client, headers, activity, current_query="bewerken=1", **fields):
    return client.post(
        f"/admin/activiteiten/{activity.id}",
        headers={
            **headers,
            "HX-Request": "true",
            "HX-Current-URL": f"http://testserver/admin/activiteiten/{activity.id}?{current_query}",
        },
        data={"name": activity.name, **fields},
    )


def _menu(html: str) -> str:
    start = html.index("data-actions-menu")
    return html[start : html.index("</header>", start)]


# ── One save, and it ends the edit state ─────────────────────────────────────


def test_a_save_returns_the_fiche_to_read_and_says_so_in_the_address(client, db_session):
    """The page was at `?bewerken=1`; after the save the fragment is the read
    state and the address loses the flag, so a reload does not reopen the
    editor. The way back survives."""
    activity = _activity(db_session)
    headers = _login(client)
    keep = "terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer"

    r = _save(
        client, headers, activity, current_query=f"bewerken=1&{keep}", location="Parochiezaal"
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers["HX-Push-Url"] == f"/admin/activiteiten/{activity.id}?{keep}"
    assert 'data-mode="read"' in r.text and '<form id="aa-act-form"' not in r.text
    head = r.text[r.text.index('id="aa-recordkop"') :]
    assert ">Bewerken<" in head[head.index("data-head-controls") :], "the primary is back"
    assert "Parochiezaal" in r.text

    plain = _save(client, headers, activity)
    assert plain.headers["HX-Push-Url"] == f"/admin/activiteiten/{activity.id}"


def test_a_refused_save_stays_in_the_edit_state(client, db_session):
    """A slug that another activity has: the fiche stays open with the reason,
    and the address keeps its flag."""
    activity = _activity(db_session)
    other = Activity(name="Bezet", slug="bezet-1558")
    db_session.add(other)
    db_session.commit()
    headers = _login(client)

    r = _save(client, headers, activity, slug="bezet-1558")
    assert r.status_code == 200
    assert "HX-Push-Url" not in r.headers
    assert 'data-mode="edit"' in r.text and '<form id="aa-act-form"' in r.text


def test_the_switch_saves_on_and_off(client, db_session):
    activity = _activity(db_session)
    headers = _login(client)

    _save(client, headers, activity, members_only="1")
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).members_only is True
    _save(client, headers, activity)  # an unticked switch sends no key
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).members_only is False


# ── Cancelling is an action ──────────────────────────────────────────────────


def test_cancelling_and_taking_it_back_from_the_menu(client, db_session):
    activity = _activity(db_session)
    headers = _login(client)
    base = f"/admin/activiteiten/{activity.id}"

    menu = _menu(client.get(base).text)
    item = re.search(r"<button[^>]*annulering[^>]*>([^<]+)<", menu)
    assert item.group(1) == "Activiteit annuleren"
    assert "&#34;cancelled&#34;: &#34;1&#34;" in item.group(0) or '"cancelled": "1"' in item.group(
        0
    )
    assert "data-confirm=" in item.group(0), "calling an activity off asks first"
    assert "geen inschrijvingen meer" in item.group(0), "and names the consequence"

    r = client.post(f"{base}/annulering", headers=headers, data={"cancelled": "1"})
    assert r.status_code == 204 and r.headers["HX-Refresh"] == "true"
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).is_cancelled is True

    page = client.get(base).text
    assert ">Geannuleerd<" in page[page.index("data-badges") : page.index("data-head-controls")]
    back = re.search(r"<button[^>]*annulering[^>]*>([^<]+)<", _menu(page))
    assert back.group(1) == "Annulering intrekken"
    assert "data-confirm=" not in back.group(0), "taking it back needs no question"
    assert "Activiteit annuleren" not in _menu(page)

    client.post(f"{base}/annulering", headers=headers, data={"cancelled": "0"})
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).is_cancelled is False


def test_the_cancel_action_stands_after_the_state_action_and_before_the_tools(client, db_session):
    activity = _activity(db_session)
    _login(client)
    labels = re.findall(
        r'role="menuitem"[^>]*>([^<]+)<',
        _menu(client.get(f"/admin/activiteiten/{activity.id}").text),
    )
    assert (
        labels.index("Terug naar concept")
        < labels.index("Activiteit annuleren")
        < labels.index("Design Studio")
    )


def test_a_save_does_not_take_a_cancellation_back(client, db_session):
    """The checkbox is gone from the form. A save that still wrote the field
    from the (absent) key would silently un-cancel the activity.

    Proven red by putting `is_cancelled=bool(is_cancelled)` back in
    `activiteit_bijwerken`.
    """
    activity = _activity(db_session)
    headers = _login(client)
    client.post(
        f"/admin/activiteiten/{activity.id}/annulering", headers=headers, data={"cancelled": "1"}
    )

    assert _save(client, headers, activity, location="Elders").status_code == 200
    db_session.expire_all()
    saved = db_session.get(Activity, activity.id)
    assert saved.location == "Elders"
    assert saved.is_cancelled is True


def test_the_form_has_no_cancelled_field(client, db_session):
    activity = _activity(db_session)
    _login(client)
    edit = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert 'name="is_cancelled"' not in edit
    assert ">Geannuleerd<" not in edit[edit.index("data-form-flow") :].split("Datums", 1)[0]


def test_cancelling_needs_the_csrf_token_and_an_existing_activity(client, db_session):
    activity = _activity(db_session)
    headers = _login(client)
    assert (
        client.post(
            f"/admin/activiteiten/{activity.id}/annulering", data={"cancelled": "1"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/admin/activiteiten/999999/annulering", headers=headers, data={"cancelled": "1"}
        ).status_code
        == 404
    )
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).is_cancelled is False

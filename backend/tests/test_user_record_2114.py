"""A user is a record page with one save (#2114, CR-11 phase 5, track 2, round 1).

The users list is a `list_page` on the kit's table and a row opens the account's
record: the e-mail address as title, the state as a badge, the roles as a fact,
a summary beside the cards Account and the roles; editing (`?bewerken=1`) has ONE
save. The inline editing per row is gone. Rights are what they were: the services
and the gates are the same (the who-gets-in snapshot gained one line, for the new
GET, and no line moved).

"Laatst aangemeld" is left out on purpose: no datum of it exists today.
"""

import re

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, email=SEEDED_ADMIN_EMAIL):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _user(db, email, *roles):
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for code, tenant in roles:
        db.add(UserRole(user_id=user.id, role_code=code, tenant_id=tenant))
    db.commit()
    return user


def _roles_of(db, user_id):
    db.expire_all()
    return {
        (row.role_code.value, row.tenant_id)
        for row in db.query(UserRole).filter(UserRole.user_id == user_id)
    }


def test_the_list_opens_a_record_and_edits_nothing_inline(client, db_session):
    doel = _user(db_session, "doelwit-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    _login(client)
    html = client.get("/admin/gebruikers").text
    assert "data-user" in html, "the kit's table has not been read"
    link = re.search(rf'href="(/admin/gebruikers/{doel.id}[^"]*)"[^>]*data-row-link', html)
    assert link, "the row is the way in to the record"
    assert "gu-email-" not in html and 'name="role_codes"' not in html, "the inline form is gone"
    assert client.get(link.group(1)).status_code == 200


def test_the_record_reads_first_with_title_state_roles_and_a_summary(client, db_session):
    doel = _user(db_session, "lezen-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    _login(client)
    html = client.get(f"/admin/gebruikers/{doel.id}").text
    assert "<h1" in html and "lezen-2114@example.com" in html
    assert "data-summary-card" in html and "Actief" in html and "Rollen" in html
    assert 'id="gu-form"' not in html, "a record reads first"
    assert f"/admin/gebruikers/{doel.id}?bewerken=1" in html, "Bewerken"
    assert "Laatst aangemeld" not in html, "that datum does not exist today"


def test_the_editor_has_one_form_and_one_save(client, db_session):
    doel = _user(db_session, "bewerken-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    _login(client)
    html = client.get(f"/admin/gebruikers/{doel.id}?bewerken=1").text
    assert html.count('id="gu-form"') == 1
    assert html.count("data-form-save") == 1
    assert re.search(r'name="role_codes" value="ADMIN"[^>]*checked', html)


def test_changing_a_role_and_saving_changes_exactly_that_role(client, db_session):
    doel = _user(
        db_session,
        "wijzigen-2114@example.com",
        ("ADMIN", TENANT_MILLEGEM_ID),
        ("FINANCE", TENANT_VOORBEELD_ID),
    )
    csrf = _login(client)
    response = client.post(
        f"/admin/gebruikers/{doel.id}",
        data={
            "email": "wijzigen-2114@example.com",
            "is_active": "1",
            "role_codes": ["ADMIN", "FINANCE"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert _roles_of(db_session, doel.id) == {
        ("ADMIN", TENANT_MILLEGEM_ID),
        ("FINANCE", TENANT_MILLEGEM_ID),
        ("FINANCE", TENANT_VOORBEELD_ID),
    }, "the other workspace's row stays, and only the ticked roles are here"
    db_session.expire_all()
    user = db_session.get(User, doel.id)
    assert user.email == "wijzigen-2114@example.com" and user.is_active
    assert 'data-mode="read"' in response.text, "the answer is the record, read again"


def test_a_refused_save_shows_at_the_field(client, db_session):
    _user(db_session, "bezet-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    doel = _user(db_session, "ander-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    csrf = _login(client)
    response = client.post(
        f"/admin/gebruikers/{doel.id}",
        data={"email": "bezet-2114@example.com", "is_active": "1", "role_codes": ["ADMIN"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#gu-melding"
    assert "E-mailadres is al in gebruik." in response.text
    assert 'data-error-for="email"' in response.text, "the banner names the field"
    db_session.expire_all()
    assert db_session.get(User, doel.id).email == "ander-2114@example.com", "nothing was written"


def test_a_workspace_without_the_account_does_not_open_it(client, db_session):
    doel = _user(db_session, "elders-2114@example.com", ("ADMIN", TENANT_VOORBEELD_ID))
    _login(client)
    assert client.get(f"/admin/gebruikers/{doel.id}").status_code == 404


def test_deleting_from_the_record_goes_back_to_the_list(client, db_session):
    doel = _user(db_session, "weg-2114@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    csrf = _login(client)
    response = client.post(
        f"/admin/gebruikers/{doel.id}/verwijderen",
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert response.status_code == 204 and response.headers["HX-Redirect"] == "/admin/gebruikers"
    db_session.expire_all()
    assert db_session.get(User, doel.id).deleted_at is not None

"""The user record's save and delete answer in the scope its GET answers in (#2162).

Opening a user record answers only for an account the current workspace's
Gebruikers shows; another workspace's account is 404. Saving and deleting go
through the same scope — one function in the users service,
`user_of_workspace`, which the GET, `update_user` and `delete_user` call — and
answer the same 404, writing nothing.

An account with a platform-wide role is shown in a workspace, and read-only
there: the platform manages it (Koen, 19 October 2026). Its record opens without
Bewerken and Verwijderen, and a save or a delete is refused on the record with
its reason (422, the banner), writing nothing.

Proven red, additively (put back each time): `return db.query(User).filter(User.id
== user_id).first()` added at the top of `user_of_workspace` → the save and the
delete answer 200 instead of 404 (the delete after its redirect to the list);
the body of `changeable_here` replaced by `return True` → the platform-wide account's
save and delete go through and change it, and its record offers Bewerken.
"""

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.kernel.tenancy import TENANT_VOORBEELD_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "elders-2162@example.com"
PLATFORM_WIDE = "platformbreed-2162@example.com"
REFUSAL = "Dit account is platformbreed en wordt op het platform beheerd."


@pytest.fixture
def elsewhere(client, db_session):
    """An account with a role at the Voorbeeldafdeling only, and the board of
    Millegem signed in."""
    user = User(email=EMAIL, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN", tenant_id=TENANT_VOORBEELD_ID))
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return user.id, {"X-CSRF-Token": csrf_token_for(value)}


def _stored(db, user_id):
    db.expire_all()
    user = db.query(User).execution_options(include_deleted=True).filter(User.id == user_id).one()
    roles = {
        (r.role_code.value, r.tenant_id)
        for r in db.query(UserRole).filter(UserRole.user_id == user_id)
    }
    return user.email, user.is_active, user.deleted_at, roles


def test_saving_an_account_of_another_workspace_answers_404_and_writes_nothing(
    client, db_session, elsewhere
):
    user_id, headers = elsewhere
    before = _stored(db_session, user_id)
    response = client.post(
        f"/admin/gebruikers/{user_id}",
        data={"email": "anders-2162@example.com", "role_codes": ["FINANCE"]},
        headers=headers,
    )
    assert response.status_code == 404
    assert _stored(db_session, user_id) == before


def test_deleting_an_account_of_another_workspace_answers_404_and_writes_nothing(
    client, db_session, elsewhere
):
    user_id, headers = elsewhere
    before = _stored(db_session, user_id)
    response = client.post(f"/admin/gebruikers/{user_id}/verwijderen", headers=headers)
    assert response.status_code == 404
    assert _stored(db_session, user_id) == before


@pytest.fixture
def platform_wide(client, db_session):
    """An account with the platform-wide role only, and the board of Millegem
    signed in."""
    user = User(email=PLATFORM_WIDE, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR", tenant_id=None))
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return user.id, {"X-CSRF-Token": csrf_token_for(value)}


def test_a_platform_wide_account_opens_read_only_in_a_workspace(client, platform_wide):
    user_id, _headers = platform_wide
    response = client.get(f"/admin/gebruikers/{user_id}")
    assert response.status_code == 200 and PLATFORM_WIDE in response.text
    assert f"/admin/gebruikers/{user_id}?bewerken=1" not in response.text, "no Bewerken"
    assert f"/admin/gebruikers/{user_id}/verwijderen" not in response.text, "no Verwijderen"


def test_saving_a_platform_wide_account_in_a_workspace_is_refused_and_writes_nothing(
    client, db_session, platform_wide
):
    user_id, headers = platform_wide
    before = _stored(db_session, user_id)
    response = client.post(
        f"/admin/gebruikers/{user_id}",
        data={"email": "anders-2162@example.com", "role_codes": ["FINANCE"]},
        headers=headers,
    )
    assert response.status_code == 422
    assert REFUSAL in response.text
    assert _stored(db_session, user_id) == before


def test_deleting_a_platform_wide_account_in_a_workspace_is_refused_and_writes_nothing(
    client, db_session, platform_wide
):
    user_id, headers = platform_wide
    before = _stored(db_session, user_id)
    response = client.post(f"/admin/gebruikers/{user_id}/verwijderen", headers=headers)
    assert response.status_code == 422
    assert REFUSAL in response.text
    assert _stored(db_session, user_id) == before

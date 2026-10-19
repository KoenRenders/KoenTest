"""The user record's save and delete answer in the scope its GET answers in (#2162).

Opening a user record answers only for an account the current workspace's
Gebruikers shows; another workspace's account is 404. Saving and deleting go
through the same scope — one function in the users service,
`user_of_workspace`, which the GET, `update_user` and `delete_user` call — and
answer the same 404, writing nothing.

Proven red, additively (put back): `return db.query(User).filter(User.id ==
user_id).first()` added at the top of `user_of_workspace` → the save and the
delete answer 200 instead of 404 (the delete after its redirect to the list).
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

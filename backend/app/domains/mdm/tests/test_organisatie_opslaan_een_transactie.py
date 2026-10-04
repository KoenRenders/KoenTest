"""#1244 — the organisation form is saved in one transaction, and it lasts.

`update_organization_details` committed, `update_organization_address` only
flushed, and `get_db` commits nothing: closing a session rolls back what is still
open. So an address typed on `/admin/organisaties/<id>` was gone after the request,
while the screen — rendered from that same session — showed it as saved. And a
refused address came after a committed name: half a form saved.

**Why the existing tests did not see it.** They share `db_session` with the
request, and inside one session a flushed row is visible. That is the second
cause of #1223, again. So these tests do what production does: the route gets
its own `SessionLocal()`, closed at the end of the request like `get_db` closes
it, and the test reads back through a **second, fresh session**. Only what the
request committed can be seen there. Because these writes are real commits, the
tests put back what they changed (name, address, the operator role and the
postal code) when they finish.

Broken on purpose to check that these tests can go red: the `db.commit()` at the
end of `save_organization` removed → the address test and the removal test fall
over. And against the route as it was on v2.6.0 (the two functions called one
after the other) all three are red — the half-save test too, because the name
was committed before the address was refused.
"""

import pytest
from sqlalchemy import text

from app.database import SessionLocal, get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.main import app

pytestmark = pytest.mark.ui_serverrendered

ACCOUNT_ID = 1  # the legal entity; any organisation with an editor will do
EMAIL = "operator-1244@example.org"
POSTCODE = "9999"


def _sql(statement: str, **params):
    """One statement in its own session, committed — the tests' own writes."""
    db = SessionLocal()
    try:
        result = db.execute(text(statement), params)
        rows = result.fetchall() if result.returns_rows else None
        db.commit()
        return rows
    finally:
        db.close()


@pytest.fixture
def real_request(client, platform_workspace):
    """The route runs on a session of its own, closed after the request."""

    def _own_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.domains.auth.api import User, UserRole
    from app.domains.mdm.api import PostalCode

    name_before = _sql("SELECT name FROM mdm.organizations WHERE id = :o", o=ACCOUNT_ID)[0][0]
    own = SessionLocal()
    try:
        user = User(email=EMAIL, is_active=True)
        own.add(user)
        own.flush()
        own.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        own.add(PostalCode(postal_code=POSTCODE, municipality="Proef"))
        own.commit()
    finally:
        own.close()
    app.dependency_overrides[get_db] = _own_session
    session = make_session_value(EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    try:
        yield client, csrf_token_for(session)
    finally:
        _sql("DELETE FROM mdm.addresses WHERE organization_id = :o", o=ACCOUNT_ID)
        _sql("UPDATE mdm.organizations SET name = :n WHERE id = :o", n=name_before, o=ACCOUNT_ID)
        _sql("DELETE FROM mdm.postal_codes WHERE postal_code = :p", p=POSTCODE)
        _sql(
            "DELETE FROM auth.user_roles WHERE user_id IN "
            "(SELECT id FROM auth.users WHERE email = :e)",
            e=EMAIL,
        )
        _sql("DELETE FROM auth.users WHERE email = :e", e=EMAIL)


def _post(real_request, **fields):
    client, csrf = real_request
    return client.post(
        f"/admin/organisaties/{ACCOUNT_ID}", data=fields, headers={"X-CSRF-Token": csrf}
    )


def _address():
    rows = _sql(
        "SELECT street, house_number FROM mdm.addresses "
        "WHERE organization_id = :o AND deleted_at IS NULL",
        o=ACCOUNT_ID,
    )
    return tuple(rows[0]) if rows else None


def _name() -> str:
    return _sql("SELECT name FROM mdm.organizations WHERE id = :o", o=ACCOUNT_ID)[0][0]


def test_an_address_outlives_the_request(real_request):
    resp = _post(
        real_request, name="Raak", street="Kerkstraat", house_number="7", postal_code=POSTCODE
    )

    assert resp.status_code == 200, resp.text[:300]
    assert _address() == ("Kerkstraat", "7"), (
        "the address was not committed: it is gone once the request's session closes"
    )


def test_removing_an_address_outlives_the_request(real_request):
    _sql(
        "INSERT INTO mdm.addresses (organization_id, tenant_id, street, house_number, "
        "postal_code_id, created_at, updated_at) SELECT :o, :o, 'Kerkstraat', '7', id, now(), now() "
        "FROM mdm.postal_codes WHERE postal_code = :p",
        o=ACCOUNT_ID,
        p=POSTCODE,
    )
    assert _address() is not None, "precondition: there is an address"

    resp = _post(real_request, name="Raak", street="", house_number="", postal_code="")

    assert resp.status_code == 200, resp.text[:300]
    assert _address() is None, "the removed address came back"


def test_a_refused_address_leaves_nothing_of_the_form(real_request):
    """The name changes, the address is refused (no house number): neither stays."""
    before = _name()

    resp = _post(
        real_request, name="Nieuwe naam", street="Kerkstraat", house_number="", postal_code=POSTCODE
    )

    # #1515: the refusal keeps its 422, and carries its banner — the shells swap
    # an HTML 422 since then, so this is what reaches the screen.
    assert resp.status_code == 422
    assert 'role="alert"' in resp.text and "Huisnummer" in resp.text, "the refusal is not shown"
    assert _name() == before, "the name was saved although the form was refused"
    assert _address() is None

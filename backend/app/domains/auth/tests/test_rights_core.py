"""CR-24 (#1722), slice 3: the core in auth — rights, the roles that bundle
them, and the gate that fails closed. Nothing in the application asks a right
yet; these tests are what holds the core until the gates switch over.

**The bundles** are rows, written by the migration. `B1` below is the table of
CR-24 §B1, written out once more as the expectation: the migration is history,
this is the rule. A bundle that changes takes a new migration and a changed
row here.

**The gate** runs behind a route of its own, in a small application on the
test's database session, so every refusal is read off a real request.

Red proofs, one edit each in the code under test, put back afterwards:

| Broken | Red |
|---|---|
| `require_right`: `right not in held` → `held and right not in held` | the empty bundle and the address without a role |
| `require_right`: the 403 taken out | every refusal of a role, the unheld right included |
| `rights_of`: the workspace filter taken out | the role held in another workspace (T2), on the set and on the gate |
| `rights_of`: `User.is_active` taken out | the inactive user |
| the migration: `payment.manage` given to ADMIN | the bundles against B1 |
| the migration: `workbench.use` taken from FINANCE | the bundles against B1 |
| `Role`: MASTERDATA taken out of the enum | a user with MASTERDATA read back (T10) |
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    Role,
    RoleRight,
    User,
    UserRole,
    get_user_roles,
    make_session_value,
    may,
    require_right,
    rights_of,
)
from app.kernel.codes import code_label, code_labels, reset_label_cache
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID, current_tenant_id

#: CR-24 §B1: per right, the roles whose bundle holds it. A changing right
#: brings its viewing right to the same roles (D1) — `_expected` adds those.
B1 = {
    "activity.manage": "ADMIN OPERATOR",
    "form.manage": "ADMIN OPERATOR",
    "page.manage": "ADMIN OPERATOR",
    "media.manage": "ADMIN OPERATOR",
    "design.manage": "ADMIN OPERATOR",
    "newsletter.manage": "ADMIN OPERATOR",
    "meeting.manage": "ADMIN OPERATOR",
    "report.manage": "ADMIN OPERATOR",
    "assistant.use": "ADMIN OPERATOR",
    "party.masterdata": "ADMIN OPERATOR MASTERDATA",
    "product.masterdata": "OPERATOR MASTERDATA",
    "price.manage": "OPERATOR PRICING",
    "sales.manage": "OPERATOR SALES",
    "stock.manage": "OPERATOR STOCK",
    "payment.view": "ADMIN FINANCE OPERATOR",
    "payment.manage": "FINANCE OPERATOR",
    "workbench.use": "ADMIN FINANCE OPERATOR MASTERDATA PRICING SALES STOCK",
    "user.manage": "ADMIN OPERATOR",
    "settings.manage": "ADMIN OPERATOR",
    "platform.manage": "OPERATOR",
}


def _expected() -> set[tuple[str, str]]:
    pairs = set()
    for right, roles in B1.items():
        obj, action = right.split(".")
        for role in roles.split():
            pairs.add((role, right))
            if action in ("manage", "masterdata"):
                pairs.add((role, f"{obj}.view"))
    return pairs


@pytest.fixture(autouse=True)
def _fresh_labels():
    reset_label_cache()
    yield
    reset_label_cache()


def _user(db, email: str, *roles: tuple[str, int | None], active: bool = True) -> str:
    user = User(email=email, is_active=active)
    db.add(user)
    db.flush()
    for code, tenant in roles:
        db.add(UserRole(user_id=user.id, role_code=code, tenant_id=tenant))
    db.commit()
    return email


def _only(db, role: str, tenant: int | None = TENANT_MILLEGEM_ID) -> str:
    return _user(db, f"{role.lower()}-1722@example.com", (role, tenant))


# ── The bundles ──────────────────────────────────────────────────────────────


def test_the_bundles_are_the_table_of_the_change_request(db_session):
    rows = {
        (role, right)
        for role, right in db_session.execute(
            text("SELECT role_code, right_code FROM auth.role_rights")
        )
    }
    expected = _expected()
    assert len(rows) > 70, f"only {len(rows)} rows: the bundles were not written"
    assert rows - expected == set(), f"held and not in B1: {sorted(rows - expected)}"
    assert expected - rows == set(), f"in B1 and not held: {sorted(expected - rows)}"


def test_every_right_is_in_a_bundle_and_the_operator_holds_them_all(db_session):
    """C4.2: a right that no bundle holds would refuse everyone. For a member
    of `Right` that cannot be: the operator's bundle is the whole list."""
    operator = {
        row.right_code for row in db_session.query(RoleRight).filter_by(role_code=Role.OPERATOR)
    }
    assert operator == set(Right)
    assert len(Right) == 36


def test_money_is_changed_by_fewer_than_see_it(db_session):
    """#83, kept as two rights: the board sees payments and does not confirm them."""
    admin = _only(db_session, "ADMIN")
    assert Right.PAYMENT_VIEW in rights_of(db_session, admin)
    assert Right.PAYMENT_MANAGE not in rights_of(db_session, admin)


def test_a_role_without_a_bundle_holds_nothing(db_session):
    """ACCOUNT_ADMIN keeps an empty bundle (R11), like the two retired codes."""
    for role in ("ACCOUNT_ADMIN", "MEMBER", "USER"):
        assert rights_of(db_session, _only(db_session, role)) == set()


# ── T3: the roles ────────────────────────────────────────────────────────────


def test_the_role_set_is_the_eight_codes_and_finance_reads_boekhouding(db_session):
    labels = dict(code_labels("role", language="nl", db=db_session))
    assert labels == {
        "ADMIN": "Beheerder",
        "FINANCE": "Boekhouding",
        "OPERATOR": "Platformbeheerder",
        "ACCOUNT_ADMIN": "Accountbeheerder",
        "MASTERDATA": "Masterdata",
        "PRICING": "Prijsbeheer",
        "SALES": "Verkoop",
        "STOCK": "Voorraadbeheer",
    }
    assert list(labels)[4:] == ["MASTERDATA", "PRICING", "SALES", "STOCK"], "after today's four"
    assert code_label("role", "FINANCE", language="en", db=db_session) == "Accounting"


def test_every_right_has_its_word_in_both_languages(db_session):
    for language in ("nl", "en"):
        labels = dict(code_labels("right", language=language, db=db_session))
        assert set(labels) == {right.value for right in Right}
        assert all(label and label != code for code, label in labels.items()), labels


# ── T10: the enum knows what the migration wrote ─────────────────────────────


def test_a_user_with_masterdata_is_read_back(db_session):
    """F9: a stored role code that is no member of `Role` raises on read, so
    the four members and the four rows arrive in one change."""
    email = _only(db_session, "MASTERDATA")
    db_session.expire_all()

    row = db_session.query(UserRole).join(User).filter(User.email == email).one()
    assert row.role_code is Role.MASTERDATA
    assert get_user_roles(db_session, email) == {"MASTERDATA"}
    assert rights_of(db_session, email) == {
        Right.PARTY_VIEW,
        Right.PARTY_MASTERDATA,
        Right.PRODUCT_VIEW,
        Right.PRODUCT_MASTERDATA,
        Right.WORKBENCH_USE,
    }


@pytest.mark.parametrize("role", ["PRICING", "SALES", "STOCK"])
def test_a_shop_role_holds_its_own_object_and_the_workbench(db_session, role):
    obj = {"PRICING": "price", "SALES": "sales", "STOCK": "stock"}[role]
    assert {right.value for right in rights_of(db_session, _only(db_session, role))} == {
        f"{obj}.view",
        f"{obj}.manage",
        "workbench.use",
    }


# ── T2: rights are held per workspace ────────────────────────────────────────


def _in(tenant: int, question):
    token = current_tenant_id.set(tenant)
    try:
        return question()
    finally:
        current_tenant_id.reset(token)


def test_a_right_in_one_workspace_is_no_right_in_another(db_session):
    email = _only(db_session, "MASTERDATA", TENANT_MILLEGEM_ID)

    assert Right.PARTY_MASTERDATA in _in(TENANT_MILLEGEM_ID, lambda: rights_of(db_session, email))
    assert _in(TENANT_VOORBEELD_ID, lambda: rights_of(db_session, email)) == set()
    assert _in(TENANT_VOORBEELD_ID, lambda: may(db_session, email, Right.WORKBENCH_USE)) is False


def test_the_platform_wide_role_holds_its_rights_in_every_workspace(db_session):
    email = _only(db_session, "OPERATOR", None)
    for tenant in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        assert _in(tenant, lambda: rights_of(db_session, email)) == set(Right)


def test_two_roles_hold_the_rights_of_both(db_session):
    email = _user(
        db_session,
        "two-roles-1722@example.com",
        ("FINANCE", TENANT_MILLEGEM_ID),
        ("SALES", TENANT_MILLEGEM_ID),
    )
    held = rights_of(db_session, email)
    assert {Right.PAYMENT_MANAGE, Right.SALES_MANAGE} <= held
    assert Right.ACTIVITY_VIEW not in held


def test_an_inactive_user_holds_nothing(db_session):
    email = _user(
        db_session, "inactive-1722@example.com", ("ADMIN", TENANT_MILLEGEM_ID), active=False
    )
    assert rights_of(db_session, email) == set()
    assert may(db_session, email, Right.ACTIVITY_VIEW) is False


# ── C4.2: the gate fails closed ──────────────────────────────────────────────


@pytest.fixture
def gated(db_session):
    """A route behind `require_right`, on the test's session. Requests land in
    the default workspace, Raak Millegem."""
    application = FastAPI()
    application.dependency_overrides[get_db] = lambda: db_session

    @application.get("/gated")
    @application.post("/gated")
    def gated_route(email: str = Depends(require_right(Right.ACTIVITY_MANAGE))):
        return {"email": email}

    @application.get("/workbench")
    def workbench(email: str = Depends(require_right(Right.WORKBENCH_USE))):
        return {"email": email}

    with TestClient(application, follow_redirects=False) as client:
        yield client


def _as(client, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_who_holds_the_right_is_let_in_and_named(gated, db_session):
    email = _only(db_session, "ADMIN")
    _as(gated, email)

    answer = gated.get("/gated")

    assert answer.status_code == 200
    assert answer.json() == {"email": email}
    assert gated.post("/gated").status_code == 200


def test_without_a_session_a_page_goes_to_the_sign_in_and_comes_back(gated):
    """#1458, unchanged: a plain GET is sent to the sign-in with the page it
    asked for; an htmx request and every other method get the 401."""
    page = gated.get("/gated?x=1")
    assert page.status_code == 303
    assert page.headers["location"] == "/aanmelden?terug=/gated%3Fx%3D1"

    assert gated.get("/gated", headers={"HX-Request": "true"}).status_code == 401
    assert gated.post("/gated").status_code == 401


def test_a_session_of_an_address_without_an_account_is_refused(gated):
    _as(gated, "nobody-1722@example.com")
    assert gated.get("/gated").status_code == 403


@pytest.mark.parametrize("role", ["FINANCE", "MASTERDATA", "SALES", "ACCOUNT_ADMIN"])
def test_a_role_whose_bundle_lacks_the_right_is_refused(gated, db_session, role):
    _as(gated, _only(db_session, role))

    answer = gated.get("/gated")

    assert answer.status_code == 403
    assert answer.json() == {"detail": "Geen toegang"}, "the refusal names no right and no role"
    assert gated.post("/gated").status_code == 403


def test_an_empty_bundle_opens_nothing_at_all(gated, db_session):
    _as(gated, _only(db_session, "ACCOUNT_ADMIN"))
    assert gated.get("/workbench").status_code == 403


def test_a_role_in_another_workspace_is_refused(gated, db_session):
    _as(gated, _only(db_session, "ADMIN", TENANT_VOORBEELD_ID))
    assert gated.get("/gated").status_code == 403


def test_an_inactive_user_is_refused(gated, db_session):
    _as(gated, _user(db_session, "left-1722@example.com", ("ADMIN", None), active=False))
    assert gated.get("/gated").status_code == 403


def test_a_right_that_no_bundle_holds_refuses_everyone(gated, db_session):
    """The gate admits by one condition and has no default: take the right out
    of every bundle and the operator is refused like anyone."""
    email = _only(db_session, "OPERATOR", None)
    _as(gated, email)
    assert gated.get("/gated").status_code == 200

    gone = db_session.execute(
        text("DELETE FROM auth.role_rights WHERE right_code = 'activity.manage'")
    ).rowcount
    db_session.commit()

    assert gone == 2, "ADMIN and OPERATOR held it"
    assert gated.get("/gated").status_code == 403
    assert may(db_session, email, Right.ACTIVITY_MANAGE) is False


@pytest.mark.parametrize("asked", ["activity.manage", "ADMIN", Role.ADMIN, None])
def test_a_gate_on_something_that_is_no_right_is_refused_when_declared(asked):
    """Not at the first request: a route cannot be declared behind it."""
    with pytest.raises(TypeError, match="member of Right"):
        require_right(asked)

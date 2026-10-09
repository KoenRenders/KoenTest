"""CR-24 C4.1 (F1, T1) — who gets in, per route, recorded before a gate is touched.

CR-24 makes every gate ask for a right where it asks for a role today, and
promises that nobody's reach changes (R7). This is the list that promise is held
against: the running app with every module on, **every route** asked once per
user holding **exactly one role** — ADMIN, FINANCE, OPERATOR, ACCOUNT_ADMIN, or
none — in a tenant's workspace and in the platform's, and per route who was let
in. The outcome is `snapshots/who_gets_in.json`, taken on master `d68dbc21`
before any gate moved; the test asks again and wants the same list.

**Asked of the running routes, not read from the dependencies.** When the list
was taken, twenty-two routes kept their real gate in the body, behind a wider
one in the signature (`require_finance_mutation`, `require_platform_operator_ui`,
`_require_admin`); a walk over the dependencies would have recorded the wider
gate for them. They are dependencies since slice 2 (C2), and the list did not
move by a line: that is the proof that the move changed nobody's reach.

**Let in** is every answer but 401 and 403. That is on purpose:

- a 422 is let in — FastAPI solves the dependencies, and so the gate, before it
  validates the body (`test_the_gate_answers_before_the_body_is_judged`), so a
  request without a body still shows who passes;
- a 404 is let in — path parameters are filled with `1`, and most rows do not
  exist. Nothing is lost by that: no route looks a row up before it asks who is
  there (each of the twenty-two gates in a body was its first statement). It also
  means the platform's screens read "let in" for an operator in a tenant's
  workspace, where they answer 404 to who passes the first gate; that condition
  has a test of its own (T9).

Each user signs in and sends the CSRF token of his own session with every
request: `require_csrf` stands on the decorator and answers 403 before the gate,
so without it every change would read "refused" for everyone. Each request runs
in a savepoint that is rolled back, so one user's DELETE is no 404 for the next.

**The questions beside the gates** (F6) are in the same file: what a screen asks
to show or hide a way in — may this user see payments, change them, use the
assistant, enter the back office, and where — per user and workspace.

Recording again is a decision, never a repair:

    SNAPSHOT_UPDATE=1 pytest app/domains/auth/tests/test_who_gets_in_unchanged_1722.py

A new route adds its line; a line that changes for a route that already existed
is somebody's reach changing, and CR-24 names the only one it allows (the
workbench for FINANCE, Q11).

Proven red (9 October 2026), each additively and removed again:
- `"FINANCE"` added to `_GENERAL_ADMIN_ROLES` → the routes red with 465
  differences, each "ADMIN OPERATOR → ADMIN FINANCE OPERATOR" (the platform's
  screens "OPERATOR → …" stay as they are), and the questions red too;
- `"ADMIN"` added to `_PAYMENTS_MUTATE_ROLES` — the set a gate **in a body**
  asks → 14 differences, the seven routes that change a payment in both
  workspaces, "FINANCE OPERATOR → ADMIN FINANCE OPERATOR", and the question
  "may change payments";
- a new route `GET /admin/zz-proef` without a gate → red: "not in the
  snapshot — a new route records its line".
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine, get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    admits_admin_ui,
    back_office_home,
    csrf_token_for,
    get_user_roles,
    make_session_value,
    may_mutate_payments,
    may_use_admin_assistant,
    may_view_payments,
)
from app.kernel.tenancy import current_tenant_id
from app.main import app

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "who_gets_in.json"

#: One user per role, and one with a login and no role at all.
USERS = ("ADMIN", "FINANCE", "OPERATOR", "ACCOUNT_ADMIN", "none")

REFUSED = (401, 403)

#: The routes that refuse all five users, and why that is no role: for these the
#: list shows nothing of a gate, and the reason is written here instead.
NOBODY = {
    "GET /login/verify": "public — the sign-in link's own token is missing",
    "POST /leden/gezin": "the member's own household: none of the five is a member",
    "POST /leden/gezin/vernieuwen": "the same, for a renewal",
    "GET /admin/rapporten/raakje/paneel": (
        "behind `require_admin_ui`, then 403 because the assistant's switches are off in a "
        "test; its role half is the question 'may use the assistant' below"
    ),
}


def every_route() -> list[tuple[str, str]]:
    """(method, path as declared) of every HTTP route the app serves. A websocket
    has no method and is not asked: `/stt/voxtral` checks its own session."""
    found: set[tuple[str, str]] = set()

    def walk(items, prefix: str = "") -> None:
        for item in items:
            context = getattr(item, "include_context", None)
            if context is not None:
                walk(item.original_router.routes, prefix + (context.prefix or ""))
            elif getattr(item, "endpoint", None) is not None:
                for method in sorted(
                    (getattr(item, "methods", None) or set()) - {"HEAD", "OPTIONS"}
                ):
                    found.add((method, prefix + item.path))

    walk(app.routes)
    assert len(found) >= 300, f"the walk found only {len(found)} routes — is it still looking?"
    return sorted(found, key=lambda route: (route[1], route[0]))


def _email(role: str) -> str:
    return f"only-{role.lower().replace('_', '-')}@example.com"


@pytest.fixture
def world(every_module_on, _migrate_schema):
    """The five users, each holding his one role in both workspaces, on a
    connection whose work is rolled back. OPERATOR is the platform-wide row
    (no tenant), as it is only ever assigned."""
    connection = engine.connect()
    outer = connection.begin()
    db = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    for role in USERS:
        user = User(email=_email(role), is_active=True)
        db.add(user)
        db.flush()
        if role == "OPERATOR":
            db.add(UserRole(user_id=user.id, role_code=role, tenant_id=None))
        elif role != "none":
            for tenant_id, _headers in every_module_on.values():
                db.add(UserRole(user_id=user.id, role_code=role, tenant_id=tenant_id))
    db.commit()
    db.close()
    yield connection, every_module_on
    outer.rollback()
    connection.close()
    app.dependency_overrides.clear()


def _ask(client, connection, method: str, path: str, headers: dict) -> int:
    """One request in a savepoint of its own, rolled back whatever it did."""
    savepoint = connection.begin_nested()
    db = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")

    def _this_session():
        yield db

    app.dependency_overrides[get_db] = _this_session
    client.cookies.clear()
    try:
        return client.request(method, path, headers=headers).status_code
    finally:
        db.close()
        savepoint.rollback()


def _who(admitted: list[str]) -> str:
    if len(admitted) == len(USERS):
        return "everyone"
    return " ".join(admitted) or "nobody"


def who_gets_in(world, *, csrf: bool = True) -> dict[str, dict[str, str]]:
    connection, workspaces = world
    sessions = {role: make_session_value(_email(role)) for role in USERS}
    out: dict[str, dict[str, str]] = {}
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
        for method, path in every_route():
            route = f"{method} {path}"
            address = re.sub(r"\{[^}]+\}", "1", path)
            out[route] = {}
            for workspace, (_tenant_id, host) in workspaces.items():
                admitted = []
                for role in USERS:
                    headers = {"cookie": f"{SESSION_COOKIE}={sessions[role]}", **host}
                    if csrf:
                        headers["x-csrf-token"] = csrf_token_for(sessions[role])
                    status = _ask(client, connection, method, address, headers)
                    if status not in REFUSED:
                        admitted.append(role)
                out[route][workspace] = _who(admitted)
    return out


def the_questions(world) -> dict[str, dict[str, str]]:
    """What the screens ask beside the gates (F6), per workspace: who gets "yes",
    and for the way into the back office, who is sent where."""
    connection, workspaces = world
    db = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    asked = {
        "may see payments": may_view_payments,
        "may change payments": may_mutate_payments,
        "may use the assistant": may_use_admin_assistant,
        "enters the back office": lambda db, email: admits_admin_ui(get_user_roles(db, email)),
    }
    out: dict[str, dict[str, str]] = {name: {} for name in asked}
    out["way into the back office"] = {}
    try:
        for workspace, (tenant_id, _headers) in workspaces.items():
            token = current_tenant_id.set(tenant_id)
            try:
                for name, question in asked.items():
                    out[name][workspace] = _who([r for r in USERS if question(db, _email(r))])
                out["way into the back office"][workspace] = " · ".join(
                    f"{r}: {back_office_home(get_user_roles(db, _email(r))) or '—'}" for r in USERS
                )
            finally:
                current_tenant_id.reset(token)
    finally:
        db.close()
    return out


def _differences(want: dict, got: dict) -> list[str]:
    lines = []
    for key in sorted(set(want) | set(got)):
        if key not in want:
            lines.append(f"{key}: not in the snapshot — a new route records its line")
        elif key not in got:
            lines.append(f"{key}: in the snapshot, no longer asked")
        else:
            for workspace in sorted(set(want[key]) | set(got[key])):
                before, now = want[key].get(workspace), got[key].get(workspace)
                if before != now:
                    lines.append(f"{key} [{workspace}]: {before} → {now}")
    return lines


def _compare(part: str, got: dict) -> None:
    recorded = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {}
    if os.environ.get("SNAPSHOT_UPDATE") == "1":
        recorded[part] = got
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(
            json.dumps(recorded, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        )
    assert part in recorded, f"no snapshot of the {part}; record it before a gate is touched"
    differences = _differences(recorded[part], got)
    assert not differences, (
        f"who gets in changed — {len(differences)} differences in the {part} (CR-24 R7: "
        "nobody's reach changes):\n" + "\n".join(differences)
    )


def test_every_route_lets_in_who_it_let_in_before(world):
    _compare("routes", who_gets_in(world))


def test_the_questions_beside_the_gates_answer_as_before(world):
    _compare("questions", the_questions(world))


def test_the_list_tells_users_apart():
    """The snapshot is no list of "everyone": it holds the routes only the board
    and the operator open, the ones Boekhouding opens too, the ones it alone may
    change, and the platform's — so a walk that stopped signing in, or a gate that
    answers before the role is asked, cannot record itself as unchanged."""
    routes = json.loads(SNAPSHOT.read_text())["routes"]
    assert len(routes) >= 300, len(routes)
    kinds: dict[str, int] = {}
    for outcome in routes.values():
        kinds[outcome["tenant"]] = kinds.get(outcome["tenant"], 0) + 1
    assert kinds.get("ADMIN OPERATOR", 0) >= 200, kinds
    assert kinds.get("ADMIN FINANCE OPERATOR", 0) >= 7, kinds
    assert kinds.get("FINANCE OPERATOR", 0) >= 7, kinds
    assert kinds.get("everyone", 0) >= 30, kinds
    changes = [o["tenant"] for route, o in routes.items() if not route.startswith("GET ")]
    assert changes.count("ADMIN OPERATOR") >= 100, "the changing routes do not tell users apart"
    platform_only = [r for r, o in routes.items() if o["platform"] == "OPERATOR"]
    assert len(platform_only) >= 11, platform_only
    assert routes["GET /admin/tenants"]["tenant"] == "ADMIN OPERATOR"
    nobody = {r for r, o in routes.items() if "nobody" in o.values()}
    assert nobody == set(NOBODY), (
        "a route that refuses everyone shows nothing of its gate — name why in NOBODY: "
        f"{sorted(nobody ^ set(NOBODY))}"
    )


@pytest.mark.parametrize(
    ("route", "answers"),
    [
        # `title` is required; the gate was always in the signature.
        ("/admin/formulieren", {"none": 403, "ADMIN": 422, "FINANCE": 403}),
        # `status` is required; its narrower gate stood in the body until slice 2,
        # and a request without the field then answered 422 to ADMIN, who may not
        # change a payment. The one failure path CR-24 B6 names as changing.
        ("/admin/betalingen/1/status", {"none": 403, "ADMIN": 403, "FINANCE": 422}),
    ],
)
def test_the_gate_answers_before_the_body_is_judged(world, route, answers):
    """Why a 422 counts as let in: on a route with a required field, a request
    without it is refused 403 for who lacks the role and 422 for who holds it —
    the dependencies, and so the gate, are solved before the body is validated.

    Proven red: `Depends(require_finance_mutation)` put back to
    `Depends(require_finance_ui)` on `betaling_status`, without the line in its
    body → the second case red (ADMIN 422), and the list red on that route."""
    connection, _workspaces = world
    got = {}
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
        for role in answers:
            session = make_session_value(_email(role))
            headers = {
                "cookie": f"{SESSION_COOKIE}={session}",
                "x-csrf-token": csrf_token_for(session),
            }
            got[role] = _ask(client, connection, "POST", route, headers)
    assert got == answers, got


@pytest.mark.parametrize("screen", ["/admin/tenants", "/admin/organisaties"])
def test_a_platform_screen_answers_as_before_in_each_workspace(world, screen):
    """What the list above cannot see, because a 404 counts as let in: in a
    tenant's workspace a platform screen does not exist — 404 for who passes the
    back office's gate, the operator included — and whoever does not pass that
    gate is refused first, 403. On the platform it opens for the operator alone.
    The order is the one the routes had with the platform check in their body
    (#1535); `require_platform_operator_ui` stands on `require_admin_ui` to keep
    it.

    Proven red: `is_platform_workspace` made to answer True in
    `require_platform_operator_ui` → the tenant's column reads 403, 403, 200."""
    connection, workspaces = world
    got = {}
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
        for workspace, (_tenant_id, host) in workspaces.items():
            for role in ("FINANCE", "ADMIN", "OPERATOR"):
                session = make_session_value(_email(role))
                headers = {"cookie": f"{SESSION_COOKIE}={session}", **host}
                got[workspace, role] = _ask(client, connection, "GET", screen, headers)
    assert got == {
        ("tenant", "FINANCE"): 403,
        ("tenant", "ADMIN"): 404,
        ("tenant", "OPERATOR"): 404,
        ("platform", "FINANCE"): 403,
        ("platform", "ADMIN"): 403,
        ("platform", "OPERATOR"): 200,
    }, got

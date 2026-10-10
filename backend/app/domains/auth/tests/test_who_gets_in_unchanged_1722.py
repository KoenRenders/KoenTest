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

**Recorded again once, for eleven lines** (slice 4, group c): the platform's
routes in a tenant's workspace read "ADMIN OPERATOR" and read "OPERATOR" now.
Nobody's reach changed: an ADMIN got a 404 there — he passed the back office's
gate and found no such page — and gets a 403, on an address his menu does not
show, because the gate asks the platform's right first and the workspace after
(`require_platform_right`).

**And once more, for sixteen lines and two questions** (slice 5) — the
difference CR-24 names (Q11) and Koen's answer of 9 October 2026 on the shell
around it: Boekhouding opens the workbench. Eight routes, in both workspaces,
read "ADMIN OPERATOR" and read "ADMIN FINANCE OPERATOR" now — the four of the
workbench, and the account menu, the profile and the two of switching
workspace. The start page `/admin` did not move: it asks `report.view`. The
way into the back office is one address, the workbench, for all three (Q13);
and the question "enters the back office" is gone with the role set that
answered it — whoever has a way in, enters.

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
from sqlalchemy import text as sql

from app.database import SessionLocal, engine, get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    User,
    UserRole,
    back_office_home,
    csrf_token_for,
    make_session_value,
    may,
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
        "may see payments": lambda db, email: may(db, email, Right.PAYMENT_VIEW),
        "may change payments": lambda db, email: may(db, email, Right.PAYMENT_MANAGE),
        "may use the assistant": lambda db, email: may(db, email, Right.ASSISTANT_USE),
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
                    f"{r}: {back_office_home(db, _email(r)) or '—'}" for r in USERS
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
    assert routes["GET /admin/tenants"] == {"platform": "OPERATOR", "tenant": "OPERATOR"}
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
def test_a_platform_screen_asks_the_right_and_then_the_workspace(world, screen):
    """What the list above cannot see, because a 404 counts as let in (CR-24 F8,
    T9): on the platform a platform screen opens for who holds its right, the
    operator alone; in a tenant's workspace it does not exist, also for him —
    404 — and whoever lacks the right is refused before that, 403.

    Until slice 4 an ADMIN got the 404 in a tenant's workspace: the first gate
    was the back office's, by role. The named difference of group (c).

    Proven red: the workspace check taken out of `require_platform_right` →
    the operator opens the screen in a tenant's workspace, 200."""
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
        ("tenant", "ADMIN"): 403,
        ("tenant", "OPERATOR"): 404,
        ("platform", "FINANCE"): 403,
        ("platform", "ADMIN"): 403,
        ("platform", "OPERATOR"): 200,
    }, got


#: The screens whose routes ask a right (CR-24 slice 4), by the start of their
#: address, with the right that opens them and the right that changes them. The
#: longest start that fits is the screen. It grows with each group of slice 4;
#: when no role-named gate is left, it is every gated screen.
ON_A_RIGHT = {
    "/admin/paginas": ("page.view", "page.manage"),
    "/admin/media": ("media.view", "media.manage"),
    "/admin/ontwerpen": ("design.view", "design.manage"),
    "/admin/nieuwsbrieven": ("newsletter.view", "newsletter.manage"),
    "/admin/vergaderingen": ("meeting.view", "meeting.manage"),
    "/admin/formulieren": ("form.view", "form.manage"),
    "/admin/activiteiten": ("activity.view", "activity.manage"),
    "/admin/inschrijvingen": ("activity.view", "activity.manage"),
    "/admin/leden": ("party.view", "party.masterdata"),
    "/admin/leden-import": ("party.view", "party.masterdata"),
    "/admin/personen": ("party.view", "party.masterdata"),
    "/admin/producten": ("product.view", "product.masterdata"),
    "/admin/betalingen": ("payment.view", "payment.manage"),
    "/admin/rapporten": ("report.view", "report.manage"),
    "/admin/rapporten/raakje": ("assistant.use", "assistant.use"),
    "/admin/ai-context": ("settings.view", "settings.manage"),
    "/admin/e-maillog": ("settings.view", "settings.manage"),
    "/admin/ledenwijzigingen": ("settings.view", "settings.manage"),
    "/admin/design-system": ("settings.view", "settings.manage"),
    "/admin/info": ("settings.view", "settings.manage"),
    "/admin/instellingen": ("settings.view", "settings.manage"),
    "/admin/organisatie": ("party.view", "party.masterdata"),
    "/admin/gebruikers": ("user.view", "user.manage"),
    "/admin/gebruikers/alle-werkruimtes": ("platform.view", "platform.manage"),
    "/admin/organisaties": ("platform.view", "platform.manage"),
    "/admin/tenants": ("platform.view", "platform.manage"),
    # Slice 5. The workbench and the shell around it: one right, to look and to act.
    "/admin/werkbank": ("workbench.use", "workbench.use"),
    "/admin/accountmenu": ("workbench.use", "workbench.use"),
    "/admin/profiel": ("workbench.use", "workbench.use"),
    "/admin/werkruimte-wisselen": ("workbench.use", "workbench.use"),
    # The start page: its tiles are figures of saved reports (#848). The shortest
    # start of all — every other screen above is a longer one and wins.
    "/admin": ("report.view", "report.manage"),
}


#: Routes whose object is not the one their address starts with: the payments
#: of an activity, a household and a registration are payment's screens.
NOT_BY_ITS_START = {
    "/admin/activiteiten/{activity_id}/betalingen": "/admin/betalingen",
    "/admin/leden/gezin/{family_id}/betalingen": "/admin/betalingen",
    "/admin/inschrijvingen/{registration_id}/betalingen": "/admin/betalingen",
}


def _right_of(method: str, path: str) -> str | None:
    """The right this route is to ask: its screen's viewing right for a GET, its
    changing right for every other method (C4.3a)."""
    path = NOT_BY_ITS_START.get(path, path)
    fits = [s for s in ON_A_RIGHT if path == s or path.startswith(s + "/")]
    if not fits:
        return None
    view, change = ON_A_RIGHT[max(fits, key=len)]
    return view if method == "GET" else change


def _routes_on_a_right() -> list[tuple[str, str]]:
    """The gated routes of `ON_A_RIGHT`: what the list records as open to everyone
    has no gate, and what it records as refused to everyone shows none (`NOBODY`)."""
    recorded = json.loads(SNAPSHOT.read_text())["routes"]
    routes = [
        (method, path)
        for method, path in every_route()
        if _right_of(method, path)
        and recorded[f"{method} {path}"]["tenant"] not in ("everyone", "nobody")
    ]
    assert len(routes) >= 252, f"only {len(routes)} routes on a right — is the walk still looking?"
    return routes


def _operator_without(world, rights: set[str]) -> dict[tuple[str, str], bool]:
    """Per route on a right, whether the operator — who holds every right — is
    let in when his bundle has lost `rights`; in the tenant's workspace, the
    bundle put back afterwards. A platform screen answers 404 there to who holds
    its right, and that counts as let in, as in the list."""
    connection, workspaces = world
    _tenant_id, host = workspaces["tenant"]
    session = make_session_value(_email("OPERATOR"))
    headers = {
        "cookie": f"{SESSION_COOKIE}={session}",
        "x-csrf-token": csrf_token_for(session),
        **host,
    }
    bundle = connection.begin_nested()
    gone = connection.execute(
        sql("DELETE FROM auth.role_rights WHERE role_code = 'OPERATOR' AND right_code = ANY(:r)"),
        {"r": sorted(rights)},
    ).rowcount
    assert gone == len(rights), f"the operator's bundle held {gone} of {sorted(rights)}"
    out = {}
    try:
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as client:
            for method, path in _routes_on_a_right():
                address = re.sub(r"\{[^}]+\}", "1", path)
                status = _ask(client, connection, method, address, headers)
                out[method, path] = status not in REFUSED
    finally:
        bundle.rollback()
    return out


def _all_rights() -> set[str]:
    return {right for pair in ON_A_RIGHT.values() for right in pair}


@pytest.mark.parametrize("right", sorted(_all_rights()))
def test_a_route_asks_the_right_written_beside_its_screen(world, right):
    """With one right taken out of the operator's bundle, exactly the routes that
    are to ask it are refused, and every other converted route opens as before:
    a GET asks its screen's viewing right, every other method its changing right
    (C4.3a), and each the right of its own object. The list cannot hold this —
    every bundle holds viewing beside changing, so it reads the same whichever
    of the two a route asks.

    Proven red, each for the two rights involved: `Right.USER_VIEW` put on the
    route that deletes a user ("open without user.manage", "refused without
    user.view"); `Right.SETTINGS_MANAGE` put on the save of Onze organisatie
    ("open without party.masterdata"); `Right.REPORT_MANAGE` put on opening a
    saved report ("open without report.view")."""
    let_in = _operator_without(world, {right})
    wrong = [
        f"{method} {path}: {'open' if admitted else 'refused'} without {right}"
        for (method, path), admitted in sorted(let_in.items())
        if admitted == (_right_of(method, path) == right)
    ]
    assert not wrong, "\n".join(wrong)

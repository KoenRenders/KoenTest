"""CR-19 #1475 — the enabled module set per tenant, and `require_module`.

C6 test 1 (off is 404), test 2 (defaults and the seed), test 12 (no extra
session per request). The gate — every router guarded, every registry entry
real — is `tests/test_module_gate.py`.

The set is read by the middleware through a process cache (one query for every
tenant), so a test switches a module off by setting that cache, exactly what
`set_modules` will leave behind after #1478: the request path from middleware
to guard is the real one.

Proven red against master `b024a779`: there is no `require_module` and no
`mdm.tenant_modules`, so the module does not import. On this branch, with the
guard's `raise` taken out, `test_off_is_404_for_every_route_of_the_module`
fails on its first route.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as sql

from app import main
from app.config import settings
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import create_tenant, enabled_modules, invalidate_tenant_codes
from app.kernel.modules import DEFAULTS, ModuleCode
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EVERY = frozenset(code.value for code in ModuleCode)


@pytest.fixture
def modules_of(monkeypatch):
    """Set the cached module set of tenants, as the middleware will read it."""
    invalidate_tenant_codes()

    def apply(sets: dict[int, frozenset[str]]):
        monkeypatch.setattr(tenant_lookup, "_modules_cache", dict(sets))

    yield apply
    invalidate_tenant_codes()


def _guarded_get_paths(code: ModuleCode) -> list[str]:
    """Every GET path of the routers guarded by this module, params filled."""
    paths = []
    for route in main.app.routes:
        context = getattr(route, "include_context", None)
        if context is None:
            continue
        if not any(
            getattr(d.dependency, "module_code", None) is code for d in context.dependencies
        ):
            continue
        for r in route.original_router.routes:
            if "GET" in getattr(r, "methods", ()):
                path = context.prefix + r.path
                paths.append(path.replace("{", "").replace("}", "").replace(":path", ""))
    return sorted(set(paths))


def _with_ids(path: str) -> str:
    """Fill a path's parameters with a plausible value: digits for ids."""
    parts = []
    for part in path.split("/"):
        parts.append("1" if part.endswith("id") or part in {"token", "key"} else part)
    return "/".join(parts)


def test_off_is_404_for_every_route_of_the_module(client, modules_of):
    """C6 test 1: with activities off, every GET route of its routers — public,
    admin and JSON — answers 404, for a visitor and for the tenant's admin."""
    paths = [_with_ids(p) for p in _guarded_get_paths(ModuleCode.ACTIVITIES)]
    assert len(paths) >= 20, f"the walk found only {paths}"
    # The same paths with the module on: most must answer something else, or a
    # 404 below would prove nothing (a filled-in id that does not exist).
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    modules_of({TENANT_MILLEGEM_ID: EVERY})
    live = [p for p in paths if client.get(p, follow_redirects=False).status_code != 404]
    # A third and not a half since CR-13 phase 4b (#1251): the JSON GET routes that
    # answered without an existing id are gone, the screens of one activity remain.
    assert len(live) >= len(paths) // 3, f"only {len(live)} of {len(paths)} answer when on"
    client.cookies.clear()
    modules_of({TENANT_MILLEGEM_ID: EVERY - {"activities"}})

    for who in ("visitor", "admin"):
        if who == "admin":
            client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
        answers = {p: client.get(p, follow_redirects=False).status_code for p in paths}
        not_404 = {p: s for p, s in answers.items() if s != 404}
        assert not not_404, f"{who}: still answering with activities off: {not_404}"


def test_on_answers_as_before_and_other_modules_stay(client, modules_of):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    modules_of({TENANT_MILLEGEM_ID: EVERY})
    for path in ("/admin/activiteiten", "/activiteiten"):
        assert client.get(path).status_code == 200, path

    modules_of({TENANT_MILLEGEM_ID: EVERY - {"activities"}})
    assert client.get("/admin/formulieren").status_code == 200, "another module is untouched"
    assert client.get("/admin/gebruikers").status_code == 200, "the shell has no module"
    assert client.get("/").status_code == 200, "the public site core has no module"


def test_signing_in_works_without_the_membership_module(client, modules_of):
    """The login routes moved from the membership router to auth (#1475): a
    tenant without members still signs in through the mail link."""
    modules_of({TENANT_MILLEGEM_ID: EVERY - {"membership"}})
    assert client.get("/lid-worden").status_code == 404
    assert client.get("/login", follow_redirects=False).headers["location"] == "/aanmelden"
    expired = client.get("/login/verify?token=onbekend")
    assert expired.status_code == 401, "the expired-link page, not a 404"


def test_every_unit_is_seeded_full_and_the_platform_with_its_own_set(db_session):
    """C6 test 2, the seed: every UNIT has every module; an ACCOUNT has none — it
    never serves a request. The PLATFORM had every module too, until #1523 gave
    it its own kind and set (migration 191, `DEFAULTS["PLATFORM"]`)."""
    rows = db_session.execute(
        sql(
            "SELECT o.org_type, o.id, array_agg(m.module_code ORDER BY m.module_code) "
            "FROM mdm.organizations o LEFT JOIN mdm.tenant_modules m ON m.tenant_id = o.id "
            "GROUP BY o.org_type, o.id"
        )
    ).all()
    assert {r.org_type for r in rows} >= {"UNIT", "ACCOUNT"}
    for org_type, org_id, codes in rows:
        got = frozenset(c for c in codes if c)
        if org_type == "UNIT":
            assert got == EVERY, f"{org_type} {org_id}: {sorted(got)}"
        elif org_type == "PLATFORM":
            platform = frozenset(code.value for code in DEFAULTS["PLATFORM"])
            assert got == platform, f"{org_type} {org_id}: {sorted(got)}"
        else:
            assert got == frozenset(), f"{org_type} {org_id}: {sorted(got)}"


def test_the_defaults_per_kind_and_a_new_tenant(db_session):
    """C6 test 2, the defaults: an association has everything, a company the
    four of §C2. A tenant made today starts as an association (the kind is #1478)."""
    assert DEFAULTS["VERENIGING"] == frozenset(ModuleCode)
    assert {c.value for c in DEFAULTS["BEDRIJF"]} == {"cms", "media", "forms", "workflow"}

    org = create_tenant(db_session, name="Proeftenant 1475", code="proef-1475")
    assert enabled_modules(org.id, db=db_session) == EVERY


def test_a_module_code_outside_the_list_is_refused_by_the_database(db_session):
    with pytest.raises(Exception, match="ck_tenant_modules_module_code"):
        with db_session.begin_nested():
            db_session.execute(
                sql("INSERT INTO mdm.tenant_modules VALUES (:t, 'stamboom')"),
                {"t": TENANT_MILLEGEM_ID},
            )


def test_the_set_adds_no_session_or_query_to_a_request(client, monkeypatch):
    """C6 test 12: on a non-default tenant the middleware opens two sessions —
    language and noindex, as before — and reading the module set adds none and
    runs no query once the cache is warm."""
    import app.database

    monkeypatch.setattr(settings, "platform_hosts", "platform.example")
    url, headers = "/raakvoorbeeldafdeling/robots.txt", {"host": "platform.example"}
    invalidate_tenant_codes()
    assert client.get(url, headers=headers).status_code == 200  # warms the caches

    opened, reads = [], []
    real_session, real_query = app.database.SessionLocal, tenant_lookup._query_modules
    monkeypatch.setattr(
        app.database, "SessionLocal", lambda *a, **k: opened.append(1) or real_session(*a, **k)
    )
    monkeypatch.setattr(
        tenant_lookup, "_query_modules", lambda db: reads.append(1) or real_query(db)
    )
    assert client.get(url, headers=headers).status_code == 200
    assert reads == [], "the module set was read from the database again"
    assert len(opened) == 2, f"{len(opened)} sessions for one request; language + noindex is 2"


def test_site_context_compares_the_kind_of_organisation_with_the_member(db_session, monkeypatch):
    """C6 test 11: `site_context` asks "is this the platform?" with the enum
    member. On master it compared a CodeEnum with the string "PLATFORM" — never
    equal — so the platform offered a newsletter it does not send."""
    from app.domains.mdm.api import Organization, OrganizationType
    from app.kernel import tenant_config
    from app.ui import site_context

    platform = Organization(
        org_type=OrganizationType.PLATFORM, code="platform-1475", name="Platform", is_active=True
    )
    db_session.add(platform)
    db_session.flush()

    monkeypatch.setattr(tenant_config, "_actieve_tenant", lambda _t: platform.id)
    assert site_context(db_session)["nieuwsbrief_inschrijven"] is False
    monkeypatch.setattr(tenant_config, "_actieve_tenant", lambda _t: TENANT_MILLEGEM_ID)
    assert site_context(db_session)["nieuwsbrief_inschrijven"] is True

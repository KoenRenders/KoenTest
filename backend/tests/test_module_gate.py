"""CR-19 C6 test 10 — every module router guarded, every registry entry real
(#1475, the gate of §C7).

What it holds, against the running app rather than the source text:

1. Every router `main.py` includes carries exactly one `require_module`, or is
   one of the `SHELL_ROUTERS` that `main.py` declares — never both, never
   neither. A router included without a decision is red.
2. No router of a module-only domain sits on the shell list.
3. Every module guards at least one router, each of its route prefixes is
   served by a route of a router it guards, and each of its admin menu items
   is a route that exists.

Proven by violation (additive, per CLAUDE.md): an extra
`app.include_router(APIRouter-with-one-route)` in `main.py` without a
dependency → part 1 red, naming the router; the same router added to
`SHELL_ROUTERS` from `app.domains.meetings` → part 2 red; a prefix
"/admin/nergens" added to the meetings entry → part 3 red.
"""

from __future__ import annotations

from app import main
from app.kernel.modules import MODULES, ModuleCode

# Domains whose every router belongs to a module. A shell router from one of
# them is a mistake, not a decision.
MODULE_ONLY_PACKAGES = {
    "app.domains.activities",
    "app.domains.designstudio",
    "app.domains.forms",
    "app.domains.media",
    "app.domains.meetings",
    "app.domains.membership",
    "app.domains.newsletter",
    "app.domains.reporting",
}

# Included by `include_stub_routes` in development and the tests only: the stub
# payment provider's pretend checkout (#1274). Never registered elsewhere.
DEV_ONLY = {"app.domains.payment.stub_router"}


def _included():
    """(router, prefix, module codes it is guarded by) per include."""
    found = []
    for route in main.app.routes:
        context = getattr(route, "include_context", None)
        if context is None:
            continue
        codes = [
            getattr(dep.dependency, "module_code", None)
            for dep in context.dependencies
            if getattr(dep.dependency, "module_code", None) is not None
        ]
        found.append((route.original_router, context.prefix, codes))
    # A floor, not a count: it only proves the walk found the routers. 38 after CR-13
    # phase 4b took the JSON routers of membership and mdm (#1251); the rest of that
    # phase takes a few more.
    assert len(found) >= 30, f"the app includes only {len(found)} routers — did the walk break?"
    return found


def _source(router) -> str:
    modules = {r.endpoint.__module__ for r in router.routes if hasattr(r, "endpoint")}
    return ",".join(sorted(modules)) or "?"


def _paths(router, prefix: str) -> set[str]:
    """Every path a router serves, nested includes followed."""
    paths = set()
    for r in router.routes:
        context = getattr(r, "include_context", None)
        if context is not None:
            paths |= _paths(r.original_router, prefix + context.prefix)
        elif hasattr(r, "path"):
            paths.add(prefix + r.path)
    return paths


def test_every_included_router_is_guarded_or_declared_shell():
    shell = {id(r) for r in main.SHELL_ROUTERS}
    wrong = []
    for router, _prefix, codes in _included():
        source = _source(router)
        if source in DEV_ONLY:
            continue
        guarded, declared = len(codes) == 1, id(router) in shell
        if len(codes) > 1:
            wrong.append(f"{source}: guarded by {len(codes)} modules")
        elif guarded == declared:
            wrong.append(f"{source}: {'both guarded and shell' if guarded else 'neither'}")
    assert not wrong, "routers without a module decision in main.py:\n" + "\n".join(wrong)


def test_no_shell_router_from_a_module_only_domain():
    wrong = [
        _source(router)
        for router in main.SHELL_ROUTERS
        if any(_source(router).startswith(package + ".") for package in MODULE_ONLY_PACKAGES)
    ]
    assert not wrong, f"on the shell list but part of a module: {wrong}"


def test_every_registry_entry_is_real():
    served: dict[ModuleCode, set[str]] = {}
    every_path: set[str] = set()
    for router, prefix, codes in _included():
        paths = _paths(router, prefix)
        every_path |= paths
        for code in codes:
            served.setdefault(code, set()).update(paths)

    problems = []
    for module in MODULES:
        paths = served.get(module.code, set())
        if not paths:
            problems.append(f"{module.code}: guards no router")
        for prefix in module.route_prefixes:
            if not any(p.startswith(prefix) for p in paths):
                problems.append(f"{module.code}: no guarded route under {prefix}")
        for href, _label in module.admin_items:
            if href not in every_path:
                problems.append(f"{module.code}: menu item {href} is no route")
    assert not problems, "\n".join(problems)
    assert len(MODULES) == len(ModuleCode), "every ModuleCode has its registry entry"


def test_every_counted_table_exists_and_belongs_to_a_tenant():
    """#1478: `record_counts` filters each table on its `tenant_id`. A table
    without one would count across tenants; a misspelt name would fail in the
    editor. Proven by adding "media.asset_tags" (no tenant_id) to the media
    entry → red, naming it."""
    import app.models  # noqa: F401 — every table registered
    from app.database import Base
    from app.kernel.modules import UNCOUNTED

    problems = []
    for module in MODULES:
        if module.code in UNCOUNTED:
            assert not module.record_tables, f"{module.code}: uncounted, yet lists tables"
            continue
        assert module.record_tables, f"{module.code}: counts nothing and is not in UNCOUNTED"
        for name in module.record_tables:
            table = Base.metadata.tables.get(name)
            if table is None:
                problems.append(f"{module.code}: no table {name}")
            elif "tenant_id" not in table.c:
                problems.append(f"{module.code}: {name} has no tenant_id")
    assert not problems, "\n".join(problems)

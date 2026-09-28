"""The gate of CR-13 (`docs/change_request_13_oo_foundation.md`, §B9.3) — phase 0a.

**A rule has one home, and every entrance passes through it.** This file holds
the checks that make that a property of the code instead of a habit. Phase 0a
builds the six simple ones and the meter; phase 0c (#1254) adds the heavy AST
gates to this same file.

| gate | kind | looks at |
|---|---|---|
| no session on an entity | ratchet | `models.py` naming `Session`, `db`, `.query(` or `app.database` |
| module shape | ratchet; **hard for a new package** | `api.py`, `codes.py`, `CONTRACT.md`, `models.py`, `tests/` per domain |
| no commit in an event handler | ratchet (one entry, phase 4); **hard for a new handler** | a `@subscribe` function, and what it calls up to three levels deep |
| no network in an event handler | ratchet | the same, for `smtplib`/`httpx`/`requests`/`urllib.request`/`http.client` |
| JSON route with a caller | ratchet; **hard for a new route** | every `/api/v1` route (method × path) named under `## Callers` in its domain's `CONTRACT.md` |
| validator without constraint | **hard** | every `@validates` column has `NOT NULL` or a `CHECK` naming it, read from the model's `__table__` |

An *event handler* is a `@subscribe` function, wherever it stands (§B4.9): a
`handlers.py` also carries `@job` functions, and a job is exactly where the
network belongs — so the handler gates never look at the file name.

**A ratchet has two halves** (the CR-12 shape): nothing new may appear, and
nothing fixed may stay on the list — a list that does not shrink is no ratchet.
The frozen lists are in `rules_baseline.py`; phase 4 deletes that file. Keys carry
no line numbers (they shift on the first unrelated edit); the messages do.

**Every collector proves it looked** (#678): it asserts it found what it walks —
the models, the packages, the handlers, the routes, the mappers — before any
verdict, so a moved folder or a changed decorator cannot turn it silently green.

Broken on purpose, each additively, then restored — the proofs are recorded per
test in its docstring.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests import rules_baseline as baseline

pytestmark = pytest.mark.ui_agnostisch

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
DOMAINS = APP / "domains"

SHAPE = ("api.py", "codes.py", "CONTRACT.md", "models.py", "tests/")
NETWORK_MODULES = {"smtplib", "httpx", "requests", "urllib.request", "http.client", "aiosmtplib"}


def _rel(path: Path) -> str:
    return str(path.relative_to(APP))


def _python_files() -> list[Path]:
    files = sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)
    assert len(files) > 150, f"only {len(files)} Python files under app/ — the walk is blind"
    return files


def _enclosing(tree: ast.AST) -> dict[ast.AST, str]:
    """Map every node to the qualified name of the function or class around it."""
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{name}.{child.name}" if name != "<module>" else child.name
                owner[child] = inner
                visit(child, inner)
            else:
                owner[child] = name
                visit(child, name)

    visit(tree, "<module>")
    return owner


# ── 1. No session on an entity (ratchet) ─────────────────────────────────────


def collect_session_on_entity() -> dict[str, str]:
    """`models.py` that touches a session → key `file::owner`.

    An entity reads what is already loaded and nothing else (§B4.1): a lazy
    relationship looks like data and is a hidden query, and a method that opens a
    session drags persistence into the domain.
    """
    models = sorted(DOMAINS.glob("*/models.py"))
    assert len(models) >= 15, f"only {len(models)} models.py found — the walk is blind"
    found: dict[str, str] = {}
    for path in models:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = _enclosing(tree)
        for node in ast.walk(tree):
            what = None
            if isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy.orm":
                if any(a.name == "Session" for a in node.names):
                    what = "imports Session"
            elif isinstance(node, ast.ImportFrom) and node.module == "app.database":
                # Every models.py imports the declarative `Base` from here: that is
                # the mapping, not a session. `SessionLocal`, `get_db`, `engine` are.
                names = [a.name for a in node.names if a.name != "Base"]
                if names:
                    what = f"imports {', '.join(names)} from app.database"
            elif isinstance(node, ast.arg) and node.arg == "db":
                what = "takes a `db` parameter"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"query", "object_session", "execute"}:
                    what = f"calls .{node.func.attr}("
            elif isinstance(node, ast.Name) and node.id == "object_session":
                what = "uses object_session"
            if what:
                key = f"{_rel(path)}::{owner.get(node, '<module>')}"
                found.setdefault(
                    key,
                    f"{_rel(path)}:{node.lineno} — `{owner.get(node, '<module>')}` {what}: an "
                    f"entity never opens a session (CR-13 §B4.1); that is a service function",
                )
    return found


# ── 2. Module shape (ratchet; hard for a new package) ────────────────────────


def _packages() -> list[Path]:
    packages = sorted(p for p in DOMAINS.iterdir() if p.is_dir() and (p / "__init__.py").exists())
    assert len(packages) >= 15, f"only {len(packages)} domain packages — the walk is blind"
    return packages


def collect_module_shape() -> dict[str, str]:
    """A domain package without a piece of its shape → key `package:piece` (§B4.5)."""
    found: dict[str, str] = {}
    for package in _packages():
        for piece in SHAPE:
            present = (
                (package / piece.rstrip("/")).is_dir()
                if piece.endswith("/")
                else (package / piece).is_file()
            )
            if not present:
                found[f"{package.name}:{piece}"] = (
                    f"`app/domains/{package.name}/` has no `{piece}` — a domain package has "
                    f"{', '.join(SHAPE)} (CR-13 §B4.5)"
                )
    return found


# ── 3 and 4. Event handlers: no commit, no network ───────────────────────────


def _is_subscribe(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
    return name == "subscribe"


def _event_handlers() -> list[tuple[Path, ast.Module, ast.FunctionDef]]:
    handlers = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _is_subscribe(d) for d in node.decorator_list
            ):
                handlers.append((path, tree, node))
    assert len(handlers) >= 2, f"only {len(handlers)} @subscribe handlers found — the walk is blind"
    return handlers


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


_TREES: dict[Path, ast.Module] = {}


def _tree(path: Path) -> ast.Module:
    if path not in _TREES:
        _TREES[path] = ast.parse(path.read_text(encoding="utf-8"))
    return _TREES[path]


def _module_path(dotted: str) -> Path | None:
    if not dotted.startswith("app."):
        return None
    base = BACKEND / Path(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


Reached = tuple[Path, ast.Module, ast.FunctionDef, str]


def _reachable(
    path: Path, tree: ast.Module, function: ast.FunctionDef, depth: int = 3
) -> list[Reached]:
    """The function itself and what it calls, up to `depth` levels, following calls
    into the same module and into functions imported from other `app.` modules.

    Why further than "one level in the same module": the one handler that reaches
    SMTP today does it through `mail.service._dispatch` → `_send`, two calls and one
    module away. A gate that cannot find its own known offender proves nothing.
    Calls through attributes (`obj.method()`) and dynamic dispatch are not followed.
    """
    seen: set[tuple[Path, str]] = set()
    out: list[Reached] = []

    def visit(p: Path, t: ast.Module, fn: ast.FunctionDef, via: str, level: int) -> None:
        if (p, fn.name) in seen:
            return
        seen.add((p, fn.name))
        out.append((p, t, fn, via))
        if level == depth:
            return
        local = _module_functions(t)
        imported: dict[str, tuple[str, str]] = {}
        for node in t.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                for alias in node.names:
                    imported[alias.asname or alias.name] = (node.module, alias.name)
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            name = n.func.id
            chain = f"{via} → {name}" if via else name
            if name in local and local[name] is not fn:
                visit(p, t, local[name], chain, level + 1)
            elif name in imported:
                module, original = imported[name]
                target = _module_path(module)
                if target is not None:
                    target_tree = _tree(target)
                    callee = _module_functions(target_tree).get(original)
                    if callee is not None:
                        visit(target, target_tree, callee, chain, level + 1)

    visit(path, tree, function, "", 0)
    return out


def _commits(function: ast.FunctionDef) -> int | None:
    for n in ast.walk(function):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "commit"
        ):
            return n.lineno
    return None


def collect_commit_in_handler() -> dict[str, str]:
    """A `@subscribe` function that commits → key `file::handler`.

    The dispatcher runs handlers inside the publisher's transaction (§B4.1): the
    door service commits once, and a handler that commits splits it in two.
    """
    found: dict[str, str] = {}
    for path, tree, handler in _event_handlers():
        for where, _t, function, chain in _reachable(path, tree, handler):
            line = _commits(function)
            if line is not None:
                via = f" via `{chain}`" if chain else ""
                found[f"{_rel(path)}::{handler.name}"] = (
                    f"{_rel(where)}:{line} — event handler `{handler.name}` commits{via}; the door "
                    f"service commits once, a handler never does (CR-13 §B4.1)"
                )
                break
    return found


def _network_names(tree: ast.Module) -> set[str]:
    """The local names under which this module imported a network library."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in NETWORK_MODULES:
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module in NETWORK_MODULES:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _uses_network(function: ast.FunctionDef, network: set[str]) -> int | None:
    for n in ast.walk(function):
        if isinstance(n, ast.Name) and n.id in network:
            return n.lineno
    return None


def collect_network_in_handler() -> dict[str, str]:
    """A `@subscribe` function that reaches the network → key `file::handler`.

    A handler runs inside the transaction; one that talks to SMTP holds it open
    for the round trip and rolls the business change back when a mail server is
    down (§B4.1). It enqueues a job; the job sends.
    """
    found: dict[str, str] = {}
    for path, tree, handler in _event_handlers():
        for where, t, function, chain in _reachable(path, tree, handler):
            network = _network_names(t)
            line = _uses_network(function, network) if network else None
            if line is not None:
                via = f" via `{chain}`" if chain else ""
                found[f"{_rel(path)}::{handler.name}"] = (
                    f"{_rel(where)}:{line} — event handler `{handler.name}` reaches the "
                    f"network{via}; a handler enqueues a job and the job sends (CR-13 §B4.1)"
                )
                break
    return found


# ── 5. JSON route with a caller (ratchet; hard for a new route) ──────────────

_CALLER_LINE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/api/v1/[^`\s]+)`")


def _api_routes() -> dict[str, str]:
    """Every route under /api/v1 as `METHOD path` → the module that defines it."""
    from app.main import app

    routes: dict[str, str] = {}

    def walk(items, prefix: str = "") -> None:
        for item in items:
            if type(item).__name__ == "_IncludedRouter":
                walk(item.original_router.routes, prefix + (item.include_context.prefix or ""))
                continue
            if hasattr(item, "routes") and not hasattr(item, "endpoint"):
                walk(item.routes, prefix)
                continue
            path = prefix + getattr(item, "path", "")
            if not path.startswith("/api/v1"):
                continue
            module = getattr(getattr(item, "endpoint", None), "__module__", "")
            for method in sorted((getattr(item, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
                routes[f"{method} {path}"] = module

    walk(app.routes)
    assert len(routes) > 100, f"only {len(routes)} /api/v1 routes found — the walk is blind"
    return routes


def _contract_of(module: str) -> Path:
    parts = module.split(".")
    if parts[:2] == ["app", "domains"] and len(parts) > 2:
        return DOMAINS / parts[2] / "CONTRACT.md"
    return APP / parts[1] / "CONTRACT.md" if len(parts) > 1 else APP / "CONTRACT.md"


def _named_callers(contract: Path) -> set[str]:
    """The routes a `## Callers` section of a CONTRACT.md names, as `METHOD path`."""
    if not contract.is_file():
        return set()
    named: set[str] = set()
    inside = False
    for line in contract.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            inside = line.lstrip("#").strip().lower().startswith("callers")
            continue
        if inside:
            named.update(f"{m} {p}" for m, p in _CALLER_LINE.findall(line))
    return named


def collect_json_route_without_caller() -> dict[str, str]:
    """A `/api/v1` route not named under `## Callers` in its `CONTRACT.md` (R14)."""
    found: dict[str, str] = {}
    contracts: dict[Path, set[str]] = {}
    for route, module in _api_routes().items():
        contract = _contract_of(module)
        named = contracts.setdefault(contract, _named_callers(contract))
        if route not in named:
            where = contract.relative_to(BACKEND) if contract.is_relative_to(BACKEND) else contract
            found[route] = (
                f"`{route}` has no caller in `{where}` — a JSON route exists because a machine "
                f"caller exists (R14): name it under `## Callers`, or remove the route"
            )
    return found


# ── 6. Validator without constraint (hard) ───────────────────────────────────


def _mappers():
    from app.database import Base
    from app.domains.registry import load_all_models

    load_all_models()
    mappers = list(Base.registry.mappers)
    assert len(mappers) > 50, f"only {len(mappers)} mapped classes — the walk is blind"
    return mappers


def collect_validator_without_constraint(mappers=None) -> dict[str, str]:
    """A `@validates` column without `NOT NULL` or a `CHECK` naming it (§B4.2).

    `@validates` fires on assignment, not on absence and not on a bulk path; alone
    it is a promise. If PostgreSQL can say it about one row, PostgreSQL says it.
    """
    from sqlalchemy import CheckConstraint

    found: dict[str, str] = {}
    for mapper in mappers if mappers is not None else _mappers():
        table = mapper.local_table
        checks = [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]
        for column_name in mapper.validators:
            column = table.columns.get(column_name)
            if column is None:
                continue  # a relationship validator: not a column rule
            if not column.nullable or any(re.search(rf"\b{column_name}\b", c) for c in checks):
                continue
            key = f"{mapper.class_.__name__}.{column_name}"
            found[key] = (
                f"`{key}` has a validator and neither `NOT NULL` nor a `CHECK` on the column — "
                f"add the constraint in the same commit (CR-13 §B4.2)"
            )
    return found


# ── The ratchet shape ────────────────────────────────────────────────────────

COLLECTORS = {
    "SESSION_ON_ENTITY": collect_session_on_entity,
    "MODULE_SHAPE": collect_module_shape,
    "COMMIT_IN_HANDLER": collect_commit_in_handler,
    "NETWORK_IN_HANDLER": collect_network_in_handler,
    "JSON_ROUTE_WITHOUT_CALLER": collect_json_route_without_caller,
}


def _ratchet(name: str) -> None:
    """Nothing new, and nothing left behind."""
    found = COLLECTORS[name]()
    frozen = getattr(baseline, name)
    added = sorted(set(found) - set(frozen))
    gone = sorted(set(frozen) - set(found))
    errors = []
    if added:
        errors.append("New violations:\n  " + "\n  ".join(found[k] for k in added))
    if gone:
        errors.append(
            f"These are still in `rules_baseline.{name}` but no longer occur:\n  "
            + "\n  ".join(gone)
            + "\nRemove them from the list — a ratchet that does not shrink is no ratchet."
        )
    assert not errors, "\n\n".join(errors)


def test_no_session_on_an_entity():
    """Ratchet. Proof (run, restored): a function `_probe_session(db)` returning
    `db.query(...)` added to `activities/models.py` → red, "`_probe_session` takes a
    `db` parameter"."""
    _ratchet("SESSION_ON_ENTITY")


def test_module_shape():
    """Ratchet for today's packages; a new package is not on the list, so any
    missing piece of it is red. Proof: an empty `app/domains/proefdomein/__init__.py`
    added → red with five missing pieces."""
    _ratchet("MODULE_SHAPE")


def test_no_commit_in_an_event_handler():
    """Ratchet on one entry, hard for any other handler.

    The change request planned this gate hard from phase 0, reading "one level in
    the same module". Followed three levels, it finds the one offender that
    reading missed: `mail.on_mail_requested` commits through `_dispatch → _send →
    _log_email`. Phase 4 turns that handler into a job enqueuer (§B4.1) and removes
    the entry. Proof: `db.commit()` added to
    `workflow.handlers.create_behartigen_task` → red, naming that handler."""
    _ratchet("COMMIT_IN_HANDLER")


def test_no_network_in_an_event_handler():
    """Ratchet on `mail.on_mail_requested` (SMTP via `_send`) until phase 4 turns it
    into a job. Proof: an `import httpx` and an `httpx.get(...)` added to
    `workflow.handlers.create_behartigen_task` → red, naming that handler."""
    _ratchet("NETWORK_IN_HANDLER")


def test_every_json_route_names_its_caller():
    """Ratchet on today's routes; a new route is red until its domain's
    `CONTRACT.md` names its caller under `## Callers`. Proofs (run, restored): a
    `@router.get("/probe")` added to `cms/router.py` → red, "`GET /api/v1/probe` has
    no caller"; a `## Callers` line for `GET /api/v1/sponsors` added to
    `media/CONTRACT.md` → red, "no longer occur", because a named route must leave
    the list. The same line in `cms/CONTRACT.md` stayed green: only the contract of
    the domain that defines the route counts."""
    _ratchet("JSON_ROUTE_WITHOUT_CALLER")


def test_no_validator_without_its_constraint():
    """Hard. No `@validates` exists yet (phase 1 brings the first), so the gate is
    also proven on classes of its own, below."""
    found = collect_validator_without_constraint()
    assert not found, "\n".join(found[k] for k in sorted(found))


def test_the_validator_gate_sees_a_validator_without_constraint():
    """The additive proof, on a mapped class that exists only in this test: a
    nullable column with a validator is red; `nullable=False` or a `CHECK` naming
    the column makes it green."""
    from sqlalchemy import CheckConstraint, Column, Integer, String
    from sqlalchemy.orm import declarative_base, validates

    Base = declarative_base()

    class Loose(Base):
        __tablename__ = "rules_gate_loose"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=True)

        @validates("name")
        def _name(self, key, value):
            return value

    class NotNull(Base):
        __tablename__ = "rules_gate_not_null"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=False)

        @validates("name")
        def _name(self, key, value):
            return value

    class Checked(Base):
        __tablename__ = "rules_gate_checked"
        __table_args__ = (CheckConstraint("name <> ''"),)
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=True)

        @validates("name")
        def _name(self, key, value):
            return value

    found = collect_validator_without_constraint(list(Base.registry.mappers))
    assert set(found) == {"Loose.name"}, found

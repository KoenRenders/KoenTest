"""The gate of CR-13 (`docs/change_request_13_oo_foundation.md`, §B9.3) — phases 0a and 0c.

**A rule has one home, and every entrance passes through it.** This file holds
the checks that make that a property of the code instead of a habit. Phase 0a
built the six simple ones and the meter; phase 0c (#1254) added the heavy AST
gates below them.

| gate | kind | looks at |
|---|---|---|
| no session on an entity | ratchet | `models.py` naming `Session`, `db`, `.query(` or `app.database` |
| module shape | ratchet; **hard for a new package** | `api.py`, `codes.py`, `CONTRACT.md`, `models.py`, `tests/` per domain |
| no commit in an event handler | ratchet (one entry, phase 4); **hard for a new handler** | a `@subscribe` function, and what it calls up to three levels deep |
| no network in an event handler | ratchet | the same, for `smtplib`/`httpx`/`requests`/`urllib.request`/`http.client` |
| JSON route with a caller | ratchet; **hard for a new route** | every `/api/v1` route (method × path) named under `## Callers` in its domain's `CONTRACT.md` |
| validator without constraint | **hard** | every `@validates` column has `NOT NULL` or a `CHECK` naming it, read from the model's `__table__` |
| English identifiers (#780) | ratchet; **hard outside the baseline** | `def`/`class`/module/column/migration/test-file names against a Dutch-only word list |
| no foreign writes | ratchet | seven write forms on another domain's mapped class, outside that domain |
| no write after a commit | ratchet | a write after a commit on a path that carries it, in AST order |
| no commit behind another domain's api | ratchet | an `api.py` export called from another domain's service, handler or tool that commits |
| events, not calls | ratchet | a call into another domain's command (an export that writes) outside a `@subscribe` function |
| no rule in a router | ratchet, **a reason per entry** | an `if` that refuses in a router or screen, the doorman's own refusals aside |
| one entrance rule | (a) **hard**; (b), (c) ratchets | (a) aggregates mapped, with their own `check()`; (b) writes in a router, screen or handler; (c) writes past the ORM |
| one owner per derived value | ratchet | a registered value's shape computed outside its owner (Python only) |
| promise kept | two ratchets (**not kept is empty**) | template `required`/`pattern`/`min` walked to a kept column; the unwalkable ones with the step where they stop |

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
import functools
import re
import textwrap
from pathlib import Path

import pytest

from tests import rules_baseline as baseline
from tests._bestanden import is_app_test

# CR-29 R7: one worker for the file, so what a walk of the tree found is found once
# (`api_commands`, `_tree`) and not once per process.
pytestmark = [pytest.mark.ui_agnostisch, pytest.mark.xdist_group("rules_gate")]

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
DOMAINS = APP / "domains"

SHAPE = ("api.py", "codes.py", "CONTRACT.md", "models.py", "tests/")
NETWORK_MODULES = {"smtplib", "httpx", "requests", "urllib.request", "http.client", "aiosmtplib"}


def _rel(path: Path) -> str:
    return str(path.relative_to(APP))


def _python_files() -> list[Path]:
    """The application's Python files — a domain's tests (CR-13 R15) are not the app."""
    files = sorted(
        p for p in APP.rglob("*.py") if "__pycache__" not in p.parts and not is_app_test(p)
    )
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


def _is_handles(decorator: ast.expr) -> bool:
    """`@handles(SomePort)` — the one handler of a port (`kernel/ports.py`)."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
    return name == "handles"


def _event_handlers() -> list[tuple[Path, ast.Module, ast.FunctionDef]]:
    """The functions that run inside somebody else's transaction: the handlers of
    an event (`@subscribe`) and of a port (`@handles`). Neither commits and neither
    reaches the network — the door service that started it all commits once."""
    handlers = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _is_subscribe(d) or _is_handles(d) for d in node.decorator_list
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


def _imported_file(importer: Path, node: ast.ImportFrom, name: str = "") -> Path | None:
    """The file an import names — `from app.x import f` and `from .x import f` → x;
    with `name`, the module that name itself is (`from . import service` → service)."""
    if node.level:
        base = importer.parents[node.level - 1]
        base = base.joinpath(*node.module.split(".")) if node.module else base
    elif node.module and node.module.startswith("app."):
        base = BACKEND.joinpath(*node.module.split("."))
    else:
        return None
    base = base / name if name else base
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _reachable(
    path: Path, tree: ast.Module, function: ast.FunctionDef, depth: int = 3
) -> list[Reached]:
    """The function itself and what it calls, up to `depth` levels, following calls
    into the same module, into functions imported from other `app.` modules
    (absolute or relative) and into `module.function()` of an imported module.

    Why further than "one level in the same module": the one handler that reaches
    SMTP today does it through `mail.service._dispatch` → `_send`, two calls and one
    module away. A gate that cannot find its own known offender proves nothing.
    Calls on an object (`obj.method()`) and dynamic dispatch are not followed.

    Why `service.function()` and `from .service import` are followed (#1251, the
    port gate): a port handler is thin by design — it turns a contract into one
    call of its own service — and that call is usually written one of those two
    ways. A walk that stopped at the handler would hold nothing of what it does.
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
        imported: dict[str, tuple[Path, str]] = {}
        modules: dict[str, Path] = {}
        # Module-level imports, and the ones inside the function itself — a late
        # import (`from app.kernel.jobs import enqueue`) is a call target all the same.
        for node in [*t.body, *ast.walk(fn)]:
            if not isinstance(node, ast.ImportFrom):
                continue
            source = _imported_file(p, node)
            for alias in node.names:
                as_module = _imported_file(p, node, alias.name)
                if as_module is not None:
                    modules[alias.asname or alias.name] = as_module
                elif source is not None:
                    imported[alias.asname or alias.name] = (source, alias.name)
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            func = n.func
            if isinstance(func, ast.Name):
                name = func.id
                if name in local and local[name] is not fn:
                    visit(p, t, local[name], f"{via} → {name}" if via else name, level + 1)
                    continue
                target, original = imported.get(name, (None, ""))
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            ):
                name = f"{func.value.id}.{func.attr}"
                target, original = modules[func.value.id], func.attr
            else:
                continue
            if target is None:
                continue
            target_tree = _tree(target)
            callee = _module_functions(target_tree).get(original)
            if callee is not None:
                visit(target, target_tree, callee, f"{via} → {name}" if via else name, level + 1)

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
    # The floor is what stays when CR-13 phase 4b (#1251) has pruned the rest: the
    # media file and its thumbnail and the two payment webhooks. It was 100 while the
    # routes without a caller still stood, then 50; a floor above what is left stops
    # the pruning, and a blind walk finds none.
    assert len(routes) >= 4, f"only {len(routes)} /api/v1 routes found — the walk is blind"
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


# ── 7. English identifiers (#780; ratchet, hard outside the baseline) ────────

# Words that exist only in Dutch. A word both languages use (`status`, `type`,
# `data`, `code`, `form`, `post`, `tenant`, `filter`, `agenda`, `bus`) is not here,
# so an English identifier can never match. A false positive is fixed by refining
# this list, never by adding the name to the baseline (#780 point 4).
#
# `DUTCH_WORDS` match a whole word only; `DUTCH_STEMS` also match the start of a
# word (`inschrijf` → `inschrijving`, `inschrijvingen`). Stems are long enough that
# no English word starts with them.
DUTCH_WORDS = frozenset(
    """
    aantal adres alle als bij dag dan dicht doel geen jaar kort leeg lees lege lid naam
    mijn namen naar niet nieuw oud rij rijen rol som tel toon uit veld voor wel werk zet
    """.split()
)
DUTCH_STEMS = (
    "aanmak",
    "aanpass",
    "achternaam",
    "activiteit",
    "afbeelding",
    "afzender",
    "antwoord",
    "bedrag",
    "beeld",
    "beheer",
    "bepaal",
    "bereken",
    "bericht",
    "bestand",
    "bestuur",
    "betaal",
    "betaling",
    "bevestig",
    "bewaar",
    "bewerk",
    "breedte",
    "controleer",
    "databank",
    "datum",
    "eerst",
    "formulier",
    "fout",
    "gebruiker",
    "geboorte",
    "gedaan",
    "geldig",
    "gemeente",
    "gesloten",
    "geslacht",
    "gezin",
    "groep",
    "haal",
    "hoofdlid",
    "hoogte",
    "huisnummer",
    "icoon",
    "iconen",
    "inhoud",
    "inschrijf",
    "inschrijv",
    "instelling",
    "kaart",
    "keten",
    "keuze",
    "kleur",
    "knop",
    "kolom",
    "laatste",
    "leden",
    "lidmaatschap",
    "lijst",
    "maak",
    "maand",
    "melding",
    "migratie",
    "ontbreek",
    "ontvang",
    "onderdeel",
    "onderdelen",
    "onderwerp",
    "ongeldig",
    "opmaak",
    "opslaan",
    "ouder",
    "overschrijving",
    "pagina",
    "persoon",
    "personen",
    "poort",
    "prijs",
    "rechten",
    "regel",
    "rekening",
    "saldo",
    "scherm",
    "sjabloon",
    "sleutel",
    "soort",
    "sorteer",
    "sortering",
    "straat",
    "stuur",
    "taken",
    "tekst",
    "telling",
    "terugbetal",
    "toevoeg",
    "totaal",
    "uitlijning",
    "uniek",
    "velden",
    "verborgen",
    "vergadering",
    "verleng",
    "verplicht",
    "verslag",
    "verstuur",
    "vertaling",
    "verwijder",
    "verwerk",
    "voeg",
    "volgend",
    "volgorde",
    "voornaam",
    "vorige",
    "vraag",
    "vragen",
    "waarde",
    "weergave",
    "wijzig",
    "zichtbaar",
    "zoek",
    "afdruk",
    "afreken",
    "bestel",
    "bijwerk",
    "gegevens",
    "geannuleerd",
    "geschrapt",
    "hernoem",
    "huidige",
    "ingetypt",
    "inzending",
    "klaar",
    "notitie",
    "opmerking",
    "organisatie",
    "registreer",
    "schrijf",
    "sectie",
    "statisch",
    "verhuis",
    "vernieuw",
    "verplaats",
    "ververs",
    "vordering",
    "wacht",
    "werkruimte",
    "actieve",
    "lopend",
    "organisator",
    "portaal",
    "wissel",
    "worden",
)

# English words that happen to start with a Dutch stem: `pagina` → `paginated`.
ENGLISH_PREFIXES = ("paginat",)

_WORD_SPLIT = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def dutch_words_in(identifier: str) -> list[str]:
    """The Dutch words an identifier is made of (snake_case and CamelCase)."""
    words = [w.lower() for part in identifier.split("_") for w in _WORD_SPLIT.findall(part)]
    return [
        w
        for w in words
        if w in DUTCH_WORDS or (w.startswith(DUTCH_STEMS) and not w.startswith(ENGLISH_PREFIXES))
    ]


def collect_dutch_identifiers() -> dict[str, str]:
    """A Dutch `def`, `class`, module, model column, migration or test file name.

    Keys: `file::name` for a definition, `file::Class.column` for a column,
    `module:file`, `migration:<file name>`, `test file:<file name>`. Scope per #780
    point 3 and CR-13 §B9.3: identifiers, not strings, comments or stored values.
    """
    found: dict[str, str] = {}

    def note(key: str, where: str, name: str) -> None:
        words = dutch_words_in(name)
        if words:
            found.setdefault(
                key,
                f"{where} `{name}` ({', '.join(words)}) — new code is English "
                f"(`CLAUDE.md`, *Code language*; #780)",
            )

    files = _python_files()
    for path in files:
        note(f"module:{_rel(path)}", f"{_rel(path)}:", path.stem)
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                note(f"{_rel(path)}::{node.name}", f"{_rel(path)}:{node.lineno}", node.name)
        if path.name == "models.py":
            for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
                for stmt in cls.body:
                    if (
                        isinstance(stmt, ast.Assign)
                        and isinstance(stmt.value, ast.Call)
                        and getattr(stmt.value.func, "id", None) == "Column"
                    ):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                note(
                                    f"{_rel(path)}::{cls.name}.{target.id}",
                                    f"{_rel(path)}:{stmt.lineno} column",
                                    target.id,
                                )
    migrations = sorted((BACKEND / "alembic" / "versions").glob("*.py"))
    assert len(migrations) > 150, f"only {len(migrations)} migrations — the walk is blind"
    for path in migrations:
        # `170_2026_09_28_…_what_it_does.py`: the words after the id are the name.
        note(f"migration:{path.name}", "alembic/versions/", path.stem)
    test_files = sorted(
        {*(BACKEND / "tests").rglob("test_*.py"), *DOMAINS.glob("*/tests/test_*.py")}
    )
    assert len(test_files) > 400, f"only {len(test_files)} test files — the walk is blind"
    for path in test_files:
        note(f"test file:{path.name}", str(path.relative_to(BACKEND)), path.stem)
    return found


# ── 8. No foreign writes (ratchet; hard for a new package) ───────────────────


def _owner_of_module(module: str) -> str:
    """`app.domains.mdm.models` → `mdm`; `app.kernel.jobs` → `kernel`."""
    parts = module.split(".")
    if parts[:2] == ["app", "domains"] and len(parts) > 2:
        return parts[2]
    if parts[:2] == ["app", "kernel"]:
        return "kernel"
    return "app"


def _owner_of_file(path: Path) -> str:
    return _owner_of_module(".".join(path.relative_to(BACKEND).with_suffix("").parts))


def _mapped_owners() -> tuple[dict[str, str], dict[str, str]]:
    """Mapped class name → owning domain, and schema → owning domain."""
    classes: dict[str, str] = {}
    schemas: dict[str, str] = {}
    for mapper in _mappers():
        cls = mapper.class_
        owner = _owner_of_module(cls.__module__)
        assert classes.get(cls.__name__, owner) == owner, f"two mapped classes named {cls.__name__}"
        classes[cls.__name__] = owner
        schema = mapper.local_table.schema
        if schema and owner != "kernel":
            schemas[schema] = owner
    assert len(classes) > 100, f"only {len(classes)} mapped classes — the walk is blind"
    return classes, schemas


_READERS = {"first", "one", "one_or_none", "get", "scalar", "scalar_one", "scalar_one_or_none"}
_SQL_WRITE = re.compile(r"\b(?:insert\s+into|update|delete\s+from)\s+([a-z_]+)\.[a-z_]+", re.I)


def _class_names(tree: ast.Module, classes: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """Local names bound to a mapped class, and names bound to an `app` module."""
    names: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            for alias in node.names:
                if alias.name in classes:
                    names[alias.asname or alias.name] = alias.name
                else:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    modules.add(alias.asname or alias.name.split(".")[0])
    return names, modules


def _class_of(node: ast.AST, names: dict[str, str], modules: set[str], classes) -> str | None:
    """The mapped class an expression names: `Person` or `mdm_api.Person`."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr in classes:
        root = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in modules:
            return node.attr
    return None


def _queried_class(node: ast.AST, resolve) -> str | None:
    """The class a read chain returns: `db.get(C, …)`, `db.query(C)…first()`,
    `db.execute(select(C)…).scalar_one()`, `db.scalars(select(C))…`."""
    while isinstance(node, (ast.Call, ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"query", "get", "select"} and node.args:
                found = resolve(node.args[0])
                if found:
                    return found
            if name in {"execute", "scalars", "scalar"} and node.args:
                inner = _queried_class(node.args[0], resolve)
                if inner:
                    return inner
            node = func
        else:
            node = node.value
    return None


def _annotation_class(node: ast.AST | None, resolve) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return None
    if isinstance(node, ast.BinOp):  # `C | None`
        return _annotation_class(node.left, resolve) or _annotation_class(node.right, resolve)
    if isinstance(node, ast.Subscript):  # `Optional[C]`, `list[C]`
        return _annotation_class(node.slice, resolve)
    return resolve(node)


def _own_nodes(function: ast.AST):
    """The nodes of a function without those of the functions nested in it — each
    nested function is walked on its own, so a write is counted once."""
    todo = list(ast.iter_child_nodes(function))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            todo.extend(ast.iter_child_nodes(node))


def _foreign_writes_in(function, resolve, schemas: dict[str, str], owner: str):
    """Yield `(class or schema, line, what)` for every write to a class of another owner."""
    typed: dict[str, str] = {}
    for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
        cls = _annotation_class(arg.annotation, resolve)
        if cls:
            typed[arg.arg] = cls
    body = list(_own_nodes(function))
    for node in body:  # first pass: what each local name holds
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                value = node.value
                cls = (
                    resolve(value.func) if isinstance(value, ast.Call) else None
                ) or _queried_class(value, resolve)
                if cls:
                    typed[target.id] = cls
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            cls = _annotation_class(node.annotation, resolve)
            if cls:
                typed[node.target.id] = cls
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            cls = _queried_class(node.iter, resolve)
            if cls:
                typed[node.target.id] = cls

    def instance(expr) -> str | None:
        if isinstance(expr, ast.Name):
            return typed.get(expr.id)
        if isinstance(expr, ast.Call):
            return resolve(expr.func)
        return None

    for node in body:
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            cls = resolve(func)
            if cls:
                yield cls, node.lineno, "constructs"
            elif name in {"add", "delete", "merge"} and isinstance(func, ast.Attribute):
                for arg in node.args[:1]:
                    if isinstance(arg, ast.Name) and arg.id in typed:
                        yield typed[arg.id], node.lineno, f"db.{name}()"
            elif name == "soft_delete" and node.args:
                cls = instance(node.args[0])
                if cls:
                    yield cls, node.lineno, "soft_delete()"
            elif name in {"update", "delete"} and isinstance(func, ast.Attribute):
                cls = _queried_class(func.value, resolve)
                if cls:
                    yield cls, node.lineno, f"bulk .{name}()"
            elif name in {"update", "delete", "insert"} and isinstance(func, ast.Name):
                cls = resolve(node.args[0]) if node.args else None
                if cls:
                    yield cls, node.lineno, f"core {name}()"
            elif (
                name in {"append", "remove", "extend"}
                and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Attribute)
            ):
                cls = instance(func.value.value)
                if cls:
                    yield cls, node.lineno, f"relationship .{name}()"
            elif name == "setattr" and node.args:
                cls = instance(node.args[0])
                if cls:
                    yield cls, node.lineno, "setattr()"
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute):
                    cls = instance(target.value)
                    if cls:
                        yield cls, node.lineno, f"assigns .{target.attr}"
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for match in _SQL_WRITE.finditer(node.value):
                schema = match.group(1).lower()
                if schemas.get(schema, owner) != owner:
                    yield f"schema {schema}", node.lineno, "raw SQL writes"


# Once per process (CR-29 R7): a ratchet test and the meter both ask it.
@functools.cache
def collect_foreign_writes() -> dict[str, str]:
    """A write to a mapped class of domain B outside `app/domains/B/` → key
    `file::function → owner.Class` (CR-13 §B9.3, *no foreign writes*). Reads are free."""
    classes, schemas = _mapped_owners()
    found: dict[str, str] = {}
    for path in _python_files():
        owner = _owner_of_file(path)
        tree = _tree(path)
        names, modules = _class_names(tree, classes)
        if not names and not modules and "insert" not in path.read_text().lower():
            continue

        def resolve(node, names=names, modules=modules):
            return _class_of(node, names, modules, classes)

        functions = [
            n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        qualified = _enclosing(tree)
        for function in functions:
            for cls, line, what in _foreign_writes_in(function, resolve, schemas, owner):
                target = cls if cls.startswith("schema ") else f"{classes[cls]}.{cls}"
                if not cls.startswith("schema ") and classes[cls] == owner:
                    continue
                name = qualified.get(function, function.name)
                key = f"{_rel(path)}::{name} → {target}"
                found.setdefault(
                    key,
                    f"{_rel(path)}:{line} `{name}` {what} `{target}` — a domain's data is "
                    f"written by its owner: call its `api.py` or publish the event it "
                    f"subscribes to (CR-13 §B9.3)",
                )
    return found


# ── 9. One transaction per request, parts (b) and (c) (ratchets) ────────────

_WRITE_CALLS = {"add", "add_all", "delete", "merge", "bulk_save_objects", "bulk_insert_mappings"}


def _is_commit(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    )


_SESSION_NAMES = {"db", "session", "sess", "db_session"}


def _is_session(node: ast.AST) -> bool:
    """`db`, `session`, `self.db`: a receiver that is a session — `seen.add(x)` is not."""
    if isinstance(node, ast.Name):
        return node.id in _SESSION_NAMES
    return isinstance(node, ast.Attribute) and node.attr in _SESSION_NAMES


def _write_in(node: ast.AST) -> tuple[int, str] | None:
    """The first ORM write in a statement: `db.add/delete/merge(...)`, `soft_delete(...)`,
    a bulk `.update()`/`.delete()` on a query, or `db.execute(update|insert|delete(...))`."""
    for n in _own_nodes(node) if not isinstance(node, ast.expr) else ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if isinstance(func, ast.Attribute) and name in _WRITE_CALLS and _is_session(func.value):
            return n.lineno, f"db.{name}()"
        if name == "soft_delete":
            return n.lineno, "soft_delete()"
        if name in {"update", "delete"} and isinstance(func, ast.Attribute):
            receiver = func.value
            if isinstance(receiver, ast.Call) and getattr(receiver.func, "attr", "") in {
                "filter",
                "filter_by",
                "query",
                "where",
            }:
                return n.lineno, f"bulk .{name}()"
        if name == "execute" and n.args and isinstance(n.args[0], ast.Call):
            inner = n.args[0].func
            if getattr(inner, "id", getattr(inner, "attr", "")) in {"update", "insert", "delete"}:
                return n.lineno, "execute(update/insert/delete)"
    return None


def _statement_nodes(stmt: ast.stmt):
    """A statement's own nodes, nested function bodies left out."""
    yield stmt
    yield from _own_nodes(stmt)


def _terminates(block: list[ast.stmt]) -> bool:
    return bool(block) and isinstance(block[-1], (ast.Return, ast.Raise, ast.Continue, ast.Break))


def _writes_after_commit(block: list[ast.stmt], committed: int | None, out: list) -> int | None:
    """Walk a block in order; return the line of a commit that may have happened
    before the block ends (None if none), and collect `(write line, what, commit line)`.

    A branch that ends in `return`/`raise` does not carry its commit past the `if`;
    a sibling branch never sees the other's commit. A loop that commits and writes
    anywhere in its body writes after a commit on the next pass.
    """
    for stmt in block:
        if isinstance(stmt, ast.If):
            after_body = _writes_after_commit(stmt.body, committed, out)
            after_else = _writes_after_commit(stmt.orelse, committed, out)
            carried = [
                c
                for c, branch in ((after_body, stmt.body), (after_else, stmt.orelse))
                if c is not None and not _terminates(branch)
            ]
            committed = carried[0] if carried else (committed if not stmt.orelse else committed)
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            inner = _writes_after_commit(stmt.body, committed, out)
            if inner is not None:
                write = next((w for s in stmt.body for w in [_write_in(s)] if w), None)
                if write:
                    out.append((write[0], write[1] + " (next pass of the loop)", inner))
                committed = inner
            _writes_after_commit(stmt.orelse, committed, out)
            continue
        if isinstance(stmt, (ast.Try, ast.With, ast.AsyncWith)):
            blocks = [stmt.body]
            if isinstance(stmt, ast.Try):
                blocks += [h.body for h in stmt.handlers] + [stmt.orelse, stmt.finalbody]
            for inner_block in blocks:
                result = _writes_after_commit(inner_block, committed, out)
                if result is not None and not _terminates(inner_block):
                    committed = result
            continue
        if committed is not None:
            write = _write_in(stmt)
            if write:
                out.append((write[0], write[1], committed))
        for node in _statement_nodes(stmt):
            if _is_commit(node):
                committed = node.lineno
    return committed


def collect_write_after_commit() -> dict[str, str]:
    """A function that writes after it committed → key `file::function` (§B9.3 (b)).

    One request, one transaction, one commit at the end by the door service: a
    write after a commit is a second transaction, and a failure in it leaves the
    first half stored.
    """
    found: dict[str, str] = {}
    files = _python_files()
    for path in files:
        tree = _tree(path)
        qualified = _enclosing(tree)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            out: list = []
            _writes_after_commit(function.body, None, out)
            if out:
                line, what, commit = out[0]
                name = qualified.get(function, function.name)
                found[f"{_rel(path)}::{name}"] = (
                    f"{_rel(path)}:{line} `{name}` {what} after the commit on line {commit} — "
                    f"one commit, at the end, by the door service (CR-13 §B9.3)"
                )
    return found


def _api_exports(domain: Path) -> dict[str, tuple[Path, ast.Module, ast.FunctionDef]]:
    """The functions a domain's `api.py` exports, resolved to where they are defined."""
    api = domain / "api.py"
    tree = _tree(api)
    exports: dict[str, tuple[Path, ast.Module, ast.FunctionDef]] = {}
    for name, fn in _module_functions(tree).items():
        exports[name] = (api, tree, fn)
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            target = domain / Path(*(node.module or "").split("."))
            target = target.with_suffix(".py") if target.with_suffix(".py").is_file() else None
        else:
            target = _module_path(node.module or "")
        if target is None:
            continue
        functions = _module_functions(_tree(target))
        for alias in node.names:
            fn = functions.get(alias.name)
            if fn is not None:
                exports[alias.asname or alias.name] = (target, _tree(target), fn)
    return exports


def _is_door(path: Path) -> bool:
    """A router or UI module: the doorman of a request, whose door service commits."""
    return (
        path.name in {"main.py", "router.py", "ui.py", "admin_ui.py"}
        or path.stem.endswith(("_router", "_ui"))
        or path.parent == APP / "ui"
    )


def _foreign_api_calls() -> dict[tuple[str, str], str]:
    """(domain, exported name) → one caller in another domain's non-door code
    (a service, a handler, a tool), `file:line`. A router or screen calling another
    domain's service makes that service the door — its commit is the one commit."""
    callers: dict[tuple[str, str], str] = {}
    for path in _python_files():
        if _is_door(path):
            continue
        caller_domain = _owner_of_file(path)
        tree = _tree(path)
        direct: dict[str, tuple[str, str]] = {}
        modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if parts[:2] == ["app", "domains"] and len(parts) == 4 and parts[3] == "api":
                    for alias in node.names:
                        direct[alias.asname or alias.name] = (parts[2], alias.name)
                elif node.module == "app.domains" or (
                    parts[:2] == ["app", "domains"] and len(parts) == 3
                ):
                    for alias in node.names:
                        if alias.name == "api":
                            modules[alias.asname or alias.name] = parts[2]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            target = None
            if isinstance(func, ast.Name) and func.id in direct:
                target = direct[func.id]
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            ):
                target = (modules[func.value.id], func.attr)
            if target and target[0] != caller_domain:
                callers.setdefault(target, f"{_rel(path)}:{node.lineno}")
    return callers


def _own_transaction(function: ast.FunctionDef) -> str | None:
    """The table an `@own_transaction("schema.table", reason)` function declares."""
    for decorator in function.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and getattr(decorator.func, "id", getattr(decorator.func, "attr", ""))
            == "own_transaction"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            return decorator.args[0].value
    return None


def _not_a_command(function: ast.FunctionDef) -> bool:
    """`@own_transaction(..., command=False)`: telemetry, not a consequence (§B4.9)."""
    for decorator in function.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and getattr(decorator.func, "id", getattr(decorator.func, "attr", ""))
            == "own_transaction"
        ):
            return any(
                k.arg == "command" and isinstance(k.value, ast.Constant) and k.value.value is False
                for k in decorator.keywords
            )
    return False


#: The one function whose own transaction is not a command (master CLI, 29 September
#: 2026). A second is red: `command=False` must not become a general way out.
NOT_A_COMMAND = {"domains/chatbot/logbook.py::_store"}


def _mapped_tables() -> dict[str, str]:
    return {m.class_.__name__: m.local_table.fullname for m in _mappers()}


def _own_transaction_problem(
    path: Path, tree: ast.Module, function: ast.FunctionDef, table: str, tables=None
) -> str | None:
    """Why a declared own transaction is not one — or None when it holds.

    It holds when (1) every commit in it is on a session it opened itself
    (`x = SessionLocal()`), never on one it received, and (2) every mapped class it
    builds, types or reaches is the declared table's — at least one, or the gate
    could not see what it writes.
    """
    where = f"{_rel(path) if path.is_relative_to(APP) else path.name}::{function.name}"
    own = {
        target.id
        for node in _own_nodes(function)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", "") == "SessionLocal"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for node in _own_nodes(function):
        if _is_commit(node):
            receiver = node.func.value
            if not (isinstance(receiver, ast.Name) and receiver.id in own):
                return (
                    f"{where}:{node.lineno} is declared an own transaction and commits a "
                    f"session it did not open — the caller's (CR-13 §B9.3)"
                )
    tables = tables if tables is not None else _mapped_tables()
    written: set[str] = set()
    for _p, _t, reached, _via in _reachable(path, tree, function, depth=2):
        for node in ast.walk(reached):
            name = None
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None)
            elif isinstance(node, ast.arg) and isinstance(node.annotation, ast.Name):
                name = node.annotation.id
            if name in tables:
                written.add(tables[name])
    if not written:
        return f"{where} is declared an own transaction on {table} and writes no table the gate can see"
    if written != {table}:
        return (
            f"{where} is declared an own transaction on {table} and writes "
            f"{', '.join(sorted(written))} — a log writes its log table only (CR-13 §B9.3)"
        )
    return None


def collect_commit_behind_api() -> dict[str, str]:
    """A function another domain calls through `api.py` that commits → key
    `domain.api.name` (§B9.3 (c)). The caller owns the transaction; a commit inside
    the callee ends it behind the caller's back."""
    callers = _foreign_api_calls()
    assert len(callers) > 10, f"only {len(callers)} cross-domain api calls — the walk is blind"
    # A package without `api.py` (stt) exports nothing; module shape reports it.
    exports = {p.name: _api_exports(p) for p in _packages() if (p / "api.py").is_file()}
    found: dict[str, str] = {}
    for (domain, name), caller in sorted(callers.items()):
        target = exports.get(domain, {}).get(name)
        if target is None:
            continue
        path, tree, function = target
        for reached_path, reached_tree, reached, via in _reachable(path, tree, function):
            declared = _own_transaction(reached)
            if declared is not None:
                problem = _own_transaction_problem(reached_path, reached_tree, reached, declared)
                if problem is None:
                    continue  # a declared own transaction, checked: not the caller's
                found[f"{domain}.api.{name}"] = problem
                break
            line = _commits(reached)
            if line is not None:
                where = f"{_rel(reached_path)}:{line}"
                found[f"{domain}.api.{name}"] = (
                    f"`{domain}.api.{name}` commits ({where}{' via ' + via if via else ''}) "
                    f"and is called from another domain ({caller}) — the caller's door "
                    f"service commits, once (CR-13 §B9.3)"
                )
                break
    return found


# ── 10. Events, not calls (ratchet; hard for a new package) ─────────────────


#: A change to a mapped collection: `submission.answers.clear()`, `.append(row)`.
_COLLECTION_CALLS = {"append", "extend", "remove", "clear", "pop", "insert"}


def _collection_write_or_flush(node: ast.AST) -> tuple[int, str] | None:
    """A write the ORM persists without `db.add`: a change to a collection reached
    through an attribute (`submission.answers.clear()`), or a `db.flush()` that sends
    what the function changed (#1368). The first shape was the blind spot:
    `forms.api.update_attached` replaced a submission's answers through its
    collection and flushed, and the command walk saw no write at all.

    A collection on a bare name (`rows.append(x)`, `seen.clear()`) is a local list,
    not a mapped one: only an attribute receiver counts."""
    for n in _own_nodes(node) if not isinstance(node, ast.expr) else ast.walk(node):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        name, receiver = n.func.attr, n.func.value
        if name == "flush" and _is_session(receiver):
            return n.lineno, "db.flush()"
        if (
            name in _COLLECTION_CALLS
            and isinstance(receiver, ast.Attribute)
            and not (_is_session(receiver))
        ):
            return n.lineno, f".{receiver.attr}.{name}()"
    return None


def _writes(function: ast.AST) -> int | None:
    """The line of the first ORM write or commit in a function's own body — a
    change through a mapped collection and a flush included (#1368)."""
    for node in _own_nodes(function):
        if _is_commit(node):
            return node.lineno
        if isinstance(node, ast.stmt):
            write = _write_in(node) or _collection_write_or_flush(node)
            if write:
                return write[0]
    return None


@functools.cache
def api_commands() -> dict[tuple[str, str], str]:
    """(domain, name) → where it writes, for every `api.py` export that writes.

    Walked once per process (CR-29 R7): eleven tests ask it, the tree does not
    change while they run, and the walk was the slowest thing in this file.

    A command is derived from the code, not listed next to it (master CLI, 29
    September 2026): an export that writes or commits, itself or through what it
    calls three levels deep (the handler gates' walk). A read — `get_person` — is
    not a command, whatever its name.
    """
    commands: dict[tuple[str, str], str] = {}
    for package in _packages():
        if not (package / "api.py").is_file():
            continue
        for name, (path, tree, function) in _api_exports(package).items():
            for reached_path, _t, reached, via in _reachable(path, tree, function):
                if _not_a_command(reached):
                    continue
                line = _writes(reached)
                if line is not None:
                    commands[(package.name, name)] = (
                        f"{_rel(reached_path)}:{line}{' via ' + via if via else ''}"
                    )
                    break
    domains = {domain for domain, _ in commands}
    assert len(domains) >= 10, f"commands found in only {sorted(domains)} — the walk is blind"
    return commands


# Once per process (CR-29 R7): a ratchet test and the meter both ask it.
@functools.cache
def collect_command_calls_outside_handlers() -> dict[str, str]:
    """A call from domain A into a command of domain B outside a `@subscribe`
    function → key `file::function → B.api.name` (§B4.9, R12). A consequence in
    another domain goes through an event; a read through `api.py` is free."""
    commands = api_commands()
    found: dict[str, str] = {}
    for path in _python_files():
        caller = _owner_of_file(path)
        if caller in {"app", "kernel"}:
            continue  # not a domain: the rule is about domain pairs
        tree = _tree(path)
        direct: dict[str, tuple[str, str]] = {}
        modules: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if parts[:2] == ["app", "domains"] and len(parts) == 4 and parts[3] == "api":
                    for alias in node.names:
                        direct[alias.asname or alias.name] = (parts[2], alias.name)
                elif parts[:2] == ["app", "domains"] and len(parts) == 3:
                    for alias in node.names:
                        if alias.name == "api":
                            modules[alias.asname or alias.name] = parts[2]
        if not direct and not modules:
            continue
        qualified = _enclosing(tree)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # An EVENT handler is exempt and a PORT handler is not, on purpose. An
            # event handler reacts to a fact: its own domain decides what follows,
            # and a command of another domain from there is that domain's doing. A
            # port handler IS a command from outside: were it exempt, a domain could
            # walk into a third one through its own handler, and the port would be a
            # licence instead of a boundary. A port handler that needs another domain
            # calls a port or publishes an event itself.
            if any(_is_subscribe(d) for d in function.decorator_list):
                continue
            for node in _own_nodes(function):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                target = None
                if isinstance(func, ast.Name) and func.id in direct:
                    target = direct[func.id]
                elif (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id in modules
                ):
                    target = (modules[func.value.id], func.attr)
                if not target or target[0] == caller or target not in commands:
                    continue
                name = qualified.get(function, function.name)
                key = f"{_rel(path)}::{name} → {target[0]}.api.{target[1]}"
                found.setdefault(
                    key,
                    f"{_rel(path)}:{node.lineno} `{name}` calls `{target[0]}.api.{target[1]}` "
                    f"(a command: writes at {commands[target]}) — publish an event and let "
                    f"`{target[0]}` subscribe (CR-13 §B4.9)",
                )
    return found


# ── 14. Ports: a synchronous command between domains (architecture §3.2.1 step 2) ──
#
# A port is a contract in `kernel/contracts/<owner>.py` (a subclass of `Port`) with
# exactly one handler (`@handles(ThePort)`) in the owner's domain; a caller in
# another domain goes through `kernel.ports.call(ThePort(...), db)`. What the gates
# hold, and where:
#
# - a call through `kernel.ports.call` is no command call (it calls no `api.py`), and
#   a command through another domain's `api.py` outside an event handler stays red —
#   `collect_command_calls_outside_handlers`, unchanged;
# - a port handler is no licence there — see the comment at that collector's exemption;
# - a port handler does not commit and reaches no network — `_event_handlers`;
# - every port has exactly one handler, at home; a contract carries plain values
#   only; a port is called from a service or a handler, never from a door — below.
#
# A repository without a port is in order as long as nothing handles or calls one;
# "found nothing" is accepted only together with "nothing asks for one".

#: What a contract's field may be: a plain value, or a dataclass of `kernel/contracts/`.
_PLAIN = {"int", "str", "bool", "float", "bytes", "None", "date", "datetime", "Decimal"}
_PLAIN_GENERICS = {"Optional", "tuple"}


def _contracts_dir() -> Path:
    return APP / "kernel" / "contracts"


def _annotation_offences(annotation: ast.AST | None, contract_classes: set[str]) -> list[str]:
    """The names in an annotation that are no plain value — looked for inside
    generics and unions too (`tuple[Form, ...]`, `Form | None`, `"Form"`)."""
    if annotation is None:
        return ["an unannotated field"]
    if isinstance(annotation, ast.Constant):
        if annotation.value is None or annotation.value is Ellipsis:
            return []
        if isinstance(annotation.value, str):
            return _annotation_offences(
                ast.parse(annotation.value, mode="eval").body, contract_classes
            )
        return [repr(annotation.value)]
    if isinstance(annotation, ast.Name):
        known = _PLAIN | _PLAIN_GENERICS | contract_classes
        return [] if annotation.id in known else [annotation.id]
    if isinstance(annotation, ast.Attribute):
        return [] if annotation.attr in _PLAIN else [ast.unparse(annotation)]
    if isinstance(annotation, ast.Subscript):
        outer = _annotation_offences(annotation.value, contract_classes)
        inner = annotation.slice
        parts = inner.elts if isinstance(inner, ast.Tuple) else [inner]
        return outer + [o for part in parts for o in _annotation_offences(part, contract_classes)]
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotation_offences(annotation.left, contract_classes) + _annotation_offences(
            annotation.right, contract_classes
        )
    return [ast.unparse(annotation)]


def collect_port_findings() -> list[str]:
    """Hard, without a baseline: what is wrong with the ports, their handlers, their
    contracts and their callers."""
    contracts = _contracts_dir()
    modules = sorted(p for p in contracts.glob("*.py") if p.name != "__init__.py")
    assert modules, f"no contract modules under {contracts} — the walk is blind"

    classes: dict[str, tuple[Path, ast.ClassDef]] = {}
    for path in modules:
        for node in _tree(path).body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = (path, node)

    def is_port(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name == "Port":
            return True
        if name not in classes or name in seen:
            return False
        bases = [getattr(b, "attr", getattr(b, "id", "")) for b in classes[name][1].bases]
        return any(is_port(base, seen | {name}) for base in bases)

    ports = {name: where for name, where in classes.items() if is_port(name)}
    findings: list[str] = []

    handlers: dict[str, list[tuple[Path, ast.FunctionDef]]] = {}
    callers: list[tuple[Path, int]] = []
    for path in _python_files():
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if (
                        _is_handles(decorator)
                        and isinstance(decorator, ast.Call)
                        and decorator.args
                    ):
                        handlers.setdefault(ast.unparse(decorator.args[0]), []).append((path, node))
            if (
                isinstance(node, (ast.Import, ast.ImportFrom))
                and "kernel" not in path.relative_to(APP).parts[:1]
            ):
                named = [a.name for a in node.names]
                module = getattr(node, "module", "") or ""
                if (
                    module == "app.kernel.ports"
                    or "app.kernel.ports" in named
                    or (module == "app.kernel" and "ports" in named)
                ):
                    callers.append((path, node.lineno))

    # Rule 2: exactly one handler per port, in the domain its contract file is named after.
    for name, (contract, _cls) in sorted(ports.items()):
        owner = contract.stem
        found = handlers.get(name, [])
        if not found:
            findings.append(
                f"port `{name}` ({_rel(contract)}) has no handler — `@handles({name})` belongs "
                f"in `domains/{owner}/handlers.py`"
            )
        if len(found) > 1:
            where = ", ".join(sorted(f"{_rel(p)}::{fn.name}" for p, fn in found))
            findings.append(
                f"port `{name}` has {len(found)} handlers ({where}) — a port has exactly one"
            )
        for path, function in found:
            if _owner_of_file(path) != owner:
                findings.append(
                    f"{_rel(path)}::{function.name} handles port `{name}`, whose contract is "
                    f"`{owner}`'s — the handler lives in the owner's domain"
                )
    for name, found in sorted(handlers.items()):
        if name not in ports:
            for path, function in found:
                findings.append(
                    f"{_rel(path)}::{function.name} handles `{name}`, which is no `Port` of "
                    f"`kernel/contracts/`"
                )

    # Rule 5: a contract carries plain values — the port, what it holds, and its outcome.
    judged: set[str] = set()

    def judge(name: str) -> None:
        if name in judged or name not in classes:
            return
        judged.add(name)
        path, cls = classes[name]
        for stmt in cls.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                findings.append(
                    f"{_rel(path)}:{stmt.lineno} `{name}.{stmt.name}` is a method — a contract "
                    f"is data only: what builds it or reads it lives in the domain that does"
                )
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                continue
            for offence in _annotation_offences(stmt.annotation, set(classes)):
                findings.append(
                    f"{_rel(path)}:{stmt.lineno} `{name}.{stmt.target.id}` carries `{offence}` — a "
                    f"contract carries plain values, tuples of them, or dataclasses of "
                    f"`kernel/contracts/` (no ORM object, no schema of a domain, no list or dict)"
                )
            for inner in ast.walk(stmt.annotation):
                if isinstance(inner, ast.Name):
                    judge(inner.id)

    for name in sorted(ports):
        judge(name)
        for path, function in handlers.get(name, []):
            outcome = function.returns
            outcome_name = getattr(outcome, "id", None)
            if outcome_name not in classes:
                findings.append(
                    f"{_rel(path)}::{function.name} returns "
                    f"`{ast.unparse(outcome) if outcome else 'nothing declared'}` — a port's "
                    f"outcome is a dataclass of `kernel/contracts/`"
                )
            else:
                judge(outcome_name)

    # Rule 6: called from a service or a handler, never from a door.
    for path, line in callers:
        if _is_door(path):
            findings.append(
                f"{_rel(path)}:{line} imports `kernel.ports` — a port is called from a service "
                f"or a handler; a router or a screen calls its own domain's service"
            )
    # Nothing found is in order only when nothing asks for a port.
    if not ports and callers:
        where = ", ".join(sorted(f"{_rel(p)}:{line}" for p, line in callers))
        findings.append(
            f"`kernel.ports` is imported ({where}) and `kernel/contracts/` defines no `Port`"
        )
    return findings


# ── 11. No rule in a router (ratchet with a reason per entry) ───────────────

# The doorman's own refusals — not a business rule: not found, not logged in, not
# allowed, too many requests (§B9.3). CSRF refuses with 403 and is covered by it.
_DOORMAN_STATUS = {401, 403, 404, 405, 429}
_ERROR_HELPERS = {"_fout", "_error", "fout", "error_response"}
_ERROR_KEYS = {"error", "fout", "foutmelding", "fout_veld_id"}


def _status_of(raise_: ast.Raise) -> int | None:
    call = raise_.exc
    if not isinstance(call, ast.Call):
        return None
    for keyword in call.keywords:
        if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
        if keyword.arg == "status_code" and isinstance(keyword.value, ast.Attribute):
            digits = re.search(r"HTTP_(\d{3})", keyword.value.attr)
            return int(digits.group(1)) if digits else None
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, int):
        return call.args[0].value
    return None


def _refusal_in(block: list[ast.stmt]) -> tuple[int, str] | None:
    """A refusal that is not the doorman's: a raise (other than 401/403/404/405/429)
    or an error helper, directly in the branch."""
    for stmt in block:
        for node in _statement_nodes(stmt):
            if isinstance(node, ast.If):
                break  # a nested `if` is judged on its own test
            if isinstance(node, ast.Raise):
                if node.exc is None or (
                    isinstance(node.exc, ast.Name) and node.exc.id.startswith("_")
                ):
                    continue  # a re-raise, or a private signal for control flow
                status = _status_of(node)
                if status is not None and status >= 500:
                    continue  # a failure upstream (the payment provider), not a refusal
                if status not in _DOORMAN_STATUS:
                    return node.lineno, f"raises{f' {status}' if status else ''}"
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in _ERROR_HELPERS:
                return node.lineno, f"{node.func.id}()"
            # A screen refuses by showing the form again with a message:
            # `ctx["error"] = "…"`, or a view-model built with `error="…"`.
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value in _ERROR_KEYS
                        and _is_message(node.value)
                    ):
                        return node.lineno, f"sets [{target.slice.value!r}]"
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg in _ERROR_KEYS and _is_message(keyword.value):
                        return node.lineno, f"shows {keyword.arg}="
    return None


def _is_message(node: ast.AST) -> bool:
    """A message written at the door — `"…"` or `_("…")`. A variable passes on a
    refusal someone else decided (`error=_upload_error(exc)`), which is not a rule here."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_" and node.args:
        node = node.args[0]
    return isinstance(node, (ast.Constant, ast.JoinedStr)) and bool(getattr(node, "value", True))


# The doorman's own checks are the TRANSPORT, and nothing else (CR-13 phase 4c, #1251;
# `docs/code-style.md`, *A rule has one home*). Three shapes, told by what the
# condition reads — never by a list of entries:
#
# 1. **a file**: the condition reads only an `UploadFile` parameter (the parameter
#    itself, or its `filename`, `content_type`, `size`) or the bytes read from one
#    (`data = await file.read()`), beside constants;
# 2. **a parse**: the refusal stands in the `except ValueError` of a `try` that
#    does nothing but parse (`int()`, `float()`, `Decimal()`, a date);
# 3. **a token's age**: a clock minus a moment, compared with a constant.
#
# Everything else that refuses at a door is a rule and has its home in the service
# or on the entity — also the emptiness of a text. "An empty title" and "an empty
# question" look alike at the door and are alike: neither is transport, so neither
# is excepted; the question's rule lives in `chatbot.service.asked`, the title's
# on its entity. There is no fourth shape for "a text that is not stored": what a
# condition reads is visible, where a text goes afterwards is not.
_UPLOAD_ATTRS = {"filename", "content_type", "size"}
_PARSERS = {"int", "float", "Decimal", "fromisoformat", "strptime"}
_PARSE_ERRORS = {"ValueError", "InvalidOperation", "TypeError"}
_CLOCKS = {"time.monotonic", "time.time"}
_CONSTANT = re.compile(r"_?[A-Z][A-Z0-9_]*$")


def _files_of(function: ast.AST) -> tuple[set[str], set[str]]:
    """The `UploadFile` parameters of a function, and the names that hold bytes
    read from one of them."""
    args = function.args
    files = {
        a.arg
        for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
        if a.annotation is not None and "UploadFile" in ast.unparse(a.annotation)
    }
    read: set[str] = set()
    for node in ast.walk(function):
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        value = node.value.value if isinstance(node.value, ast.Await) else node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "read"
        ):
            continue
        source = value.func.value
        if isinstance(source, ast.Attribute) and source.attr == "file":
            source = source.value
        if isinstance(source, ast.Name) and source.id in files:
            read.add(node.targets[0].id)
    return files, read


def _reads_only_a_file(test: ast.expr, files: set[str], read: set[str]) -> bool:
    names = [n for n in ast.walk(test) if isinstance(n, ast.Name)]
    if not any(n.id in files or n.id in read for n in names):
        return False
    for name in names:
        if name.id not in files and name.id not in read and name.id != "len":
            if not _CONSTANT.match(name.id):
                return False
    for node in ast.walk(test):
        if not isinstance(node, ast.Attribute):
            continue
        root: ast.AST = node
        chain = []
        while isinstance(root, ast.Attribute):
            chain.append(root.attr)
            root = root.value
        while isinstance(root, ast.Call):  # `file.filename.lower().endswith(…)`
            root = root.func
            while isinstance(root, ast.Attribute):
                chain.append(root.attr)
                root = root.value
        if not isinstance(root, ast.Name) or root.id not in files:
            return False  # an attribute of the bytes, or of anything that is no file
        if chain[-1] not in _UPLOAD_ATTRS:
            return False
    return True


def _is_parser(call: ast.AST) -> bool:
    if not isinstance(call, ast.Call):
        return False
    name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
    return name in _PARSERS


def _refuses_a_parse(node: ast.If) -> bool:
    """Every refusal of this `if` stands in the `except` of a `try` that only parses."""
    tries = [s for s in node.body if isinstance(s, ast.Try)]
    rest = [s for s in node.body if not isinstance(s, ast.Try)]
    if not tries or _refusal_in(rest):
        return False
    for attempt in tries:
        parses = all(
            isinstance(s, (ast.Assign, ast.Expr)) and _is_parser(s.value) for s in attempt.body
        )
        caught = {
            n.id
            for h in attempt.handlers
            for n in ast.walk(h.type or ast.Name(id="Exception"))
            if isinstance(n, ast.Name)
        } | {
            n.attr
            for h in attempt.handlers
            for n in ast.walk(h.type or ast.Name(id="Exception"))
            if isinstance(n, ast.Attribute)
        }
        if not parses or not caught or not caught <= _PARSE_ERRORS:
            return False
    return True


def _is_a_tokens_age(test: ast.expr) -> bool:
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return False
    if not isinstance(test.ops[0], (ast.Gt, ast.GtE)):
        return False
    left, limit = test.left, test.comparators[0]
    if not (isinstance(left, ast.BinOp) and isinstance(left.op, ast.Sub)):
        return False
    clock = left.left
    if not (isinstance(clock, ast.Call) and ast.unparse(clock.func) in _CLOCKS):
        return False
    return isinstance(limit, ast.Constant) or (
        isinstance(limit, ast.Name) and bool(_CONSTANT.match(limit.id))
    )


def transport_shape(node: ast.If, function: ast.AST | None) -> str | None:
    """The shape that makes this refusal the doorman's own, or None when it is a rule."""
    if _is_a_tokens_age(node.test):
        return "a token's age"
    if _refuses_a_parse(node):
        return "a parse"
    if function is not None:
        files, read = _files_of(function)
        if (files or read) and _reads_only_a_file(node.test, files, read):
            return "a file"
    return None


def _functions_around(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Every node → the innermost function around it."""
    around: dict[ast.AST, ast.AST] = {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(function):
                if node is not function:
                    around[node] = function
    return around


def collect_rule_in_router() -> dict[str, str]:
    """An `if` that refuses, in a router or UI module → key `file::function::condition`
    (§B9.3); the doorman's own refusals — 401, 403, 404, 405, 429, and a check of the
    transport (`transport_shape`) — excepted. A rule at the door holds for that door
    only; the service's rule holds for every entrance."""
    found: dict[str, str] = {}
    shapes: dict[str, int] = {}
    doors = [p for p in _python_files() if _is_door(p) and p.name != "main.py"]
    assert len(doors) > 30, f"only {len(doors)} router/UI modules — the walk is blind"
    for path in doors:
        tree = _tree(path)
        qualified = _enclosing(tree)
        around = _functions_around(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            refusal = _refusal_in(node.body)
            shape = transport_shape(node, around.get(node)) if refusal else None
            if shape:
                shapes[shape] = shapes.get(shape, 0) + 1
                continue
            if refusal:
                name = qualified.get(node, "<module>")
                condition = ast.unparse(node.test)
                found.setdefault(
                    f"{_rel(path)}::{name}::{condition}",
                    f"{_rel(path)}:{refusal[0]} `{name}` decides on `{condition}` and "
                    f"{refusal[1]} — a rule belongs to the entity or its service, where "
                    f"every entrance meets it (CR-13 §B9.3)",
                )
    # The exception is alive only while each shape still meets real code: a shape
    # that finds nothing excuses nothing, and would hide that its reader broke.
    assert set(shapes) == {"a file", "a parse", "a token's age"}, (
        f"the transport shapes found in the doors: {shapes} — one of the three is blind"
    )
    return found


# ── 12. One entrance rule (a hard, b and c ratchets) ─────────────────────────


def _handler_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_subscribe(d) for d in n.decorator_list)
    ]


def collect_write_outside_service() -> dict[str, str]:
    """A router, UI module or event handler that constructs or assigns a mapped class
    → key `file::function → owner.Class` (§B9.3 (b)). The write belongs in a service,
    where the aggregate's `check()` runs on flush for every entrance alike."""
    classes, schemas = _mapped_owners()
    found: dict[str, str] = {}
    for path in _python_files():
        tree = _tree(path)
        functions = (
            [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if _is_door(path)
            else _handler_functions(tree)
        )
        if not functions:
            continue
        names, modules = _class_names(tree, classes)
        qualified = _enclosing(tree)

        def resolve(node, names=names, modules=modules):
            return _class_of(node, names, modules, classes)

        for function in functions:
            for cls, line, what in _foreign_writes_in(function, resolve, {}, owner=""):
                if cls.startswith("schema "):
                    continue
                name = qualified.get(function, function.name)
                found.setdefault(
                    f"{_rel(path)}::{name} → {classes[cls]}.{cls}",
                    f"{_rel(path)}:{line} `{name}` {what} `{classes[cls]}.{cls}` outside a "
                    f"service — move the write to the service; `check()` runs on flush "
                    f"(CR-13 §B9.3)",
                )
    return found


# Once per process (CR-29 R7): a ratchet test and the meter both ask it.
@functools.cache
def collect_non_orm_writes() -> dict[str, str]:
    """A write that bypasses the ORM flush → key `file::function → target` (§B9.3 (c),
    the entrances discovery of §B10): a bulk `.update()`/`.delete()` on a query, a core
    `insert`/`update`/`delete`, raw SQL that writes a table. None of them passes
    `before_flush`, so an aggregate's `check()` never sees them. What the walk cannot
    see: a statement built with `getattr` or assembled from strings at runtime."""
    classes, schemas = _mapped_owners()
    found: dict[str, str] = {}
    for path in _python_files():
        tree = _tree(path)
        names, modules = _class_names(tree, classes)
        qualified = _enclosing(tree)

        def resolve(node, names=names, modules=modules):
            return _class_of(node, names, modules, classes)

        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for cls, line, what in _foreign_writes_in(function, resolve, schemas, owner=""):
                if not (what.startswith(("bulk", "core", "raw SQL"))):
                    continue
                target = cls if cls.startswith("schema ") else f"{classes[cls]}.{cls}"
                name = qualified.get(function, function.name)
                found.setdefault(
                    f"{_rel(path)}::{name} → {target}",
                    f"{_rel(path)}:{line} `{name}` {what} `{target}` past the ORM — no "
                    f"`check()` runs on it; write through the aggregate (CR-13 §B9.3)",
                )
    return found


# ── 13. One owner per derived value (ratchet) ───────────────────────────────


def _names_in(node: ast.AST) -> set[str]:
    """Every attribute and variable name an expression reads."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Name):
            out.add(n.id)
    return out


def _is_total_shape(node: ast.AST) -> bool:
    """`quantity * price` in either order — a registration line's subtotal."""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)):
        return False
    left, right = _names_in(node.left), _names_in(node.right)
    both = left | right
    return any("quantity" in n for n in both) and any("price" in n for n in both)


def _is_paid_sum(node: ast.AST) -> bool:
    """`sum(... amount_paid ...)` — the paid side of a registration's balance."""
    return (
        isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "sum"
        and any("amount_paid" in _names_in(a) for a in node.args)
    )


def _is_record_state_decision(node: ast.AST) -> bool:
    """A branch on a record's `status` that reads `amount_paid` inside it — the shape
    of "pending, but partly paid". Comparing `amount` with `amount_paid` to correct a
    charge is a write, not a state, and does not match."""
    if not isinstance(node, (ast.If, ast.IfExp)) or "status" not in _names_in(node.test):
        return False
    body = node.body if isinstance(node, ast.If) else [ast.Expr(node.body)]
    paid = {"amount_paid"}
    for stmt in body:  # `betaald = record.amount_paid` makes `betaald` the paid amount
        for n in ast.walk(stmt):
            if isinstance(n, ast.Assign) and "amount_paid" in _names_in(n.value):
                paid |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return any(
        isinstance(n, ast.Compare) and paid & _names_in(n) for stmt in body for n in ast.walk(stmt)
    )


def _is_deadline_decision(node: ast.AST) -> bool:
    """Today compared with a deadline or an end date — whether registration is open."""
    if not isinstance(node, ast.Compare):
        return False
    if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub) for n in ast.walk(node)):
        return False  # a distance to a deadline ("near") is not open or closed
    names = {n.lower() for n in _names_in(node)}
    today = any(n in {"today", "vandaag", "belgian_today"} for n in names)
    deadline = any(("deadline" in n or "closes_on" in n or "effective_end" in n) for n in names)
    return today and deadline


DERIVED_SHAPES = {
    "registration.total": _is_total_shape,
    "registration.balance": _is_paid_sum,
    "payment_record.state": _is_record_state_decision,
    "registration.state": _is_deadline_decision,
}


def _owner_functions(value) -> set[tuple[Path, str]]:
    """The owner function of a derived value and what it calls in its own module —
    `_line` and `_telt_mee` are part of `compute_registration_total`."""
    module, _, name = value.today.rpartition(".")
    path = _module_path(module)
    assert path is not None, f"the owner of {value.name} ({value.today}) does not exist"
    tree = _tree(path)
    function = _module_functions(tree).get(name)
    assert function is not None, f"{value.today} is not a function in {_rel(path)}"
    return {(p, fn.name) for p, _t, fn, _via in _reachable(path, tree, function) if p == path}


# Once per process (CR-29 R7): a ratchet test and the meter both ask it.
@functools.cache
def collect_derived_value_elsewhere() -> dict[str, str]:
    """A second computation of a registered derived value outside its owner → key
    `file::function → value` (§B9.3, *one owner per derived value*). Python only: a
    template that computes is not walked — say so, do not assume it is clean."""
    from app.kernel import rules

    values = rules.derived_values()
    assert set(values) == set(DERIVED_SHAPES), (
        "every registered derived value needs its shape here, and every shape a value: "
        f"{sorted(set(values) ^ set(DERIVED_SHAPES))}"
    )
    owners = {name: _owner_functions(value) for name, value in values.items()}
    # A shape that does not even recognise its owner looks nowhere (#678).
    for name, shape in DERIVED_SHAPES.items():
        assert any(
            shape(n)
            for path, fn_name in owners[name]
            for fn in [_module_functions(_tree(path)).get(fn_name)]
            if fn is not None
            for n in _own_nodes(fn)
        ), f"the shape of {name} does not match its own owner — the gate is blind to it"
    found: dict[str, str] = {}
    for path in _python_files():
        tree = _tree(path)
        qualified = _enclosing(tree)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for name, shape in DERIVED_SHAPES.items():
                if (path, function.name) in owners[name]:
                    continue
                hit = next((n for n in _own_nodes(function) if shape(n)), None)
                if hit is not None:
                    fn = qualified.get(function, function.name)
                    found.setdefault(
                        f"{_rel(path)}::{fn} → {name}",
                        f"{_rel(path)}:{hit.lineno} `{fn}` computes `{name}` a second time — "
                        f"its owner is `{values[name].today}`; ask it (CR-13 §B9.3)",
                    )
    return found


# ── 14. Promise kept (two ratchets: not kept, and not walkable with a reason) ─

# A template input that promises something, as the kit macro or as raw HTML.
_MACRO_PROMISE = re.compile(
    r"ui\.(?:input_control|select_control|textarea_control|input|select|textarea)"
    r'\(\s*"(?P<name>[a-z_0-9]+)"(?P<rest>[^\n]*)'
)
_RAW_INPUT = re.compile(r"<(?:input|select|textarea)\b(?P<attrs>[^>]*)>", re.S)
_FORM_TARGET = re.compile(r'<form\b[^>]*?(?:hx-post|action)="([^"]+)"', re.S)
_PROMISE_KINDS = ("required", "pattern", "min")
#: `{# promise walked by: test_a, test_b #}` — on the line of the input or the one above.
_WALKED_BY = re.compile(r"\{#\s*promise walked by:\s*([a-z0-9_,\s]+?)\s*#\}")


def _declared_walkers(text: str, position: int) -> tuple[str, ...]:
    """The tests an input names as walking its promise: the declaration stands on
    the input's own line or on the line above it, nowhere else — so it moves with
    the input and disappears with it."""
    start = text.rfind("\n", 0, position) + 1
    above = text.rfind("\n", 0, max(start - 1, 0)) + 1
    end = text.find("\n", position)
    found = _WALKED_BY.search(text, above, end if end != -1 else len(text))
    if not found:
        return ()
    return tuple(name for name in re.split(r"[,\s]+", found.group(1)) if name)


def _template_promises(text: str):
    """Yield `(line, field, kinds, form path, declared walkers)` for every promising input."""
    forms = [(m.start(), m.group(1)) for m in _FORM_TARGET.finditer(text)]

    def form_for(position: int) -> str | None:
        before = [path for start, path in forms if start < position]
        return before[-1] if before else None

    for m in _MACRO_PROMISE.finditer(text):
        rest = m.group("rest")
        kinds = [k for k in _PROMISE_KINDS if re.search(rf"\b{k}\s*=\s*(True|\")", rest)]
        if kinds:
            yield (
                text.count("\n", 0, m.start()) + 1,
                m.group("name"),
                kinds,
                form_for(m.start()),
                _declared_walkers(text, m.start()),
            )
    for m in _RAW_INPUT.finditer(text):
        attrs = m.group("attrs")
        name = re.search(r'\bname="([a-z_0-9]+)"', attrs)
        # The attribute, not a word inside another attribute's value or inside the
        # Jinja between them: the form builder's tick, `<input type="checkbox"
        # name="required" {% if f.required %}checked{% endif %}>`, promises nothing.
        bare = re.sub(r'"[^"]*"|\'[^\']*\'', '""', attrs)
        bare = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", bare, flags=re.S)
        kinds = [k for k in _PROMISE_KINDS if re.search(rf"(?<![-\w]){k}\b(?!-)", bare)]
        if name and kinds:
            yield (
                text.count("\n", 0, m.start()) + 1,
                name.group(1),
                kinds,
                form_for(m.start()),
                _declared_walkers(text, m.start()),
            )


def _route_path(path: str) -> str:
    """`/admin/x/{{ a.id }}/y?z` and `/admin/x/{a_id}/y` → `/admin/x/{}/y`."""
    path = re.sub(r"\{\{.*?\}\}", "{}", path)
    path = re.sub(r"\{[a-z_0-9:]+\}", "{}", path)
    path = re.sub(r"'\s*~\s*[^~]+~\s*'", "{}", path)
    return path.split("?")[0].rstrip("/") or "/"


def _writing_routes() -> dict[str, tuple[ast.FunctionDef, dict[str, ast.AST]]]:
    """Each writing route by its path, with the module-level functions of its module:
    the helpers it may delegate to (`_route_source`)."""
    routes: dict[str, tuple[ast.FunctionDef, dict[str, ast.AST]]] = {}
    for path in _python_files():
        tree = _tree(path)
        helpers = {
            n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.decorator_list:
                    if (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Attribute)
                        and d.func.attr in {"post", "put", "patch"}
                        and d.args
                        and isinstance(d.args[0], ast.Constant)
                        and isinstance(d.args[0].value, str)
                    ):
                        routes.setdefault(_route_path(d.args[0].value), (node, helpers))
    assert len(routes) > 50, f"only {len(routes)} writing routes — the walk is blind"
    return routes


def _route_source(route: ast.AST, helpers: dict[str, ast.AST]) -> str:
    """The code a route runs for its form: its own body, and the body of the
    module-level function of the same module it delegates to (#1535).

    Delegating means returning that function's result — `return f(...)` or
    `return await f(...)` — the shape of one save path behind two routes (a
    platform screen and a workspace's own one). **One level, same module, and
    nothing else:** a helper the route merely calls along the way is not
    followed, and neither is a function the helper delegates to in turn. Further
    than that the walk would read code the route does not run for this form,
    and a promise could turn green on a field some other helper happens to name.
    `test_the_walk_follows_one_delegation_and_no_further` holds these limits.
    """
    delegates = []
    for node in ast.walk(route):
        if isinstance(node, ast.Return) and node.value is not None:
            call = node.value.value if isinstance(node.value, ast.Await) else node.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                helper = helpers.get(call.func.id)
                if helper is not None and helper is not route:
                    delegates.append(helper)
    return "\n".join([ast.unparse(route), *(ast.unparse(h) for h in delegates)])


def _kept_columns() -> tuple[dict[str, bool], set[str]]:
    """Column name → kept at an address (NOT NULL, a CHECK naming it, a validator) on
    any mapped class; and the field names a Pydantic schema constrains."""
    from sqlalchemy import CheckConstraint

    columns: dict[str, bool] = {}
    for mapper in _mappers():
        table = mapper.local_table
        checks = " ".join(
            str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)
        )
        for column in table.columns:
            kept = (
                not column.nullable
                or re.search(rf"\b{column.name}\b", checks) is not None
                or column.key in mapper.validators
            )
            columns[column.key] = columns.get(column.key, False) or kept
    schema: set[str] = set()
    constraint = re.compile(r"min_length|constr\(|EmailStr|Field\(\.\.\.|pattern=|ge=|gt=")
    for path in _python_files():
        for cls in ast.walk(_tree(path)):
            if not isinstance(cls, ast.ClassDef):
                continue
            if "BaseModel" not in {getattr(b, "id", getattr(b, "attr", "")) for b in cls.bases}:
                continue
            for stmt in cls.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if constraint.search(ast.unparse(stmt)):
                        schema.add(stmt.target.id)
    return columns, schema


@functools.cache
def _test_functions() -> dict[str, tuple[str, ...]]:
    """Every test function of the suite by its name, with its source — a name may
    stand in more than one file, which is why the value is a tuple."""
    found: dict[str, list[str]] = {}
    files = [*(BACKEND / "tests").rglob("test_*.py"), *DOMAINS.glob("*/tests/**/test_*.py")]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                found.setdefault(node.name, []).append(ast.unparse(node))
    assert len(found) > 2000, f"only {len(found)} test functions found — the walk is blind"
    return {name: tuple(sources) for name, sources in found.items()}


def _judge_promise(
    reason: str | None, walkers: tuple[str, ...], field: str, tests: dict[str, tuple[str, ...]]
) -> str | None:
    """What is wrong with a promise the static walk stopped on (`reason`) or
    followed to its column (`reason is None`), given the tests its input declares.
    `None` means: in order.

    - stopped, nothing declared → the step where the walk stops, as before;
    - stopped, declared → every named test exists exactly once and names the field;
    - followed, declared → the declaration is not needed and must go.

    **What this cannot prove:** that the named test really posts an empty value to
    the form this input stands in. It checks that the test exists, once, and names
    the field — so a renamed or deleted test turns the gate red, and a test that
    never mentions the field does not count. That the test walks THIS promise is
    review's, which is why the failure message asks for it in the test's docstring.
    """
    if reason is None:
        if walkers:
            return (
                f"declares `promise walked by: {', '.join(walkers)}` although the walk follows "
                f"it to its column — remove the declaration"
            )
        return None
    if not walkers:
        return reason
    problems = []
    for walker in walkers:
        sources = tests.get(walker, ())
        if len(sources) != 1:
            problems.append(
                f"`{walker}` is the name of {len(sources)} test functions — it must be exactly one"
            )
        elif not re.search(rf"['\"]{field}['\"]", sources[0]):
            problems.append(f"`{walker}` does not name the field `{field}`")
    if not problems:
        return None
    return (
        f"{reason}; declared walked by {', '.join(walkers)}, but "
        + "; ".join(problems)
        + " — name the test that posts what the browser refuses to the form this input stands "
        "in (one per form for a partial in several), and say in its docstring which form and "
        "route it walks and that it posts an empty value"
    )


def collect_promises() -> tuple[dict[str, str], dict[str, str]]:
    """Every `required`/`pattern`/`min` a template promises, walked to the column (§B9.3,
    *promise kept*; the spike of §B10): template → the form's `hx-post`/`action` →
    the route → the field read by name → a column of that name → kept by `NOT NULL`,
    a `CHECK`, a validator or a Pydantic constraint.

    Returns `(not_kept, unwalkable)`, keyed `template::field::kinds`. `not_kept` walks
    all the way and finds nothing that keeps the promise — the server accepts what the
    browser refuses. `unwalkable` stops earlier; its value is the step where it stops,
    the reason the change request asks for.

    A promise the static walk cannot follow — the field is no column, the form's
    target is a variable, the input stands in a partial — is walked by a test
    instead, and the input says which: `{# promise walked by: test_name #}` on its
    own line or the line above (`_judge_promise`). No list beside the source: the
    declaration lives at the promise.
    """
    routes = _writing_routes()
    columns, schema = _kept_columns()
    tests = _test_functions()
    templates = sorted(APP.rglob("templates/**/*.html"))
    assert len(templates) > 100, f"only {len(templates)} templates — the walk is blind"
    not_kept: dict[str, str] = {}
    unwalkable: dict[str, str] = {}
    seen = 0
    for template in templates:
        for line, name, kinds, form_path, walkers in _template_promises(template.read_text()):
            seen += 1
            key = f"{_rel(template)}::{name}::{'/'.join(kinds)}"
            where = f"{_rel(template)}:{line}"
            reason: str | None = None
            entry = routes.get(_route_path(form_path)) if form_path else None
            if not form_path:
                reason = "no form target (built in JS, by a macro, or GET)"
            elif entry is None:
                reason = f"no writing route for {_route_path(form_path)}"
            else:
                route, helpers = entry
                source = _route_source(route, helpers)
                if not re.search(rf"['\"]{name}['\"]|\b{name}\s*[:=]", source):
                    reason = f"route `{route.name}` does not read `{name}` by name"
                elif name not in columns and name not in schema:
                    reason = f"no column named `{name}`"
                elif name in columns and not (columns[name] or name in schema):
                    if not walkers:
                        not_kept.setdefault(
                            key,
                            f"{where} promises `{name}` {'/'.join(kinds)}; the column `{name}` "
                            f"has no NOT NULL, CHECK, validator or schema constraint — the "
                            f"server accepts what the browser refuses (CR-13 §B9.3)",
                        )
                        continue
                    # Followed to a column that keeps nothing, and a test is declared:
                    # the rule lives in the service, and the test is what shows it.
                    reason = f"the column `{name}` keeps nothing itself"
            judged = _judge_promise(reason, walkers, name, tests)
            if judged is not None:
                unwalkable.setdefault(key, judged)
    assert seen > 30, f"only {seen} promises in the templates — the walk is blind"
    return not_kept, unwalkable


def collect_promise_not_kept() -> dict[str, str]:
    return collect_promises()[0]


def collect_promise_unwalkable() -> dict[str, str]:
    found = collect_promises()[1]
    return {key: f"{key} — cannot be walked: {reason}" for key, reason in found.items()}


# ── The ratchet shape ────────────────────────────────────────────────────────

COLLECTORS = {
    "SESSION_ON_ENTITY": collect_session_on_entity,
    "MODULE_SHAPE": collect_module_shape,
    "COMMIT_IN_HANDLER": collect_commit_in_handler,
    "NETWORK_IN_HANDLER": collect_network_in_handler,
    "JSON_ROUTE_WITHOUT_CALLER": collect_json_route_without_caller,
    "DUTCH_IDENTIFIERS": collect_dutch_identifiers,
    "FOREIGN_WRITES": collect_foreign_writes,
    "WRITE_AFTER_COMMIT": collect_write_after_commit,
    "COMMIT_BEHIND_API": collect_commit_behind_api,
    "COMMAND_CALLS": collect_command_calls_outside_handlers,
    "RULE_IN_ROUTER": collect_rule_in_router,
    "WRITE_OUTSIDE_SERVICE": collect_write_outside_service,
    "NON_ORM_WRITES": collect_non_orm_writes,
    "DERIVED_ELSEWHERE": collect_derived_value_elsewhere,
    "PROMISE_NOT_KEPT": collect_promise_not_kept,
    "PROMISE_UNWALKABLE": collect_promise_unwalkable,
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


def test_no_new_dutch_identifier():
    """Ratchet (#780), hard for any name outside the baseline. Proofs (run, removed),
    the three directions #780 asks for: a `def controleer_iets()` added to
    `activities/service.py` → red, naming the file, the line and `controleer`; the key
    `domains/activities/service.py::bereken_iets` added to the baseline without the
    code → red, "no longer occur"; the existing Dutch names in the baseline → green,
    which this run is."""
    _ratchet("DUTCH_IDENTIFIERS")


def test_no_new_foreign_write():
    """Ratchet, hard for a new package (CR-13 §B9.3). Proofs (run, removed), each
    additive, in `cms/service.py`: a function constructing `Person` imported from
    `mdm.api` → red, "constructs `mdm.Person`"; a function doing
    `person = db.get(Person, 1)` then `person.first_name = "x"` → red, "assigns
    .first_name"; a function holding the string `"UPDATE mdm.persons SET …"` → red,
    "raw SQL writes `schema mdm`"."""
    _ratchet("FOREIGN_WRITES")


def test_no_write_after_a_commit():
    """Ratchet on one entry (`delete_registration`, phase 1). Proof (run, removed): a
    function `db.add(a); db.commit(); db.add(b)` added to `cms/service.py` → red,
    "db.add() after the commit on line …". The shapes that are not a violation are
    pinned below, on sources of their own."""
    _ratchet("WRITE_AFTER_COMMIT")


@pytest.mark.parametrize(
    ("source", "red"),
    [
        ("db.add(a)\ndb.commit()\ndb.add(b)\n", True),
        ("db.add(a)\ndb.commit()\n", False),
        # A commit in a branch that returns is not carried past the `if`.
        ("if x:\n    db.commit()\n    return\ndb.add(b)\n", False),
        # A commit in one branch is not seen by its sibling.
        ("if x:\n    db.commit()\nelse:\n    db.add(b)\n", False),
        # A commit in a branch that falls through is carried.
        ("if x:\n    db.commit()\ndb.add(b)\n", True),
        # A loop that commits and writes writes after a commit on the next pass.
        ("for a in items:\n    db.add(a)\n    db.commit()\n", True),
    ],
)
def test_what_counts_as_a_write_after_a_commit(source, red):
    out: list = []
    _writes_after_commit(ast.parse(source).body, None, out)
    assert bool(out) is red, out


def test_no_commit_behind_another_domains_api():
    """Ratchet on twelve (§B9.3 (c)). Proof (run, removed): a function in
    `cms/service.py` calling `add_to_circle` imported from `mdm.api` → red,
    "`mdm.api.add_to_circle` commits (domains/mdm/service.py:…) and is called from
    another domain (domains/cms/service.py:…)"."""
    _ratchet("COMMIT_BEHIND_API")


_SINK = """
from app.database import SessionLocal
from app.kernel.rules import own_transaction

@own_transaction("mail.email_log", "the log outlives the caller")
def sink(to):
    own = SessionLocal()
    own.add(EmailLog(recipient=to))
    own.commit()

@own_transaction("mail.email_log", "the log outlives the caller")
def sink_on_the_callers_session(db, to):
    db.add(EmailLog(recipient=to))
    db.commit()

@own_transaction("mail.email_log", "the log outlives the caller")
def sink_that_writes_domain_data(to):
    own = SessionLocal()
    own.add(Person(first_name=to))
    own.commit()

def undeclared(to):
    own = SessionLocal()
    own.add(EmailLog(recipient=to))
    own.commit()
"""


@pytest.mark.parametrize(
    ("name", "red"),
    [
        ("sink", None),
        ("sink_on_the_callers_session", "commits a session it did not open"),
        ("sink_that_writes_domain_data", "writes mdm.persons"),
    ],
)
def test_a_declared_own_transaction_is_checked(tmp_path, name, red):
    """The three cases the master CLI asked for (29 September 2026), on a module
    built for the test: a sink on its own session and its log table passes; a sink
    that commits the session it received, or writes a table not its own, is red."""
    path = tmp_path / "sink.py"
    path.write_text(_SINK, encoding="utf-8")
    tree = ast.parse(_SINK)
    function = _module_functions(tree)[name]
    table = _own_transaction(function)
    assert table == "mail.email_log"
    tables = {"EmailLog": "mail.email_log", "Person": "mdm.persons"}
    problem = _own_transaction_problem(path, tree, function, table, tables=tables)
    if red is None:
        assert problem is None, problem
    else:
        assert problem is not None and red in problem, problem


def test_an_own_session_that_is_not_declared_still_commits():
    """The third case: without the declaration, a commit on a session the function
    opened itself is a commit like any other — nothing lets it pass."""
    tree = ast.parse(_SINK)
    function = _module_functions(tree)["undeclared"]
    assert _own_transaction(function) is None
    assert _commits(function) is not None


def test_only_the_ai_call_log_is_an_own_transaction_that_is_not_a_command():
    """`command=False` is one declared exception, not a way out. Proof (run,
    removed), additive: `command=False` added to `mail._log_email` → red, naming it."""
    found = set()
    for path in _python_files():
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _not_a_command(node):
                found.add(f"{_rel(path)}::{node.name}")
    assert found, "the walk found no `command=False` at all — is it still looking?"
    assert found == NOT_A_COMMAND, (
        f"`@own_transaction(..., command=False)` on {sorted(found - NOT_A_COMMAND)} — only "
        f"the AI call log is telemetry; anything else is a command (§B4.9)"
    )


def test_events_not_calls():
    """Ratchet (§B4.9), hard for a new package. Proof (run, removed), additive, both
    halves at once: in `cms/api.py` a `probe_write(db)` that commits through a helper
    in `cms/service.py`, and a `probe_read(db)` that only queries; both called from
    `forms/service.py` → exactly one new violation, "`forms/service.py` … calls
    `cms.api.probe_write` (a command: writes at domains/cms/service.py:… via
    _probe_helper)"; the read stays off the list."""
    _ratchet("COMMAND_CALLS")


@pytest.mark.parametrize(
    ("domain", "name", "command"),
    [
        # The couplings §B4.9 names, found by the walk, not listed by hand.
        # The two registration confirmations left the facade in phase 4 (events,
        # built and queued by `mail` itself); the form confirmation is still a call.
        ("mail", "send_form_confirmation", True),
        ("payment", "create_payment_record", True),
        ("payment", "reconcile_registration_charges", True),
        ("payment", "reconcile_charges", True),
        ("workflow", "vervroeg_sweep", True),
        # #1368: a write through a mapped collection and a flush is a write too.
        # (The example was `forms.update_attached`, where #1368 was found; that one
        # leaves the facade when it is reached through its port.)
        ("workflow", "close_subject_tasks", True),
        # Reads are not commands — the picture of an activity among them, since
        # its lazy rendering and the flush behind it left (#1251).
        ("media", "activity_image_path", False),
        ("mdm", "get_person", False),
        ("mdm", "name_parts", False),
    ],
)
def test_a_command_is_an_export_that_writes(domain, name, command):
    assert ((domain, name) in api_commands()) is command


def test_the_walk_sees_a_write_through_a_collection_or_a_flush():
    """#1368: the command walk counted `db.add/delete/merge`, commits and bulk
    statements — and missed a write the ORM persists from a changed collection and a
    `flush` (`forms.api.update_attached`: `submission.answers.clear()`/`.append()`,
    `db.flush()`). Measured when the shape was added (30 September 2026): it finds
    103 functions whose only write in a statement is of this shape (73 of them a
    `db.flush()`), and the facade's commands went from 178 to 187. The count is a
    floor: a refactor that made the shape invisible again would drop it.

    Proven red (run, removed), additively: a facade function in `cms/api.py` that
    only appends to `page.blocks` and flushes, called from `newsletter/service.py`
    → exactly one new violation in `test_events_not_calls`."""
    found = 0
    for path in _python_files():
        tree = _tree(path)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in _own_nodes(function):
                if (
                    isinstance(node, ast.stmt)
                    and _collection_write_or_flush(node)
                    and not _write_in(node)
                ):
                    found += 1
                    break
    assert found >= 100, f"the collection/flush shape found only {found} functions"
    assert len(api_commands()) >= 187


def test_no_new_rule_in_a_router():
    """Ratchet with a reason per entry (§B9.3). Proof (run, removed), additive, both
    halves at once: a function in `cms/admin_ui.py` with `if page is None: raise
    HTTPException(status_code=404)` and `if page.slug == "home": raise
    HTTPException(status_code=400, …)` → exactly one new violation, the 400 on
    `page.slug == 'home'`; the doorman's 404 stays off the list.

    CR-13 phase 4c (#1251): a check of the transport is the doorman's too, by three
    shapes (`transport_shape`). Their proofs are tests of their own below — each
    shape, and beside it the offence that must stay red."""
    _ratchet("RULE_IN_ROUTER")


def _shape_of(source: str) -> str | None:
    """The shape the gate gives the FIRST `if` of the one function in `source`."""
    tree = ast.parse(textwrap.dedent(source))
    function = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
    )
    first = next(n for n in ast.walk(function) if isinstance(n, ast.If))
    assert _refusal_in(first.body), "the proof's `if` refuses nothing — it would prove nothing"
    return transport_shape(first, function)


_REFUSE = "raise HTTPException(status_code=400, detail='nee')"


@pytest.mark.parametrize(
    "condition",
    [
        "not data",
        "len(data) > MAX_BYTES",
        "file.content_type not in ALLOWED_TYPES",
        "file is None or not file.filename",
        "file.filename.lower().endswith('.xlsx')",
    ],
)
def test_a_check_of_a_file_is_the_doormans(condition):
    """Shape 1: the condition reads the upload or its bytes, and constants."""
    assert (
        _shape_of(f"""
        async def door(file: UploadFile = File(...), title: str = Form("")):
            data = await file.read()
            page = load(title)
            if {condition}:
                {_REFUSE}
        """)
        == "a file"
    )


@pytest.mark.parametrize(
    "condition",
    [
        # A text's emptiness dressed up beside a check of the file: still a rule.
        "not data or not title.strip()",
        # A domain object beside the file.
        "file.content_type not in ALLOWED_TYPES and page.kind == 'poster'",
        "len(data) > page.max_bytes",
        # A text alone, and a text that only LOOKS like the bytes of a file.
        "not title.strip()",
        "not text",
        # An attribute of a file that is no property of the upload.
        "file.owner is None",
    ],
)
def test_proof_a_rule_beside_a_file_stays_a_rule(condition):
    assert (
        _shape_of(f"""
        async def door(file: UploadFile = File(...), title: str = Form("")):
            data = await file.read()
            text = title.strip()
            page = load(title)
            if {condition}:
                {_REFUSE}
        """)
        is None
    )


def test_a_refused_parse_is_the_doormans():
    """Shape 2: the refusal stands in the `except` of a `try` that only parses."""
    assert (
        _shape_of(f"""
        def door(sort_order: str = Form("")):
            if sort_order is not None:
                try:
                    number = int(sort_order or "0")
                except ValueError:
                    {_REFUSE}
        """)
        == "a parse"
    )


@pytest.mark.parametrize(
    "body",
    [
        # The `try` does more than parse: a service's refusal is not a parse error.
        "try:\n    number = service.place(page, sort_order)\nexcept ValueError:\n    " + _REFUSE,
        # Everything is caught: that hides more than a parse.
        "try:\n    number = int(sort_order)\nexcept Exception:\n    " + _REFUSE,
    ],
)
def test_proof_a_try_that_is_more_than_a_parse_stays_a_rule(body):
    indented = textwrap.indent(body, " " * 8)
    source = "def door(sort_order: str = Form('')):\n    if sort_order is not None:\n" + indented
    tree = ast.parse(source)
    function = tree.body[0]
    first = function.body[0]
    assert _refusal_in(first.body) or any(
        _refusal_in([s]) for s in ast.walk(first) if isinstance(s, ast.stmt)
    )
    assert transport_shape(first, function) is None


def test_proof_a_rule_after_a_parse_is_judged_on_its_own():
    """The parse is the doorman's; the `if` beside it that reads a domain object is a
    rule, and the gate meets it as an `if` of its own."""
    tree = ast.parse(
        textwrap.dedent(f"""
        def door(sort_order: str = Form("")):
            if sort_order is not None:
                try:
                    number = int(sort_order)
                except ValueError:
                    {_REFUSE}
                if number > page.limit:
                    {_REFUSE}
        """)
    )
    function = tree.body[0]
    outer = function.body[0]
    inner = outer.body[1]
    assert transport_shape(outer, function) == "a parse"
    assert _refusal_in(inner.body) and transport_shape(inner, function) is None


def test_the_age_of_a_token_is_the_doormans():
    """Shape 3: a clock minus a moment, against a constant."""
    for condition in (
        "time.monotonic() - entry['created_at'] > _TTL_SECONDS",
        "time.time() - issued >= 900",
    ):
        assert (
            _shape_of(f"""
            def door(token: str):
                entry = PENDING.get(token)
                issued = entry["at"]
                if {condition}:
                    {_REFUSE}
            """)
            == "a token's age"
        )


@pytest.mark.parametrize(
    "condition",
    [
        # A deadline of a domain object is a rule, however much it looks like a clock.
        "date.today() > activity.deadline",
        "time.time() - booking.created_at > booking.component.hold_seconds",
        "now - membership.valid_until > GRACE",
    ],
)
def test_proof_a_deadline_of_the_domain_stays_a_rule(condition):
    assert (
        _shape_of(f"""
        def door(token: str):
            if {condition}:
                {_REFUSE}
        """)
        is None
    )


def test_every_rule_in_a_router_carries_its_reason():
    """The change request's condition for this baseline: each entry says whether it
    is a rule on its way to the entity (and in which phase) or the doorman's own."""
    bad = {
        key: reason
        for key, reason in baseline.RULE_IN_ROUTER.items()
        if not re.match(r"(rule: .+ — phase [1-4]|door: .+)$", reason)
    }
    assert not bad, bad


def test_every_aggregate_is_mapped_and_defines_its_own_check():
    """Hard (§B9.3 (a)). `aggregate()` already refuses a class without `check`; this
    also refuses one that only inherits it, or is not mapped — a registration the
    flush listener would never meet. Proof (run, removed): a plain class `_Probe`
    with a `check()` registered at the bottom of `kernel/rules.py` → red, "_Probe is
    not a mapped class"."""
    from sqlalchemy import inspect as sa_inspect

    from app.kernel import rules

    bad = []
    for cls in rules.aggregates():
        if "check" not in vars(cls):
            bad.append(f"{cls.__name__} inherits check() instead of defining it")
        if sa_inspect(cls, raiseerr=False) is None:
            bad.append(f"{cls.__name__} is not a mapped class")
    assert not bad, bad


def test_no_new_write_outside_a_service():
    """Ratchet (§B9.3 (b)). Proof (run, removed): a function in `cms/admin_ui.py` doing
    `db.add(CmsPage(title="x"))` → red, "constructs `cms.CmsPage` outside a service"."""
    _ratchet("WRITE_OUTSIDE_SERVICE")


def test_no_new_write_past_the_orm():
    """Ratchet (§B9.3 (c)). Proof (run, removed): a function in `cms/service.py` doing
    `db.query(CmsPage).filter(CmsPage.id == 1).update({"title": "x"})` → red, "bulk
    .update() `cms.CmsPage` past the ORM"."""
    _ratchet("NON_ORM_WRITES")


def test_one_owner_per_derived_value():
    """Ratchet (§B9.3). The collector first proves each shape recognises its own owner.
    Proof (run, removed): a function in `cms/service.py` returning
    `sum(i.quantity * i.product.price for i in items)` → red, "computes
    `registration.total` a second time"."""
    _ratchet("DERIVED_ELSEWHERE")


@pytest.mark.parametrize(
    ("shape", "source", "match"),
    [
        ("registration.total", "i.quantity * i.product.price", True),
        ("registration.total", "i.quantity * 2", False),
        ("registration.state", "_effective_end(d) >= vandaag", True),
        ("registration.state", "vandaag > deadline", True),
        # A distance to a deadline, and another period's end, are not the state.
        ("registration.state", "0 <= (deadline - vandaag).days <= 7", False),
        ("registration.state", "half_start <= today <= half_end", False),
    ],
)
def test_the_derived_shapes(shape, source, match):
    node = ast.parse(source, mode="eval").body
    assert DERIVED_SHAPES[shape](node) is match


def test_a_record_state_is_decided_on_the_paid_amount():
    decides = ast.parse(
        "if r.status == PENDING:\n    betaald = r.amount_paid\n    if betaald != 0:\n"
        "        x = 1\n"
    ).body[0]
    passes_on = ast.parse("if status is not None:\n    f(amount_paid=amount_paid)\n").body[0]
    assert DERIVED_SHAPES["payment_record.state"](decides)
    assert not DERIVED_SHAPES["payment_record.state"](passes_on)


def test_every_promise_is_kept():
    """Ratchet on nothing today — so hard (§B9.3). Proof (run, removed), additive, in a
    new `activities/templates/_zz_probe.html`: a `<textarea name="description"
    required>` inside `<form hx-post="/admin/activiteiten/{{ a.id }}">` → red,
    "promises `description` required; the column `description` has no NOT NULL,
    CHECK, validator or schema constraint"."""
    _ratchet("PROMISE_NOT_KEPT")


def test_no_new_promise_that_cannot_be_walked():
    """Ratchet with the step where each walk stops (§B9.3, the 21 of §B10). Proof (run,
    removed): in the same probe template, an `<input name="zz_probe" required>` before
    the form → red, "cannot be walked: no form target"."""
    _ratchet("PROMISE_UNWALKABLE")


# ── A promise walked by a test: the declaration at the input ─────────────────

_TESTS = {
    "test_an_empty_street_is_refused": (
        'def test_an_empty_street_is_refused():\n    post({"street": ""})',
    ),
    "test_named_twice": ("def test_named_twice(): ...", "def test_named_twice(): ..."),
    "test_about_something_else": ('def test_about_something_else():\n    post({"city": ""})',),
}
_STOP = "no form target (built in JS, by a macro, or GET)"


def test_a_declaration_is_read_on_the_inputs_line_or_the_one_above():
    """And nowhere else: two lines above is another input's business."""
    same = '<input name="street" required> {# promise walked by: test_a #}\n'
    above = '{# promise walked by: test_a, test_b #}\n{{ ui.input("street", required=True) }}\n'
    far = '{# promise walked by: test_a #}\n<p>text</p>\n<input name="street" required>\n'
    none = '<input name="street" required>\n'
    assert [w for *_x, w in _template_promises(same)] == [("test_a",)]
    assert [w for *_x, w in _template_promises(above)] == [("test_a", "test_b")]
    assert [w for *_x, w in _template_promises(far)] == [()]
    assert [w for *_x, w in _template_promises(none)] == [()]


def test_proof_a_word_inside_an_attributes_value_is_no_promise():
    """The form builder's "Verplicht" tick is an input NAMED `required`; that was
    read as a promise. The attribute itself, with or without a value, still is."""
    named = '<input type="checkbox" name="required" value="1">\n'
    ticked = (
        '<input type="checkbox" name="required" value="1" '
        "{% if f and f.required %}checked{% endif %}>\n"
    )
    assert list(_template_promises(named)) == []
    assert list(_template_promises(ticked)) == []
    for real in (
        '<input name="required" required>\n',
        '<input name="amount" min="1">\n',
        '<input name="code" pattern="[0-9]+" title="required digits">\n',
    ):
        ((_line, _name, kinds, _form, _walkers),) = _template_promises(real)
        assert len(kinds) == 1, (real, kinds)


def test_a_promise_the_walk_cannot_follow_is_in_order_with_its_test():
    assert _judge_promise(_STOP, ("test_an_empty_street_is_refused",), "street", _TESTS) is None
    # Without a declaration it is what it was: the step where the walk stops.
    assert _judge_promise(_STOP, (), "street", _TESTS) == _STOP
    # And a promise the walk follows needs nothing.
    assert _judge_promise(None, (), "street", _TESTS) is None


@pytest.mark.parametrize(
    ("walkers", "said"),
    [
        (("test_that_was_renamed",), "is the name of 0 test functions"),
        (("test_named_twice",), "is the name of 2 test functions"),
        (("test_about_something_else",), "does not name the field `street`"),
        # One good test does not carry a bad one: a partial in two forms names both.
        (
            ("test_an_empty_street_is_refused", "test_that_was_renamed"),
            "`test_that_was_renamed` is the name of 0 test functions",
        ),
    ],
)
def test_proof_a_declaration_that_names_no_real_walk_is_refused(walkers, said):
    judged = _judge_promise(_STOP, walkers, "street", _TESTS)
    assert judged is not None and said in judged
    # The message says what to write, and asks for the docstring review reads.
    assert "which form and route it walks" in judged and _STOP in judged


def test_proof_a_declaration_where_the_walk_can_follow_is_refused():
    """No decoration where it is not needed: it would read as "this one is special"."""
    judged = _judge_promise(None, ("test_an_empty_street_is_refused",), "street", _TESTS)
    assert judged is not None and "remove the declaration" in judged


def test_the_test_tree_the_declarations_point_into_is_seen():
    """The walk of the tests is not blind, and it reads sources: this very test is
    found once, with its own text."""
    tests = _test_functions()
    (source,) = tests["test_the_test_tree_the_declarations_point_into_is_seen"]
    assert "not blind" in source


#: The Registration aggregate (CR-13 phase 1): its classes and its schema.
REGISTRATION_TARGETS = {
    "activities.Registration",
    "activities.RegistrationItem",
    "schema activities",
}


def test_nothing_writes_a_registration_past_the_orm():
    """Hard for the Registration aggregate since phase 1 — the entrances test of B8
    test 1. The ORM paths meet `check()` through the flush listener; this finds the
    paths that would not: a bulk update or delete on its classes, a core statement, or
    raw SQL writing the `activities` schema. Today there is none, so any is red.

    What it cannot see, and says so (§B10): a statement built with `getattr` or put
    together from strings at runtime. Proof (run, removed): a function in
    `cms/service.py` executing `"UPDATE activities.registrations SET phone = NULL"`
    → red, naming the call site and `schema activities`."""
    found = {
        key: message
        for key, message in collect_non_orm_writes().items()
        if key.split(" → ", 1)[1] in REGISTRATION_TARGETS
    }
    assert not found, "\n".join(found[k] for k in sorted(found))


@pytest.mark.parametrize(
    ("identifier", "dutch"),
    [
        ("controleer_inschrijfvelden", ["controleer", "inschrijfvelden"]),
        ("AdminActiviteitenView", ["activiteiten"]),
        ("093_formulier_posities_uniek_per_ouder", ["formulier", "uniek", "ouder"]),
        # English, and words both languages use: never a match.
        ("paginated_list", []),
        ("create_payment_record", []),
        ("form_status_type_filter", []),
        ("post_tenant_data_code", []),
        ("RegistrationView", []),
    ],
)
def test_the_word_list(identifier, dutch):
    assert dutch_words_in(identifier) == dutch


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


def test_the_walk_follows_one_delegation_and_no_further():
    """The limits of `_route_source` (#1535), on a module made for it.

    A route that returns its helper's result reads what the helper reads; a
    helper that does not read the field leaves the promise unwalked (the
    additive violation the master CLI asked for); a second level is not
    followed; a helper merely called along the way is not followed either.
    """
    module = ast.parse(
        """
@router.post("/a")
async def delegates(request):
    return await _save(request)

@router.post("/b")
def delegates_to_one_that_reads_nothing(request):
    return _ignore(request)

@router.post("/c")
def two_levels(request):
    return _outer(request)

@router.post("/d")
def calls_along_the_way(request):
    _save(request)
    return None

async def _save(request):
    return form["name"]

def _ignore(request):
    return None

def _outer(request):
    return _save(request)
"""
    )
    helpers = {
        n.name: n for n in module.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def reads_name(route: str) -> bool:
        return bool(re.search(r"['\"]name['\"]", _route_source(helpers[route], helpers)))

    assert reads_name("delegates"), "one level of delegation is followed"
    assert not reads_name("delegates_to_one_that_reads_nothing"), (
        "a helper that reads nothing stays red"
    )
    assert not reads_name("two_levels"), "a second level is not followed"
    assert not reads_name("calls_along_the_way"), "a call that is not returned is not followed"

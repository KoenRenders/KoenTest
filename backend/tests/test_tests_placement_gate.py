"""CR-13 R15 and §B9.3 — every test file sits where its imports say it belongs.

The rule (R15, Koen, 27 September 2026):

- a test that imports exactly one domain lives in `app/domains/<x>/tests/`;
- a test that imports several lives in `backend/tests/integration/`;
- a test that imports no domain (kernel, `app/ui`, the gates) stays in `backend/tests/`;
- a gate (`test_*_gate.py`) that imports several domains stays in `backend/tests/` too:
  it checks the whole app, it does not walk a flow through it. A gate that imports one
  domain is that domain's gate and moves with it.

"Imports a domain" means a `from app.domains.<x>… import …` or `import app.domains.<x>…`
anywhere in the file; `app.domains.registry` loads every domain, so importing it counts
as importing all of them. One exception, and it lives only here: an import from `auth`
that fetches nothing but the login plumbing in `LOGIN_HELPERS` does not count. A
screen test logs in to reach the screen it is about; without the exception, dozens of
forms, payment and member screen tests would land in `auth/tests/`, and the folder
would say how a test logs in instead of what it tests (master CLI, 28 September 2026).
An `auth` import that fetches one name more counts as `auth` like any other.

Hard from phase 0b, no baseline: the move and the gate land in the same PR. The same
function places the files (the one-off move) and judges them (this gate), so the two
cannot disagree.

Broken on purpose, additively, to see these tests go red (run, then removed):
- a new `tests/test_zz_red.py` importing `app.domains.payment.api` → the gate names it
  and says it belongs in `app/domains/payment/tests/`;
- the same file importing `SESSION_COOKIE` and `create_access_token` from
  `app.domains.auth.api` → the gate says `app/domains/auth/tests/` (one real auth name
  is enough);
- a new `app/domains/cms/tests/test_zz_red.py` importing no domain → the gate says
  `tests/`;
- a new `tests/integration/test_zz_red_gate.py` importing `forms` and `payment` → the
  gate says `tests/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests._bestanden import bestanden

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
DOMAINS = BACKEND / "app" / "domains"
INTEGRATION = TESTS / "integration"

# The auth names a test imports only to log in or to name a role, never as its
# subject. The one list: the classification and the gate both read it.
LOGIN_HELPERS: frozenset[str] = frozenset(
    {"SESSION_COOKIE", "make_session_value", "csrf_token_for", "User", "UserRole", "Role"}
)


# Not a domain: the module that imports every domain's models (`load_all_models`).
REGISTRY = "registry"


def domain_names() -> frozenset[str]:
    names = frozenset(
        p.name for p in DOMAINS.iterdir() if p.is_dir() and (p / "__init__.py").is_file()
    )
    assert len(names) >= 15, f"only {len(names)} domain packages found — the walk is blind"
    return names


def imported_domains(source: str, domains: frozenset[str]) -> frozenset[str]:
    """The domains a test file imports, login plumbing from `auth` left out."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            if parts[:2] != ["app", "domains"]:
                continue
            if len(parts) == 2:
                found.update(a.name for a in node.names if a.name in domains | {REGISTRY})
                continue
            names = {a.name for a in node.names}
            if parts[2] == "auth" and names <= LOGIN_HELPERS:
                continue
            found.add(parts[2])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[:2] == ["app", "domains"] and len(parts) >= 3:
                    found.add(parts[2])
    if REGISTRY in found:
        return domains
    return frozenset(found & domains)


def home(name: str, source: str, domains: frozenset[str]) -> Path:
    """The folder the test file `name` with this source belongs in (R15)."""
    imported = imported_domains(source, domains)
    if len(imported) == 1:
        return DOMAINS / next(iter(imported)) / "tests"
    if imported and not name.endswith("_gate.py"):
        return INTEGRATION
    return TESTS


def _test_files() -> list[Path]:
    return bestanden(
        TESTS.rglob("test_*.py"),
        DOMAINS.glob("*/tests/**/test_*.py"),
        wat="test files under tests/ and app/domains/*/tests/",
        minstens=400,
        met_tests=True,
    )


def collect_misplaced() -> dict[str, str]:
    domains = domain_names()
    misplaced: dict[str, str] = {}
    for path in _test_files():
        expected = home(path.name, path.read_text(), domains)
        if path.parent != expected:
            misplaced[str(path.relative_to(BACKEND))] = str(expected.relative_to(BACKEND))
    return misplaced


def test_every_test_file_sits_where_its_imports_say():
    misplaced = collect_misplaced()
    assert not misplaced, "test files outside their home (CR-13 R15):\n" + "\n".join(
        f"  {path} → belongs in {where}/" for path, where in sorted(misplaced.items())
    )


def test_the_walk_sees_all_three_homes():
    """A glob that stopped matching one home would make the gate blind to it (#678)."""
    homes = {path.parent for path in _test_files()}
    assert TESTS in homes
    assert INTEGRATION in homes
    assert sum(1 for h in homes if h.parent.parent == DOMAINS) >= 10


def test_every_domain_tests_folder_is_a_package_with_the_shared_fixtures():
    """A domain's tests reach the root fixtures through their own `conftest.py`.

    A `conftest.py` in `backend/` would reach them too, but it would also load for
    `tests_e2e/`, and its autouse fixture drops every schema of the test database.
    """
    folders = sorted(DOMAINS.glob("*/tests"))
    assert folders, "no app/domains/*/tests folder found"
    missing = []
    for folder in folders:
        if not (folder / "__init__.py").is_file():
            missing.append(f"{folder.relative_to(BACKEND)}/__init__.py")
        conftest = folder / "conftest.py"
        if not conftest.is_file() or "from tests.conftest import" not in conftest.read_text():
            missing.append(f"{folder.relative_to(BACKEND)}/conftest.py importing tests.conftest")
    assert not missing, "missing: " + ", ".join(missing)


DOMAINS_FOR_PROOF = frozenset({"auth", "payment", "forms"})


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from app.domains.auth.api import SESSION_COOKIE, make_session_value\n", frozenset()),
        (
            "from app.domains.auth.api import SESSION_COOKIE, create_access_token\n",
            frozenset({"auth"}),
        ),
        (
            "from app.domains.auth.api import csrf_token_for\n"
            "from app.domains.forms.api import Form\n",
            frozenset({"forms"}),
        ),
        (
            "from app.domains.forms.api import Form\nimport app.domains.payment.service\n",
            frozenset({"forms", "payment"}),
        ),
        ("def f():\n    from app.domains import payment\n", frozenset({"payment"})),
        ("from app.models import Person\n", frozenset()),
        ("from app.domains.registry import load_all_models\n", DOMAINS_FOR_PROOF),
    ],
)
def test_the_classification(source, expected):
    assert imported_domains(source, DOMAINS_FOR_PROOF) == expected


def test_one_real_auth_name_next_to_the_login_helpers_makes_it_auth():
    """The exception covers the six names and nothing more (master CLI's condition)."""
    source = "from app.domains.auth.api import SESSION_COOKIE, User, create_access_token\n"
    assert home("test_x.py", source, DOMAINS_FOR_PROOF) == DOMAINS / "auth" / "tests"
    with_forms = source + "from app.domains.forms.api import Form\n"
    assert home("test_x.py", with_forms, DOMAINS_FOR_PROOF) == INTEGRATION


def test_a_gate_over_several_domains_stays_and_a_one_domain_gate_moves():
    several = "from app.domains.forms.api import Form\nfrom app.domains.payment import api\n"
    assert home("test_x_gate.py", several, DOMAINS_FOR_PROOF) == TESTS
    one = "from app.domains.forms.api import Form\n"
    assert home("test_x_gate.py", one, DOMAINS_FOR_PROOF) == DOMAINS / "forms" / "tests"

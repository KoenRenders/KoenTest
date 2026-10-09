"""Gate (CR-24 §B7, §C7; #1722): a gate names a right, never a role.

A role is a bundle of rights and nothing more. Code that asks "is this an
ADMIN?" decides what a role may do in a second place, beside the bundle — and
the next role, or a bundle that changes, then means editing code again. So:

1. **No role-named gate or question exists** — the functions and sets every
   screen asked until CR-24 (`require_admin_ui`, `may_view_payments`,
   `_GENERAL_ADMIN_ROLES`, …). Not defined, not imported, not called, anywhere
   under `backend/app`. A new gate is `require_right(Right.…)`, a new question
   `may(db, email, Right.…)`.
2. **Role names in application code may only become fewer** — a ratchet, per
   file: a string literal that is a role code, a use of auth's `Role.<member>`,
   and a role code quoted inside a template expression (`{{ … }}`, `{% … %}`).
   Copy is not counted: a page that says "enkel OPERATOR" in its text says
   something true. What is left assigns a role or names the one platform-wide
   role, and is listed below with the reason.

**`STILL_NAMED` is the part of (1) that is not finished.** The call sites
convert domain by domain (CR-24 slice 4) and the screens last (slice 5); until
they have, the names below still stand in the files listed with them. Nothing
may join: a name in a file that is not listed is refused today. A file that
stops using a name must leave its line, so the name cannot come back there;
when the dictionary is empty it goes, and (1) is hard without it.

Proven by violation (9 October 2026), each added and removed again:
- `def require_admin_ui(): ...` in a new module `app/domains/cms/zz_proof.py`
  → (1) red, naming the module;
- `from app.domains.auth.api import may_view_payments` in
  `app/domains/activities/service.py`, converted in slice 4 → (1) red;
- `if role == "ADMIN":` in `app/domains/cms/service.py` → (2) red, "1 role
  name where 0 are allowed";
- `{% if "OPERATOR" in roles %}` in a template → (2) red, naming the template;
- a number of `ROLE_NAMES` raised by one without the code changing → (2) red:
  "lower its number"; a name added to `STILL_NAMED` for a file that does not
  use it → (1) red: "take it out of STILL_NAMED".
"""

from __future__ import annotations

import ast
import re
from collections import Counter

from tests._bestanden import APP, bestanden

MESSAGE = "Gate on a right (`require_right`, `may`), not on a role — CR-24"

#: C7 (1): what every screen asked before CR-24, and the JSON door's guards.
ROLE_NAMED = {
    "_GENERAL_ADMIN_ROLES",
    "_PAYMENTS_VIEW_ROLES",
    "_PAYMENTS_MUTATE_ROLES",
    "_require_admin",
    "_require_ui_roles",
    "require_admin_ui",
    "require_finance_ui",
    "get_current_admin",
    "get_current_finance",
    "get_finance_or_admin",
    "require_finance_mutation",
    "require_operator_ui",
    "require_platform_operator_ui",
    "require_roles",
    "admits_admin_ui",
    "may_view_payments",
    "may_mutate_payments",
    "may_use_admin_assistant",
}

#: Not finished yet (see the docstring): file → the role-named gates and
#: questions it still defines or uses. It only shrinks.
STILL_NAMED: dict[str, set[str]] = {
    # auth's own definitions and its facade. The payment questions and gates
    # have no caller left since slice 4; the rest waits for the nine routes
    # and the header below. All of it goes in the last step of slice 6.
    "domains/auth/api.py": {
        "admits_admin_ui",
        "may_mutate_payments",
        "may_view_payments",
        "require_admin_ui",
        "require_finance_mutation",
        "require_finance_ui",
    },
    "domains/auth/session.py": {
        "_GENERAL_ADMIN_ROLES",
        "_PAYMENTS_MUTATE_ROLES",
        "_PAYMENTS_VIEW_ROLES",
        "_require_ui_roles",
        "admits_admin_ui",
        "may_mutate_payments",
        "may_view_payments",
        "require_admin_ui",
        "require_finance_mutation",
        "require_finance_ui",
    },
}

#: The role codes a gate could be tempted to name. The two retired codes are
#: left out: "USER" and "MEMBER" are ordinary words in other vocabularies.
ROLE_CODES = {
    "ADMIN",
    "FINANCE",
    "OPERATOR",
    "ACCOUNT_ADMIN",
    "MASTERDATA",
    "PRICING",
    "SALES",
    "STOCK",
}

#: Where a role code is the subject itself: the list and its enum.
THE_LIST = {"domains/auth/codes.py", "domains/auth/models.py"}

#: C7 (2), the ratchet: file → how many role names stand in it. Each number
#: may only go down; a file that reaches zero leaves the dictionary.
ROLE_NAMES: dict[str, int] = {
    # OPERATOR, the one platform-wide role: shown apart, kept out of a
    # workspace's ticks, and assigned by an operator only.
    "domains/auth/admin_ui.py": 3,
    "domains/auth/users.py": 6,
    # A board member the member report names gets a login with ADMIN.
    "domains/auth/service.py": 1,
    # The three role sets: they go with the role-named gates (STILL_NAMED).
    "domains/auth/session.py": 7,
    # A workbench task names the role it is for (CR-24 D4: tasks keep their
    # role in part 1; the workbench per role is CR-25).
    "domains/workflow/api.py": 3,
    "domains/workflow/handlers.py": 6,
    "domains/workflow/models.py": 1,
}

_EXPRESSION = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_QUOTED_ROLE = re.compile(r"""["'](%s)["']""" % "|".join(sorted(ROLE_CODES)))


def _python() -> list:
    return bestanden(APP.rglob("*.py"), wat="application modules", minstens=200)


def _names_in(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.alias)):
            found.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found & ROLE_NAMED


def _imports_auths_role(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("app.domains.auth")
        and any(alias.name == "Role" and alias.asname is None for alias in node.names)
        for node in ast.walk(tree)
    )


def _role_names_in(tree: ast.AST) -> int:
    auths_role = _imports_auths_role(tree)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in ROLE_CODES:
            count += 1
        elif (
            auths_role
            and isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Role"
        ):
            count += 1
    return count


def test_no_role_named_gate_or_question_exists():
    found: dict[str, set[str]] = {}
    for path in _python():
        names = _names_in(ast.parse(path.read_text(encoding="utf-8")))
        if names:
            found[str(path.relative_to(APP))] = names
    new = {
        file: sorted(names - STILL_NAMED.get(file, set()))
        for file, names in found.items()
        if names - STILL_NAMED.get(file, set())
    }
    assert not new, f"{MESSAGE}:\n" + "\n".join(
        f"  {f}: {', '.join(n)}" for f, n in sorted(new.items())
    )
    gone = {
        file: sorted(names - found.get(file, set()))
        for file, names in STILL_NAMED.items()
        if names - found.get(file, set())
    }
    assert not gone, (
        "no longer named there — take it out of STILL_NAMED, so it cannot come back:\n"
        + "\n".join(f"  {f}: {', '.join(n)}" for f, n in sorted(gone.items()))
    )


def test_role_names_in_application_code_only_become_fewer():
    counted: Counter = Counter()
    for path in _python():
        file = str(path.relative_to(APP))
        if file in THE_LIST:
            continue
        counted[file] += _role_names_in(ast.parse(path.read_text(encoding="utf-8")))
    for path in bestanden(APP.rglob("*.html"), wat="templates", minstens=200):
        for expression in _EXPRESSION.findall(path.read_text(encoding="utf-8")):
            counted[str(path.relative_to(APP))] += len(_QUOTED_ROLE.findall(expression))
    counted = Counter({file: n for file, n in counted.items() if n})

    more = [
        f"  {file}: {n} role name(s) where {ROLE_NAMES.get(file, 0)} are allowed"
        for file, n in sorted(counted.items())
        if n > ROLE_NAMES.get(file, 0)
    ]
    assert not more, f"{MESSAGE}:\n" + "\n".join(more)
    fewer = [
        f"  {file}: {counted.get(file, 0)} left of {n} — lower its number"
        for file, n in sorted(ROLE_NAMES.items())
        if counted.get(file, 0) < n
    ]
    assert not fewer, "the ratchet moves with the code:\n" + "\n".join(fewer)


def test_the_gate_sees_a_role_name_when_there_is_one():
    """Both walks, on source that holds what they look for — a gate that finds
    nothing must not be a gate that cannot see (#678)."""
    module = ast.parse(
        "from app.domains.auth.api import Role, require_admin_ui\n"
        "def page(email=Depends(require_admin_ui)):\n"
        "    return role == 'FINANCE' or role is Role.ADMIN or 'OPERATOR' in roles\n"
    )
    assert _names_in(module) == {"require_admin_ui"}
    assert _role_names_in(module) == 3
    other_enum = ast.parse("from app.domains.reporting.universe import Role\nx = Role.ADMIN\n")
    assert _role_names_in(other_enum) == 0, "reporting's own Role is another enum"
    template = (
        '<p>enkel OPERATOR</p>{% if "OPERATOR" in roles %}{{ _("OPERATOR · alle") }}{% endif %}'
    )
    hits = sum(len(_QUOTED_ROLE.findall(e)) for e in _EXPRESSION.findall(template))
    assert hits == 1, "the condition counts; the copy, inside or outside an expression, does not"

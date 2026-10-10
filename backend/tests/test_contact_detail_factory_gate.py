"""A contact detail is made in one place only (CR-22 §B7 and §C7, #1704).

**The rule.** An e-mail address of a person is written only through master
data's `new_contact_detail`, which decides whether it counts and refuses it
when another person outside the household already uses it. A writer that
constructs a `ContactDetail` itself skips that rule without anybody noticing —
the row is valid, the address simply signs in as someone else.

**Hard**: zero constructions outside the factory. There were ten, in three
files, before this change; a rule with a list of exemptions would have let the
eleventh in.

**What it does not see**, said here so nobody reads more into a green run: a
writer that changes the `value` of an EXISTING row. Those four places call
`require_email_free` and are held by tests
(`test_email_address_belongs_to_one_person_1704.py`), which is the weaker
guarantee.

Proven by an added violation (7 October 2026), never by breaking what exists:
a scratch module `app/domains/membership/scratch_gate_proof.py` holding one
`ContactDetail(person_id=1, …)` call — this test failed with the message below
naming that file and its line, and passes again with the file gone. The scratch
module was never committed.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
FACTORY_FILE = APP / "domains" / "mdm" / "service.py"
FACTORY = "new_contact_detail"
MODEL = "ContactDetail"


def _constructions(path: Path) -> list[tuple[int, str | None]]:
    """(line, enclosing function) of every `ContactDetail(...)` call in a file."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[tuple[int, str | None]] = []

    def walk(node: ast.AST, function: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            inside = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inside = child.name
            if isinstance(child, ast.Call):
                called = child.func
                name = called.id if isinstance(called, ast.Name) else getattr(called, "attr", None)
                if name == MODEL:
                    found.append((child.lineno, function))
            walk(child, inside)

    walk(tree, None)
    return found


def _source_files() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "tests" not in p.relative_to(APP).parts)


def test_a_contact_detail_is_made_by_the_factory_only():
    files = _source_files()
    # A gate that looks nowhere is green forever: it must have read the tree,
    # the factory's file among it, and found the one construction it allows.
    assert len(files) > 200, f"the gate read only {len(files)} files — did the tree move?"
    assert FACTORY_FILE in files, "mdm/service.py is not where the gate looks for it"

    allowed = [line for line, function in _constructions(FACTORY_FILE) if function == FACTORY]
    assert len(allowed) == 1, (
        f"{FACTORY} should construct the row exactly once; found {len(allowed)} — "
        "was it renamed, or does the gate no longer recognise the call?"
    )

    violations = [
        f"{path.relative_to(APP)}:{line}"
        for path in files
        for line, function in _constructions(path)
        if not (path == FACTORY_FILE and function == FACTORY)
    ]
    assert not violations, (
        "ContactDetail is made only by mdm.service.new_contact_detail — it applies "
        "the e-mail rule (CR-22 §B7). Found in " + ", ".join(violations)
    )

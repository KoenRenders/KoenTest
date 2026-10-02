"""Every copy action declares every column it copies or not (#1464).

Koen, 2 October 2026, after #1463: `copy_activity` listed its fields by hand,
`target_audience` was added later and silently left out. *"Zodanig dat we dat
nooit vergeten."* So:

- every `copy_*` function under `app/domains/` is either a copy action with a
  `COPY_PLANS` entry in its own module, or registered below as no copy action,
  with the reason;
- every plan sorts each mapped column of its model into exactly one set —
  copied, set by the copy, or not copied — with a reason for all but the first; a column in none, a set naming a column that is
  gone, or a set twice fails, naming the model and the column;
- the form copy goes through `export_definition`, not through the plan, so the
  definition must carry every column the plan calls copied.

**Proven additively** (CLAUDE.md, *Testen*): a scratch column
`Activity.proof_1464 = Column(String)` turned the gate red with
"Activity.proof_1464 is in no set of the copy plan of
activities.service.copy_activity"; a scratch `def copy_proof(): ...` in
`reporting/service.py` turned it red with "copy_proof … is neither a copy action
with a plan nor registered". Both were removed. The synthetic tests at the end
reproduce both on every run, so the gate cannot pass for one that no longer
looks.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

import app.models  # noqa: F401 — every mapper configured
from app.kernel.copying import CopyPlan, plan_problems

DOMAINS = Path(__file__).resolve().parents[1] / "app" / "domains"

#: `copy_*` functions that are no copy action, each with the reason. A new name
#: here needs the same scrutiny as a new plan: it is how a copy would hide.
NOT_COPY_ACTIONS = {
    "activities.service.copy_suggestions": "returns two suggested dates; copies nothing",
    "activities.admin_ui.copy_activity_step": "the route that shows the copy step",
    "activities.admin_ui.copy_activity_submit": "the route that calls copy_activity",
    "forms.api.copy_form": "the facade of forms.service.copy_form",
    "designstudio.handlers.copy_designs_of_copied_activity": "calls designstudio.service.copy_designs",
}

#: How many copy actions there are today (#1464): activities, forms, designs,
#: reports, newsletters. A number, not `> 0`: a scan that finds nothing passes.
EXPECTED_ACTIONS = 5


def _copy_functions() -> list[str]:
    """Every module-level `copy_*` function under app/domains, as `domain.module.name`."""
    found = []
    for path in sorted(DOMAINS.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = ".".join(path.relative_to(DOMAINS).with_suffix("").parts)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "copy_"
            ):
                found.append(f"{module}.{node.name}")
    return found


def _plans() -> dict[str, tuple[CopyPlan, ...]]:
    """Every declared copy action and its plans, read from the modules themselves."""
    plans = {}
    for qualified in _copy_functions():
        module, name = qualified.rsplit(".", 1)
        declared = getattr(importlib.import_module(f"app.domains.{module}"), "COPY_PLANS", {})
        if name in declared:
            plans[qualified] = declared[name]
    return plans


def _unregistered(functions: list[str], plans: dict) -> list[str]:
    return [f for f in functions if f not in plans and f not in NOT_COPY_ACTIONS]


def test_every_copy_function_is_a_planned_action_or_registered():
    functions = _copy_functions()
    plans = _plans()
    print(f"copy functions found: {len(functions)}; copy actions with a plan: {len(plans)}")

    assert functions, "the scan found no copy_* function at all — did app/domains move?"
    missing = _unregistered(functions, plans)
    assert not missing, (
        f"{', '.join(missing)} is neither a copy action with a plan nor registered in "
        "NOT_COPY_ACTIONS: declare COPY_PLANS beside it (#1464)"
    )
    assert len(plans) == EXPECTED_ACTIONS, sorted(plans)
    stale = sorted(set(NOT_COPY_ACTIONS) - set(functions))
    assert not stale, f"registered but gone: {stale}"


def test_every_plan_classifies_every_column():
    problems = []
    checked = 0
    for action, plans in _plans().items():
        for plan in plans:
            problems += plan_problems(plan, action=action)
            checked += 1
    print(f"copy plans checked: {checked}")

    # Activities 5, forms 4, designs 3, reports 1, newsletters 1. Exact: a
    # plan that drops out of a tuple is as silent as a missing column.
    assert checked == 14, f"{checked} plans, expected 14 — one was lost or added"
    assert not problems, "\n".join(problems)


def test_the_form_definition_carries_every_copied_form_column():
    """The form copy reads `export_definition`, not the plan: hold the two together."""
    from types import SimpleNamespace

    # Loaded like every other module here: this is a gate over five domains,
    # and it stays in backend/tests/ (docs/code-style.md, *Where a test lives*).
    forms = importlib.import_module("app.domains.forms.service")
    FORM_COPY, SECTION_COPY = forms.FORM_COPY, forms.SECTION_COPY
    FIELD_COPY, OPTION_COPY = forms.FIELD_COPY, forms.OPTION_COPY
    export_definition = forms.export_definition

    option = SimpleNamespace(**{c: None for c in OPTION_COPY.copied}, id=3, skip_to_section_id=None)
    field = SimpleNamespace(
        **{c: None for c in FIELD_COPY.copied}, id=2, section_id=1, options=[option]
    )
    field.position = option.position = 0
    section = SimpleNamespace(**{c: None for c in SECTION_COPY.copied}, id=1, next_section_id=None)
    section.position = 0
    form = SimpleNamespace(
        **{c: None for c in FORM_COPY.copied}, title="t", sections=[section], fields=[field]
    )

    definition = export_definition(form)

    def missing(plan, keys):
        return sorted(set(plan.copied) - set(keys))

    assert not missing(FORM_COPY, definition), missing(FORM_COPY, definition)
    assert not missing(SECTION_COPY, definition["sections"][0])
    assert not missing(FIELD_COPY, definition["fields"][0])
    assert not missing(OPTION_COPY, definition["fields"][0]["options"][0])


# ── The gate can go red: two synthetic cases, on every run ───────────────────

_Base = declarative_base()


class _Proof(_Base):
    __tablename__ = "copy_plan_proof_1464"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    forgotten = Column(String)


def test_a_column_in_no_set_fails_naming_model_and_column():
    plan = CopyPlan(model=_Proof, copied=("name",), not_copied={"id": "a new row"})

    problems = plan_problems(plan, action="proof.copy_proof")

    assert problems == [
        "_Proof.forgotten is in no set of the copy plan of proof.copy_proof: declare it "
        "copied, set by the copy, or not copied with its reason"
    ]


def test_a_set_naming_a_gone_column_or_no_reason_fails():
    plan = CopyPlan(
        model=_Proof,
        copied=("name", "gone"),
        not_copied={"id": "a new row", "forgotten": " "},
    )

    problems = plan_problems(plan, action="proof.copy_proof")

    assert "_Proof.gone is in copied of proof.copy_proof, and _Proof has no such column" in problems
    assert "_Proof.forgotten in not_copied of proof.copy_proof has no reason" in problems


def test_an_unregistered_copy_function_fails():
    assert _unregistered(["reporting.service.copy_proof"], {}) == ["reporting.service.copy_proof"]

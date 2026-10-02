"""What a copy action takes along, declared once per model (#1464).

Koen, 2 October 2026, after #1463: a copy action named its fields one by one, so
a field added later was silently left out — `target_audience` was — and nothing
failed. *"Zodanig dat we dat nooit vergeten."*

A `CopyPlan` sorts every mapped column of one model into exactly one of:

- `copied`: taken over as it is; the copy reads them from here (`values`), so
  this tuple is the single source and not a list beside the code;
- `set_by_copy`: the copy writes its own value (a new parent id, a shifted date,
  a fresh status), with the reason;
- `not_copied`: left at its default on purpose, with the reason.

`tests/test_copy_plans_gate.py` holds every plan to its model: a column in no
set, a set naming a column that is gone, or a `copy_*` function without a plan
fails, naming the model and the column.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect


@dataclass(frozen=True)
class CopyPlan:
    """How one model's rows are copied — every column in exactly one set."""

    model: type
    copied: tuple[str, ...]
    set_by_copy: Mapping[str, str] = field(default_factory=dict)
    not_copied: Mapping[str, str] = field(default_factory=dict)

    def values(self, source: Any) -> dict[str, Any]:
        """The copied columns of `source`, ready for the new row's constructor."""
        return {column: getattr(source, column) for column in self.copied}


def mapped_columns(model: type) -> set[str]:
    """The model's mapped columns, by attribute name."""
    return {attr.key for attr in inspect(model).column_attrs}


def plan_problems(plan: CopyPlan, *, action: str) -> list[str]:
    """Everything wrong with `plan` against its model, one line per problem."""
    name = plan.model.__name__
    columns = mapped_columns(plan.model)
    sets = {
        "copied": set(plan.copied),
        "set_by_copy": set(plan.set_by_copy),
        "not_copied": set(plan.not_copied),
    }
    problems = []
    for column in sorted(columns - set().union(*sets.values())):
        problems.append(
            f"{name}.{column} is in no set of the copy plan of {action}: declare it "
            "copied, set by the copy, or not copied with its reason"
        )
    for label, names in sets.items():
        for column in sorted(names - columns):
            problems.append(
                f"{name}.{column} is in {label} of {action}, and {name} has no such column"
            )
    seen: dict[str, str] = {}
    for label, names in sets.items():
        for column in sorted(names):
            if column in seen:
                problems.append(
                    f"{name}.{column} is in both {seen[column]} and {label} of {action}"
                )
            seen[column] = label
    for label in ("set_by_copy", "not_copied"):
        for column, reason in getattr(plan, label).items():
            if not (reason or "").strip():
                problems.append(f"{name}.{column} in {label} of {action} has no reason")
    return problems

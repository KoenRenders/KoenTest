"""What is logged — one declaration the snapshot and the gates read (#1885).

Koen, 10 October 2026: is every change to a person, a household or a membership
certain to reach Wijzigingen — and if not, should a gate hold it? It was not
certain. A change reached Wijzigingen through three links kept by hand: a
service called the snapshot after it wrote, the history table carried the
column and the snapshot copied it, and the reader compared it. A new column or
a new write path could fall through any of them, and nothing failed.

Koen, 15 October 2026: every model Wijzigingen reads is logged, every column of
it, and shown — "behalve documenten die we opladen" and "het technische
moment". So the rule is one sentence: **every column of a logged model is in
its history table, except the ones named here with their reason.**

Each domain declares its logged models in its own `history.py`, beside the
history models it owns (`declare`); this module only holds the declarations and
derives from them:

- `logged_columns`: what a snapshot copies and the history table must carry;
- `snapshot`: the one copy — a history row with every logged column of the
  object, codes as their code (CR-12 §F4: a history table carries no foreign
  key, so it stores the code and not the member);
- the gates read `declared()` (`tests/test_logged_gate.py`).

The kernel imports no domain: a domain registers here, the kernel never looks
there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

#: The moments that are technical, not a fact of the object (Koen, 15 October
#: 2026: "alles loggen behalve het technische moment"). Each with its reason.
TECHNICAL: Mapping[str, str] = {
    "created_at": "the moment the row was made; the history row records its own moment",
    "updated_at": "the moment the row last changed; each history row is that moment",
    "deleted_at": "a delete is the history row's own operation ('delete')",
    "confirmed_at": "the moment an e-mail address was confirmed: technical (Koen, 15 October 2026)",
}


@dataclass(frozen=True)
class Logged:
    """One logged model: its history model, the history column that names the
    object, and the columns deliberately not logged, each with its reason."""

    model: type
    history: type
    key: str
    not_logged: Mapping[str, str] = field(default_factory=dict)
    #: A model column stored under another name, where its own would collide with
    #: a column every history row has (`source`, `action`, `actor`, …).
    renamed: Mapping[str, str] = field(default_factory=dict)


_DECLARED: dict[type, Logged] = {}


def declare(
    model: type,
    history: type,
    *,
    key: str,
    not_logged: Optional[Mapping[str, str]] = None,
    renamed: Optional[Mapping[str, str]] = None,
) -> None:
    """Called once per logged model by the domain that owns it."""
    reasons = dict(TECHNICAL)
    reasons.update(not_logged or {})
    _DECLARED[model] = Logged(
        model=model, history=history, key=key, not_logged=reasons, renamed=dict(renamed or {})
    )


def declared() -> tuple[Logged, ...]:
    """Every declaration, in the order the domains made them."""
    return tuple(_DECLARED.values())


def is_logged(model: type) -> bool:
    """Is this model declared as logged?"""
    return model in _DECLARED


def declaration_of(model: type) -> Logged:
    try:
        return _DECLARED[model]
    except KeyError:
        raise LookupError(f"{model.__name__} is not a logged model (#1885)") from None


def logged_columns(entry: Logged) -> list[str]:
    """The model's columns a history row carries: all of them but its own id and
    what is named as not logged."""
    from sqlalchemy import inspect

    return [
        column.name
        for column in inspect(entry.model).columns
        if column.name != "id" and column.name not in entry.not_logged
    ]


def history_column(entry: Logged, column: str) -> str:
    """The history column a model column is stored in."""
    return entry.renamed.get(column, column)


def _plain(value: Any) -> Any:
    """A code as its code (CR-12 §F4), anything else as it is."""
    return value.value if isinstance(value, Enum) else value


def snapshot(
    db: Any,
    obj: Any,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
    model: Optional[type] = None,
    **extra: Any,
) -> None:
    """Write the history row of `obj`: every logged column, and who, what and why.

    The one copy for every logged model: a column added to the model is copied
    the day it is declared, and a column the history table lacks is a gate's
    red, not a forgotten line in a snapshot of its own. `extra`: what a history
    row carries beyond the object's columns (a registration's answers in words).
    `model`: the logged model, where `obj` is not an instance of it (a recorded
    source in a test)."""
    entry = declaration_of(model or type(obj))
    values = {
        history_column(entry, name): _plain(getattr(obj, _attribute(entry.model, name)))
        for name in logged_columns(entry)
    }
    db.add(
        entry.history(
            **{entry.key: obj.id},
            **values,
            **extra,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def _attribute(model: type, column: str) -> str:
    """The mapped attribute of a column (they differ where a column is reserved,
    as `metadata`)."""
    from sqlalchemy import inspect

    for attribute in inspect(model).column_attrs:
        if any(c.name == column for c in attribute.columns):
            return attribute.key
    return column

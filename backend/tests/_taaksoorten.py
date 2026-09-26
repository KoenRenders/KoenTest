"""Register a task kind from a test, the way a new source would (CR-12 phase 4).

`workflow.workflow_tasks.kind` carries a foreign key since phase 4, so a test
cannot invent a kind any more — and that is the point of the key. What a test
may do is exactly what a new source or a new `WorkflowDefinition` does: add the
row, with its Dutch and English word, and the row for its category if that is
new too.

Deliberately a helper and not a fixture that seeds every kind the tests use.
A blanket seed would hide the constraint, and then the next person to add a
source would find out on HDEV instead of here.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def registreer_taaksoort(db: Session, code: str, *, nl: str, en: str | None = None,
                         categorie_nl: str | None = None) -> str:
    """Add one task kind (and its category when missing). Returns the code."""
    categorie = code.split(".", 1)[0]
    _rij(db, "task_category", categorie, categorie_nl or categorie.capitalize(),
         categorie_nl or categorie.capitalize())
    _rij(db, "task_kind", code, nl, en or nl)
    db.flush()
    return code


def _rij(db: Session, lijst: str, code: str, nl: str, en: str) -> None:
    bestaat = db.execute(
        text(f"SELECT 1 FROM workflow.{lijst}_codes WHERE code = :c"),
        {"c": code}).first()
    if bestaat:
        return
    db.execute(text(f"INSERT INTO workflow.{lijst}_codes "
                    f"(code, sort_order, is_active, created_at) "
                    f"VALUES (:c, 900, true, now())"), {"c": code})
    for taal, waarde in (("nl", nl), ("en", en)):
        db.execute(text(f"INSERT INTO workflow.{lijst}_labels "
                        f"(code, language, value, created_at, updated_at) "
                        f"VALUES (:c, :l, :v, now(), now())"),
                   {"c": code, "l": taal, "v": waarde})

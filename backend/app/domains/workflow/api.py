"""Facade van het workflow-component (#398). Taakcontract: één vorm, veel
bronnen; de werkbank kent nul taak-types en filtert op rol (§20.5)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.domains.workflow.models import WorkflowTask


def create_task(db: Session, *, kind: str, title: str, subject_type: str,
                subject_id: int, required_role: str = "ADMIN") -> WorkflowTask:
    task = WorkflowTask(kind=kind, title=title, subject_type=subject_type,
                        subject_id=subject_id, required_role=required_role)
    db.add(task)
    return task


def open_tasks(db: Session, roles: Sequence[str]) -> list[WorkflowTask]:
    return (
        db.query(WorkflowTask)
        .filter(WorkflowTask.status == "open", WorkflowTask.required_role.in_(list(roles) or [""]))
        .order_by(WorkflowTask.created_at)
        .all()
    )


def open_count(db: Session, roles: Sequence[str]) -> int:
    return (
        db.query(WorkflowTask)
        .filter(WorkflowTask.status == "open", WorkflowTask.required_role.in_(list(roles) or [""]))
        .count()
    )


def get_task(db: Session, task_id: int) -> Optional[WorkflowTask]:
    return db.query(WorkflowTask).filter(WorkflowTask.id == task_id).first()


def close_task(db: Session, task_id: int, *, done_by: str,
               decision: Optional[str] = None) -> Optional[WorkflowTask]:
    """Sluit een taak (idempotent: een al gesloten taak blijft gesloten).
    ``decision`` is het bewaarde besluit — een afwijzing is ook een beslissing."""
    task = get_task(db, task_id)
    if task is None:
        return None
    if task.status != "done":
        task.status = "done"
        task.done_at = datetime.now(timezone.utc)
        task.done_by = done_by
        task.decision = decision
    return task


# ── Definities + instanties (fase 4b, #403) ────────────────────────────────────

def start(db: Session, definition_code: str, *, subject_type: str,
          subject_id: int, context: Optional[dict] = None):
    """Start een workflow-instantie en maak de taak van de eerste stap.
    ``context`` vult de titel-template van de stap (str.format)."""
    from app.domains.workflow.models import WorkflowDefinition, WorkflowInstance

    definition = db.get(WorkflowDefinition, definition_code)
    if definition is None or not definition.steps:
        raise ValueError(f"Onbekende of lege workflow-definitie '{definition_code}'")
    instance = WorkflowInstance(definition_code=definition_code,
                                subject_type=subject_type, subject_id=subject_id)
    db.add(instance)
    db.flush()
    _create_step_task(db, definition, instance, 0, context or {})
    return instance


def _create_step_task(db: Session, definition, instance, step_index: int,
                      context: dict) -> WorkflowTask:
    step = definition.steps[step_index]
    title = str(step.get("title", step.get("kind", "Taak")))
    try:
        title = title.format(**context)
    except (KeyError, IndexError):
        pass
    task = create_task(
        db, kind=str(step["kind"]), title=title,
        subject_type=instance.subject_type, subject_id=instance.subject_id,
        required_role=str(step.get("role", "ADMIN")),
    )
    task.instance_id = instance.id
    return task


def advance(db: Session, instance, *, context: Optional[dict] = None):
    """Zet de instantie één stap verder: volgende stap → nieuwe taak; geen
    volgende stap → instantie klaar. Idempotent op een al-voltooide instantie."""
    from app.domains.workflow.models import WorkflowDefinition

    if instance.status == "done":
        return instance
    definition = db.get(WorkflowDefinition, instance.definition_code)
    instance.current_step += 1
    if definition is None or instance.current_step >= len(definition.steps):
        instance.status = "done"
        instance.done_at = datetime.now(timezone.utc)
    else:
        _create_step_task(db, definition, instance, instance.current_step,
                          context or {})
    db.flush()
    return instance


def complete_task(db: Session, task_id: int, *, done_by: str,
                  decision: Optional[str] = None) -> Optional[WorkflowTask]:
    """Sluit een taak én — als hij bij een instantie hoort — zet de workflow
    verder ("een afwijzing is ook een beslissing": het besluit blijft bewaard,
    óók bij afwijzen; de volgende stap start hoe dan ook of de flow eindigt)."""
    from app.domains.workflow.models import WorkflowInstance

    task = close_task(db, task_id, done_by=done_by, decision=decision)
    if task is not None and task.instance_id is not None:
        instance = db.get(WorkflowInstance, task.instance_id)
        if instance is not None:
            advance(db, instance)
    return task


# Alias uit het taakcontract (§20.5) — de werkbank spreekt over list_tasks.
list_tasks = open_tasks

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

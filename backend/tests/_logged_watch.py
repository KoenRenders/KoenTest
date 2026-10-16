"""Gate 2 of #1885: a write of a logged object leaves its history row.

Koen, 10 October 2026: a new write path that forgets the snapshot writes the
change and no history row, and nothing fails. This watch is attached to the
test suite's session (`tests/conftest.py`): it notes every logged object a flush
inserts, changes in a logged column, or soft-deletes, and every history row a
flush writes; when the transaction commits — or the test ends — an object
without its row is a finding, named with the object, the operation and the
place in the application that flushed it.

What is logged is the declaration (`app/kernel/logged.py`): a change to a
technical moment alone (`updated_at`) is no change to log; a soft delete is.

A finding fails the test. `LOGGED_WATCH=report` (the measurement of #1885)
writes the findings to a file per process instead, printed at the end of the
run; `LOGGED_WATCH=off` turns the watch off. Measured on 16 October 2026 over
the whole suite in CI: the member number (no snapshot at all) and an
organisation's address and contact details wrote without a history row; both
write it now, and the run found nothing else.

Broken on purpose (16 October 2026, put back): the `snapshot_membership` call
of `membership.service` (an imported membership) taken out → the import's tests
fail, naming `Membership #… insert | app/domains/membership/service.py:507`.
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, inspect


@dataclass
class Watch:
    test: str = ""
    #: (model name, id) → (operation, where it was flushed)
    written: dict[tuple[str, Any], tuple[str, str]] = field(default_factory=dict)
    logged: set[tuple[str, Any]] = field(default_factory=set)
    findings: list[str] = field(default_factory=list)
    #: Counts the history rows that wait for a flush (set by `attach`).
    pending: Any = lambda: None

    def check(self) -> None:
        for key, (operation, where) in self.written.items():
            # A write without a frame of the application is the test's own seed
            # (a row laid down to test something else), not a write path.
            if key not in self.logged and where:
                self.findings.append(f"{self.test} | {key[0]} #{key[1]} {operation} | {where}")
        self.written.clear()
        self.logged.clear()


def _where() -> str:
    """The innermost frame of the application that is not the kernel's or a history's."""
    for frame in reversed(traceback.extract_stack()):
        path = frame.filename.replace("\\", "/")
        if "/app/backend/app/" not in path or "/kernel/" in path or "/tests/" in path:
            continue
        if path.endswith("history.py"):
            continue
        return f"{path.split('/app/backend/', 1)[1]}:{frame.lineno}"
    return ""


def _changed(obj: Any, entry: Any) -> bool:
    from app.kernel.logged import logged_columns

    state = inspect(obj)
    columns = set(logged_columns(entry)) | {"deleted_at"}
    for attribute in state.mapper.column_attrs:
        if any(c.name in columns for c in attribute.columns):
            if state.attrs[attribute.key].history.has_changes():
                return True
    return False


def attach(session: Any, watch: Watch) -> None:
    from app.kernel.logged import declared

    by_model = {entry.model: entry for entry in declared()}
    by_history = {entry.history: entry for entry in declared()}

    @event.listens_for(session, "before_flush")
    def _before(sess, _context, _instances):
        where = _where()
        for obj in list(sess.new) + list(sess.dirty) + list(sess.deleted):
            entry = by_model.get(type(obj))
            if entry is None:
                continue
            if obj in sess.new:
                operation = "insert"
            elif obj in sess.deleted:
                operation = "delete"
            elif _changed(obj, entry):
                operation = "update"
            else:
                continue
            obj.__dict__["_logged_watch"] = (operation, where)

    @event.listens_for(session, "after_flush")
    def _after(sess, _context):
        for obj in list(sess.new) + list(sess.dirty) + list(sess.deleted):
            mark = obj.__dict__.pop("_logged_watch", None)
            if mark is not None:
                watch.written.setdefault((type(obj).__name__, obj.id), mark)
            entry = by_history.get(type(obj))
            if entry is not None and obj in sess.new:
                watch.logged.add((entry.model.__name__, getattr(obj, entry.key)))

    def pending(sess) -> None:
        # A history row added since the last flush is in `new` still, and counts:
        # a commit flushes it after this point, and a test may end without one.
        for obj in sess.new:
            entry = by_history.get(type(obj))
            if entry is not None:
                watch.logged.add((entry.model.__name__, getattr(obj, entry.key)))

    watch.pending = lambda: pending(session)

    @event.listens_for(session, "after_soft_rollback")
    def _rolled_back(_sess, _previous):
        # What a rollback took back was never written: neither the object nor its
        # history row. (A savepoint's rollback takes back only its own part; the
        # watch forgets everything since the last commit — it may then miss one
        # write that came before a refusal in the same transaction, never invent one.)
        watch.written.clear()
        watch.logged.clear()

    @event.listens_for(session, "before_commit")
    def _commit(sess):
        pending(sess)
        watch.check()


#: The summary is printed once: the domains' conftests take this module's hooks
#: over with `from tests.conftest import *`, so the hook runs once per conftest.
PRINTED = {"done": False}


def mode() -> str:
    return os.environ.get("LOGGED_WATCH", "fail")

"""The history operation: insert, update or delete (CR-12 phase 4).

Every `*_history` table records which of the three happened. It is a closed
list, so it gets a code table and labels like every other one — and **no
foreign key**, by the history exemption of §B4.10 / F4: a history table is
append-only and must keep reading even if a code were ever retired, so its
columns stay plain strings and a value test replaces the key.

It lives in the kernel and in `public`, next to `kernel_jobs`, because no
single domain owns it: every domain with a history table writes it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base
from app.kernel.codes import CodeList, CodeSeed


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Operation(Enum):
    """What a history row records."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class KernelOperationCode(Base):
    """Which codes exist (CR-12 phase 4). No column points here: history exemption."""

    __tablename__ = "kernel_operation_codes"

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class KernelOperationLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "kernel_operation_labels"

    code = Column(String(10), ForeignKey("kernel_operation_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


#: The words `audit/changes.py:_OPERATION_LABELS` held (§B8.5).
OPERATION_CODES = (
    CodeSeed(code="insert", nl="Toegevoegd", en="Added", sort_order=10),
    CodeSeed(code="update", nl="Gewijzigd", en="Changed", sort_order=20),
    CodeSeed(code="delete", nl="Verwijderd", en="Deleted", sort_order=30),
)

OPERATION = CodeList(
    name="kernel_operation", schema="public",
    codes=KernelOperationCode, labels=KernelOperationLabel, enum=Operation,
    # Deliberately no `fk_from`: the history exemption (§B4.10, F4).
    derived=True,
)

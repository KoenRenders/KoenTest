"""Tables of the reporting domain (#833).

Only two, and neither holds a number: the star is views over other domains' data
(#832), so the only thing reporting owns is what a user *composed* and what left
the system.

`SavedReport.selection` is a selection, never a query. The engine rebuilds the SQL
from the universe on every run, so a report saved today keeps working when a view
gains a column tomorrow — and a report that references an object that disappeared
fails loudly, with the object's name, instead of returning a wrong number.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, String

from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class SavedReport(TenantMixin, SoftDeleteMixin, Base):
    """A report a board member composed and named.

    Shared within the tenant by default (CR-06 §5.2): a board shares its reports,
    and a personal draft is the exception. The owner edits; anyone else opens it
    and uses "Kopiëren" to get their own.
    """

    __tablename__ = "saved_reports"
    __table_args__ = {"schema": "reporting"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(String(500), nullable=True)
    # Null for the seven reports that ship with the release: they belong to the
    # tenant rather than to a person.
    owner_email = Column(String(255), nullable=True)
    selection = Column(JSON, nullable=False)
    is_shared = Column(Boolean, nullable=False, default=True, server_default="true")
    # Stable key of a shipped report; null for everything a person creates. The
    # migration's seed is idempotent on it.
    builtin_key = Column(String(60), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    @property
    def is_builtin(self) -> bool:
        return self.builtin_key is not None


class ExportLog(TenantMixin, Base):
    """One row per export — an export is data leaving the system (CR-06 §7.6).

    Append-only and without a foreign key to `saved_reports`, for the same reason
    the history tables carry none: the trail has to survive the thing it describes.
    A report that is deleted afterwards must not take the record of its exports
    with it.

    CR-06 says "in the audit domain". It is not there on purpose: the audit domain
    keeps per-row snapshots inside each domain's own schema and has no table of its
    own for an event, and nothing may import the reporting domain — so an audit
    helper could never reach the data it would be logging. The row lives with the
    domain that produces it; moving it later is a migration.
    """

    __tablename__ = "export_log"
    __table_args__ = {"schema": "reporting"}

    id = Column(BigInteger, primary_key=True, index=True)
    exported_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False,
                         index=True)
    actor = Column(String(255), nullable=True)
    # dataset · report · ad-hoc
    kind = Column(String(20), nullable=False)
    saved_report_id = Column(Integer, nullable=True)
    subject = Column(String(200), nullable=False)
    filters = Column(JSON, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)

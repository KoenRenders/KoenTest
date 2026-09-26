"""Workflow-embryo (#398, §5.7): de minimale kern — taken die sluiten door
toestand. De volwaardige workflow-component (definities/instanties, fase 4b
#403) groeit hieruit; het taakcontract (één vorm, veel bronnen) ligt hier vast."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.domains.auth.api import Role
from app.kernel.codes import EnumColumn


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── The vocabularies this domain owns (CR-12 phase 4) ───────────────────────


class TaskStatus(Enum):
    """A task closes by state (§20.5), so the code branches on this."""

    OPEN = "open"
    DONE = "done"


class RunStatus(Enum):
    """One running instance of a definition (phase 4b, #403)."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


#: The task kinds the sources in this repository create, as codes. **No enum**,
#: and that is a departure from the row §B5.3 gives this list — reported with
#: the phase, and for the reason Koen settled on the contact types on
#: 26 September 2026.
#:
#: Two things hold at once here. Nothing in Python branches on a kind: the
#: workbench derives the category from the part before the dot, looks the label
#: up, and otherwise treats it as opaque — "de werkbank kent nul taak-types"
#: (§20.5). And a `WorkflowDefinition` is **data**: its `steps` JSON names the
#: kind of every step, so a definition row can introduce a kind without a code
#: change. An enum column would refuse that row on the write side, which is the
#: whole point of permissions-as-data (§5.7).
#:
#: What does hold is the foreign key: a kind must exist in
#: `workflow.task_kind_codes`. A new source, or a new definition, brings its
#: row — and with it the Dutch and English word, instead of a fifth entry in a
#: dictionary inside a screen.
PAYMENT_WEBHOOK_MISMATCH = "payment.webhook_mismatch"
PAYMENT_CONFIRM_REFUND = "payment.refund_bevestigen"
MAIL_PERMANENTLY_FAILED = "mail.definitief_gefaald"
KERNEL_JOB_FAILED = "kernel.job_gefaald"


class WorkflowTask(TenantMixin, Base):
    __tablename__ = "workflow_tasks"
    __table_args__ = {"schema": "workflow"}

    id = Column(Integer, primary_key=True)
    # Taak-type, bv. "payment.webhook_mismatch" — `category.subject` (#549).
    # Een code en geen enum-lid; zie de constanten bovenaan voor de reden.
    kind = Column(String(100), ForeignKey("workflow.task_kind_codes.code"),
                  nullable=False, index=True)
    title = Column(String(300), nullable=False)
    # Soft-ref naar het onderwerp (waarde, geen FK — §6): bv. ("form_submission", "7").
    #
    # #704: TEKST, niet een getal. Een onderwerp-id is een ondoorzichtige sleutel en
    # hoort niet te weten of de bron een reeksnummer of een UUID gebruikt. Zolang
    # dit een `Integer` was, paste `PaymentRecord.id` (UUID in String(36)) er niet
    # in, en vulden de betaaltaken er `payable_id` in terwijl `subject_type`
    # "payment_record" zei — het type zei iets wat de waarde niet was.
    subject_type = Column(String(50), nullable=False)
    subject_id = Column(String(36), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        EnumColumn(TaskStatus, length=10),
        ForeignKey("workflow.task_status_codes.code"), nullable=False,
        default=TaskStatus.OPEN, index=True)
    # CR-12 phase 2: the same list as `auth.user_roles.role_code`, so the
    # same shape. The foreign key goes cross-schema to `auth.role_codes` —
    # the exception of §B2.4, and exactly why roles belong in `auth` and not
    # in whichever domain happens to use them.
    required_role: Mapped[Role] = mapped_column(
        EnumColumn(Role, length=20), ForeignKey("auth.role_codes.code"),
        nullable=False, default=Role.ADMIN)
    # "Een afwijzing is ook een beslissing": het bewaarde besluit bij afhandeling.
    decision = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    done_at = Column(DateTime(timezone=True), nullable=True)
    done_by = Column(String(255), nullable=True)
    # Gezet wanneer de taak een stap van een workflow-instantie is (fase 4b).
    instance_id = Column(Integer, ForeignKey("workflow.workflow_instances.id"), nullable=True, index=True)


class WorkflowDefinition(TenantMixin, Base):
    """Workflow-definitie (fase 4b, #403): een codeerbare reeks stappen.
    ``steps`` = JSON-lijst van {"kind", "title", "role"} — bewust plat en
    data-gedreven (permissies-als-data, §5.7)."""

    __tablename__ = "workflow_definitions"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    steps = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))


class WorkflowInstance(TenantMixin, Base):
    """Eén lopend exemplaar van een definitie, gekoppeld aan een onderwerp
    (soft-ref). ``current_step`` is de index in de definitie-stappen."""

    __tablename__ = "workflow_instances"
    __table_args__ = {"schema": "workflow"}

    id = Column(Integer, primary_key=True)
    definition_code = Column(String(50), nullable=False, index=True)
    subject_type = Column(String(50), nullable=False)
    # Tekst, net als bij de taak (#704): een instantie geeft dit door aan de taak
    # van elke stap, dus twee vormen voor hetzelfde begrip lopen daar samen.
    subject_id = Column(String(36), nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    status: Mapped[RunStatus] = mapped_column(
        EnumColumn(RunStatus, length=10),
        ForeignKey("workflow.run_status_codes.code"), nullable=False,
        default=RunStatus.RUNNING, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    done_at = Column(DateTime(timezone=True), nullable=True)


class TaskStatusCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "task_status_codes"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class TaskStatusLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "task_status_labels"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(10), ForeignKey("workflow.task_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class RunStatusCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "run_status_codes"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class RunStatusLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "run_status_labels"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(10), ForeignKey("workflow.run_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class TaskKindCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "task_kind_codes"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(100), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class TaskKindLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "task_kind_labels"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(100), ForeignKey("workflow.task_kind_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class TaskCategoryCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "task_category_codes"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(50), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class TaskCategoryLabel(Base):
    """The word a screen shows for this code, per language (CR-12 phase 4)."""

    __tablename__ = "task_category_labels"
    __table_args__ = {"schema": "workflow"}

    code = Column(String(50), ForeignKey("workflow.task_category_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

"""Workflow-embryo (#398, §5.7): de minimale kern — taken die sluiten door
toestand. De volwaardige workflow-component (definities/instanties, fase 4b
#403) groeit hieruit; het taakcontract (één vorm, veel bronnen) ligt hier vast."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database import Base
from app.kernel.tenancy import TenantMixin


class WorkflowTask(TenantMixin, Base):
    __tablename__ = "workflow_tasks"
    __table_args__ = {"schema": "workflow"}

    id = Column(Integer, primary_key=True)
    # Taak-type, bv. "bericht.behartigen" — de bron bepaalt de betekenis.
    kind = Column(String(100), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    # Soft-ref naar het onderwerp (waarde, geen FK — §6): bv. ("form_submission", 7).
    subject_type = Column(String(50), nullable=False)
    subject_id = Column(Integer, nullable=False)
    # open | done — taken sluiten door toestand (§20.5).
    status = Column(String(10), nullable=False, default="open", index=True)
    required_role = Column(String(20), nullable=False, default="ADMIN")
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
    subject_id = Column(Integer, nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    # running | done
    status = Column(String(10), nullable=False, default="running", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    done_at = Column(DateTime(timezone=True), nullable=True)

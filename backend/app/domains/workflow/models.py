"""Workflow-embryo (#398, §5.7): de minimale kern — taken die sluiten door
toestand. De volwaardige workflow-component (definities/instanties, fase 4b
#403) groeit hieruit; het taakcontract (één vorm, veel bronnen) ligt hier vast."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class WorkflowTask(Base):
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

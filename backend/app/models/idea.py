from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.database import Base


class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True)
    submitter_name = Column(String(200), nullable=False)
    submitter_email = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_reviewed = Column(Boolean, default=False, nullable=False)

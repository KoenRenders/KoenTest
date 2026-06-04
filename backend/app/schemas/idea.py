from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IdeaCreate(BaseModel):
    submitter_name: str
    submitter_email: Optional[str] = None
    content: str


class IdeaResponse(BaseModel):
    id: int
    submitter_name: str
    submitter_email: Optional[str] = None
    content: str
    submitted_at: datetime
    is_reviewed: bool

    model_config = {"from_attributes": True}

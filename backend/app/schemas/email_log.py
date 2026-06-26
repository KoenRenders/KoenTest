from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class EmailLogResponse(BaseModel):
    id: int
    recipient: str
    subject: str
    email_type: str
    body: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EmailLogPage(BaseModel):
    items: List[EmailLogResponse]
    total: int
    page: int
    per_page: int

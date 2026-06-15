from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CmsPageCreate(BaseModel):
    title: str
    slug: str
    content: Optional[str] = None
    is_published: bool = False
    show_in_nav: bool = True
    sort_order: int = 0


class CmsPageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    is_published: Optional[bool] = None
    show_in_nav: Optional[bool] = None
    sort_order: Optional[int] = None


class CmsPageResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: Optional[str] = None
    is_published: bool
    show_in_nav: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

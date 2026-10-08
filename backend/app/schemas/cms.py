from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
    is_home: Optional[bool] = None
    show_in_footer: Optional[bool] = None
    sort_order: Optional[int] = None


class CmsPageApiUpdate(BaseModel):
    """The JSON door's page update (Koen, 8 October 2026, decision 2a on
    #1734): `content` and `is_published` no longer ride — the editor writes
    the documents, publishing is the screen's action. Extra inputs are
    REFUSED, so a caller who still sends them learns it instead of being
    silently ignored."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    slug: Optional[str] = None
    show_in_nav: Optional[bool] = None
    is_home: Optional[bool] = None
    show_in_footer: Optional[bool] = None
    sort_order: Optional[int] = None


class CmsPageResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: Optional[str] = None
    is_published: bool
    show_in_nav: bool
    show_in_footer: bool = False
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

from __future__ import annotations

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
    is_home: Optional[bool] = None
    show_in_footer: Optional[bool] = None
    sort_order: Optional[int] = None
    opening: Optional[str] = None
    hero: Optional[dict] = None
    # CR-17 phase 6 (#2024). Unlike the fields above, None is a value here —
    # no section, the title in the menu — so these two are applied when they
    # were SET, not when they are not None (`cms.service._apply_page_fields`).
    parent_id: Optional[int] = None
    menu_label: Optional[str] = None

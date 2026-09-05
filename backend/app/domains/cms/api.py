"""Publieke facade van het cms-component (fase 4c, #404)."""
from app.domains.cms.models import CmsPage  # noqa: F401
from app.domains.cms.render import (  # noqa: F401
    _format_md, _format_price, render_cms_content, sanitize_cms_html,
)

from app.domains.cms.service import (  # noqa: F401
    SlugBestaatAl,
    create_page,
    delete_page,
    get_page,
    get_page_by_id,
    get_published_page,
    list_pages,
    placeholders,
    published_slugs,
    update_page,
)

__all__ = [
    "SlugBestaatAl", "create_page", "delete_page", "get_page",
    "get_page_by_id", "get_published_page", "list_pages", "placeholders",
    "published_slugs", "update_page","CmsPage", "render_cms_content", "sanitize_cms_html",
           "_format_md", "_format_price"]

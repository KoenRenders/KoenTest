"""Publieke facade van het cms-component (fase 4c, #404)."""

from app.domains.cms.models import CmsPage  # noqa: F401
from app.domains.cms.render import (  # noqa: F401
    _format_md,
    _format_price,
    render_cms_content,
    sanitize_cms_html,
)
from app.domains.cms.service import (  # noqa: F401
    SITE_BLOCK_SLUGS,
    SlugBestaatAl,
    create_page,
    delete_page,
    get_page_by_id,
    get_published_page,
    is_page,
    list_pages,
    placeholders,
    published_home_page,
    published_page,
    published_slugs,
    references_to_media,
    seed_site_blocks,
    update_page,
    verplaats_pagina,
)

__all__ = [
    "SlugBestaatAl",
    "create_page",
    "delete_page",
    "verplaats_pagina",
    "get_page_by_id",
    "get_published_page",
    "list_pages",
    "placeholders",
    # CR-15 #1471: which pages show a picture.
    "references_to_media",
    # CR-19 #1478: the blocks a new tenant's site starts with.
    "seed_site_blocks",
    "published_home_page",
    "published_slugs",
    "published_page",
    "is_page",
    "SITE_BLOCK_SLUGS",
    "update_page",
    "CmsPage",
    "render_cms_content",
    "sanitize_cms_html",
    "_format_md",
    "_format_price",
]

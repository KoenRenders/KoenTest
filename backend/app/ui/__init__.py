"""UI-fundament (#396/#398, §21): Jinja-templates + htmx/Alpine, server-rendered.

Elke component levert zijn schermen als ``ui.py`` (routes: view-model bouwen,
template kiezen) + ``templates/`` (dom: alleen tonen). Dit pakket levert de
gedeelde machinerie: de template-omgeving (met de component-template-mappen),
de UI-kit-macro's en de shells (base-layouts).
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

_UI_DIR = Path(__file__).parent

# Component-template-mappen haken hier in (fase 0+ voegen paden toe).
_DOMAINS = _UI_DIR.parent / "domains"
template_dirs: list[str] = [str(_UI_DIR / "templates")] + sorted(
    str(p) for p in _DOMAINS.glob("*/templates") if p.is_dir()
)

templates = Jinja2Templates(directory=template_dirs)


def site_context(db) -> dict:
    """Gedeelde context van de SiteShell (site_base.html): navigatie-pagina's,
    footer-blok en sponsors. Eén plek, elke publieke route neemt hem mee."""
    from datetime import date

    from app.domains.cms.api import CmsPage, render_cms_content
    from app.domains.media.api import MediaAsset

    pages = (db.query(CmsPage)
             .filter(CmsPage.is_published == True)  # noqa: E712
             .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc()).all())
    footer = db.query(CmsPage).filter(CmsPage.slug == "site-footer").first()
    footer_block = None
    if footer is not None:
        footer_block = {"content": render_cms_content(footer.content or "")}
    sponsors = (db.query(MediaAsset)
                .filter(MediaAsset.kind == "sponsor", MediaAsset.is_active == True)  # noqa: E712
                .order_by(MediaAsset.sort_order, MediaAsset.id).all())
    return {"nav_pages": pages, "footer_block": footer_block,
            "sponsors": sponsors, "current_year": date.today().year}

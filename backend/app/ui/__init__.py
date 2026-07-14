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

# Taalbeleid (#407-T): {{ _("...") }} beschikbaar in alle templates, volgend
# op de actieve tenant-taal.
from app.i18n import install_jinja_i18n  # noqa: E402

install_jinja_i18n(templates.env)


def _langedatum(d) -> str:
    """Lange Nederlandse datum, bv. 'zaterdag 29 augustus 2026' (#451)."""
    if d is None:
        return ""
    from babel.dates import format_date
    from app.i18n import current_locale

    return format_date(d, format="full", locale=current_locale.get())


templates.env.filters["langedatum"] = _langedatum

# Canonieke admin-navigatie (React-exit 405-d, #405): één bron voor alle
# server-rendered beheer-schermen i.p.v. een kopie per module.
_ADMIN_NAV: list[tuple[str, str]] = [
    ("/admin/werkbank", "Werkbank"),
    ("/admin/activiteiten", "Activiteiten"),
    ("/admin/leden", "Leden"),
    ("/admin/betalingen", "Betalingen"),
    ("/admin/formulieren", "Formulieren"),
    ("/admin/paginas", "Pagina's"),
    ("/admin/media", "Media"),
    ("/admin/gebruikers", "Gebruikers"),
    ("/admin/ledenwijzigingen", "Wijzigingen"),
    ("/admin/ai-context", "Raakje"),
    ("/admin/e-maillog", "E-maillog"),
    ("/admin/info", "Info"),
    ("/admin/instellingen", "Instellingen"),
]


def admin_nav(active: str) -> list[dict]:
    """Navigatie-items voor de AdminShell; `active` is de href van het scherm."""
    from app.i18n import _

    return [{"href": href, "label": _(label), "active": href == active}
            for href, label in _ADMIN_NAV]


def _huidige_gebruiker(db, request) -> dict | None:
    """Ingelogde gebruiker uit de sessie-cookie (#467): naam + is_admin, of None.
    Mag het renderen nooit breken."""
    if request is None:
        return None
    try:
        from app.domains.auth.api import (
            SESSION_COOKIE, get_user_roles, login_person_for_email, read_session_value)

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
        if not email:
            return None
        naam = email
        person = login_person_for_email(db, email)
        if person is not None:
            naam = f"{person.first_name} {person.last_name}".strip() or email
        return {"email": email, "naam": naam,
                "is_admin": "ADMIN" in get_user_roles(db, email)}
    except Exception:
        return None


def site_context(db, request=None) -> dict:
    """Gedeelde context van de SiteShell (site_base.html): navigatie-pagina's,
    footer-blok en sponsors. Eén plek, elke publieke route neemt hem mee."""
    from datetime import date

    from app.domains.cms.api import CmsPage, render_cms_content
    from app.domains.media.api import MediaAsset

    pages = (db.query(CmsPage)
             .filter(CmsPage.is_published == True,        # noqa: E712
                     CmsPage.show_in_nav == True)         # noqa: E712  (#465)
             .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc()).all())
    footer = db.query(CmsPage).filter(CmsPage.slug == "site-footer").first()
    footer_block = None
    if footer is not None:
        footer_block = {"content": render_cms_content(footer.content or "")}
    sponsors = (db.query(MediaAsset)
                .filter(MediaAsset.kind == "sponsor", MediaAsset.is_active == True)  # noqa: E712
                .order_by(MediaAsset.sort_order, MediaAsset.id).all())
    from app.kernel.tenant_config import get_setting, tenant_display_name
    from app.config import settings

    return {"nav_pages": pages, "footer_block": footer_block,
            "sponsors": sponsors, "current_year": date.today().year,
            "chat_enabled": settings.chat_enabled,
            "gebruiker": _huidige_gebruiker(db, request),
            # Branding per tenant (#407): naam/tagline/Facebook uit de
            # tenant-config, met de Millegem-waarden als default.
            "site_name": tenant_display_name(db),
            "site_tagline": get_setting(db, "tagline") or "Beleef meer in Millegem",
            "facebook_url": get_setting(db, "facebook_url")
                or "https://www.facebook.com/raakmillegem"}

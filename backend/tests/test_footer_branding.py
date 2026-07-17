"""Footer/branding zonder hardgecodeerde Millegem-defaults (#519 Deel B).

De multi-tenancy-invariant: een tenant zonder eigen tagline/Facebook krijgt GEEN
Millegem-fallback te zien (die lekte vroeger naar andere afdelingen). Leeg = niet
tonen; met waarde = de tenant-eigen waarde.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"


def _env():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    from app.i18n import install_jinja_i18n
    install_jinja_i18n(env)
    return env


def _render(**overrides):
    ctx = dict(nav_pages=[], sponsors=[], gebruiker=None, footer_block=None,
               current_year=2026, chat_enabled=False, canonical_url=None,
               base_url="", site_name="Raak Voorbeeld", site_tagline="",
               facebook_url=None, instagram_url=None, tiktok_url=None,
               omgeving="prod")
    ctx.update(overrides)
    return _env().get_template("site_base.html").render(**ctx)


def test_geen_millegem_fallback_zonder_waarden():
    html = _render()
    assert "Millegem" not in html                 # geen hardgecodeerde default
    assert 'aria-label="Facebook"' not in html     # geen kapotte lege FB-link


def test_tenant_eigen_waarden_getoond():
    html = _render(site_tagline="Onze eigen leuze",
                   facebook_url="https://www.facebook.com/raakvoorbeeld")
    assert "Onze eigen leuze" in html
    assert 'aria-label="Facebook"' in html
    assert "raakvoorbeeld" in html


def test_site_context_default_leeg(db_session):
    """De context-bron zelf: zonder settings is tagline leeg en facebook None."""
    from app.ui import site_context

    ctx = site_context(db_session)
    assert ctx["site_tagline"] == ""
    assert ctx["facebook_url"] is None

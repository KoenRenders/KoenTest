"""E2E: a tenant's brand and accent colour on the public site (#1622, CR-11 Q68).

What only a browser shows — what the cascade made of the tokens on the body:

- **with the two colours set**, a section heading, a link, the primary button
  and the footer's one call ("Aanmelden") render in them, the call's text in
  the colour derived on contrast;
- **the other tenants keep the palette**: a company and the platform that set
  nothing still resolve the brand token to Atelier's;
- **the back office does not change colour**: its tokens and a screenshot of an
  admin screen are the same before and after;
- **only colour changes**: the boxes of the heading, the first card, the button
  and the footer stand where they stood, at 390 and at 1 440 px.

The colours are set on the seeded association through `set_setting` and taken
away again; no other test sees them.

Proven red (on this branch, restored after): the `style` taken off the `<body>`
in `site_base.html` → the tokens stay Atelier's and the heading `rgb(33, 45, 58)`;
`--c-kop` left out of `brand_tokens` → "the section heading @390: rgb(33, 45, 58)",
the tokens themselves pass.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

BRAND = "#0051a4"
ACCENT = "#ffd200"
BRAND_RGB = "rgb(0, 81, 164)"
ACCENT_RGB = "rgb(255, 210, 0)"
INK_ON_ACCENT = "rgb(37, 44, 53)"
ATELIER_BRAND = "37 78 115"
ATELIER_ACCENT = "238 193 94"

READ = """() => {
  const css = (e, p) => e ? getComputedStyle(e)[p] : null;
  const box = e => { if (!e) return null; const r = e.getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)]; };
  const q = s => document.querySelector(s);
  const heading = [...document.querySelectorAll('#main h2')].find(e => !e.closest('.rounded-2xl'));
  const link = q('#main h2 a[href*="/activiteiten/"]');
  const button = [...document.querySelectorAll('#main a, #main button')].find(e => e.textContent.trim() === 'Inschrijven');
  const call = q('#nb-voet-link');
  const body = getComputedStyle(document.body);
  return {
    tokens: {brand: body.getPropertyValue('--c-brand').trim(), accent: body.getPropertyValue('--c-accent').trim()},
    heading: css(heading, 'color'), link: css(link, 'color'), button: css(button, 'backgroundColor'),
    button_text: css(button, 'color'), call: css(call, 'backgroundColor'), call_text: css(call, 'color'),
    boxes: {heading: box(heading), card: box(link && link.closest('.rounded-2xl')), button: box(button),
            call: box(call), footer: box(q('footer')), page: document.documentElement.scrollWidth},
  };
}"""


def _set(brand, accent):
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.kernel.tenant_config import (
        SITE_ACCENT_COLOR_KEY,
        SITE_BRAND_COLOR_KEY,
        _actieve_tenant,
        set_setting,
    )

    db = SessionLocal()
    try:
        tenant = _actieve_tenant(None)
        set_setting(db, SITE_BRAND_COLOR_KEY, brand, tenant_id=tenant)
        set_setting(db, SITE_ACCENT_COLOR_KEY, accent, tenant_id=tenant)
        db.commit()
    finally:
        db.close()


def _company_home() -> str | None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Organization, TenantKind

    db = SessionLocal()
    try:
        company = (
            db.query(Organization.code)
            .filter(Organization.kind == TenantKind.COMPANY, Organization.is_active.is_(True))
            .execution_options(include_all_tenants=True)
            .order_by(Organization.id.desc())
            .first()
        )
    finally:
        db.close()
    return f"{PLATFORM}/{company[0].lower()}/" if company else None


@pytest.fixture(scope="module")
def measured():
    """Every page before the colours are set and after, in one browser."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    out: dict = {}
    others = {"platform": PLATFORM + "/"}
    company = _company_home()
    if company:
        others["company"] = company
    _set(None, None)
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        try:
            for moment in ("before", "after"):
                if moment == "after":
                    _set(BRAND, ACCENT)
                for width, height in ((390, 844), (1440, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto(BASE + "/")
                    pagina_klaar(page)
                    page.evaluate("() => document.fonts.ready")
                    out[(moment, "association", width)] = page.evaluate(READ)
                    page.close()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                for kind, url in others.items():
                    page.goto(url)
                    pagina_klaar(page)
                    out[(moment, kind)] = page.evaluate(READ)["tokens"]
                login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
                page.goto(BASE + "/admin/design-system")
                pagina_klaar(page)
                page.evaluate("() => document.fonts.ready")
                out[(moment, "admin")] = {
                    "tokens": page.evaluate(READ)["tokens"],
                    "style": page.evaluate("() => document.body.getAttribute('style')"),
                    "shot": page.screenshot(),
                }
                page.close()
        finally:
            _set(None, None)
            browser.close()
    print(
        "MEASURE colours",
        {k: v for k, v in out.items() if k[1] != "admin"},
        {k: (v["tokens"], v["style"], len(v["shot"])) for k, v in out.items() if k[1] == "admin"},
    )
    return out


def test_without_a_setting_the_association_wears_the_palette(measured):
    for width in (390, 1440):
        before = measured[("before", "association", width)]
        assert before["tokens"] == {"brand": ATELIER_BRAND, "accent": ATELIER_ACCENT}, before
        assert before["call"] == "rgb(238, 193, 94)" and before["button"] == "rgb(37, 78, 115)"


@pytest.mark.parametrize("width", [390, 1440])
def test_with_the_colours_set_the_site_wears_them(measured, width):
    after = measured[("after", "association", width)]
    assert after["tokens"] == {"brand": "0 81 164", "accent": "255 210 0"}, after
    assert after["heading"] == BRAND_RGB, f"the section heading @{width}: {after['heading']}"
    assert after["link"] == BRAND_RGB, f"a link @{width}: {after['link']}"
    assert after["button"] == BRAND_RGB, f"the primary button @{width}: {after['button']}"
    assert after["button_text"] == "rgb(255, 255, 255)", after["button_text"]
    assert after["call"] == ACCENT_RGB, f"Aanmelden @{width}: {after['call']}"
    assert after["call_text"] == INK_ON_ACCENT, (
        f"the text on Aanmelden @{width}: {after['call_text']}"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_only_the_colour_changes(measured, width):
    before = measured[("before", "association", width)]["boxes"]
    after = measured[("after", "association", width)]["boxes"]
    assert all(before[name] for name in ("heading", "card", "button", "call", "footer")), before
    assert after == before, f"the layout moved @{width}: {before} → {after}"
    assert after["page"] == width


def test_the_other_tenants_keep_the_palette(measured):
    others = [
        key[1] for key in measured if key[0] == "after" and len(key) == 2 and key[1] != "admin"
    ]
    assert "platform" in others, "the platform was not reached"
    for kind in others:
        assert measured[("after", kind)] == {"brand": ATELIER_BRAND, "accent": ATELIER_ACCENT}, (
            f"{kind} took the association's colours: {measured[('after', kind)]}"
        )


def test_the_back_office_does_not_change_colour(measured):
    before, after = measured[("before", "admin")], measured[("after", "admin")]
    assert before["tokens"]["brand"], "the admin's brand token was not read"
    assert after["tokens"] == before["tokens"], (before["tokens"], after["tokens"])
    assert after["style"] is None and before["style"] is None, "the admin body carries a style"
    assert after["shot"] == before["shot"], "the design-system page renders differently"

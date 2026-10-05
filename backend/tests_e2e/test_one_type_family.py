"""E2E: one type family on both shells, and the public headings a little larger
(#1606, Koen, 5 October 2026; `docs/design-system-end-state.md` §1.6, §2.6).

P1 (#1588) gave the public headings a serif face of their own. Koen, after
seeing HDEV: "Ik vind het publieke lettertype geen vooruitgang (vooral headings
en titels activiteiten). Kunnen we meer aligneren met back office?" — and on
the scale: "iets groter houden". So: Inter everywhere, and the public headings
on their own scale — page title 40 px (32 on a phone), section head 24 px, card
title 18 px, Inter 600, line height 1.15.

#1621 (Koen, 5 October 2026): a title INSIDE a card is the scale's card title,
18 px at every width, on Tailwind's line of 28 px — not a section head. Red
against master `3f1525a2`: the home's card titles measured 24 px on a line of
27.6 px, at both widths. (v2.12.0 showed 20 px on a phone; the scale of Q61
says 18.)

Read from the rendered page (`getComputedStyle`), because a class in a template
says nothing about what the cascade made of it: the scale stands on the
heading's tag in the shell's CSS and must win from whatever size class a page
still carries.

Proven red against master `1d985b16`: the public `h1` rendered in "Fraunces"
at weight 650, and the activity's title at 30 px on a desktop and 24 px on a
phone.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

HEADINGS = """() => {
  const main = document.querySelector('#main');
  const read = e => { const s = getComputedStyle(e); return {
    family: s.fontFamily.split(',')[0].replace(/"/g, '').trim(), size: parseFloat(s.fontSize),
    weight: s.fontWeight, ratio: Math.round(parseFloat(s.lineHeight) / parseFloat(s.fontSize) * 100) / 100,
    line: parseFloat(s.lineHeight), section: !!e.closest('.form-section'),
    card: !!e.closest('.rounded-2xl') && e.tagName !== 'H1' }; };
  const all = t => [...main.querySelectorAll(t)].filter(e => e.checkVisibility()).map(read);
  const footer = [...document.querySelectorAll('.site-footer h2')].map(read);
  return {h1: all('h1'), h2: all('h2'), h3: all('h3'), footer: footer,
          body: getComputedStyle(document.body).fontFamily.split(',')[0].replace(/"/g, '').trim()};
}"""


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    activity, component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    email = f"e2e-1606-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {
        "public": {
            "home": "/",
            "activities": "/activiteiten",
            "activity": f"/activiteiten/{activity.id}",
            "register": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
            "Word lid": "/lid-worden",
        },
        "admin": f"/admin/activiteiten/{activity.id}",
        "session": make_session_value(email),
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def measured(setup):
    out: dict = {}
    fonts: set[str] = set()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        for width, height in ((390, 844), (1440, 900)):
            page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
            page.on(
                "request",
                lambda r: (
                    fonts.add(r.url.rsplit("/", 1)[-1].split("?")[0])
                    if "/fonts/" in r.url
                    else None
                ),
            )
            for name, path in setup["public"].items():
                page.goto(path)
                pagina_klaar(page)
                page.evaluate("() => document.fonts.ready")
                out[(name, width)] = page.evaluate(HEADINGS)
            login_met_sessie(page, setup["session"])
            page.goto(setup["admin"])
            pagina_klaar(page)
            out[("admin", width)] = page.evaluate(HEADINGS)
            page.close()
        browser.close()
    out["fonts"] = fonts
    print("MEASURE headings", {k: v for k, v in out.items() if k != "fonts"}, sorted(fonts))
    return out


@pytest.mark.parametrize("width", [390, 1440])
def test_every_heading_on_both_shells_is_inter(measured, width):
    seen = 0
    for key, page in measured.items():
        if key == "fonts" or key[1] != width:
            continue
        name = key[0]
        assert page["body"] == "Inter", (name, page["body"])
        for level in ("h1", "h2", "h3", "footer"):
            for heading in page[level]:
                seen += 1
                assert heading["family"] == "Inter", f"{name} @{width} {level}: {heading}"
    assert seen >= 10, f"only {seen} headings measured"
    assert measured[("admin", width)]["h1"], "the admin page was measured without its title"


def test_no_font_file_of_another_family_is_asked_for(measured):
    assert measured["fonts"], "no font request was seen — the listener looks nowhere"
    other = sorted(f for f in measured["fonts"] if not f.startswith("Inter"))
    assert other == [], f"a font file of another family is requested: {other}"


@pytest.mark.parametrize(("width", "title"), [(390, 32), (1440, 40)])
def test_the_public_headings_follow_their_scale(measured, width, title):
    titles = 0
    for name in ("activity", "register", "Word lid"):
        page = measured[(name, width)]
        assert len(page["h1"]) == 1, f"{name}: {len(page['h1'])} titles"
        h1 = page["h1"][0]
        titles += 1
        assert (h1["size"], h1["weight"], h1["ratio"]) == (title, "600", 1.15), (
            f"{name} @{width}: {h1}"
        )
    assert titles == 3
    for name in ("home", "activities", "activity", "register", "Word lid"):
        page = measured[(name, width)]
        for h2 in page["h2"]:
            if h2["card"] and not h2["section"]:
                continue  # #1621: its own test below
            # A section of a FORM keeps the kit's head; every other h2 is a section head.
            expected = (16, "600") if h2["section"] else (24, "600")
            assert (h2["size"], h2["weight"]) == expected, f"{name} @{width} h2: {h2}"
            if not h2["section"]:
                assert h2["ratio"] == 1.15, f"{name} @{width} h2: {h2}"
        for h3 in page["h3"]:
            expected = (16, "600") if h3["section"] else (18, "600")
            assert (h3["size"], h3["weight"]) == expected, f"{name} @{width} h3: {h3}"
        for h2 in page["footer"]:
            assert (h2["size"], h2["weight"]) == (18, "600"), f"{name} @{width} footer: {h2}"
    # The scale is the PUBLIC one: the admin's title is smaller.
    admin = measured[("admin", width)]["h1"][0]
    assert admin["size"] < title, f"the admin's title is {admin['size']} px"


@pytest.mark.parametrize(("width", "size"), [(390, 18), (1440, 18)])
def test_a_card_title_is_a_card_title_on_its_own_line(measured, width, size):
    """#1621: an activity card's title renders at the scale's card size,
    18 px, on Tailwind's line of 28 px, in the shell's family and weight —
    and the page title above it keeps 1.15."""
    seen = 0
    for name in ("home", "activities"):
        titles = [h for h in measured[(name, width)]["h2"] if h["card"] and not h["section"]]
        assert titles, f"{name} @{width}: no card title was measured"
        for h2 in titles:
            seen += 1
            assert (h2["size"], h2["line"]) == (size, 28), f"{name} @{width}: {h2}"
            assert (h2["family"], h2["weight"]) == ("Inter", "600"), f"{name} @{width}: {h2}"
    assert seen >= 2
    h1 = measured[("activities", width)]["h1"][0]
    assert h1["ratio"] == 1.15, f"the page title @{width}: {h1}"


def test_the_three_kinds_of_tenant_share_the_headings_and_name_their_own_newsletter():
    """An association, a company and the platform: the same family and scale on
    each, and where the footer carries the newsletter its heading is "Nieuws
    van" plus THAT site's name (#1606 — never the town)."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.mdm.api import Organization, TenantKind
    from tests_e2e.schermen import PLATFORM

    db = SessionLocal()
    company = (
        db.query(Organization.code)
        .filter(Organization.kind == TenantKind.COMPANY, Organization.is_active.is_(True))
        .execution_options(include_all_tenants=True)
        .order_by(Organization.id.desc())
        .first()
    )
    db.close()
    homes = {"association": BASE + "/", "platform": PLATFORM + "/"}
    if company:
        homes["company"] = f"{PLATFORM}/{company[0].lower()}/"

    read = """() => {
      const fam = e => getComputedStyle(e).fontFamily.split(',')[0].replace(/"/g, '').trim();
      const heads = [...document.querySelectorAll('#main h1, #main h2, #main h3, .site-footer h2')].filter(e => e.checkVisibility());
      const news = document.querySelector('[data-footer-newsletter] h2');
      return {families: [...new Set(heads.map(fam))], count: heads.length,
              site: document.querySelector('meta[property="og:site_name"]').content,
              newsletter: news ? news.textContent.trim() : null};
    }"""
    found = {}
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for kind, url in homes.items():
            page.goto(url)
            pagina_klaar(page)
            found[kind] = page.evaluate(read)
        browser.close()
    print("MEASURE tenants", found)
    assert len(found) >= 2, "only one tenant was reached"
    with_newsletter = 0
    for kind, m in found.items():
        # A home page may be empty (a new company has no heading yet): what it
        # has, is Inter.
        assert set(m["families"]) <= {"Inter"}, f"{kind}: {m}"
        if m["newsletter"] is not None:
            with_newsletter += 1
            assert m["newsletter"] == f"Nieuws van {m['site']}", f"{kind}: {m}"
    assert with_newsletter >= 1, "no tenant showed the newsletter's heading"
    assert sum(m["count"] for m in found.values()) >= 5, "hardly a heading was measured"

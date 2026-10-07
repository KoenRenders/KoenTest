"""E2E: the small visible corrections of the public activity and photo pages
(#1664; CR-11 pilot C, C2 — Z2, Z3, Z4, Z7; end state §2.7). Z1, the sponsor
block, stands with the footer's other measures in
`test_calm_footer_and_badges.py`.

- **one year heading**: the photo overview's is the activity list's;
- **the album card on the public card**: the kit's radius and line colour;
- **one way back**: the kit's chevron and the origin's name — "Activiteiten",
  "Archief", "Foto's" — with a larger hit area on a phone that takes no room;
- **the browser title** names the site, never a literal association.

An activity that is over, with one photo, is made for this file and removed
again: the e2e seed has no album.

Red against C1 (`c252bea9`, measured): the photo overview's heading with a line
in `rgb(156, 184, 210)` and 8 px above it, the list's in `rgb(216, 224, 230)`
and 4 px (both 18 px in weight 600 at every width: the public title scale sets
an `h3`); the way back "← Alle activiteiten" / "← Terug naar alle albums"
without an icon, and above the album no `nav` at all; the title "Foto's — Raak
Millegem". The album card's test was GREEN against C1 already: `rounded-2xl` is
14 px in the public shell and `gray-200` is the line colour there — Z3 changes
the token, not the picture.
"""

import os
import sys
from datetime import date, timedelta
from io import BytesIO

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

NAME = "Meting voorbije wandeling 1664"


def _png() -> bytes:
    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (320, 240), (37, 78, 115)).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(scope="module")
def album():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    try:
        activity = Activity(name=NAME)
        db.add(activity)
        db.flush()
        day = ActivityDate(activity_id=activity.id, start_date=date.today() - timedelta(days=60))
        photo = MediaAsset(
            kind="activity_photo",
            activity_id=activity.id,
            title="Meting foto",
            data=_png(),
            content_type="image/png",
            thumbnail=_png(),
            thumb_content_type="image/png",
            width=320,
            height=240,
            byte_size=10,
            sort_order=0,
            is_active=True,
        )
        db.add_all([day, photo])
        db.commit()
        made = {"activity": activity.id, "day": day.id, "photo": photo.id}
    finally:
        db.close()

    yield made

    db = SessionLocal()
    try:
        for model, key in ((MediaAsset, "photo"), (ActivityDate, "day"), (Activity, "activity")):
            db.query(model).filter(model.id == made[key]).execution_options(
                include_all_tenants=True, include_deleted=True
            ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, path: str, width: int):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.goto(path)
    pagina_klaar(page)
    return page


HEADING = """() => { const h = document.querySelector('[data-year-heading]'), s = getComputedStyle(h);
  return {tag: h.tagName, size: s.fontSize, weight: s.fontWeight, colour: s.color, line: s.lineHeight,
          border: [s.borderBottomWidth, s.borderBottomColor], pad: s.paddingBottom}; }"""


@pytest.mark.parametrize(("width", "size"), [(390, "18px"), (1440, "18px")])
def test_the_photo_overviews_year_heading_is_the_activity_lists(browser, album, width, size):
    page = _open(browser, "/fotos", width)
    photos = page.evaluate(HEADING)
    page.close()
    page = _open(browser, "/activiteiten", width)
    activities = page.evaluate(HEADING)
    page.close()
    print("MEASURE year heading", width, photos, activities)
    assert photos == activities, f"@{width}: Foto's {photos}, Activiteiten {activities}"
    assert (photos["size"], photos["weight"], photos["border"][0]) == (size, "600", "1px"), photos


CARD = """() => { const c = document.querySelector('[data-photo-card]'), s = getComputedStyle(c);
  const probe = document.createElement('div'); probe.className = 'border border-line'; document.body.append(probe);
  const line = getComputedStyle(probe).borderTopColor; probe.remove();
  const r = c.getBoundingClientRect(), img = c.querySelector('img').parentElement.getBoundingClientRect();
  const name = getComputedStyle(c.querySelector('.font-semibold')), day = getComputedStyle(c.querySelector('.text-sm'));
  return {tag: c.tagName, radius: s.borderTopLeftRadius, border: [s.borderTopWidth, s.borderTopColor], line: line,
          shadow: s.boxShadow, cover: [Math.round(img.width), Math.round(img.height)], card: Math.round(r.width),
          pad: getComputedStyle(c.querySelector('.p-4')).paddingLeft,
          name: [name.fontSize, name.lineHeight, name.fontWeight], day: [day.fontSize, day.lineHeight]}; }"""


@pytest.mark.parametrize("width", [390, 1440])
def test_the_album_card_is_the_public_card(browser, album, width):
    page = _open(browser, "/fotos", width)
    m = page.evaluate(CARD)
    page.close()
    print("MEASURE album card", width, m)
    assert m["tag"] == "A" and m["radius"] == "14px", m
    assert m["border"] == ["1px", m["line"]], (
        f"the card's line is {m['border']}, the kit's {m['line']}"
    )
    assert m["shadow"] == "none", "the card has a shadow at rest"
    # The cover in 16 : 9 to the card's edges (inside its 1 px line), 16 px of padding under it.
    assert m["cover"][0] == m["card"] - 2 and abs(m["cover"][1] - m["cover"][0] * 9 / 16) <= 1, m
    assert m["pad"] == "16px"
    assert m["name"] == ["16px", "24px", "600"] and m["day"] == ["14px", "20px"], m


WAY = """() => { const nav = document.querySelector('[data-way-back]'), a = nav.querySelector('a');
  const r = a.getBoundingClientRect(), s = getComputedStyle(a);
  const hit = (y) => { const e = document.elementFromPoint(r.left + 20, y); return !!e && (e === a || a.contains(e)); };
  return {text: a.textContent.trim(), icons: a.querySelectorAll('svg').length, href: a.getAttribute('href'),
          size: s.fontSize, colour: s.color, h: Math.round(r.height), nav: Math.round(nav.getBoundingClientRect().height),
          above: hit(r.top - 8), under: hit(r.bottom + 8), far: hit(r.top - 13),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [390, 1440])
def test_one_way_back_the_chevron_and_the_origins_name(browser, album, width):
    seen = {}
    for origin, path in (
        ("Activiteiten", None),
        ("Archief", f"/activiteiten/{album['activity']}"),
        ("Foto's", f"/activiteiten/{album['activity']}/fotos"),
    ):
        page = _open(browser, path or "/activiteiten", width)
        if path is None:
            # A full load of the seeded activity's page, not a boosted click.
            href = page.locator('[data-card-title] a:text-is("E2E-activiteit")').get_attribute(
                "href"
            )
            page.goto(href)
            pagina_klaar(page)
        seen[origin] = page.evaluate(WAY)
        page.close()
    print("MEASURE way back", width, seen)
    for origin, m in seen.items():
        assert m["text"] == origin and m["icons"] == 1, f"{origin}: {m}"
        # A line of 24 px on a phone, 20 px from 768 px.
        assert m["size"] == "14px" and m["h"] == (24 if width == 390 else 20), m
        assert m["page"][0] == m["page"][1]
        if width == 390:
            # 10 px above and under the line still hit the link: 44 px in all…
            assert m["above"] and m["under"] and not m["far"], f"{origin}: the hit area is {m}"
            # …and the line itself takes no more room for it.
            assert m["nav"] in (24, 40), m
        else:
            assert not m["above"] and not m["under"], (
                f"{origin}: a hit area beside the words on a desktop"
            )
    assert (
        len({m["colour"] for m in seen.values()}) == 1
        and len({m["size"] for m in seen.values()}) == 1
    )
    assert seen["Activiteiten"]["href"].endswith("/activiteiten")
    assert seen["Archief"]["href"].endswith("/activiteiten/archief")
    assert seen["Foto's"]["href"].endswith("/fotos")


def test_the_browser_title_of_the_photo_pages_names_the_site(browser, album):
    page = _open(browser, "/fotos", 1440)
    site = page.evaluate(
        """() => document.querySelector('meta[property="og:site_name"]').content"""
    )
    title = page.title()
    page.close()
    assert site, "the page names no site"
    assert title.endswith(f"Foto's · {site}"), title
    page = _open(browser, f"/activiteiten/{album['activity']}/fotos", 1440)
    assert page.title().endswith(f"Foto's — {NAME} · {site}"), page.title()
    page.close()

"""E2E: a calmer public footer, and every badge on one line (#1647).

Koen, 6 October 2026, two corrections in one slice:

- **the footer** (CR-11 Q82; end state §2.5): the social icons and the sponsor
  logos stand without a line or a frame; the newsletter's heading is the word
  "Nieuwsbrief" with the button directly under it; so the three columns read
  heading above content on ONE line at 1 440 px — the three headings at one
  height, and under them the button, the icons and the logos at one height;
- **a badge** (CR-11 Q81; `docs/design-system.md` §2.3): never on two lines.
  "Terug te betalen" broke in the Status column, which was 1 px too narrow for
  it; the column is as wide as its longest badge now.

And two more, the same day (CR-11 Q82, Q83):

- **the footer's call in the kit's small size**: 40 px high on a desktop, 14 px
  in medium weight, less padding; 44 px to touch on a phone; yellow stays;
- **the public activity page**: the way back stands on the left line of the
  content column, and the description is reading text of 16 px on a line of
  24 px, a blank line in it a paragraph.

All geometry, so all read from the rendered page. The footer's social link and
sponsor, and the booking with a refund still to pay out, are made for this file
and removed again.

Red against master `4747a136` (measured): the headings level but the second
row not (the sentence stood between the newsletter's heading and its button:
the button 40 px lower than the icons); a border of 1 px on every icon and
every logo; the badge "Terug te betalen" 36 px high where "Vereffend" is 20;
the call 44 px high in 16 px semibold with 16 px of padding; the way back at
x 96 where the content starts at x 208 (a window of 1 440; Koen saw 78 against
190 at his); the description 14 px on a line of 20 px at 1 440, one block.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

FOOTER = """() => {
  const box = e => { const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height)}; };
  const part = (s, inner) => { const sec = document.querySelector(s); if (!sec) return null;
    const first = sec.querySelector(inner), cs = first ? getComputedStyle(first) : null;
    return {head: box(sec.querySelector('h2')), text: sec.querySelector('h2').textContent.trim(), first: first ? box(first) : null,
            border: cs ? cs.borderTopWidth : null, background: cs ? cs.backgroundColor : null,
            between: [...sec.children].filter(c => c.tagName === 'P').length}; };
  return {news: part('[data-footer-newsletter]', '#nb-voet-link'), social: part('[data-footer-social]', 'a'),
          sponsors: part('[data-footer-sponsors]', '.site-sponsor'),
          // This file's own sponsor, by its name: another test's logo may stand before it.
          logo: (() => { const i = document.querySelector('[data-footer-sponsors] img[alt="Voorbeeldsponsor"]'); return i ? box(i) : null; })(),
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""
BADGES = """() => { const rows = [...document.querySelectorAll('tr[data-row]')];
  const badge = r => r.querySelector('[data-cell="status"] [data-badge]');
  return {badges: rows.map(r => ({text: badge(r).textContent.trim(), h: Math.round(badge(r).getBoundingClientRect().height),
                                   w: Math.round(badge(r).getBoundingClientRect().width), row: Math.round(r.getBoundingClientRect().height)})),
          status: Math.round(document.querySelector('th[data-cell="status"]').getBoundingClientRect().width),
          amount: Math.round(document.querySelector('th[data-cell="amount"]').getBoundingClientRect().width),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


def _png() -> bytes:
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (300, 100), (255, 255, 255)).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(scope="module")
def world():
    """A social link and a sponsor in the footer, and a paid booking with a
    refund still to pay out ("Terug te betalen") on the seeded activity."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.activities.api import Registration
    from app.domains.mdm.api import ContactDetail
    from app.domains.media.api import MediaAsset
    from app.domains.payment.api import PaymentRecord
    from app.kernel.tenant_config import _actieve_tenant

    db = SessionLocal()
    tenant = _actieve_tenant(None)
    made: dict = {}
    try:
        contact = ContactDetail(
            tenant_id=tenant,
            organization_id=tenant,
            contact_type_code="FACEBOOK",
            value="https://facebook.example/voorbeeld-1647",
        )
        sponsor = MediaAsset(
            kind="sponsor",
            title="Voorbeeldsponsor",
            content_type="image/png",
            data=_png(),
            is_active=True,
            show_in_footer=True,
            link_url="https://sponsor.example/",
        )
        db.add_all([contact, sponsor])
        db.flush()
        registration = db.query(Registration).order_by(Registration.id).first()
        charge = PaymentRecord(
            payable_type="registration",
            payable_id=registration.id,
            amount=Decimal("10.00"),
            amount_paid=Decimal("10.00"),
            method="transfer",
            status="paid",
        )
        db.add(charge)
        db.flush()
        refund = PaymentRecord(
            payable_type="registration",
            payable_id=registration.id,
            amount=Decimal("-4.00"),
            method="transfer",
            status="pending",
            type="refund",
            refund_of_id=charge.id,
        )
        db.add(refund)
        db.commit()
        made = {
            "contact": contact.id,
            "sponsor": sponsor.id,
            "refund": refund.id,
            "charge": charge.id,
            "activity": registration.activity_id,
        }
        # The activity's public page: an UPLOADED poster (only then the page
        # shows the picture and centres its block; an external address is a
        # link) and a description of two paragraphs, markup included as text.
        from app.domains.activities.api import Activity

        activity = db.get(Activity, registration.activity_id)
        made["was"] = activity.description
        poster = MediaAsset(
            kind="activity_poster",
            activity_id=activity.id,
            title="Affiche voor de meting",
            content_type="image/png",
            data=_png(),
        )
        db.add(poster)
        db.flush()
        made["poster"] = poster.id
        activity.description = (
            "Eerste alinea van de omschrijving.\nMet een tweede regel.\n\n"
            "Tweede alinea, met <b>geen</b> opmaak."
        )
        db.commit()
    finally:
        db.close()

    yield made

    db = SessionLocal()
    try:
        if "was" in made:
            from app.domains.activities.api import Activity

            activity = db.get(Activity, made["activity"])
            activity.description = made["was"]
            db.commit()
        for model, key in (
            (MediaAsset, "poster"),
            (PaymentRecord, "refund"),
            (PaymentRecord, "charge"),
            (ContactDetail, "contact"),
            (MediaAsset, "sponsor"),
        ):
            if key in made:
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


def _footer(browser, width: int, height: int) -> dict:
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto("/")
    pagina_klaar(page)
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-footer-sponsors] img')].every(i => i.complete)"
    )
    measured = page.evaluate(FOOTER)
    page.close()
    return measured


def test_at_1440_the_footer_reads_heading_above_content_on_one_line(browser, world):
    m = _footer(browser, 1440, 900)
    print("MEASURE footer 1440", m)
    parts = [m["news"], m["social"], m["sponsors"]]
    assert all(parts), f"a column of the footer is missing: {m}"
    assert m["news"]["text"] == "Nieuwsbrief"
    # The three headings at one height…
    assert len({p["head"]["y"] for p in parts}) == 1, [p["head"] for p in parts]
    # …and under them the button, the icons and the logos at one height.
    assert len({p["first"]["y"] for p in parts}) == 1, [p["first"] for p in parts]
    assert m["news"]["between"] == 0, "a sentence stands between the heading and the button"
    # Three columns beside each other.
    xs = [p["head"]["x"] for p in parts]
    assert xs == sorted(xs) and len(set(xs)) == 3, xs
    assert m["page"][0] == m["page"][1]


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_the_icons_and_the_logos_stand_without_a_frame(browser, world, width, height):
    m = _footer(browser, width, height)
    for name in ("social", "sponsors"):
        assert m[name]["border"] == "0px", f"{name} @{width}: a line of {m[name]['border']}"
        assert m[name]["background"] == "rgba(0, 0, 0, 0)", f"{name} @{width}: {m[name]}"
    # The icon's target stays 44 px; the logo keeps its proportions inside 144 × 64.
    assert (m["social"]["first"]["w"], m["social"]["first"]["h"]) == (44, 44), m["social"]
    # A 300 × 100 logo takes the full 144 px and keeps its proportions.
    assert (m["logo"]["w"], m["logo"]["h"]) == (144, 48), f"the logo is {m['logo']}"
    assert m["page"][0] == m["page"][1]


def test_on_a_phone_the_columns_stand_under_each_other(browser, world):
    m = _footer(browser, 390, 844)
    print("MEASURE footer 390", m)
    parts = [m["news"], m["social"], m["sponsors"]]
    assert len({p["head"]["x"] for p in parts}) == 1, "the columns are not stacked"
    ys = [p["head"]["y"] for p in parts]
    assert ys == sorted(ys) and len(set(ys)) == 3, ys
    assert m["news"]["between"] == 0 and m["news"]["text"] == "Nieuwsbrief"


def _admin(browser, width: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    return page


@pytest.mark.parametrize("width", [1440, 1100])
@pytest.mark.parametrize("tab", [False, True])
def test_every_badge_in_the_status_column_stands_on_one_line(browser, world, width, tab):
    """The payments list and the activity's Betalingen tab, at 1 440 and at
    1 100 px: "Terug te betalen" as high as every other badge, the rows equally
    high, and the room taken from the name's column — not from the amounts."""
    page = _admin(browser, width)
    page.goto(f"/admin/activiteiten/{world['activity']}/betalingen" if tab else "/admin/betalingen")
    pagina_klaar(page)
    m = page.evaluate(BADGES)
    print("MEASURE badges", "tab" if tab else "list", width, m)
    texts = [b["text"] for b in m["badges"]]
    assert "Terug te betalen" in texts, f"no booking with a refund to pay out is shown: {texts}"
    heights = {b["h"] for b in m["badges"]}
    assert heights == {20}, f"a badge is not one line high: {m['badges']}"
    # The badge does not make its row higher: the lowest row of the list is as
    # high as the row of "Terug te betalen" (rows differ for other reasons — a
    # long name, a line under it).
    refund = next(b for b in m["badges"] if b["text"] == "Terug te betalen")
    assert refund["row"] <= min(b["row"] for b in m["badges"]) + 16, (
        f'the row of "Terug te betalen" is {refund["row"]} px: {m["badges"]}'
    )
    longest = max(b["w"] for b in m["badges"])
    assert m["status"] >= longest + 24, (
        f"the Status column is {m['status']} px for a badge of {longest}"
    )
    assert m["amount"] == 104, f"the amount's column gave room: {m['amount']} px"
    assert m["page"][0] == m["page"][1], "the table overflows"
    page.close()


def test_the_kit_page_shows_every_badge_on_one_line(browser):
    page = _admin(browser, 1440)
    page.goto("/admin/design-system")
    pagina_klaar(page)
    heights = page.evaluate(
        "() => [...document.querySelectorAll('[data-badge]')].filter(e => e.checkVisibility())"
        ".map(e => [e.textContent.trim(), Math.round(e.getBoundingClientRect().height),"
        " getComputedStyle(e).whiteSpace])"
    )
    assert len(heights) >= 15, f"only {len(heights)} badges on the kit page"
    wrong = [h for h in heights if h[1] != 20 or h[2] != "nowrap"]
    assert not wrong, f"a badge of the kit is not one line: {wrong}"
    page.close()


CALL = """() => { const a = document.querySelector('#nb-voet-link'), s = getComputedStyle(a), r = a.getBoundingClientRect();
  return {h: Math.round(r.height), w: Math.round(r.width), size: s.fontSize, weight: s.fontWeight,
          pad: [s.paddingLeft, s.paddingRight], colour: s.backgroundColor, text: s.color}; }"""


def test_the_footers_call_is_the_kits_small_button(browser, world):
    """#1647 (Q82). Red against master: 44 px high in 16 px semibold with 16 px
    of padding, at every width."""
    seen = {}
    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
        page.goto("/")
        pagina_klaar(page)
        seen[width] = page.evaluate(CALL)
        page.close()
    print("MEASURE call", seen)
    wide, phone = seen[1440], seen[390]
    assert (wide["h"], wide["size"], wide["weight"]) == (40, "14px", "500"), wide
    assert wide["pad"] == ["12px", "12px"], f"the small size has 12 px of padding: {wide['pad']}"
    # A finger needs 44 px; the phone keeps the readable 16 px.
    assert phone["h"] >= 44 and phone["size"] == "16px", phone
    for m in (wide, phone):
        assert m["colour"] == "rgb(238, 193, 94)" and m["text"] == "rgb(37, 44, 53)", m


PAGE = """() => { const x = e => Math.round(e.getBoundingClientRect().left); const q = s => document.querySelector(s);
  const d = q('[data-activity-description]'), s = getComputedStyle(d), ps = [...d.querySelectorAll('p')];
  return {back: x(q('[data-way-back] a')), columns: x(q('[data-activity-columns]')), title: x(q('#main h1')),
          first: x(q('[data-activity-columns] > div > div')), shell: x(q('#main')),
          size: s.fontSize, line: s.lineHeight, paragraphs: ps.length, breaks: d.querySelectorAll('br').length, lines: d.querySelectorAll('[data-line]').length,
          gap: ps.length > 1 ? Math.round(ps[1].getBoundingClientRect().top - ps[0].getBoundingClientRect().bottom) : null,
          bold: d.querySelectorAll('b').length, text: d.textContent.includes('<b>geen</b>'),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_the_activity_pages_way_back_and_description(browser, world, width):
    """#1647 (Q83). At 1 440 the way back starts where the content starts, inside
    the centred block; at 390 everything starts at the shell's gutter, as
    before. The description is reading text with paragraphs."""
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.goto(f"/activiteiten/{world['activity']}")
    pagina_klaar(page)
    m = page.evaluate(PAGE)
    print("MEASURE activity page", width, m)
    assert m["back"] == m["columns"] == m["first"], (
        f"the way back is not on the content's line: {m}"
    )
    if width == 1440:
        assert m["columns"] > m["shell"], "the block is not centred — the page has no poster?"
    else:
        assert m["back"] == m["shell"] == 16
    assert (m["size"], m["line"]) == ("16px", "24px"), f"the description @{width}: {m}"
    # #1688: a single Enter is a line of its own (two of them in the first
    # paragraph), no longer a `<br>`; the paragraphs stay 16 px apart.
    assert (m["paragraphs"], m["breaks"], m["lines"], m["gap"]) == (2, 0, 2, 16), m
    assert m["bold"] == 0 and m["text"], "markup of the description reached the page as markup"
    assert m["page"][0] == m["page"][1]
    page.close()


# ── #1654: the footer refined (CR-11 Q85; end state §2.5) ────────────────────
# Koen, 6 October 2026, on the footer above as built: no line above the row of
# columns, three columns of one width, the first social icon's GLYPH on the
# left line of its heading (the 44 px target reaches left of it), and 32 px of
# air above and under the row on a desktop, 24 px on a phone.
#
# Red against master `637e9b6a` (measured, all eight cases, windows of 1 440 /
# 768 / 390): a line of 1 px above the row; columns of 483 / 297 / 372 px at
# 1 440 and two columns at 768; the glyph 10 px right of its heading at every
# width; 65 / 49 px from the footer's top to the headings (64 / 48 and the line).
#
# And the same air from the last content to the footer's ground (the master
# CLI, the same day): the footer's own margin of 64 / 48 px is gone, the
# content's padding under it is 32 / 24 px. Red with that margin put back
# (measured): 96 / 96 / 80 px at 1 440 / 768 / 390.
REFINED = """() => {
  const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const social = q('[data-footer-social]'), link = social.querySelector('a'), glyph = link.querySelector('svg');
  const row = q('[data-footer-row]'), legal = q('[data-footer-line]'), footer = q('.site-footer');
  const heads = [...row.querySelectorAll('h2')];
  return {heading: r(social.querySelector('h2')).left, glyph: r(glyph).left, glyph_w: r(glyph).width,
          target: [r(link).width, r(link).height], target_x: r(link).left,
          columns: [...row.children].map(s => r(s).width), lefts: [...row.children].map(s => r(s).left),
          above: Math.min(...heads.map(h => r(h).top)) - r(footer).top,
          under: r(legal).top - r(row).bottom,
          content: r(footer).top - Math.max(...[...q('#main').children].filter(c => c.checkVisibility()).map(c => r(c).bottom)),
          long: document.documentElement.scrollHeight > innerHeight + 200,
          lines: [getComputedStyle(footer).borderTopWidth, getComputedStyle(q('.site-footer-core')).borderTopWidth,
                  getComputedStyle(row).borderTopWidth],
          legal_line: getComputedStyle(legal).borderTopWidth,
          // The FIRST logo of the row, whoever's it is: this file's own sponsor is not
          // the first once another file has added one (#1745), and the rule is the first's.
          logo: (() => { const i = q('[data-footer-sponsors] img'); return i ? [r(i).left, r(i.closest('section').querySelector('h2')).left] : null; })(),
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


def _refined(browser, width: int, height: int) -> dict:
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto("/")
    pagina_klaar(page)
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-footer-sponsors] img')].every(i => i.complete)"
    )
    measured = page.evaluate(REFINED)
    page.close()
    print("MEASURE refined", width, measured)
    return measured


@pytest.mark.parametrize(
    ("width", "height", "margin"), [(1440, 900, None), (768, 900, None), (390, 844, 16)]
)
def test_the_first_social_glyph_stands_on_the_line_of_its_heading(
    browser, world, width, height, margin
):
    m = _refined(browser, width, height)
    assert m["glyph_w"] == 24, m
    assert abs(m["glyph"] - m["heading"]) < 0.5, (
        f"@{width}: the glyph at x {m['glyph']}, the heading 'Volg ons' at x {m['heading']}"
    )
    # The target stays 44 × 44 and reaches 10 px left of that line.
    assert m["target"] == [44, 44], m["target"]
    assert abs(m["heading"] - m["target_x"] - 10) < 0.5, m
    # The first sponsor logo had no inner margin: it stands on its heading's line already.
    assert abs(m["logo"][0] - m["logo"][1]) < 0.5, m["logo"]
    if margin is not None:
        assert round(m["glyph"]) == margin, f"the glyph is not on the phone's margin: {m['glyph']}"
    # The part of the target left of the line makes the page no wider.
    assert m["page"][0] == m["page"][1]


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (768, 900)])
def test_the_three_columns_are_equally_wide(browser, world, width, height):
    m = _refined(browser, width, height)
    assert len(m["columns"]) == 3, m
    assert max(m["columns"]) - min(m["columns"]) < 0.5, f"@{width}: columns of {m['columns']}"
    assert len({round(x) for x in m["lefts"]}) == 3, (
        f"@{width}: not three beside each other: {m['lefts']}"
    )
    # A logo of the full 144 px fits its column.
    assert min(m["columns"]) >= 144, m["columns"]


@pytest.mark.parametrize(
    ("width", "height", "air"), [(1440, 400, 32), (768, 400, 32), (390, 400, 24)]
)
def test_the_air_above_and_under_the_row_and_no_line_above_it(browser, world, width, height, air):
    m = _refined(browser, width, height)
    assert abs(m["above"] - air) < 0.5, (
        f"@{width}: {m['above']} px from the footer's top to the headings"
    )
    assert abs(m["under"] - air) < 0.5, f"@{width}: {m['under']} px from the row to the legal line"
    assert m["lines"] == ["0px", "0px", "0px"], f"@{width}: a line above the row: {m['lines']}"
    # From the last content to the footer's ground: the same air as inside it
    # (a page longer than the window: on a short one the content is stretched).
    assert m["long"], "the page is not longer than the window — the measure would say nothing"
    assert abs(m["content"] - air) < 0.5, (
        f"@{width}: {m['content']} px from the last content to the footer's ground"
    )
    # The line above the legal line stays.
    assert m["legal_line"] == "1px", m


# ── #1664 (CR-11 pilot C, C2 — Z1; end state §2.5, §2.7): the sponsor block ends
# on the container's right edge — the line the legal line ends on — with its
# heading on the left above the first logo INSIDE that block. The three columns
# stay equally wide (#1654); only the third's content stands at its right. On a
# phone everything stays stacked on the left.
#
# Red against master `a8c0e5a2` (measured at 1 440): the logo's right edge at
# x 1104 where the container ends at x 1344 — 240 px short.
SPONSORS = """() => {
  const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const row = q('[data-footer-row]'), block = q('[data-footer-sponsors] > div');
  const logos = [...block.querySelectorAll('.site-sponsor')];
  return {container: [r(row).left, r(row).right], legal: r(q('[data-footer-line]')).right,
          block: [r(block).left, r(block).right], heading: r(block.querySelector('h2')).left,
          first: r(logos[0]).left, last: Math.max(...logos.map(l => r(l).right)),
          columns: [...row.children].map(s => r(s).width), column3: r(row.children[2]).left,
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


def _sponsors(browser, width: int, height: int) -> dict:
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto("/")
    pagina_klaar(page)
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-footer-sponsors] img')].every(i => i.complete)"
    )
    measured = page.evaluate(SPONSORS)
    page.close()
    print("MEASURE sponsors", width, measured)
    return measured


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (768, 900)])
def test_the_sponsor_block_ends_on_the_containers_right_edge(browser, world, width, height):
    m = _sponsors(browser, width, height)
    assert abs(m["last"] - m["container"][1]) < 0.5, (
        f"@{width}: the last logo ends at x {m['last']}, the container at x {m['container'][1]}"
    )
    assert abs(m["container"][1] - m["legal"]) < 0.5, m
    # The heading stands on the left above the first logo, inside the block.
    assert abs(m["heading"] - m["first"]) < 0.5 and abs(m["heading"] - m["block"][0]) < 0.5, m
    # The block is in the third column and no wider than it; the columns stay even.
    assert m["block"][0] >= m["column3"] - 0.5, m
    assert max(m["columns"]) - min(m["columns"]) < 0.5, m["columns"]
    assert m["page"][0] == m["page"][1]


def test_on_a_phone_the_sponsor_block_stays_on_the_left(browser, world):
    m = _sponsors(browser, 390, 844)
    assert round(m["heading"]) == 16 and round(m["first"]) == 16, m
    assert m["page"][0] == m["page"][1]

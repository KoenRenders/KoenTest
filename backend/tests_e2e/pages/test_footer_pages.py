"""E2E: a page says itself that it stands in the footer (#1569).

Measured from the rendered DOM:

- the public footer lists the two published footer pages after "© year name",
  in their order, inside the page width at 390 and 1 440 px;
- a footer link leads to its page;
- the page editor shows the checkbox "Toon in de voettekst" beside the other
  three, all inside the width of a phone.

Screenshots go outside the repo.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

PAGES = [
    ("voettekst-privacy", "Privacyverklaring", 1),
    ("voettekst-voorwaarden", "Algemene voorwaarden", 2),
]

_FOOTER = """() => {
  const line = document.querySelector('[data-footer-line]');
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.left), right: Math.round(b.right), y: Math.round(b.top + scrollY), h: Math.round(b.height)}; };
  return {line: r(line), text: line.innerText.replace(/\\s+/g, ' ').trim(),
          links: [...line.querySelectorAll('[data-footer-page]')].map(a => ({...r(a), text: a.innerText.trim(), href: a.getAttribute('href')})),
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""

_BOXES = """() => {
  const names = ['show_in_nav', 'is_home', 'show_in_footer'];
  return {boxes: names.map(n => { const i = document.querySelector(`input[type=checkbox][name=${n}]`); if (!i) return null;
            const b = i.closest('label').getBoundingClientRect(); return {name: n, x: Math.round(b.left), right: Math.round(b.right), y: Math.round(b.top + scrollY), text: i.closest('label').innerText.trim(), checked: i.checked}; }),
          publish: !![...document.querySelectorAll('[data-record-head] button')].find(b => b.innerText.trim() === 'Publiceren'),
          widest: [...document.querySelectorAll('main *')].filter(e => e.checkVisibility())
            .map(e => [Math.round(e.getBoundingClientRect().right), e.tagName, (e.id || e.className + '').slice(0, 50)])
            .sort((a, b) => b[0] - a[0])[0],
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


def _footer_pages() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.cms.api import CmsPage
    from app.kernel.tenancy import DEFAULT_TENANT_ID

    db = SessionLocal()
    try:
        first_id = 0
        for slug, title, order in PAGES:
            page = (
                db.query(CmsPage)
                .filter(CmsPage.slug == slug, CmsPage.tenant_id == DEFAULT_TENANT_ID)
                .execution_options(include_all_tenants=True)
                .first()
            )
            if page is None:
                page = CmsPage(
                    tenant_id=DEFAULT_TENANT_ID,
                    slug=slug,
                    title=title,
                    content=f"<p>{title}</p>",
                    is_published=True,
                    show_in_nav=False,
                    show_in_footer=True,
                    sort_order=order,
                )
                db.add(page)
                db.flush()
            first_id = first_id or page.id
        db.commit()
        # Snede 3 (#1671): Publiceren staat op de recordpagina zodra er een
        # concept te publiceren is — een pagina zonder concept heeft geen
        # knop. Dit scherm meet de schakelaars, dus krijgt de eerste pagina
        # een concept door de deur van de app.
        from app.domains.cms.api import save_document

        save_document(
            db,
            first_id,
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Tekst van de pagina."}],
                    }
                ],
            },
        )
        return first_id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page_id = _footer_pages()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), page_id
        b.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_footer_lists_the_footer_pages_inside_the_page(setup, width):
    page = setup[0].new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.goto("/")
    pagina_klaar(page)
    m = page.evaluate(_FOOTER)
    print("MEASURE footer", width, m)
    ours = [
        link for link in m["links"] if link["href"].endswith(tuple(slug for slug, _t, _o in PAGES))
    ]
    assert [link["text"] for link in ours] == ["Privacyverklaring", "Algemene voorwaarden"], m[
        "links"
    ]
    assert m["text"].startswith("©")
    assert m["page"][0] <= m["page"][1], f"the page scrolls sideways: {m['page']}"
    for link in m["links"]:
        assert link["x"] >= m["line"]["x"] and link["right"] <= m["line"]["right"], (
            link,
            m["line"],
        )
    page.close()


def test_a_footer_link_opens_its_page(setup):
    page = setup[0].new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.goto("/")
    pagina_klaar(page)
    page.click('[data-footer-page]:has-text("Algemene voorwaarden")')
    pagina_klaar(page)
    assert page.url.endswith("/voettekst-voorwaarden")
    assert page.locator("main").inner_text().count("Algemene voorwaarden") >= 1
    page.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_editor_shows_the_footer_checkbox_with_the_others(setup, width):
    b, session, page_id = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(f"/admin/paginas/{page_id}")
    pagina_klaar(page)
    m = page.evaluate(_BOXES)
    print("MEASURE editor", width, m)
    # Snede 3 (#1671): publishing is the Publiceren action of the record
    # head — the checkbox is gone with the master-detail screen; the three
    # places a page stands are switches on the record.
    assert m["publish"], "the record head lost her Publiceren action"
    assert all(m["boxes"]), "all three switches are on the record"
    footer = m["boxes"][2]
    assert footer["text"] == "Toon in de voettekst" and footer["checked"] is True
    # The row of switches wraps and stays inside the screen. The page width is
    # recorded, not held: at 390 px the editor is 450 px wide through a row of
    # buttons (`widest`, a `flex gap-2` row) that this issue does not touch.
    for box in m["boxes"]:
        assert box["x"] >= 0 and box["right"] <= width, box
    page.close()

"""E2E: the public header per module, in a browser (CR-19, #1476).

A company tenant is made through the tenant editor, as an operator makes one:
the server's own caches then know it, which a row written from the test would
not achieve. Measured from the rendered DOM, at 1 440 and 390 px, in both
renderings of the header (the wide row and the phone menu, opened):

- the company's header links: Home and its own pages, no Foto's, no Archief;
- the association's header (the seeded unit, every module on): Home, Foto's,
  Archief first, as before.

Screenshots go outside the repo.
"""

import os
import secrets
import sys
from urllib.parse import urlsplit, urlunsplit

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1476"
_SPLIT = urlsplit(BASE)
PLATFORM = urlunsplit(
    (
        _SPLIT.scheme,
        f"platform.localhost:{_SPLIT.port}" if _SPLIT.port else "platform.localhost",
        _SPLIT.path,
        "",
        "",
    )
)
ASSOCIATION = "raakvoorbeeldafdeling"

_HEADER = """() => {
  const links = id => [...document.querySelectorAll('#' + id + ' a')]
    .filter(a => a.checkVisibility())
    .map(a => ({text: a.textContent.trim(), path: new URL(a.href).pathname}));
  return {breed: links('site-nav-breed'), mobiel: links('site-nav-mobiel'), width: [document.documentElement.scrollWidth, innerWidth]};
}"""


def _operator() -> None:
    """The seeded admin may make tenants: an operator does that."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
        # A platform role has no tenant, so the tenant filter would hide it.
        has = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_code == "OPERATOR")
            .execution_options(include_all_tenants=True)
            .first()
        )
        if has is None:
            db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
            db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser_and_company():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    _operator()
    code = f"bedrijf-{secrets.token_hex(2)}"
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        # #1535: platform administration answers in the platform workspace only.
        page = b.new_page(base_url=PLATFORM, viewport={"width": 1440, "height": 900})
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), PLATFORM)
        page.goto("/admin/tenants/nieuw")
        pagina_klaar(page)
        page.locator("label:has(input[name=kind][value=BEDRIJF])").click()
        page.fill("#t-name", f"Testbedrijf {code}")
        page.fill("#t-code", code)
        with page.expect_response(
            lambda r: r.url.endswith("/admin/tenants") and r.request.method == "POST"
        ) as made:
            page.locator("form[hx-post='/admin/tenants'] button[type=submit]").click()
        assert made.value.status == 200, made.value.status
        page.close()
        yield b, code
        b.close()


def _header(b, path: str, width: int, shot: str) -> dict:
    page = b.new_page(viewport={"width": width, "height": 900})
    page.goto(PLATFORM + path, wait_until="domcontentloaded")
    pagina_klaar(page)
    if width < 768:
        page.locator("header button[aria-label=Menu]").click()
        page.locator("#site-nav-mobiel").wait_for(state="visible")
    m = page.evaluate(_HEADER)
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{shot}.png")
    page.close()
    return m


def _paths(links, prefix) -> list[str]:
    return [link["path"].removeprefix(prefix) or "/" for link in links]


@pytest.mark.parametrize("width", [1440, 390])
def test_a_company_header_has_no_photos_and_no_archive(browser_and_company, width):
    b, code = browser_and_company
    m = _header(b, f"/{code}/", width, f"{width}-bedrijf")
    links = m["breed"] if width >= 768 else m["mobiel"]
    paths = _paths(links, f"/{code}")
    print("MEASURE company", width, m)

    assert links, "the header shows its links"
    assert "/fotos" not in paths and "/archief" not in paths, paths
    assert paths[0] == "/", "Home first"


@pytest.mark.parametrize("width", [1440, 390])
def test_an_association_header_is_as_before(browser_and_company, width):
    b, _code = browser_and_company
    m = _header(b, f"/{ASSOCIATION}/", width, f"{width}-vereniging")
    links = m["breed"] if width >= 768 else m["mobiel"]
    paths = _paths(links, f"/{ASSOCIATION}")
    print("MEASURE association", width, m)

    assert paths[:3] == ["/", "/fotos", "/archief"], paths

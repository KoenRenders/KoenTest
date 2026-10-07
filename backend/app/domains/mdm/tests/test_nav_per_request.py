"""The admin menu and the public header per request, from the registry (CR-19, #1476).

C6 tests 4 and 6, and what keeps the menu's one source:

- **the menu per tenant** (test 4): a tenant with the company's modules sees
  only their items plus the shell's; an association sees the full menu; the
  desktop and the phone share one rendering (since #1482);
- **the public header per module** (test 6): a company's header has no Foto's
  and no Archief — both mean the albums and the archive of activities — and
  an association's has them, as before; Mijn gezin goes with membership;
- **two owners**: an item is shown only when the module that lists it and the
  module that serves its path are both on;
- **one source for a label**: every registry admin item stands in the menu
  layout exactly once, and nowhere with a label of its own.

The render gate per kind (test 5) is in `tests/test_render_gate.py`. Here and
not in `tests/integration`: its imports are mdm's (the placement gate).
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import invalidate_tenant_codes
from app.kernel.modules import DEFAULTS, MODULES, ModuleCode, current_modules, nav_item_shown
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from app.ui import _ADMIN_NAV, _ADMIN_NAV_LAYOUT, PLATFORM_ONLY_ITEMS, _public_nav, admin_nav
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EVERY = frozenset(code.value for code in ModuleCode)
COMPANY = frozenset(code.value for code in DEFAULTS["BEDRIJF"])


@pytest.fixture
def modules_of(monkeypatch):
    """Set the cached module set of the tenant the test client resolves to."""
    invalidate_tenant_codes()

    def apply(enabled: frozenset[str]):
        monkeypatch.setattr(tenant_lookup, "_modules_cache", {TENANT_MILLEGEM_ID: enabled})

    yield apply
    invalidate_tenant_codes()


def _hrefs(html: str, nav_id: str) -> list[str]:
    if nav_id == "site-nav-mobiel":
        # #1588: the drawer is a dialog with more than links in it. Its page
        # links are the <nav> inside, above the divider of the account.
        start = html.find('<div id="site-nav-mobiel"')
        assert start >= 0, "no #site-nav-mobiel on the page"
        pages = html[start : html.index("data-drawer-account", start)]
        block = re.search(r"<nav\b.*?</nav>", pages, re.S)
        assert block, "the drawer has no navigation"
        return re.findall(r'href="([^"#]+)"', block.group(0))
    # Closed on its own tag: the admin menus and the public header's row are
    # <nav>s (the admin ones with <div>s inside).
    block = re.search(rf'<(nav|div) id="{nav_id}".*?</\1>', html, re.S)
    assert block, f"no #{nav_id} on the page"
    return re.findall(r'href="([^"#]+)"', block.group(0))


def _admin_page(client, modules_of, enabled) -> str:
    modules_of(enabled)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    response = client.get("/admin/gebruikers")
    assert response.status_code == 200
    return response.text


def test_a_company_sees_only_its_modules_and_the_shell(client, modules_of):
    """C6 test 4."""
    html = _admin_page(client, modules_of, COMPANY)
    sidebar = _hrefs(html, "admin-nav-zijbalk")

    assert "/admin/media" in sidebar and "/admin/werkbank" in sidebar, sidebar
    assert "/admin/gebruikers" in sidebar and "/admin" in sidebar, "the shell stays"
    # A prefix matches whole segments: membership's `/admin/leden` does not
    # serve the shell's `/admin/ledenwijzigingen` (caught on the screenshot).
    assert "/admin/ledenwijzigingen" in sidebar, "Wijzigingen is the shell's"
    for gone in ("/admin/activiteiten", "/admin/leden", "/admin/betalingen", "/admin/rapporten"):
        assert gone not in sidebar, f"{gone} belongs to a module that is off"
    # Desktop and phone: since CR-11 block 1 (#1482) there is one rendering —
    # the phone's drawer is the sidebar itself — so the same items by
    # construction; the frame gate holds that there is no second one.
    assert 'id="admin-nav-mobiel"' not in html


def test_an_association_sees_the_full_menu_as_before(client, modules_of):
    """C6 test 4: every item of the layout, in its order — the one rendering a
    desktop and a phone share since #1482."""
    html = _admin_page(client, modules_of, EVERY)
    # #1535: a tenant workspace — platform administration is the platform's menu.
    full = [href for href, _label in _ADMIN_NAV if href not in PLATFORM_ONLY_ITEMS]

    assert [h for h in _hrefs(html, "admin-nav-zijbalk") if h in full] == full


def test_a_group_left_empty_goes(client):
    groups = [g["label"] for g in admin_nav("/admin", modules=COMPANY)]

    assert "Financieel" not in groups, "Betalingen is off: no empty Financieel heading"
    assert "Werking" in groups, "Formulieren keeps Werking"


def test_finance_only_still_sees_payments_and_only_when_payment_is_on():
    """#530 and #1476 together: the role cut works on the tenant's menu."""
    items = [
        i["href"] for g in admin_nav("/x", roles=["FINANCE"], modules=EVERY) for i in g["items"]
    ]
    assert items == ["/admin/betalingen"]
    assert not [i for g in admin_nav("/x", roles=["FINANCE"], modules=COMPANY) for i in g["items"]]


def test_an_item_needs_the_module_that_lists_it_and_the_one_that_serves_it(monkeypatch):
    """Foto's: listed by activities, served by media.

    Until #1562 the admin menu had such an item too — "AI · Raakje", listed by
    the chatbot and served by reporting. It left the menu: the Assistent is the
    panel behind the top bar's trigger. The two-module rule went with it to the
    shell (`assistant_in_shell`): the trigger and the panel are there only when
    the chatbot and reporting are both on."""
    from app.config import settings
    from app.ui import _assistant_in_shell

    without = lambda *off: EVERY - {code.value for code in off}  # noqa: E731

    assert nav_item_shown("public_items", "/fotos", EVERY)
    assert not nav_item_shown("public_items", "/fotos", without(ModuleCode.ACTIVITIES))
    assert not nav_item_shown("public_items", "/fotos", without(ModuleCode.MEDIA))
    assert not [
        module.code for module in MODULES for href, _l in module.admin_items if "raakje" in href
    ], "the assistant is back in a module's menu items"
    # What the chatbot still lists is its own screen, and that needs the chatbot.
    assert nav_item_shown("admin_items", "/admin/ai-context", EVERY)
    assert not nav_item_shown("admin_items", "/admin/ai-context", without(ModuleCode.CHATBOT))
    assert nav_item_shown("admin_items", "/admin/gebruikers", frozenset()), (
        "the shell is always there"
    )

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    for enabled, expected in (
        (EVERY, True),
        (without(ModuleCode.REPORTING), False),
        (without(ModuleCode.CHATBOT), False),
    ):
        token = current_modules.set(enabled)
        try:
            assert _assistant_in_shell() is expected, sorted(EVERY - enabled)
        finally:
            current_modules.reset(token)


def test_a_company_header_has_no_photos_and_no_archive(client, modules_of):
    """C6 test 6, and the measurement Koen asked for: what a company sees."""
    modules_of(COMPANY)
    html = client.get("/").text

    for nav_id in ("site-nav-breed", "site-nav-mobiel"):
        links = _hrefs(html, nav_id)
        assert "/fotos" not in links and "/archief" not in links, (nav_id, links)
        assert "/" in links, "Home stays"


def test_an_association_header_is_as_before(client, modules_of):
    """C6 test 6: Home, Foto's, Archief — in that order, in both renderings."""
    modules_of(EVERY)
    html = client.get("/").text

    for nav_id in ("site-nav-breed", "site-nav-mobiel"):
        links = _hrefs(html, nav_id)
        assert links[:3] == ["/", "/fotos", "/archief"], (nav_id, links)


def test_mijn_gezin_goes_with_membership():
    token = current_modules.set(EVERY)
    try:
        assert [n["href"] for n in _public_nav("member_items")] == ["/leden/gezin"]
        # CR-22 S3 (#1706): an account-menu item brings its own icon.
        assert [n["icon"] for n in _public_nav("member_items")] == ["users"]
    finally:
        current_modules.reset(token)
    token = current_modules.set(EVERY - {ModuleCode.MEMBERSHIP.value})
    try:
        assert _public_nav("member_items") == []
    finally:
        current_modules.reset(token)


def test_every_registry_admin_item_stands_in_the_layout_once_by_href_only():
    """One source for a label: the layout names a module's item by its href,
    and the label comes from the registry. A module item the layout forgot
    would be missing from every menu; one with its own label would be the
    second place for that label."""
    layout = [item for _group, items in _ADMIN_NAV_LAYOUT for item in items]
    for module in MODULES:
        for href, _label in module.admin_items:
            assert layout.count(href) == 1, (
                f"{href} ({module.code}) stands in the layout {layout.count(href)}x"
            )
            assert not [i for i in layout if isinstance(i, tuple) and i[0] == href], (
                f"{href} carries its own label in the layout"
            )

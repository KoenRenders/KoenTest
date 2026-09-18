"""The public header colour per tenant (#992).

Koen, 17 September 2026: the logo and the cobalt header clash; the public header
of a site gets its own colour, every other tenant keeps today's.

The value goes into a `style` attribute and the CSP allows inline style, so the
refusal tests read the STORED value, not only the message. And the header text
is white, so a light colour is refused with its contrast ratio.

Broken to see them red (measured):
- the `SITE_HEADER_COLOR_KEY` branch removed from `update_tenant_settings` →
  all eight injection cases and the contrast test fail on the stored value, and
  the colour test too (`#005D29` is then stored as typed);
- `tenant_site_header_color` returning the raw setting → the read-side test
  fails with the injected text on the home page;
- the `style` removed from the <nav> in `site_base.html` → the colour test fails.
"""
import re

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value)
from app.kernel.tenancy import DEFAULT_TENANT_ID
from app.kernel.tenant_config import (SITE_HEADER_COLOR_KEY, contrast_with_white,
                                      get_setting, set_setting)

pytestmark = pytest.mark.ui_serverrendered

KAAL_NAV = '<nav class="bg-blue-700 text-white shadow-md" x-data="{ open: false }">'


def _operator(client, db_session, email="op-kopkleur@example.com"):
    u = User(email=email, is_active=True)
    db_session.add(u)
    db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_code="OPERATOR"))
    db_session.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _opslaan(client, csrf, kleur):
    return client.post(f"/admin/tenants/{DEFAULT_TENANT_ID}",
                       data={SITE_HEADER_COLOR_KEY: kleur},
                       headers={"X-CSRF-Token": csrf})


def _opgeslagen(db_session):
    db_session.expire_all()
    return get_setting(db_session, SITE_HEADER_COLOR_KEY, tenant_id=DEFAULT_TENANT_ID)


def _nav(html: str) -> str:
    """The public header, from <nav> to </nav> — the mobile menu included."""
    m = re.search(r"<nav\b.*?</nav>", html, re.S)
    assert m, "no <nav> in the page"
    return m.group(0)


def test_without_a_setting_the_header_is_exactly_as_today(client):
    html = client.get("/").text
    assert KAAL_NAV in html


def test_a_colour_covers_the_header_and_its_mobile_menu(client, db_session):
    csrf = _operator(client, db_session)
    resp = _opslaan(client, csrf, "#005D29")
    assert resp.status_code == 200, resp.text[:300]
    assert _opgeslagen(db_session) == "#005d29"

    client.cookies.clear()
    nav = _nav(client.get("/").text)
    assert nav.startswith('<nav class="bg-blue-700 text-white shadow-md" '
                          'style="background-color: #005d29"')
    assert 'id="site-nav-mobiel"' in nav, "the mobile menu sits inside the coloured nav"
    assert 'id="site-nav-breed"' in nav


def test_an_empty_value_goes_back_to_the_shell_colour(client, db_session):
    csrf = _operator(client, db_session)
    _opslaan(client, csrf, "#005d29")
    _opslaan(client, csrf, "")
    assert _opgeslagen(db_session) is None
    client.cookies.clear()
    assert KAAL_NAV in client.get("/").text


@pytest.mark.parametrize("kleur", [
    "red; background:url(x)",
    "#005d29; background:url(https://evil.example/x)",
    '#005d29" onmouseover="alert(1)',
    "005d29",
    "#05d",
    "#005d2g",
    "rgb(0, 93, 41)",
    "var(--c-brand-green)",
])
def test_anything_but_rrggbb_is_refused_and_never_stored(client, db_session, kleur):
    csrf = _operator(client, db_session)
    _opslaan(client, csrf, "#005d29")

    resp = _opslaan(client, csrf, kleur)

    assert resp.status_code == 422
    assert "#rrggbb" in resp.text
    assert _opgeslagen(db_session) == "#005d29", "the refused value replaced the old one"


def test_a_colour_too_light_for_white_text_is_refused_with_its_ratio(client, db_session):
    csrf = _operator(client, db_session)
    resp = _opslaan(client, csrf, "#f0f0f0")

    assert resp.status_code == 422
    assert "contrast 1,14:1" in resp.text and "4,5:1" in resp.text
    assert _opgeslagen(db_session) is None


def test_the_contrast_boundary_is_aa():
    """#767676 is the lightest grey that passes AA on white; #777777 is not."""
    assert contrast_with_white("#767676") >= 4.5 > contrast_with_white("#777777")
    assert round(contrast_with_white("#005d29"), 2) == 8.08


def test_a_bad_value_that_reached_the_table_another_way_never_reaches_a_page(
        client, db_session):
    """The second line: an import or a hand-made row does not pass the form."""
    set_setting(db_session, SITE_HEADER_COLOR_KEY, "red;background:url(x)",
                tenant_id=DEFAULT_TENANT_ID)
    db_session.flush()

    html = client.get("/").text
    assert KAAL_NAV in html
    assert "url(x)" not in html


def test_the_admin_shell_does_not_change(client, db_session):
    csrf = _operator(client, db_session)
    _opslaan(client, csrf, "#005d29")

    html = client.get("/admin").text
    assert "#005d29" not in html
    assert "background-color: #005d29" not in html

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
- the `style` removed from the <header> in `site_base.html` → the colour test fails.

Since #1588 (CR-11 pilot B) the band is `<header class="site-header">`: without a
setting it carries NO style attribute and its colour is the CSS token
`--c-site-header`; with one the style stands on the <header> — which has no id
and is never an out-of-band target, so htmx' settle cannot reset it. The drawer
is white and stands outside the band.
"""

import re
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.kernel.tenancy import DEFAULT_TENANT_ID
from app.kernel.tenant_config import (
    SITE_HEADER_COLOR_KEY,
    contrast_with_white,
    get_setting,
    set_setting,
)

pytestmark = pytest.mark.ui_serverrendered

BARE_HEADER = '<header class="site-header" :inert="menu">'
BUILD_CSS = Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh"


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
    return client.post(
        # #1535: the workspace's own settings — Raak Millegem, on the default host.
        "/admin/instellingen",
        data={SITE_HEADER_COLOR_KEY: kleur},
        headers={"X-CSRF-Token": csrf},
    )


def _opgeslagen(db_session):
    db_session.expire_all()
    return get_setting(db_session, SITE_HEADER_COLOR_KEY, tenant_id=DEFAULT_TENANT_ID)


def _header(html: str) -> str:
    """The public header, from <header> to </header>."""
    m = re.search(r"<header\b.*?</header>", html, re.S)
    assert m, "no <header> in the page"
    return m.group(0)


def test_without_a_setting_the_header_takes_the_shell_colour(client):
    """No style attribute, and the band's colour is the token `--c-site-header`."""
    html = client.get("/").text
    assert BARE_HEADER in html
    assert "background-color:" not in _header(html)

    css = BUILD_CSS.read_text()
    assert len(re.findall(r"--c-site-header:36 75 197;", css)) == 1, "the token's one value"
    (rule,) = re.findall(r"(?m)^\.site-header\{([^}]*)\}", css)
    assert "background:rgb(var(--c-site-header))" in rule.split(";")
    assert "color:#fff" in rule.split(";"), "the text on the band is white"


def test_a_colour_covers_the_header_band(client, db_session):
    """The style stands on the <header>; the links and the account sit inside it.

    Until #1588 it stood on the <nav>, which also held the mobile menu. The
    drawer is white now and stands outside the band, and neither element with
    an id (the out-of-band targets) carries the colour.
    """
    csrf = _operator(client, db_session)
    resp = _opslaan(client, csrf, "#005D29")
    assert resp.status_code == 200, resp.text[:300]
    assert _opgeslagen(db_session) == "#005d29"

    client.cookies.clear()
    html = client.get("/").text
    header = _header(html)
    assert header.startswith(
        '<header class="site-header" style="background-color: #005d29" :inert="menu">'
    )
    assert html.count("#005d29") == 1, "the colour stands once, on the band"
    assert '<nav id="site-nav-breed" class="site-pages"' in header
    assert "data-site-account" in header and "data-site-brand" in header
    assert 'id="site-nav-mobiel"' not in header, "the drawer is not part of the band"
    assert 'id="site-nav-mobiel"' in html


def test_an_empty_value_goes_back_to_the_shell_colour(client, db_session):
    csrf = _operator(client, db_session)
    _opslaan(client, csrf, "#005d29")
    _opslaan(client, csrf, "")
    assert _opgeslagen(db_session) is None
    client.cookies.clear()
    assert BARE_HEADER in client.get("/").text


@pytest.mark.parametrize(
    "kleur",
    [
        "red; background:url(x)",
        "#005d29; background:url(https://evil.example/x)",
        '#005d29" onmouseover="alert(1)',
        "005d29",
        "#05d",
        "#005d2g",
        "rgb(0, 93, 41)",
        "var(--c-brand-green)",
    ],
)
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


def test_a_bad_value_that_reached_the_table_another_way_never_reaches_a_page(client, db_session):
    """The second line: an import or a hand-made row does not pass the form."""
    set_setting(
        db_session, SITE_HEADER_COLOR_KEY, "red;background:url(x)", tenant_id=DEFAULT_TENANT_ID
    )
    db_session.flush()

    html = client.get("/").text
    assert BARE_HEADER in html
    assert "url(x)" not in html


def test_the_admin_shell_does_not_change(client, db_session):
    csrf = _operator(client, db_session)
    _opslaan(client, csrf, "#005d29")

    html = client.get("/admin").text
    assert "#005d29" not in html
    assert "background-color: #005d29" not in html

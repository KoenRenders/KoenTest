"""The brand and the accent colour of the public site, per tenant (#1622).

Koen, 5 October 2026 (CR-11 Q68; end state §1.1): after P1 the public site wears
the Atelier palette, and Raak's own colours "belong to Raak". Two settings beside
the header colour: the BRAND colour (headings, links, the primary button, the
active navigation — its tints derived from that one value) and the ACCENT colour
(the site's one call to action, its text colour derived on contrast). Without a
setting nothing is written and the stylesheet's palette stands; the back office
never changes colour.

The values land in a `style` attribute on the public `<body>`, as RGB triplets
built from three integers — so the refusal tests read the STORED value and the
page, not only the message.

Broken to see them red (measured, each restored after):
- the colour branch removed from `_write_settings` → the eight injection cases
  per field and both contrast tests fail on the stored value;
- `_site_color` returning the raw setting → the read-side test fails;
- the `style` removed from the `<body>` in `site_base.html` → the body tests fail;
- a step's share changed in `_BRAND_STEPS` (0.27 → 0.30) → the three fixed
  outcomes fail;
- `SITE_COLOR_DEFAULTS` given another brand value → the stylesheet test fails.
"""

import re
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.kernel.tenancy import DEFAULT_TENANT_ID
from app.kernel.tenant_config import (
    SITE_ACCENT_COLOR_KEY,
    SITE_BRAND_COLOR_KEY,
    SITE_COLOR_DEFAULTS,
    accent_color_problem,
    accent_tokens,
    brand_color_problem,
    brand_tokens,
    contrast_between,
    get_setting,
    set_setting,
)

pytestmark = pytest.mark.ui_serverrendered

BUILD_CSS = Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh"
BARE_BODY = '<body class="bg-ground min-h-screen text-ink" data-shell="site" hx-boost="true"'
WHITE = (255, 255, 255)
INK = (37, 44, 53)


def _operator(client, db_session, email="op-kleuren@example.com"):
    u = User(email=email, is_active=True)
    db_session.add(u)
    db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_code="OPERATOR"))
    db_session.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _save(client, csrf, **colours):
    # The workspace's own settings — Raak Millegem, on the default host (#1535).
    return client.post("/admin/instellingen", data=colours, headers={"X-CSRF-Token": csrf})


def _stored(db_session, key):
    db_session.expire_all()
    return get_setting(db_session, key, tenant_id=DEFAULT_TENANT_ID)


def _body(html: str) -> str:
    found = re.search(r"<body\b[^>]*>", html)
    assert found, "no <body> in the page"
    return found.group(0)


def _triplet(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split())


# ── the derived tints: one value in, fixed outcomes ──────────────────────────


@pytest.mark.parametrize(
    ("colour", "soft", "focus", "hover", "darkest"),
    [
        # Raak's house-style blue.
        ("#0051a4", "232 239 247", "38 107 178", "0 59 120", "0 29 59"),
        # A green (the header colour of #992).
        ("#005d29", "232 240 236", "38 117 73", "0 68 30", "0 33 15"),
        # A dark red.
        ("#7a1f1f", "243 235 235", "142 65 65", "89 23 23", "44 11 11"),
    ],
)
def test_the_tints_are_derived_from_the_one_brand_colour(colour, soft, focus, hover, darkest):
    tokens = brand_tokens(colour)
    own = " ".join(str(int(colour[i : i + 2], 16)) for i in (1, 3, 5))
    assert tokens["--c-blue-700"] == own, "step 700 is the colour itself"
    assert (
        tokens["--c-blue-50"],
        tokens["--c-blue-500"],
        tokens["--c-blue-800"],
        tokens["--c-blue-950"],
    ) == (soft, focus, hover, darkest)
    # The roles read the scale: nothing is a second number.
    assert tokens["--c-brand"] == tokens["--c-brand-ocean"] == tokens["--c-link"] == own
    assert tokens["--c-kop"] == own
    assert tokens["--c-brand-ocean-hover"] == hover and tokens["--c-focus"] == focus
    # The scale runs from light to dark without a step out of order.
    steps = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
    sums = [sum(_triplet(tokens[f"--c-blue-{step}"])) for step in steps]
    assert len(tokens) == len(steps) + 6
    # 600 is a little DARKER than 700 in Atelier (31 70 110 against 37 78 115).
    assert sums[:6] == sorted(sums[:6], reverse=True) and sums[7:] == sorted(sums[7:], reverse=True)
    assert sums[6] < sums[7] < sums[5]
    # What the derived steps are used for keeps its contrast on white: the hover
    # carries white text, the focus ring needs 3 : 1.
    assert contrast_between(_triplet(hover), WHITE) >= 4.5
    assert contrast_between(_triplet(focus), WHITE) >= 3


def test_every_token_is_three_integers():
    """What reaches the style attribute is built from numbers, whatever came in."""
    for tokens in (brand_tokens("#0051A4"), accent_tokens("#FFD200")):
        for name, value in tokens.items():
            assert re.fullmatch(r"--c-[a-z0-9-]+", name), name
            assert re.fullmatch(r"\d{1,3} \d{1,3} \d{1,3}", value), (name, value)
            assert all(0 <= part <= 255 for part in _triplet(value)), (name, value)


def test_the_accents_text_is_the_one_that_reads_best():
    yellow = accent_tokens("#ffd200")
    assert yellow == {"--c-accent": "255 210 0", "--c-on-accent": "37 44 53"}
    assert round(contrast_between((255, 210, 0), INK), 2) == 9.71
    red = accent_tokens("#e2001a")
    assert red == {"--c-accent": "226 0 26", "--c-on-accent": "255 255 255"}
    assert round(contrast_between((226, 0, 26), WHITE), 2) == 4.94


def test_the_two_rules_refuse_what_cannot_carry_text():
    # The brand colour: the header colour's rule, white text on it.
    assert brand_color_problem("#0051a4") is None
    assert "contrast 1,45:1" in brand_color_problem("#ffd200")
    # The accent: dark or white text must reach 4,5 : 1 — a mid-tone carries neither.
    assert accent_color_problem("#ffd200") is None and accent_color_problem("#0051a4") is None
    assert "hoogstens 3,95:1" in accent_color_problem("#808080")
    assert "hoogstens 4,36:1" in accent_color_problem("#5b8def")
    for bad in ("ffd200", "#fd0", "rgb(255, 210, 0)", ""):
        assert "#rrggbb" in accent_color_problem(bad)
        assert "#rrggbb" in brand_color_problem(bad)


def test_the_placeholders_are_the_stylesheets_own_colours():
    """`SITE_COLOR_DEFAULTS` names what an empty field means; the stylesheet is
    where it is true. One fact in two forms, so they are held together here."""
    css = BUILD_CSS.read_text()
    site = css[css.index('body[data-shell="site"]{') :]
    site = site[: site.index("}")]
    for key, token in ((SITE_BRAND_COLOR_KEY, "--c-brand"), (SITE_ACCENT_COLOR_KEY, "--c-accent")):
        found = re.search(re.escape(token) + r":(\d+ \d+ \d+);", site)
        assert found, f"{token} is not in the site shell's tokens"
        own = " ".join(str(int(SITE_COLOR_DEFAULTS[key][i : i + 2], 16)) for i in (1, 3, 5))
        assert found.group(1) == own, f"{key}: placeholder {own}, stylesheet {found.group(1)}"


# ── the public body ──────────────────────────────────────────────────────────


def test_without_a_setting_the_body_carries_no_style(client):
    html = client.get("/").text
    assert _body(html).startswith(BARE_BODY), _body(html)
    assert "--c-brand:" not in html and "--c-accent:" not in html


def test_the_two_colours_stand_on_the_public_body_as_tokens(client, db_session):
    csrf = _operator(client, db_session)
    resp = _save(
        client, csrf, **{SITE_BRAND_COLOR_KEY: "#0051A4", SITE_ACCENT_COLOR_KEY: "#FFD200"}
    )
    assert resp.status_code == 200, resp.text[:300]
    assert _stored(db_session, SITE_BRAND_COLOR_KEY) == "#0051a4"
    assert _stored(db_session, SITE_ACCENT_COLOR_KEY) == "#ffd200"

    client.cookies.clear()
    body = _body(client.get("/").text)
    style = re.search(r' style="([^"]*)"', body).group(1)
    tokens = dict(part.split(":") for part in style.split(";"))
    assert tokens == {**brand_tokens("#0051a4"), **accent_tokens("#ffd200")}
    assert tokens["--c-brand"] == "0 81 164" and tokens["--c-accent"] == "255 210 0"
    assert "#0051a4" not in body and "#ffd200" not in body, "numbers, not the stored text"


def test_one_colour_alone_leaves_the_other_to_the_palette(client, db_session):
    csrf = _operator(client, db_session)
    _save(client, csrf, **{SITE_ACCENT_COLOR_KEY: "#ffd200"})
    client.cookies.clear()
    style = re.search(r' style="([^"]*)"', _body(client.get("/").text)).group(1)
    assert style == "--c-accent:255 210 0;--c-on-accent:37 44 53"


def test_an_empty_value_goes_back_to_the_palette(client, db_session):
    csrf = _operator(client, db_session)
    _save(client, csrf, **{SITE_BRAND_COLOR_KEY: "#0051a4", SITE_ACCENT_COLOR_KEY: "#ffd200"})
    _save(client, csrf, **{SITE_BRAND_COLOR_KEY: "", SITE_ACCENT_COLOR_KEY: ""})
    assert _stored(db_session, SITE_BRAND_COLOR_KEY) is None
    assert _stored(db_session, SITE_ACCENT_COLOR_KEY) is None
    client.cookies.clear()
    assert _body(client.get("/").text).startswith(BARE_BODY)


# ── refused, never repaired ──────────────────────────────────────────────────


@pytest.mark.parametrize("key", [SITE_BRAND_COLOR_KEY, SITE_ACCENT_COLOR_KEY])
@pytest.mark.parametrize(
    "colour",
    [
        "red; background:url(x)",
        "#0051a4; background:url(https://evil.example/x)",
        '#0051a4" onmouseover="alert(1)',
        "0051a4",
        "#05d",
        "#0051ag",
        "rgb(0, 81, 164)",
        "var(--c-brand)",
    ],
)
def test_anything_but_rrggbb_is_refused_and_never_stored(client, db_session, key, colour):
    csrf = _operator(client, db_session)
    _save(client, csrf, **{key: "#0051a4"})

    resp = _save(client, csrf, **{key: colour})

    assert resp.status_code == 422
    assert "#rrggbb" in resp.text
    assert _stored(db_session, key) == "#0051a4", "the refused value replaced the old one"


def test_a_brand_colour_too_light_for_white_text_is_refused_with_its_ratio(client, db_session):
    csrf = _operator(client, db_session)
    resp = _save(client, csrf, **{SITE_BRAND_COLOR_KEY: "#ffd200"})
    assert resp.status_code == 422
    assert "contrast 1,45:1" in resp.text and "4,5:1" in resp.text
    assert _stored(db_session, SITE_BRAND_COLOR_KEY) is None


def test_an_accent_that_carries_no_text_is_refused_with_its_ratio(client, db_session):
    csrf = _operator(client, db_session)
    resp = _save(client, csrf, **{SITE_ACCENT_COLOR_KEY: "#808080"})
    assert resp.status_code == 422
    assert "hoogstens 3,95:1" in resp.text and "4,5:1" in resp.text
    assert _stored(db_session, SITE_ACCENT_COLOR_KEY) is None


def test_a_bad_value_that_reached_the_table_another_way_never_reaches_a_page(client, db_session):
    """The second line: an import or a hand-made row does not pass the form."""
    for key in (SITE_BRAND_COLOR_KEY, SITE_ACCENT_COLOR_KEY):
        set_setting(db_session, key, "red;background:url(x)", tenant_id=DEFAULT_TENANT_ID)
    db_session.flush()

    html = client.get("/").text
    assert _body(html).startswith(BARE_BODY)
    assert "url(x)" not in html


# ── the editor and the back office ───────────────────────────────────────────


def test_the_editor_shows_both_fields_with_the_standard_as_placeholder(client, db_session):
    csrf = _operator(client, db_session)
    page = client.get("/admin/instellingen").text
    for key in (SITE_BRAND_COLOR_KEY, SITE_ACCENT_COLOR_KEY):
        field = re.search(rf'<input [^>]*name="{key}"[^>]*>', page).group(0)
        assert f'placeholder="{SITE_COLOR_DEFAULTS[key]}"' in field and "value=" not in field, field
        assert f'data-colour-field="{key}"' in page
        # The kit's field (the ratchet on raw form elements only falls).
        assert f'data-field="{key}" data-kind="text"' in page
    assert page.count("data-colour-sample") == 2
    # Beside the header colour, in the card "Site".
    assert (
        page.index('name="site_header_color"')
        < page.index(f'name="{SITE_BRAND_COLOR_KEY}"')
        < page.index(f'name="{SITE_ACCENT_COLOR_KEY}"')
    )

    _save(client, csrf, **{SITE_BRAND_COLOR_KEY: "#0051a4"})
    page = client.get("/admin/instellingen").text
    field = re.search(rf'<input [^>]*name="{SITE_BRAND_COLOR_KEY}"[^>]*>', page).group(0)
    assert 'value="#0051a4"' in field


def test_the_admin_shell_does_not_change(client, db_session):
    csrf = _operator(client, db_session)
    _save(client, csrf, **{SITE_BRAND_COLOR_KEY: "#0051a4", SITE_ACCENT_COLOR_KEY: "#ffd200"})

    html = client.get("/admin").text
    assert "--c-brand:" not in html and "--c-accent:" not in html
    assert " style=" not in _body(html)

"""#1245 — the site has an icon, and `/favicon.ico` answers 200 instead of 404.

Every page load asked for `/favicon.ico` and got a 404: a browser asks for it by
itself, with or without a link in the page. The tab showed a blank sheet.

The icon is candidate B, chosen by Koen on 28 September 2026: the RaaK wordmark
cropped square from the house-style logo and scaled, on the logo's own blue —
nothing redrawn. The files are `static/favicon.ico` (16, 32 and 48 px inside) and
`static/apple-touch-icon.png` (180 px); both shells link them, and `/favicon.ico`
serves the same file for the request nobody links.

Broken on purpose to check these tests can go red (run, then restored):
  - `static/favicon.ico` moved away → the route test fails naming that path, and
    the head test fails on the linked file;
  - the two `<link>` lines taken out of `admin_base.html` → the head test fails
    for the admin page only.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def _ico_sizes(data: bytes) -> list[int]:
    """The image sizes inside an .ico, read from its directory (0 means 256)."""
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1), "not an icon file"
    return sorted((data[6 + 16 * i] or 256) for i in range(count))


def test_favicon_ico_answers_with_the_icon(client):
    path = STATIC / "favicon.ico"
    assert path.exists(), f"missing {path.relative_to(STATIC.parents[1])}"
    response = client.get("/favicon.ico")
    assert response.status_code == 200, f"/favicon.ico → {response.status_code}"
    assert response.headers["content-type"].startswith("image/")
    assert response.content == path.read_bytes()
    assert _ico_sizes(response.content) == [16, 32, 48]


def test_the_touch_icon_is_180_px():
    data = (STATIC / "apple-touch-icon.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (180, 180)


@pytest.mark.parametrize("page", ["/", "/admin/activiteiten"])
def test_both_shells_link_the_icons(client, page):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(page).text
    head = html.split("</head>", 1)[0]
    links = dict(re.findall(r'<link rel="(icon|apple-touch-icon)" href="([^"]+)"', head))
    assert set(links) == {"icon", "apple-touch-icon"}, f"{page}: head links {links}"
    for rel, href in links.items():
        linked = client.get(href)
        assert linked.status_code == 200, f"{page}: {rel} {href} → {linked.status_code}"

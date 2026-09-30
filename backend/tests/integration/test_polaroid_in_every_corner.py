"""A design with a polaroid draws, in every corner (#1388).

Koen, on HDEV: a design with a polaroid did not open — a 500, `'InsetCorner' object
has no attribute 'endswith'` in `blocks.polaroid_on`. #1180 (CR-12, v2.7.0) made
`designs.inset_corner` an `InsetCorner` member; `content_for` handed that member to
`PosterContent`, which typed the field as a string, and the renderer called
`.endswith("_left")` on it. On PROD too: its one design has a polaroid.

The field now follows `preset`, the pattern `PosterContent` already had: typed as
the member, coerced from a code or a member in `__post_init__`, compared as members
in `blocks.polaroid_on`. The editor's form keeps its own conversion to the code — a
different boundary, the one a <select> needs.

Drawn for real, for each corner: `check_design` (every layout) and the editor route
answer without an error, and in the drawn A3 the polaroid lies on the left for the
left corners, on the right for the right ones, higher for the top ones.

Red against master `215d9806` (30 September 2026): every case, with the 500's
`AttributeError`.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.designstudio import service
from app.domains.designstudio.models import InsetCorner, Layout
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.integration.test_designstudio_engine import PNG_2x2
from tests.integration.test_designstudio_service import activity, design  # noqa: F401

pytestmark = pytest.mark.ui_serverrendered

CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")


def _with_polaroid(db, d, corner: str):
    from app.domains.media.api import MediaAsset

    inset = MediaAsset(
        kind="design_image",
        activity_id=d.activity_id,
        data=PNG_2x2,
        content_type="image/png",
        thumbnail=PNG_2x2,
        thumb_content_type="image/png",
        width=2,
        height=2,
        byte_size=len(PNG_2x2),
        title="polaroid",
        sort_order=1,
        is_active=True,
    )
    db.add(inset)
    db.flush()
    service.save_design(
        db,
        d,
        {
            "duo_code": d.duo_code,
            "preset": "beeld",
            "main_image_id": str(d.main_image_id),
            "inset_image_id": str(inset.id),
            "inset_corner": corner,
        },
        highlights=[("users", "Gezellig samen", False)],
        logo_ids=[],
    )
    db.refresh(d)
    return d


def _polaroid_position(svg: str) -> tuple[float, float]:
    """The polaroid's picture is the second <image> on the poster."""
    images = re.findall(r'<image x="([0-9.]+)" y="([0-9.]+)"', svg)
    assert len(images) >= 2, f"no polaroid drawn: {len(images)} image(s)"
    x, y = images[1]
    return float(x), float(y)


@pytest.mark.parametrize("corner", CORNERS)
def test_every_corner_draws_in_check_and_in_the_editor(client, db_session, design, corner):  # noqa: F811
    d = _with_polaroid(db_session, design, corner)
    assert d.inset_corner is InsetCorner(corner)

    service.check_design(db_session, d)  # every layout, no error

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get(f"/admin/ontwerpen/{d.id}")
    assert page.status_code == 200, page.text[:300]


def test_the_polaroid_lies_in_the_chosen_corner(db_session, design):  # noqa: F811
    positions = {}
    for corner in CORNERS:
        d = _with_polaroid(db_session, design, corner)
        merged = service.merged_for(db_session, d, Layout.PRINT_A)
        positions[corner] = _polaroid_position(merged.svg)

    (tlx, tly), (trx, try_), (blx, bly), (brx, bry) = (positions[c] for c in CORNERS)
    assert tlx == blx < trx == brx, positions
    assert tly < bly and try_ < bry, positions

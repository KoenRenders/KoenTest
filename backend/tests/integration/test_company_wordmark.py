"""CR-19 #1496 — a company's site shows its own name at the top, not RaaK.

Without a logo, a tenant of kind BEDRIJF shows its name as a text wordmark where
an association shows the RaaK wordmark (`R<span>aa</span>K`, read as "Raak").
With a logo, every tenant shows the logo. Measured on the home page as served.

Proven red against master `233ac85c`: the company test fails — the header shows
the RaaK wordmark for every tenant without a logo.
"""

from __future__ import annotations

import re

import pytest

from app.domains.mdm.api import Organization, TenantKind
from app.domains.media.api import MediaAsset, MediaKind, media_url
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered

RAAK = re.compile(r'aria-label="Raak">R<span class="text-\[1\.3em\]">aa</span>K</span>')


def _home_header(client) -> str:
    html = client.get("/").text
    start = html.index("<header")
    return html[start : html.index("</header>", start)]


def _make(db_session, kind: TenantKind, name: str) -> None:
    org = db_session.get(Organization, TENANT_MILLEGEM_ID)
    org.kind = kind
    org.name = name
    db_session.commit()


def _logo(db_session) -> MediaAsset:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    asset = MediaAsset(
        kind=MediaKind.TENANT_LOGO,
        data=png,
        content_type="image/png",
        byte_size=len(png),
        title="logo",
        sort_order=0,
        is_active=True,
    )
    asset.tenant_id = TENANT_MILLEGEM_ID
    db_session.add(asset)
    db_session.commit()
    return asset


def test_a_company_without_a_logo_shows_its_name(client, db_session):
    _make(db_session, TenantKind.COMPANY, "Bakkerij Peeters")

    header = _home_header(client)

    assert 'aria-label="Bakkerij Peeters">Bakkerij Peeters</span>' in header
    assert not RAAK.search(header), "the association's wordmark on a company site"


def test_an_association_without_a_logo_keeps_the_raak_wordmark(client, db_session):
    _make(db_session, TenantKind.ASSOCIATION, "Raak Millegem")

    header = _home_header(client)

    assert RAAK.search(header)
    assert 'aria-label="Raak Millegem"' not in header


@pytest.mark.parametrize("kind", [TenantKind.COMPANY, TenantKind.ASSOCIATION])
def test_a_logo_wins_whatever_the_kind(client, db_session, kind):
    _make(db_session, kind, "Bakkerij Peeters")
    logo = _logo(db_session)

    header = _home_header(client)

    assert f'<img src="{media_url(logo.id)}"' in header
    assert not RAAK.search(header)
    assert 'aria-label="Bakkerij Peeters">' not in header

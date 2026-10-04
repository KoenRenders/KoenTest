"""#653 — de huidige bijlage staat nooit twee keer tegelijk op het scherm.

`_aa_detail.html` had een alinea met "Huidige affiche bekijken" waarvan de
code-opmerking zei "in read-modus", maar zonder `x-show`. Ze stond er dus ook
tijdens het bewerken, waar `ui.upload_field()` diezelfde link al rendert.

§2.12: de leeslink mag blijven — een bijlage kunnen openen zonder eerst te gaan
bewerken is nuttig — maar dan uitsluitend achter `x-show="!edit"`.

Since #1558 (CR-11 block 6) reading and editing are two states of the page
(`?bewerken=1`), not two layers shown and hidden in one DOM; the invariant is
the same and is checked per state.
"""

import io
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _upload_affiche(client, csrf, activity):
    """Een echte affiche opladen — zonder bijlage bestaat de leeslink niet."""
    r = client.post(
        f"/admin/activiteiten/{activity.id}",
        data={"name": activity.name},
        files={"file": ("affiche.png", io.BytesIO(PNG), "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text[:300]


def _regels_met(html: str, tekst: str) -> list[str]:
    return [r.strip() for r in html.splitlines() if tekst in r]


def test_de_affichelink_staat_er_in_elke_modus_precies_een_keer(client, db_session):
    """#653, since #1558: read and edit are two states of the page, not two layers
    in one DOM. Each state shows the attachment's link exactly once — as the
    field's value while reading, beside the upload button while editing."""
    activity, _c, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    _upload_affiche(client, csrf, activity)

    for suffix in ("", "?bewerken=1"):
        html = client.get(f"/admin/activiteiten/{activity.id}{suffix}").text
        # Only LINKS count (#1019): the preview picture is an <img>, not a link.
        links = re.findall(r'<a href="/api/v1/media/[^"]*"', html)
        assert len(links) == 1, f"{suffix or 'read'}: {len(links)} links to the attachment"
        assert "- poster" in html, "the link carries the document's title"


def test_de_locatie_staat_niet_dubbel_als_tekst_tijdens_het_bewerken(client, db_session):
    """The location stands in the record head in every state — it says what you
    are editing. While editing it is a field, not a second line of text beside
    that field; while reading it is the head and the field's value."""
    activity, _c, _p = seed_activity_with_product(db_session)
    activity.location = "Parochiezaal"
    db_session.flush()
    _login(client)

    def as_text(html: str) -> int:
        return len(re.findall(r">\s*Parochiezaal\s*<", html))

    edit = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert as_text(edit) == 1, "only the head says it as text while editing"
    assert 'name="location"' in edit and 'value="Parochiezaal"' in edit
    read = client.get(f"/admin/activiteiten/{activity.id}").text
    assert as_text(read) == 2, "the head and the field's value"
    assert 'name="location"' not in read


def test_zonder_bijlage_geen_leeslink(client, db_session):
    """De guard moet blijven staan: geen affiche, geen link."""
    activity, _c, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    # Het uploadblok toont het label enkel als er een bijlage is; de leeslink ook.
    assert "Huidige affiche bekijken" not in html

"""A page says itself that it stands in the footer (#1569).

Where a page appears is set on the page: home, the header menu, and — since this
issue — the footer. The tenant setting `privacy_url` is gone; the migration moved
it onto the page it pointed to.
"""

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.models import CmsPage
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _page(db, slug: str, title: str, *, tenant_id=TENANT_MILLEGEM_ID, **fields) -> CmsPage:
    page = CmsPage(
        tenant_id=tenant_id,
        slug=slug,
        title=title,
        content="<p>Tekst</p>",
        **{"is_published": True, "show_in_nav": False, **fields},
    )
    db.add(page)
    db.commit()
    return page


def _footer_line(html: str) -> str:
    start = html.index("data-footer-line")
    return html[start : html.index("</p>", start)]


def _footer_links(html: str) -> list[tuple[str, str]]:
    return re.findall(r'<a href="([^"]+)" data-footer-page[^>]*>(.*?)</a>', _footer_line(html))


# ── The footer ───────────────────────────────────────────────────────────────


def test_a_published_page_with_the_checkbox_stands_in_the_footer(client, db_session):
    """…an unpublished one does not, and neither does a page without the
    checkbox. Red against master, where the footer knew only `privacy_url`."""
    _page(db_session, "voorwaarden-1569", "Algemene voorwaarden", show_in_footer=True, sort_order=2)
    _page(db_session, "cookies-1569", "Cookies", show_in_footer=True, sort_order=1)
    _page(db_session, "concept-1569", "Nog niet klaar", show_in_footer=True, is_published=False)
    _page(db_session, "gewoon-1569", "Gewone pagina")

    links = _footer_links(client.get("/aanmelden").text)
    assert links == [
        ("/cookies-1569", "Cookies"),
        ("/voorwaarden-1569", "Algemene voorwaarden"),
    ], "by sort order, each by its title"


def test_a_site_without_a_footer_page_shows_only_its_name(client, db_session):
    line = _footer_line(client.get("/aanmelden").text)
    assert "<a " not in line and "©" in line


def test_another_tenants_footer_page_stays_on_its_own_site(client, db_session):
    _page(db_session, "elders-1569", "Elders", tenant_id=TENANT_VOORBEELD_ID, show_in_footer=True)
    assert _footer_links(client.get("/aanmelden").text) == []


def test_the_newsletter_form_links_the_same_pages(client, db_session):
    """The small print under the newsletter form read `privacy_url`; it shows the
    footer's pages, by their title."""
    _page(db_session, "privacy-1569", "Privacyverklaring", show_in_footer=True)
    html = client.get("/nieuwsbrief").text
    form = html[html.index('id="nb-publiek"') : html.index("data-footer-line")]
    assert re.search(r'<a class="[^"]*" href="/privacy-1569">Privacyverklaring</a>', form)


# ── The page editor and the list ─────────────────────────────────────────────


def test_the_editor_offers_the_checkbox_and_saves_it(client, db_session):
    page = _page(db_session, "bewaren-1569", "Bewaren")
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    editor = client.get(f"/admin/paginas/{page.id}").text
    # Snede 3 (#1671): the kit's switch is the screen's control now — the
    # hand-built checkbox left with the hand-built detail fragment. The
    # hidden field carries the off value, the checkbox the on value.
    box = re.search(r'<input type="checkbox"[^>]*name="show_in_footer"[^>]*>', editor)
    assert box and "checked" not in box.group(0), "off by default"
    assert "Toon in de voettekst" in editor

    def save(**extra):
        return client.post(
            f"/admin/paginas/{page.id}",
            data={
                "title": "Bewaren",
                "slug": "bewaren-1569",
                "content": "<p>x</p>",
                "is_published": "1",
                **extra,
            },
            headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
        )

    # Snede 3 (#1671): a save that succeeds is a 204 with the way back —
    # htmx follows the header (the browser navigates), the old 200-with-
    # fragment is gone with the master-detail.
    assert save(show_in_footer="1").status_code == 204
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).show_in_footer is True
    assert "in voettekst" in client.get("/admin/paginas").text, "the list shows a badge"

    assert save().status_code == 204, "unticked: the key is absent from the form"
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).show_in_footer is False


def test_the_tenant_editor_no_longer_offers_the_privacy_link(db_session):
    from app.ui.tenants_ui import BEKENDE_SLEUTELS

    keys = [key for key, _label, _help in BEKENDE_SLEUTELS]
    assert keys.count("privacy_url") == 0
    assert "base_url" in keys, "the list itself is still there"


# ── The migration ────────────────────────────────────────────────────────────


def _migration():
    [path] = Path(__file__).resolve().parents[4].glob("alembic/versions/196_*.py")
    spec = importlib.util.spec_from_file_location("migration_196", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set(db, tenant_id: int, value: str) -> None:
    db.execute(
        text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value, updated_at) "
            "VALUES (:t, 'privacy_url', :v, now())"
        ),
        {"t": tenant_id, "v": value},
    )


def test_the_migration_moves_the_setting_onto_its_page_and_removes_it(client, db_session):
    """A tenant whose setting pointed to `/privacy-…` has the same footer link
    afterwards, and the setting is gone. A value that matches no published page
    is counted, not guessed."""
    _page(db_session, "privacy-1569", "Privacyverklaring")
    _page(db_session, "klad-1569", "Klad", tenant_id=TENANT_VOORBEELD_ID, is_published=False)
    _set(db_session, TENANT_MILLEGEM_ID, "/privacy-1569")
    _set(db_session, TENANT_VOORBEELD_ID, "/klad-1569")
    db_session.commit()
    assert _footer_links(client.get("/aanmelden").text) == []

    counts = _migration().move_settings_to_pages(db_session.connection())
    db_session.commit()

    assert counts == {"with_value": 2, "moved": 1, "unmatched": [TENANT_VOORBEELD_ID], "removed": 2}
    assert _footer_links(client.get("/aanmelden").text) == [("/privacy-1569", "Privacyverklaring")]
    left = db_session.execute(
        text("SELECT count(*) FROM kernel_tenant_settings WHERE key = 'privacy_url'")
    )
    assert left.scalar() == 0


@pytest.mark.parametrize("value", ["https://elders.example/privacy", "/a/b", "  ", "/bestaat-niet"])
def test_a_value_that_names_no_page_of_the_site_ticks_nothing(db_session, value):
    _page(db_session, "privacy-1569", "Privacyverklaring")
    _set(db_session, TENANT_MILLEGEM_ID, value)
    db_session.commit()

    counts = _migration().move_settings_to_pages(db_session.connection())
    db_session.commit()

    assert counts["moved"] == 0 and counts["removed"] == 1
    assert counts["unmatched"] == ([] if not value.strip() else [TENANT_MILLEGEM_ID])
    flagged = db_session.execute(text("SELECT count(*) FROM cms.cms_pages WHERE show_in_footer"))
    assert flagged.scalar() == 0

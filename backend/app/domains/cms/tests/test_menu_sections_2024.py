"""A page stands under a section of the menu (CR-17 phase 6, R8, F10; #2024).

Koen, 15 October 2026, Q&A nr. 11, each "ja": a section is itself a page; one
level only; a section with pages under it cannot be deleted; a page under a
section shows the kit's way back to it above its title; a field "Naam in het
menu", the title when empty. And on 16 October 2026, "1a, 2a, 3a": the menu
(the walk in the browser is `tests_e2e/pages/test_menu_sections_2024.py`).

Broken on purpose (16 October 2026), each red here: `_check_section` not called
→ the one-level and home tests; the delete guard off → both delete tests; the
way back's `{% if %}` false → the way-back test; the menu name not written →
four tests; the section field off the screen → the screen test; `menu_tree`
flat → both menu tests. After the review of #2057 (B4): the length checked
after the fields are set → the too-long test; the menu name written to every
translation → the language test.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.api import (
    SectionRefused,
    create_page,
    delete_page,
    menu_name,
    section_back,
    section_choices,
    update_page,
)
from app.domains.cms.models import CmsPage
from app.schemas.cms import CmsPageCreate, CmsPageUpdate
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _page(db, slug: str, title: str, *, is_home: bool = False, **fields) -> CmsPage:
    page = create_page(db, CmsPageCreate(title=title, slug=slug, content="<p>Tekst</p>"))
    for name, value in {"is_published": True, **fields}.items():
        setattr(page, name, value)
    db.commit()
    if is_home:
        # The flag moves (#1477): the service takes it from the seeded home page.
        update_page(db, page.id, CmsPageUpdate(is_home=True))
    return page


# ── The rules ────────────────────────────────────────────────────────────────


def test_a_page_stands_under_a_section_and_leaves_it(db_session):
    section = _page(db_session, "over-ons-2024", "Over ons")
    page = _page(db_session, "bestuur-2024", "Bestuur")

    update_page(db_session, page.id, CmsPageUpdate(parent_id=section.id))
    assert db_session.get(CmsPage, page.id).parent_id == section.id

    update_page(db_session, page.id, CmsPageUpdate(title="Het bestuur"))
    assert db_session.get(CmsPage, page.id).parent_id == section.id, (
        "a save that does not name the section keeps it"
    )

    update_page(db_session, page.id, CmsPageUpdate(parent_id=None))
    assert db_session.get(CmsPage, page.id).parent_id is None, "None set is no section"


def test_the_menu_is_one_level_deep(db_session):
    section = _page(db_session, "over-ons-2024b", "Over ons")
    page = _page(db_session, "bestuur-2024b", "Bestuur", parent_id=section.id)
    third = _page(db_session, "leden-2024b", "Leden")

    with pytest.raises(SectionRefused, match="één niveau"):
        update_page(db_session, third.id, CmsPageUpdate(parent_id=page.id))
    with pytest.raises(SectionRefused, match="staat zelf onder geen sectie"):
        update_page(db_session, section.id, CmsPageUpdate(parent_id=third.id))
    with pytest.raises(SectionRefused, match="onder zichzelf"):
        update_page(db_session, third.id, CmsPageUpdate(parent_id=third.id))


def test_the_home_page_is_neither_a_section_nor_under_one(db_session):
    home = _page(db_session, "thuis-2024", "Thuis", is_home=True)
    page = _page(db_session, "info-2024", "Info")

    with pytest.raises(SectionRefused, match="startpagina is geen sectie"):
        update_page(db_session, page.id, CmsPageUpdate(parent_id=home.id))
    with pytest.raises(SectionRefused, match="startpagina staat niet"):
        update_page(db_session, home.id, CmsPageUpdate(parent_id=page.id))

    child = _page(db_session, "kind-2024", "Kind", parent_id=page.id)
    assert child.parent_id == page.id
    with pytest.raises(SectionRefused, match="startpagina is geen sectie"):
        update_page(db_session, page.id, CmsPageUpdate(is_home=True))


def test_a_section_with_pages_under_it_cannot_be_deleted(db_session):
    section = _page(db_session, "over-ons-2024c", "Over ons")
    page = _page(db_session, "bestuur-2024c", "Bestuur", parent_id=section.id)

    with pytest.raises(SectionRefused, match="Er staan nog pagina's onder"):
        delete_page(db_session, section.id)
    assert db_session.get(CmsPage, section.id) is not None

    update_page(db_session, page.id, CmsPageUpdate(parent_id=None))
    delete_page(db_session, section.id)
    assert db_session.get(CmsPage, section.id) is None, "empty, the section goes"


def test_the_choices_follow_the_rules(db_session):
    home = _page(db_session, "thuis-2024d", "Thuis", is_home=True)
    section = _page(db_session, "over-ons-2024d", "Over ons")
    under = _page(db_session, "bestuur-2024d", "Bestuur", parent_id=section.id)
    loose = _page(db_session, "los-2024d", "Los")

    offered = {pid for pid, _title in section_choices(db_session, loose)}
    assert section.id in offered and under.id not in offered and home.id not in offered
    assert loose.id not in offered, "not under itself"
    assert section_choices(db_session, section) == [], "a section holding pages stands under none"
    assert section_choices(db_session, home) == [], "the home page stands under none"


# ── The menu name and the way back ───────────────────────────────────────────


def test_the_menu_name_is_the_title_when_empty(db_session):
    page = _page(db_session, "lidmaatschap-2024", "Lidmaatschap en lidgeld")
    assert menu_name(db_session, page) == "Lidmaatschap en lidgeld"

    update_page(db_session, page.id, CmsPageUpdate(menu_label="  Lidgeld "))
    assert menu_name(db_session, page) == "Lidgeld"

    update_page(db_session, page.id, CmsPageUpdate(menu_label=""))
    assert menu_name(db_session, page) == "Lidmaatschap en lidgeld"


def test_a_page_under_a_section_shows_the_way_back(client, db_session):
    section = _page(db_session, "over-ons-2024e", "Over ons en onze werking")
    update_page(db_session, section.id, CmsPageUpdate(menu_label="Over ons"))
    page = _page(db_session, "bestuur-2024e", "Bestuur", parent_id=section.id)

    html = client.get("/bestuur-2024e").text
    back = re.search(r'<a class="[^"]*" href="([^"]+)">‹ ([^<]+)</a>', html)
    assert back and back.groups() == ("/over-ons-2024e", "Over ons"), "the section's menu name"
    assert html.index("‹ Over ons") < html.index("<h1"), "above the title"

    assert section_back(db_session, section) is None, "a section has no way back"
    section.is_published = False
    db_session.commit()
    assert "‹ Over ons" not in client.get(f"/{page.slug}").text, (
        "an offline section is no page to go back to"
    )


# ── The screen ───────────────────────────────────────────────────────────────


def test_the_screen_sets_the_section_and_the_menu_name(client, db_session):
    section = _page(db_session, "over-ons-2024f", "Over ons")
    page = _page(db_session, "bestuur-2024f", "Bestuur")
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    editor = client.get(f"/admin/paginas/{page.id}").text
    assert "Onder sectie" in editor and "Naam in het menu" in editor
    assert re.search(rf'<option value="{section.id}"[^>]*>Over ons</option>', editor)

    def save(**extra):
        return client.post(
            f"/admin/paginas/{page.id}",
            data={"title": "Bestuur", "slug": "bestuur-2024f", **extra},
            headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
        )

    assert save(parent_id=str(section.id), menu_label="Het bestuur").status_code == 204
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).parent_id == section.id
    assert menu_name(db_session, db_session.get(CmsPage, page.id)) == "Het bestuur"

    assert save(parent_id="").status_code == 204
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).parent_id is None, "— geen — clears it"


def test_the_screen_says_why_a_section_is_not_deleted(client, db_session):
    section = _page(db_session, "over-ons-2024g", "Over ons")
    _page(db_session, "bestuur-2024g", "Bestuur", parent_id=section.id)
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    response = client.post(
        f"/admin/paginas/{section.id}/verwijderen",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert response.headers.get("HX-Retarget") == "#main"
    assert "Er staan nog pagina" in response.text
    db_session.expire_all()
    assert db_session.get(CmsPage, section.id) is not None


# ── The menu (Koen, 16 October 2026: "1a, 2a, 3a") ───────────────────────────


def _wide_nav(html: str) -> str:
    start = html.index('id="site-nav-breed"')
    return html[start : html.index("</nav>", start)]


def _drawer(html: str) -> str:
    start = html.index('id="site-nav-mobiel"')
    return html[start : html.index("</nav>", start)]


def test_the_menu_holds_a_section_with_its_pages(client, db_session):
    section = _page(db_session, "over-ons-2024h", "Over ons", show_in_nav=True, sort_order=900)
    _page(db_session, "geschiedenis-2024h", "Geschiedenis", parent_id=section.id, sort_order=2)
    bestuur = _page(db_session, "bestuur-2024h", "Bestuur", parent_id=section.id, sort_order=1)
    update_page(db_session, bestuur.id, CmsPageUpdate(menu_label="Het bestuur"))
    _page(db_session, "verborgen-2024h", "Verborgen", parent_id=section.id, show_in_nav=False)

    html = client.get("/aanmelden").text
    wide = _wide_nav(html)
    block = wide[wide.index("data-menu-section") :]
    assert f'href="/{section.slug}"' in block, "the section's name opens its page"
    assert 'aria-expanded="false"' in block and "onder Over ons" in block
    pages = re.findall(r'<a href="(/[a-z0-9-]+)" @click="sub = false"[^>]*>([^<]+)</a>', block)
    assert pages == [("/bestuur-2024h", "Het bestuur"), ("/geschiedenis-2024h", "Geschiedenis")], (
        "in the order set in the back office, by menu name; a page out of the menu is not there"
    )
    assert wide.count('href="/bestuur-2024h"') == 1, "a page under a section is not also on its own"

    drawer = _drawer(html)
    rows = re.findall(r'<a href="(/[a-z0-9-]+)" class="site-drawer-row( site-drawer-sub)?"', drawer)
    at = rows.index(("/over-ons-2024h", ""))
    assert rows[at + 1 : at + 3] == [
        ("/bestuur-2024h", " site-drawer-sub"),
        ("/geschiedenis-2024h", " site-drawer-sub"),
    ], "the drawer shows them always, indented under the section"


def test_an_offline_section_hides_its_pages_from_the_menu_only(client, db_session):
    section = _page(db_session, "over-ons-2024i", "Over ons", show_in_nav=True, is_published=False)
    _page(db_session, "bestuur-2024i", "Bestuur", parent_id=section.id, show_in_nav=True)

    html = client.get("/aanmelden").text
    assert "/bestuur-2024i" not in _wide_nav(html) and "/bestuur-2024i" not in _drawer(html)
    assert client.get("/bestuur-2024i").status_code == 200, "its address keeps working (3a)"


def test_a_menu_name_too_long_changes_nothing(db_session):
    """Review B4 of #2057: the length is checked before any field is set."""
    from app.domains.cms.service import MenuNameTooLong

    page = _page(db_session, "lang-2024j", "Lang")
    with pytest.raises(MenuNameTooLong):
        update_page(db_session, page.id, CmsPageUpdate(title="Nieuw", menu_label="x" * 81))
    assert page.title == "Lang", "the title was not set on a refused save"


def test_the_menu_name_is_written_in_the_pages_own_language(db_session):
    """Review B4 of #2057: a second translation keeps its own menu name."""
    from app.domains.cms.models import CmsPageTranslation

    page = _page(db_session, "taal-2024k", "Taal")
    db_session.add(CmsPageTranslation(page_id=page.id, language="en", title="Language"))
    db_session.commit()

    update_page(db_session, page.id, CmsPageUpdate(menu_label="Talen"))
    labels = {
        t.language: t.menu_label
        for t in db_session.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page.id)
    }
    assert labels == {"nl": "Talen", "en": None}, labels


def test_the_menu_switch_says_what_it_does_for_a_section(client, db_session):
    """#2060 (Koen, 16 October 2026, "2a"): the help line under "In het menu"."""
    page = _page(db_session, "hulp-2060", "Hulp")
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    editor = client.get(f"/admin/paginas/{page.id}").text
    at = editor.index('name="show_in_nav"')
    assert "Bij een sectie verdwijnen ook haar pagina" in editor[at - 2000 : at + 2000], (
        "the help line stands with the switch"
    )


def test_from_the_lists_menu_the_refusal_and_the_delete_answer_the_list(client, db_session):
    """#2172: Verwijderen in a row's ⋯ answers the list fragment — the reason on its
    banner for a section with pages under it, the list without the page otherwise."""
    section = _page(db_session, "over-ons-2172", "Over ons 2172")
    _page(db_session, "bestuur-2172", "Bestuur 2172", parent_id=section.id)
    loose = _page(db_session, "los-2172", "Los 2172")
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"}

    listed = client.get("/admin/paginas").text
    row = listed[listed.index(f'data-page="{loose.id}"') :]
    assert f'hx-post="/admin/paginas/{loose.id}/verwijderen"' in row[: row.index("</tr>")]

    refused = client.post(
        f"/admin/paginas/{section.id}/verwijderen", data={"from_list": "1"}, headers=headers
    )
    assert "HX-Retarget" not in refused.headers, "the list's own target, not the record"
    assert 'role="alert"' in refused.text and "Er staan nog pagina" in refused.text
    assert f'data-page="{section.id}"' in refused.text

    gone = client.post(
        f"/admin/paginas/{loose.id}/verwijderen", data={"from_list": "1"}, headers=headers
    )
    assert gone.status_code == 200 and f'data-page="{loose.id}"' not in gone.text
    db_session.expire_all()
    assert db_session.get(CmsPage, loose.id) is None
    assert db_session.get(CmsPage, section.id) is not None

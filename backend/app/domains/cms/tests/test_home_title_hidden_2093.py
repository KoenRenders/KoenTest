"""The home page's title is its one h1 and is not drawn; every other page shows its title (#2093).

CR-32 phase 5 made the home page a CMS page, and the template drew every page's title
above the body: the tenant's name, large, above the membership band. v2.16's home page
opened with the band. The title stays for screen readers and search engines (`sr-only`);
the browser measurement is `tests_e2e/pages/test_home_title_hidden_2093.py`.

Red before the change: the home page's h1 carried the visible class `text-3xl`.
"""

import re

import pytest

from app.domains.cms.api import CmsPage

pytestmark = pytest.mark.ui_serverrendered

_H1 = re.compile(r"<h1\b([^>]*)>(.*?)</h1>", re.S)


def _h1s(html: str) -> list[tuple[str, str]]:
    return [(attrs, " ".join(text.split())) for attrs, text in _H1.findall(html)]


def test_the_home_page_has_one_h1_and_it_is_screen_reader_only(client, db_session):
    assert db_session.query(CmsPage).filter(CmsPage.is_home.is_(True)).count(), "no home page"
    found = _h1s(client.get("/").text)

    assert len(found) == 1, f"the home page must have exactly one h1, found {found}"
    attrs, title = found[0]
    assert title, "the h1 of the home page is empty"
    assert "sr-only" in attrs and "text-3xl" not in attrs


def test_another_page_still_shows_its_title(client, db_session):
    page = CmsPage(title="Werking van de kring", slug="werking-2093", is_published=True)
    db_session.add(page)
    db_session.commit()
    own = [(a, t) for a, t in _h1s(client.get("/werking-2093").text) if t == page.title]

    assert len(own) == 1
    assert "text-3xl" in own[0][0] and "sr-only" not in own[0][0]

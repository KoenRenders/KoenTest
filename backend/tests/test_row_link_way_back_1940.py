"""The row link of Leden and Personen carries what the way back needs (#1940).

Both lists carried every field of the toolbar to the record (`?status=…&q=…&jaar=
&sort=…`, the empty ones too) because the list holder included the toolbar's form.
They follow the list Activiteiten now: one key, `terug`, and in it only what
differs from the list's own defaults — what `list_return` writes.

The browser tests of the same (`tests_e2e/members/test_row_link_carries_the_way_back.py`)
open a record from a second page and go back; these check the addresses and the
holder.

Broken on purpose: the `?terug=` taken off a row link → the first test of its list
fails; the `hx-include` put back on a list holder → the holder test fails.
"""

import re
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


@pytest.fixture
def households(db_session):
    """Two households without a membership: they stand under Opgezegd, and their
    persons in the list Personen under "In een gezin"."""
    families = [create_test_family(db_session, email=f"rijlink{n}@example.com") for n in (1, 2)]
    db_session.commit()
    return families


def _links(html: str, prefix: str) -> list[str]:
    return re.findall(rf'data-row-link[^>]*href="({re.escape(prefix)}[^"]*)"', html) or re.findall(
        rf'href="({re.escape(prefix)}[^"]*)"[^>]*data-row-link', html
    )


def _keys(href: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(href).query, keep_blank_values=True)


def test_a_leden_row_link_holds_only_the_way_back(client, households):
    _login(client)
    page = client.get("/admin/leden?status=opgezegd&q=Persoon&sort=-naam&per_page=25").text
    links = _links(page, "/admin/leden/gezin/")
    assert len(links) >= 2, "the households are not on the list"
    for href in links:
        keys = _keys(href)
        assert list(keys) == ["terug"], f"the row link holds more than the way back: {href}"
        way_back = urlsplit(unquote(keys["terug"][0]))
        assert way_back.path == "/admin/leden"
        assert parse_qs(way_back.query, keep_blank_values=True) == {
            "status": ["opgezegd"],
            "q": ["Persoon"],
            "sort": ["-naam"],
            "per_page": ["25"],
        }, "the way back holds what differs from the defaults, and nothing empty"


def test_what_equals_the_defaults_is_not_written_in_the_way_back(client, households):
    """Only the segment differs here: the sort, the page and the page size are the
    list's own, and stay out — a plain `/admin/leden?status=opgezegd`."""
    _login(client)
    page = client.get("/admin/leden?status=opgezegd&sort=naam&page=1&per_page=50").text
    links = _links(page, "/admin/leden/gezin/")
    assert len(links) >= 2, "the households are not on the list"
    for href in links:
        assert unquote(_keys(href)["terug"][0]) == "/admin/leden?status=opgezegd"


def test_a_personen_row_link_holds_only_the_way_back(client, households):
    _login(client)
    page = client.get("/admin/personen?zicht=in&q=Persoon&per_page=25").text
    links = _links(page, "/admin/leden/gezin/")
    assert len(links) >= 2, "the persons are not on the list"
    for href in links:
        keys = _keys(href)
        assert list(keys) == ["terug"], f"the row link holds more than the way back: {href}"
        way_back = urlsplit(unquote(keys["terug"][0]))
        assert way_back.path == "/admin/personen"
        assert parse_qs(way_back.query, keep_blank_values=True) == {
            "zicht": ["in"],
            "q": ["Persoon"],
            "per_page": ["25"],
        }


def test_the_record_leads_back_to_the_list_as_it_was_left(client, households):
    """The record reads `terug` and its way back is that address: the link of a row
    of each list takes you to a record whose first line returns to the list."""
    _login(client)
    for list_url, expected in (
        ("/admin/leden?status=opgezegd&q=Persoon&sort=-naam", "/admin/leden?"),
        ("/admin/personen?zicht=in&q=Persoon", "/admin/personen?"),
    ):
        href = _links(client.get(list_url).text, "/admin/leden/gezin/")[0]
        record = client.get(href).text
        way_back = re.search(r'data-way-back href="([^"]+)"', record).group(1)
        assert way_back.startswith(expected), way_back
        assert "q=Persoon" in way_back


@pytest.mark.parametrize("page_url", ["/admin/leden", "/admin/personen"])
def test_the_list_holder_includes_nothing(client, households, page_url):
    """Nothing inside the holder needs the toolbar's form: the pager and the
    column heads carry their own state, and the row link names the list in one key.
    Broken on purpose: `hx-include="#…-filter"` put back on the holder → red."""
    _login(client)
    assert "hx-include" not in client.get(page_url).text.split("<main", 1)[-1]

"""A page has a title and a slug — the page's own rule (CR-13 phase 4d, #1251).

The screen that makes a page (`POST /admin/paginas`) decided this itself: the
last rule of cms in a door. It is a rule about one field each, so it stands on
the page now (`CmsPage`, `@validates`, `docs/code-style.md` *A rule has one
home*) and holds for every writer; the screen gives the refusal its status.

**The screen answers as it did** — the first four tests pass before and after
the move, on purpose: the same status, the same sentence, nothing made, and the
page's rule still speaks before the lookup of the slug.

**What the refusal is measured at:** the answer of the route — a JSON 400 with
the sentence as its detail, before and after. On the screen that is NOT the
sentence: the page shows the general message for an answer it cannot place. The
browser's own `required` stops an empty field first; a title of spaces gets
through to it.

The last three tests are the rule itself, red before the move (a page of spaces
was simply made). Proven red: the validator's `raise` replaced by `pass` → eleven of
the thirteen cases fail (the two "as before" tests stay green).
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage, PageIncomplete, create_page, update_page
from app.schemas.cms import CmsPageCreate, CmsPageUpdate
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

RULE = "Titel en slug zijn verplicht."


@pytest.fixture
def headers(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _pages(db) -> int:
    db.expire_all()
    return db.query(CmsPage).count()


@pytest.mark.parametrize(
    ("title", "slug"),
    [("", "over-ons"), ("Over ons", ""), ("   ", "over-ons"), ("Over ons", "   ")],
)
def test_the_screen_refuses_a_page_without_a_title_or_a_slug(
    client, db_session, headers, title, slug
):
    before = _pages(db_session)

    answer = client.post("/admin/paginas", data={"title": title, "slug": slug}, headers=headers)

    assert (answer.status_code, answer.json()) == (400, {"detail": RULE})
    assert _pages(db_session) == before, "a refused page was made"


def test_the_pages_rule_speaks_before_the_lookup_of_the_slug(client, db_session, headers):
    made = client.post(
        "/admin/paginas", data={"title": "Over ons", "slug": "over-ons"}, headers=headers
    )
    assert made.status_code == 204, made.text

    answer = client.post("/admin/paginas", data={"title": " ", "slug": "over-ons"}, headers=headers)
    taken = client.post(
        "/admin/paginas", data={"title": "Nog een", "slug": "over-ons"}, headers=headers
    )

    assert answer.json() == {"detail": RULE}
    assert taken.json() == {"detail": "Die slug bestaat al."}


def test_a_page_is_made_as_before(client, db_session, headers):
    answer = client.post(
        "/admin/paginas", data={"title": " Contact ", "slug": " Contact "}, headers=headers
    )

    assert answer.status_code == 204, answer.text
    page = db_session.query(CmsPage).filter(CmsPage.slug == "contact").one()
    assert page.title == "Contact"
    assert answer.headers["HX-Redirect"] == f"/admin/paginas/{page.id}"


def test_the_editor_keeps_a_title_that_is_sent_empty_as_before(client, db_session, headers):
    """The editor's save leaves out a field that is sent empty — the page keeps
    what it had. Not a refusal, before or after."""
    client.post("/admin/paginas", data={"title": "Over ons", "slug": "over-ons"}, headers=headers)
    page = db_session.query(CmsPage).filter(CmsPage.slug == "over-ons").one()

    answer = client.post(
        f"/admin/paginas/{page.id}", data={"title": "", "slug": "", "content": ""}, headers=headers
    )

    assert answer.status_code == 200, answer.text
    db_session.expire_all()
    assert (page.title, page.slug) == ("Over ons", "over-ons")


# ── the rule itself, for every writer ────────────────────────────────────────


@pytest.mark.parametrize(("title", "slug"), [("", "x"), ("  ", "x"), ("X", ""), ("X", " ")])
def test_the_service_refuses_it_past_the_screen(db_session, title, slug):
    before = _pages(db_session)

    with pytest.raises(PageIncomplete) as refusal:
        create_page(db_session, CmsPageCreate(title=title, slug=slug))

    assert str(refusal.value) == RULE
    assert _pages(db_session) == before


def test_a_page_cannot_lose_its_title_through_the_service(db_session):
    page = create_page(db_session, CmsPageCreate(title="Over ons", slug="over-ons"))

    with pytest.raises(PageIncomplete):
        update_page(db_session, page.id, CmsPageUpdate(title=" "))

    assert page.title == "Over ons"


def test_the_page_itself_refuses_it():
    with pytest.raises(PageIncomplete):
        CmsPage(title="Over ons", slug="")
    with pytest.raises(PageIncomplete):
        CmsPage(title=None, slug="over-ons")

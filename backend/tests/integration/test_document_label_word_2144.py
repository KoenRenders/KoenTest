"""#2144 — a document without its own label shows its kind's word, never the code.

A document that is neither an activity's poster nor a component's info was named
by its media kind's code on the AI-context list and record ("activity_poster").
It now falls back to its own title, else to the kind's word from the code list;
the list and the record read the same function.

Proven red (put back): the fallback made `code_of(asset.kind)` again → the first
test finds "activity_poster" on both screens.
"""

import re

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.models import MediaAsset
from app.kernel.codes import code_label
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def admin(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    client.headers["X-CSRF-Token"] = csrf_token_for(value)
    return client


def _poster(db, *, title=None, activity_id=None) -> int:
    asset = MediaAsset(
        kind="activity_poster",
        title=title,
        activity_id=activity_id,
        data=b"x",
        content_type="application/pdf",
    )
    db.add(asset)
    db.commit()
    return asset.id


def _names(html: str) -> list[str]:
    return [n.strip() for n in re.findall(r"<a [^>]*data-row-link[^>]*>([^<]+)</a>", html)]


def test_a_document_without_a_label_or_title_shows_its_kind_s_word(admin, db_session):
    asset_id = _poster(db_session)
    word = code_label("media_kind", "activity_poster")
    assert word and word != "activity_poster", "the code list has a word for the kind"

    listed = admin.get("/admin/ai-context").text
    assert word in _names(listed)
    assert "activity_poster" not in _names(listed)

    record = admin.get(f"/admin/ai-context/documenten/{asset_id}").text
    title = re.search(r"<h1[^>]*>([^<]+)</h1>", record).group(1).strip()
    assert title == word


def test_a_document_with_a_title_shows_its_title(admin, db_session):
    _poster(db_session, title="Huishoudelijk reglement")
    assert "Huishoudelijk reglement" in _names(admin.get("/admin/ai-context").text)


def test_an_activity_s_poster_keeps_its_label(admin, db_session):
    activity = Activity(name="Kaartavond", location="Miloheem")
    db_session.add(activity)
    db_session.flush()
    _poster(db_session, title="affiche.pdf", activity_id=activity.id)
    assert "Kaartavond — poster" in _names(admin.get("/admin/ai-context").text)


def test_a_component_s_info_keeps_its_label(admin, db_session):
    from tests.conftest import seed_activity_with_product

    activity, component, _product = seed_activity_with_product(db_session)
    db_session.add(
        MediaAsset(
            kind="component_info",
            component_id=component.id,
            data=b"x",
            content_type="application/pdf",
        )
    )
    db_session.commit()
    expected = f"{activity.name} — {component.name} (info)"
    assert expected in _names(admin.get("/admin/ai-context").text)

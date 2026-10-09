"""The media upload says why it refuses a post without a file (#1831).

The upload page (`admin_media_nieuw.html`) already answers what the service
refuses the way a page with one form does: the page again, the reason in the
banner above the form. One refusal never got that far: the route itself required
the file, so a post without one was answered by the framework with a bare JSON
422 — and the page showed the kit's general message, "Er ging iets mis; …
Probeer opnieuw.", for something no retry mends.

Two shapes reach the door without a file: no `files` field at all, and — what a
browser sends for a file input nobody filled — a `files` part with an empty
name. Both get the service's own sentence now, in the page's banner.

Read as the browser gets it: an HTML answer htmx swaps (a 200 — this form
targets `body`), with the sentence in the banner, and nothing stored.

Red proof: the route's `files` back to `File(...)` → the first case fails on the
bare 422.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.api import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL

NO_FILE = "Geen bestanden"
GENERAL = "Er ging iets mis"


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _banner(html: str) -> str:
    found = re.search(r'<div class="[^"]*bg-red-50[^"]*" role="alert">(.*?)</div>', html, re.S)
    assert found, "the answer carries no banner"
    return found.group(1).strip()


@pytest.mark.parametrize(
    "files",
    [None, {"files": ("", b"", "application/octet-stream")}],
    ids=["no files field", "an empty file field, as a browser sends it"],
)
def test_an_upload_without_a_file_says_so_in_the_pages_banner(client, db_session, files):
    headers = _board(client)
    before = db_session.query(MediaAsset).count()

    answer = client.post("/admin/media", data={"kind": "sponsor"}, files=files, headers=headers)

    # What htmx swaps into the page: HTML, not the framework's JSON.
    assert answer.status_code == 200, answer.text[:200]
    assert answer.headers["content-type"].startswith("text/html")
    assert _banner(answer.text) == NO_FILE
    # The page is the upload form again, with the kind that was chosen.
    assert 'hx-post="/admin/media"' in answer.text
    assert GENERAL not in _banner(answer.text)
    db_session.expire_all()
    assert db_session.query(MediaAsset).count() == before

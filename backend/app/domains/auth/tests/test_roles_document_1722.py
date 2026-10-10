"""CR-24 F4, T7 — `docs/rollen-en-rechten.md` is what the bundles and the gates say.

The document is rendered (`app.domains.auth.docs`), never written: it drifted for
months while it was kept by hand beside the gates. The first test holds the file
on disk against a fresh rendering; the second shows that the rendering really
reads the bundles — a document that printed a fixed text would pass the first
one for ever.

Proven red: a tick removed by hand from the file on disk → the first test names
the command that renders it again.
"""

from __future__ import annotations

import pytest

from app.domains.auth.docs import DOC_PATH, render
from app.domains.auth.models import Right, Role, RoleRight

pytestmark = pytest.mark.ui_agnostisch


def test_roles_document_matches_the_bundles(db_session):
    assert DOC_PATH.exists(), f"{DOC_PATH.name} does not exist"
    assert DOC_PATH.read_text(encoding="utf-8") == render(db_session), (
        "docs/rollen-en-rechten.md no longer says what the bundles and the gates say. "
        "Run: python -m app.domains.auth.docs"
    )


def _row(document: str, right: Right) -> str:
    return next(line for line in document.splitlines() if line.startswith(f"| `{right.value}` |"))


def test_the_document_follows_a_bundle(db_session):
    """A right added to a role's bundle is a tick more in that right's row."""
    before = render(db_session)
    db_session.add(RoleRight(role_code=Role.FINANCE, right_code=Right.PAGE_VIEW))
    db_session.flush()
    after = render(db_session)
    assert _row(after, Right.PAGE_VIEW).count("✓") == _row(before, Right.PAGE_VIEW).count("✓") + 1
    assert _row(after, Right.PAGE_MANAGE) == _row(before, Right.PAGE_MANAGE)

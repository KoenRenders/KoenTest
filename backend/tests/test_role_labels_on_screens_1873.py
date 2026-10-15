"""#1873: the profile and the overview of every workspace show a role by its
label ("Beheerder"), not by its stored code ("ADMIN"), from the same code list
Gebruikers reads (`code_label("role", …)`). One case per screen, on the rendered
screen: the label is there and the code stands nowhere as text.

Broken on purpose (14 October 2026, each put back): the `| code_label("role")` taken
off the badge of `admin_profiel.html` -> the profile case fails on ">ADMIN<";
taken off the cell of `admin_gebruikers_overzicht.html` -> the overview case fails.
"""

from __future__ import annotations

import re

import pytest

from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.test_users_per_workspace import _as, _user

pytestmark = pytest.mark.ui_serverrendered


def _visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_the_profile_shows_the_label_of_a_role(client, platform_workspace, db_session):
    email = _user(
        db_session,
        "profile-1873@example.com",
        ("ADMIN", TENANT_MILLEGEM_ID),
        ("FINANCE", TENANT_MILLEGEM_ID),
        ("OPERATOR", None),
    )
    _as(client, email)

    text = _visible_text(client.get("/admin/profiel").text)

    for label in ("Beheerder", "Boekhouding"):
        assert label in text, label
    for code in ("ADMIN", "FINANCE", "OPERATOR"):
        assert not re.search(rf"\b{code}\b", text), f"the stored code {code} is shown"


def test_the_overview_shows_the_label_of_a_role(client, platform_workspace, db_session):
    _user(db_session, "someone-1873@example.com", ("FINANCE", TENANT_MILLEGEM_ID))
    operator = _user(db_session, "operator-1873@example.com", ("OPERATOR", None))
    _as(client, operator)

    text = _visible_text(client.get("/admin/gebruikers/alle-werkruimtes").text)

    assert "Boekhouding" in text
    for code in ("ADMIN", "FINANCE", "OPERATOR", "MASTERDATA"):
        assert not re.search(rf"\b{code}\b", text), f"the stored code {code} is shown"

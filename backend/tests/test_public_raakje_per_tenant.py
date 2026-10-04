"""#1568 — Raakje on the public site is a tenant's own switch, apart from the back office.

Measured before the build: per tenant there was one setting for the back office
(`admin_chat_enabled`, a text field that took "1") and none for the public site
— the bell followed the Assistent module as a whole, so a tenant could not switch
the public Raakje off without losing the back-office one.

Now there is a second setting, `public_chat_enabled`, read by one rule
(`kernel.tenant_config.tenant_public_chat_enabled`) that the site shell and the
public chat endpoints both ask: a tenant that switched it off shows no bell and
its endpoints refuse. On is the default, so an existing tenant keeps its bell
without anyone saving anything. Both settings are a switch in the Assistent card.

Proven red. Against master `e9926d5f` this module does not import: there is no
`tenant_public_chat_enabled`. On this branch, each rule broken on its own: the
endpoints reading the environment switch alone → the "public off" test fails on
the endpoint while the bell is gone; the site shell following the module alone
→ the same test fails on the bell; the default turned to off → the
"existing tenant" test fails; the hidden field taken out of `ui.switch` → the
editor test fails on the markup (its first version only posted what a browser
would send and stayed green; the browser itself is in
`tests_e2e/test_raakje_switches.py`).
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from app.kernel.tenant_config import (
    get_setting,
    set_setting,
    switch_is_on,
    tenant_admin_chat_enabled,
    tenant_public_chat_enabled,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

BELL = 'id="raakje-widget-gesprek"'
CHAT = {"messages": [{"role": "user", "content": "Wat is Raak?"}]}


@pytest.fixture
def chat_on(monkeypatch):
    """Both environment switches on, so only the tenant's own decide."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")


def _set(db, **values) -> None:
    for key, value in values.items():
        set_setting(db, key, value, tenant_id=TENANT_MILLEGEM_ID)
    db.commit()


def test_an_existing_tenant_keeps_its_bell_without_saving_anything(client, db_session, chat_on):
    assert get_setting(db_session, "public_chat_enabled", tenant_id=TENANT_MILLEGEM_ID) is None
    assert tenant_public_chat_enabled(db_session, TENANT_MILLEGEM_ID) is True
    assert BELL in client.get("/").text


def test_public_off_hides_the_bell_and_refuses_while_the_back_office_works(
    client, db_session, chat_on
):
    _set(db_session, public_chat_enabled="0", admin_chat_enabled="1")

    assert BELL not in client.get("/").text
    assert client.post("/raakje/vraag", data={"vraag": "Wat is Raak?"}).status_code == 404
    assert client.post("/api/v1/chat", json=CHAT).status_code == 404
    assert tenant_public_chat_enabled(db_session, TENANT_MILLEGEM_ID) is False
    # The back office is its own switch.
    assert tenant_admin_chat_enabled(db_session, TENANT_MILLEGEM_ID) is True


def test_back_office_off_leaves_the_public_raakje_on(client, db_session, chat_on):
    _set(db_session, public_chat_enabled="1", admin_chat_enabled="")

    assert BELL in client.get("/").text
    answer = client.post("/raakje/vraag", data={"vraag": "Wat is Raak?"})
    assert answer.status_code == 200 and "data-raakje-answer" in answer.text
    assert tenant_admin_chat_enabled(db_session, TENANT_MILLEGEM_ID) is False


def test_the_environment_switch_still_wins(client, db_session, monkeypatch):
    """Two switches in a row: with `CHAT_ENABLED` off, the tenant's "on" shows no
    bell and the endpoint refuses."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", False)
    _set(db_session, public_chat_enabled="1")

    assert BELL not in client.get("/").text
    assert client.post("/raakje/vraag", data={"vraag": "Wat is Raak?"}).status_code == 404


@pytest.mark.parametrize(
    "key, value, on",
    [
        ("public_chat_enabled", None, True),
        ("public_chat_enabled", "", True),
        ("public_chat_enabled", "1", True),
        ("public_chat_enabled", "0", False),
        ("admin_chat_enabled", None, False),
        ("admin_chat_enabled", "", False),
        ("admin_chat_enabled", "1", True),
        ("admin_chat_enabled", "0", False),
    ],
)
def test_what_on_means_per_setting(key, value, on):
    assert switch_is_on(key, value) is on


# ── the Assistent card of the tenant editor ──────────────────────────────────


def _operator(client, db) -> str:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _switches(html: str) -> dict[str, bool]:
    """The switches on the screen: setting → ticked."""
    found = re.findall(r'<input type="checkbox" role="switch" name="(\w+)"([^>]*)>', html)
    return {name: " checked" in rest for name, rest in found}


def test_the_assistent_card_holds_two_switches_that_save_independently(
    client, platform_workspace, db_session
):
    csrf = _operator(client, db_session)
    editor = f"/admin/tenants/{TENANT_MILLEGEM_ID}"
    _set(db_session, admin_chat_enabled="")

    html = client.get(editor).text
    card = html[html.index('data-card="chatbot"') :]
    card = card[: card.index("</section>")]
    assert _switches(card) == {"admin_chat_enabled": False, "public_chat_enabled": True}
    for label in ("Raakje in de backoffice", "Raakje op de publieke site"):
        assert label in card
    assert "ADMIN_CHAT_ENABLED" in card and "CHAT_ENABLED" in card, "the help names the switch"
    assert '<input name="admin_chat_enabled"' not in card, (
        "the text field that took '1' is still there"
    )

    # An unticked checkbox sends nothing, so each switch carries a hidden field
    # with its off value first — or "off" could never be saved.
    for key, off in (("public_chat_enabled", "0"), ("admin_chat_enabled", "")):
        assert re.search(
            rf'<input type="hidden" name="{key}" value="{off}">\s*'
            rf'<input type="checkbox" role="switch" name="{key}"',
            card,
        ), f"{key}: no hidden off value before the switch"

    # What a browser sends: the hidden field always, the checkbox when ticked.
    # Public off, back office on.
    saved = client.post(
        editor,
        data={"public_chat_enabled": ["0"], "admin_chat_enabled": ["", "1"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200, saved.text[-300:]
    db_session.expire_all()
    assert get_setting(db_session, "public_chat_enabled", tenant_id=TENANT_MILLEGEM_ID) == "0"
    assert get_setting(db_session, "admin_chat_enabled", tenant_id=TENANT_MILLEGEM_ID) == "1"
    assert _switches(client.get(editor).text) == {
        "admin_chat_enabled": True,
        "public_chat_enabled": False,
    }

    # And the reverse.
    client.post(
        editor,
        data={"public_chat_enabled": ["0", "1"], "admin_chat_enabled": [""]},
        headers={"X-CSRF-Token": csrf},
    )
    db_session.expire_all()
    assert get_setting(db_session, "public_chat_enabled", tenant_id=TENANT_MILLEGEM_ID) == "1"
    assert not get_setting(db_session, "admin_chat_enabled", tenant_id=TENANT_MILLEGEM_ID)


def test_the_tenants_own_settings_show_the_same_two_switches(client, db_session):
    """#1535: the tenant's own Instellingen is the same editor."""
    _operator(client, db_session)
    html = client.get("/admin/instellingen").text
    assert _switches(html) == {"admin_chat_enabled": False, "public_chat_enabled": True}

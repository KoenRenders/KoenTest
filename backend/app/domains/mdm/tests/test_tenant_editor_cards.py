"""CR-19 #1498 — the tenant editor: one card per module, the checkbox in its
header, and one Opslaan for modules and settings together.

- Every setting renders in exactly one card, and that card is its owner's in the
  registry (`owner_of("tenant_settings", key)`), or "Site" when no module owns it.
  A gate: a registry key without a field, or a field in no card, fails.
- One POST saves a module change and a setting change; a refused dependency
  saves neither.
- Switching a module off and saving keeps its settings: the rows are counted.
- A platform gets no membership card (#854) and keeps its membership state.

Proven red against master `95c3e1a7`: six of the seven fail (no `data-card`,
no module set on the settings route). The registry half of the gate is green on
master and proven additively: a key `probe_1498_setting` added to the chatbot's
`tenant_settings` makes it fail. Writing (and committing) the settings before
the module check fails the refusal test; dropping the platform's hidden
membership input fails the platform test.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.mdm.api import TenantKind, create_tenant, enabled_modules, platform_tenant_id
from app.kernel.modules import MODULES, owner_of
from app.kernel.tenant_config import TenantSetting, get_setting, set_setting
from app.ui.tenants_ui import BEKENDE_SLEUTELS, GEHEIME_SLEUTELS
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EVERY_KEY = [k for k, _l, _h in (*BEKENDE_SLEUTELS, *GEHEIME_SLEUTELS)]
ALL_MODULES = sorted(m.code.value for m in MODULES)


def _operator(client, db_session) -> dict:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _cards(html: str) -> dict[str, str]:
    """Each card's markup by its `data-card` (a module code, or "site")."""
    found = dict(re.findall(r'<section[^>]*data-card="([^"]+)"(.*?)</section>', html, re.S))
    assert found, "no card at all — did the editor change shape?"
    return found


def _form(page_html: str) -> dict:
    """What the browser would send: every text field with its value, and the
    ticked module checkboxes."""
    data: dict = {"modules_shown": "1"}
    for name, value in re.findall(r'<input name="(\w+)" id="\w+" value="([^"]*)"', page_html):
        data[name] = value
    data["modules"] = re.findall(
        r'<input type="checkbox" name="modules" value="(\w+)"[^>]*checked', page_html
    ) + re.findall(r'<input type="hidden" name="modules" value="(\w+)">', page_html)
    return data


def test_every_setting_sits_in_exactly_its_owners_card(client, platform_workspace, db_session):
    _operator(client, db_session)
    tenant = create_tenant(db_session, name="Kaartenclub", code="kaarten-1498")
    cards = _cards(client.get(f"/admin/tenants/{tenant.id}").text)

    assert set(cards) == {"site", *ALL_MODULES}, "one card per module, plus Site"
    for key in EVERY_KEY:
        holding = [card for card, body in cards.items() if f'name="{key}"' in body]
        owner = owner_of("tenant_settings", key)
        assert holding == [owner.value if owner else "site"], (key, holding)


def test_every_registry_setting_has_a_field():
    """The other half of the gate: a key the registry gives a module but the
    editor has no field for would never be shown."""
    owned = {key for m in MODULES for key in m.tenant_settings}
    assert owned, "the registry owns no setting — did the walk break?"
    assert not owned - set(EVERY_KEY), owned - set(EVERY_KEY)


def test_the_assistant_card_uses_the_house_word(client, platform_workspace, db_session):
    _operator(client, db_session)
    tenant = create_tenant(db_session, name="Woordclub", code="woord-1498")
    card = _cards(client.get(f"/admin/tenants/{tenant.id}").text)["chatbot"]
    assert ">Assistent</span>" in card and "Raakje" not in card.split("</label>")[0]


def test_one_save_writes_a_module_and_a_setting_together(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    tenant = create_tenant(
        db_session, name="Bakkerij", code="bakkerij-1498", kind=TenantKind.COMPANY
    )
    data = _form(client.get(f"/admin/tenants/{tenant.id}").text)
    data["modules"] = [*data["modules"], "newsletter"]
    data["tagline"] = "Brood en banket"

    answer = client.post(f"/admin/tenants/{tenant.id}", data=data, headers=headers)

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    assert "newsletter" in enabled_modules(tenant.id, db=db_session)
    assert get_setting(db_session, "tagline", tenant_id=tenant.id) == "Brood en banket"


def test_a_refused_dependency_saves_nothing(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    tenant = create_tenant(db_session, name="Garage", code="garage-1498", kind=TenantKind.COMPANY)
    before = enabled_modules(tenant.id, db=db_session)
    data = _form(client.get(f"/admin/tenants/{tenant.id}").text)
    data["modules"] = [*data["modules"], "designstudio"]  # needs activities, which is off
    data["tagline"] = "Niet bewaard"

    answer = client.post(f"/admin/tenants/{tenant.id}", data=data, headers=headers)

    assert answer.status_code == 422
    card = _cards(answer.text)["designstudio"]
    assert "Design Studio heeft Activiteiten nodig." in card, "on the card concerned"
    db_session.expire_all()
    assert enabled_modules(tenant.id, db=db_session) == before
    assert get_setting(db_session, "tagline", tenant_id=tenant.id) in (None, "")


def test_switching_a_module_off_keeps_its_settings(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    tenant = create_tenant(db_session, name="Turnclub", code="turn-1498")
    set_setting(db_session, "membership_price_full", "40.00", tenant_id=tenant.id)
    set_setting(db_session, "max_item_quantity", "12", tenant_id=tenant.id)
    db_session.commit()

    def rows() -> int:
        """The settings that hold a value (an empty field is stored as NULL)."""
        return (
            db_session.query(TenantSetting)
            .filter(TenantSetting.tenant_id == tenant.id, TenantSetting.value.isnot(None))
            .execution_options(include_all_tenants=True)
            .count()
        )

    before = rows()
    data = _form(client.get(f"/admin/tenants/{tenant.id}").text)
    data["modules"] = [m for m in data["modules"] if m not in ("membership", "payment")]

    answer = client.post(f"/admin/tenants/{tenant.id}", data=data, headers=headers)

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    assert "membership" not in enabled_modules(tenant.id, db=db_session)
    assert rows() == before
    assert get_setting(db_session, "membership_price_full", tenant_id=tenant.id) == "40.00"


def test_a_platform_has_no_membership_card_and_keeps_its_state(
    client, platform_workspace, db_session
):
    headers = _operator(client, db_session)
    platform = platform_tenant_id(db_session)
    if platform is None:
        pytest.skip("no platform tenant in this database")
    html = client.get(f"/admin/tenants/{platform}").text
    assert "membership" not in _cards(html)
    before = "membership" in enabled_modules(platform, db=db_session)

    client.post(f"/admin/tenants/{platform}", data=_form(html), headers=headers)

    db_session.expire_all()
    assert ("membership" in enabled_modules(platform, db=db_session)) == before

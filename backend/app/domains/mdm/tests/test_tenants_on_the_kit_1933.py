"""Tenants on the kit (#1933; end state §5.1, §5.2; CR-11 Q99).

The list is the kit's table; a tenant is a record that is read first, with the
cards Tenant, Site and one per module, and one save for all of them. Held here
on what the pages carry and on what is stored:

- **every setting stands in both modes**: a fact in read mode, a field in the
  same card in edit mode — none of the editor's settings got lost on the way;
- **a secret is never shown**: typed into a field without a value, read as
  "gezet" or "niet gezet", left alone by an empty field, cleared by its switch;
- **the choices that were text fields** store what they stored: Mail-modus
  `send` / `log_only`, Niet indexeren `1` or nothing;
- **the modules**: a switch per card for the operator, a badge for the tenant's
  own Instellingen, which has no Tenant card either;
- **no Deactiveren** (Koen, 13 October 2026: "1c"): the record shows the status.

Broken on purpose (13 October 2026, each put back):
- `_setting_field`: the `mail_mode` branch out → the select has no options
  ("assert [] == ['send', 'log_only']") and the answer does not read "Alleen
  loggen";
- the secret's `value=""` made its placeholder text → "a secret's field carries
  a value", in the operator's record and in the own Instellingen;
- `_save`: the filter on empty module values out → "the switches' empty values
  were read as modules" (a 422);
- the Tenant card left out for the operator → "no field kind", and the type,
  the account and the card itself are missed in both modes.
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
from app.domains.mdm.api import enabled_modules
from app.kernel.modules import MODULES
from app.kernel.tenant_config import get_setting
from app.ui.tenants_ui import BEKENDE_SLEUTELS, GEHEIME_SLEUTELS
from tests._sites import new_site
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SETTINGS = [key for key, _label, _help in BEKENDE_SLEUTELS]
SECRETS = [key for key, _label, _help in GEHEIME_SLEUTELS]
ALL_MODULES = sorted(m.code.value for m in MODULES)


def _operator(client, db) -> dict:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _main(html: str) -> str:
    start = html.index("<main")
    return html[start : html.index("</main>", start)]


def _cards(html: str) -> dict[str, str]:
    return dict(re.findall(r'<section[^>]*data-card="([^"]+)"(.*?)</section>', html, re.S))


# ── the list ────────────────────────────────────────────────────────────────


def test_the_list_is_the_kits_table_with_its_five_columns(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    unit = new_site(db_session, name="Lijstclub", code="lijst-1933")
    db_session.commit()

    page = client.get("/admin/tenants").text

    heads = re.findall(r'<th scope="col" data-cell="([a-z]+)"', page)
    assert heads == ["name", "context", "extra", "extra", "status"]
    for word in ("Tenant", "Type", "Account", "Organisatie achter de site", "Status"):
        assert word in page[page.index("<thead") : page.index("</thead>")]
    row = page[page.index(f'data-tenant="{unit.id}"') :]
    row = row[: row.index("</tr>")]
    assert ">/lijst-1933</small>" in row and "Inactief" not in row, "an active tenant is quiet"
    assert "data-toolbar" in page and "Nieuwe tenant" in page
    assert "Deactiveren" not in page and "Activeren" not in page
    fragment = client.get("/admin/tenants", headers=headers).text
    assert "<html" not in fragment and f'data-tenant="{unit.id}"' in fragment


def test_the_segments_filter_on_active_and_count(client, platform_workspace, db_session):
    _operator(client, db_session)
    quiet = new_site(db_session, name="Slapende club", code="slaapt-1933")
    awake = new_site(db_session, name="Wakkere club", code="wakker-1933")
    quiet.is_active = False
    db_session.commit()

    def shown(query: str) -> tuple[bool, bool]:
        html = client.get("/admin/tenants" + query).text
        return f'data-tenant="{quiet.id}"' in html, f'data-tenant="{awake.id}"' in html

    assert shown("") == (True, True)
    assert shown("?status=actief") == (False, True)
    assert shown("?status=inactief") == (True, False)
    page = client.get("/admin/tenants").text
    row = page[page.index(f'data-tenant="{quiet.id}"') :]
    assert "Inactief" in row[: row.index("</tr>")], "an inactive tenant carries its badge"
    assert re.search(r'id="tn-filter-n-inactief"[^>]*>\(1\)<', page), "the segment's count"


# ── the record ──────────────────────────────────────────────────────────────


def test_every_setting_stands_in_both_modes(client, platform_workspace, db_session):
    _operator(client, db_session)
    unit = new_site(db_session, name="Volledige club", code="volledig-1933")
    db_session.commit()

    read = _main(client.get(f"/admin/tenants/{unit.id}").text)
    editing = _main(client.get(f"/admin/tenants/{unit.id}?bewerken=1").text)

    assert 'data-mode="read"' in read and 'data-mode="edit"' in editing
    assert "<input" not in read.replace('type="hidden"', ""), "read mode carries a field"
    for key in [*SETTINGS, "site_name", "kind", "account_id"]:
        assert f'data-setting="{key}"' in read, f"{key} is not read"
        assert f'name="{key}"' in editing, f"{key} cannot be edited"
    for key in SECRETS:
        assert f'data-secret="{key}"' in read, f"{key}: not said whether it is set"
        assert f'name="{key}"' in editing and f'name="{key}_wissen"' in editing
    assert set(_cards(read)) == {"site", *ALL_MODULES} == set(_cards(editing))
    assert "data-tenant-kind" in read, "the operator's record has no Tenant card"
    assert read.count("data-action-bar") == 0 and editing.count("data-action-bar") == 1
    assert re.search(r">\s*Bewerken\s*<", read), "the primary of the record"
    # The help under "Organisatie achter de site" says "gegevens" since every
    # tenant has an account (CR-20 F1); every other mention is gone.
    help_text = "De organisatie waarvan de site de gegevens toont."
    for gone in ("gegevens", "Deactiveren", "Activeren"):
        assert gone not in read and gone not in editing.replace(help_text, ""), gone
    assert "Modules aan" in read and "data-summary-card" in read


def test_the_fields_have_the_shape_the_issue_asks(client, platform_workspace, db_session):
    _operator(client, db_session)
    unit = new_site(db_session, name="Vormclub", code="vorm-1933")
    db_session.commit()
    editing = _main(client.get(f"/admin/tenants/{unit.id}?bewerken=1").text)

    def opening(key: str) -> str:
        found = re.search(rf'<div data-field="{key}"[^>]*>', editing)
        assert found, f"no field {key}"
        return found.group(0)

    for colour in ("site_header_color", "site_brand_color", "site_accent_color"):
        assert 'data-kind="color"' in opening(colour) and 'data-span="quarter"' in opening(colour)
    assert 'data-kind="select"' in opening("mail_mode"), "Mail-modus is no select"
    choice = editing[editing.index('name="mail_mode"') :]
    assert re.findall(r'<option value="(\w+)"', choice[: choice.index("</select>")]) == [
        "send",
        "log_only",
    ]
    assert 'data-kind="switch"' in opening("noindex"), "Niet indexeren is no switch"
    assert re.search(
        r'<input type="hidden" name="noindex" value="">\s*<input type="checkbox"', editing
    )
    for half in ("max_item_quantity", "max_registrations_per_email"):
        assert 'data-span="half"' in opening(half), f"{half}: its label would break"
    for quarter in ("language", "membership_price_full", "payment_term_days"):
        assert 'data-span="quarter"' in opening(quarter), quarter
    assert 'data-kind="select"' in opening("kind"), "Type is no select"


def test_the_choices_store_what_the_text_fields_stored(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    unit = new_site(db_session, name="Keuzeclub", code="keuze-1933")
    db_session.commit()

    saved = client.post(
        f"/admin/tenants/{unit.id}",
        data={"tagline": "Samen sterk", "mail_mode": "log_only", "noindex": ["", "1"]},
        headers=headers,
    )

    assert saved.status_code == 200, saved.text[-300:]
    assert saved.headers.get("HX-Push-Url") == f"/admin/tenants/{unit.id}"
    answer = _main(saved.text)
    assert 'data-mode="read"' in answer, "the save does not come back in read mode"
    assert "Alleen loggen" in answer and "Samen sterk" in answer
    db_session.expire_all()
    assert get_setting(db_session, "mail_mode", tenant_id=unit.id) == "log_only"
    assert get_setting(db_session, "noindex", tenant_id=unit.id) == "1"

    client.post(f"/admin/tenants/{unit.id}", data={"noindex": [""]}, headers=headers)
    db_session.expire_all()
    assert not get_setting(db_session, "noindex", tenant_id=unit.id), "off is not saved"


def test_a_secret_is_typed_and_never_shown(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    unit = new_site(db_session, name="Geheime club", code="geheim-1933")
    db_session.commit()
    url = f"/admin/tenants/{unit.id}"
    secret = "test_sleutel_1933"

    def said(html: str) -> str:
        fact = html[html.index('data-secret="mollie_api_key"') :]
        return re.sub(r"<[^>]+>", " ", fact[: fact.index("</p>")])

    assert "niet gezet" in said(client.get(url).text)
    saved = client.post(url, data={"mollie_api_key": secret}, headers=headers).text
    assert secret not in saved and "gezet" in said(saved) and "niet gezet" not in said(saved)

    editing = client.get(url + "?bewerken=1").text
    assert secret not in editing
    tag = re.search(r'<input\b[^>]*name="mollie_api_key"[^>]*>', editing).group(0)
    assert 'type="password"' in tag and "value=" not in tag, "a secret's field carries a value"

    # An empty field leaves the stored secret; its switch clears it.
    client.post(url, data={"mollie_api_key": "", "mollie_api_key_wissen": [""]}, headers=headers)
    assert "niet gezet" not in said(client.get(url).text), "an empty field wiped the secret"
    client.post(
        url, data={"mollie_api_key": "", "mollie_api_key_wissen": ["", "1"]}, headers=headers
    )
    assert "niet gezet" in said(client.get(url).text), "the switch did not clear the secret"


def test_the_module_switches_save_the_set_they_show(client, platform_workspace, db_session):
    headers = _operator(client, db_session)
    unit = new_site(db_session, name="Moduleclub", code="module-1933")
    db_session.commit()
    before = enabled_modules(unit.id, db=db_session)
    editing = client.get(f"/admin/tenants/{unit.id}?bewerken=1").text

    switches = re.findall(
        r'<input type="hidden" name="modules" value="">\s*'
        r'<input type="checkbox" role="switch" name="modules" id="[\w-]+" value="(\w+)"',
        editing,
    )
    assert sorted(switches) == ALL_MODULES, "one switch per module, each with its off value first"

    # What a browser sends: the empty value of every switch, and the code of the
    # ones that are on.
    sent = [""] * len(ALL_MODULES) + sorted(before)
    saved = client.post(
        f"/admin/tenants/{unit.id}", data={"modules_shown": "1", "modules": sent}, headers=headers
    )
    assert saved.status_code == 200, "the switches' empty values were read as modules"
    db_session.expire_all()
    assert enabled_modules(unit.id, db=db_session) == before


def test_the_tenants_own_settings_have_no_tenant_card_and_no_switches(client, db_session):
    """#1535: the tenant workspace's own Instellingen is the same record without
    what is platform administration."""
    _operator(client, db_session)

    for url in ("/admin/instellingen", "/admin/instellingen?bewerken=1"):
        page = _main(client.get(url).text)
        assert "data-tenant-kind" not in page, "the own record carries the Tenant card"
        assert 'name="modules"' not in page and 'name="kind"' not in page
        assert set(_cards(page)) >= {"site", "activities"}
        assert re.search(r'data-card="activities".*?data-badge', page, re.S), (
            "a module's state is not said"
        )
    editing = _main(client.get("/admin/instellingen?bewerken=1").text)
    assert 'hx-post="/admin/instellingen"' in editing and 'name="tagline"' in editing
    tag = re.search(r'<input\b[^>]*name="gmail_app_password"[^>]*>', editing).group(0)
    assert "value=" not in tag

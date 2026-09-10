"""#854 — the platform is a tenant of its own kind.

Decided by Koen on 10 September 2026, revising the note *"the operator is not a tenant"*
from the same morning:

> *"The platform is going to send mail, it has a name, in time a logo, a bank account
> number, a gmail password, tiktok, facebook, instagram, a privacy statement, a sender
> address, a mollie key. But it is not a Raak afdeling — companies may become customers
> too. 'Platform' is a type of tenant then."*

That list IS the list of tenant settings, so `org_type` gets a third value `PLATFORM`
next to `ACCOUNT` and `UNIT` instead of a second store for the same eight things.

**This also fixes #853.** On a platform host every path other than `/` used to fall back
to the default tenant, so a platform administrator got the shell of Raak Millegem and an
e-mail *"Inloglink Raak Millegem"*. There was nothing to resolve to; now there is.

**The price of the choice, and where it breaks silently.** Being a tenant means the
global ORM filter joins in: every select gets `tenant_id = <active tenant>`. Run an
operator screen under the platform tenant and it would see the platform row only — and
the tenant list on `/admin/tenants` is precisely the screen that must see everything.
No error, just a list that shrinks. Hence `test_the_tenant_list_survives_the_global_filter`.

Broken on purpose to check that these tests can go red:

- `TenantMixin` added to `Organization` → five of these tests fall over. The tenant list
  is the one that fails the way the danger actually looks; the settings screens fail
  loudly with a database error, because in that experiment the column does not exist
  yet. In a real change it would exist, and then only the shrinking remains — without an
  error, and that is the whole point. That `Organization` does NOT carry the mixin today
  is what keeps this screen safe, and you cannot see that by reading either file.
- `platform_tenant` dropped from the middleware call (back to the pre-#854 fallback) →
  the resolution tests and the mail test fall over, the tenant-host test stays green.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    """`PLATFORM_HOSTS` zoals het op de server staat, plus een schone lookup-cache."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


def _operator(client, db, email="operator@example.com"):
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_the_migration_created_exactly_one_platform_row(db_session):
    """The floor under everything below: without this row the rest is vacuous (#678)."""
    from app.domains.mdm.api import Organization

    rows = (db_session.query(Organization)
            .filter(Organization.org_type == "PLATFORM").all())

    assert len(rows) == 1, f"expected one PLATFORM organization, found {len(rows)}"
    assert rows[0].parent_id is None, (
        "the platform hangs under an account; row 1 is the customer and the platform "
        "is not that customer")


@pytest.mark.parametrize("path", ["/aanmelden", "/activiteiten"])
def test_a_platform_host_resolves_to_the_platform_on_every_path(client, db_session,
                                                                platform_host, path):
    """#853: every path, not only `/`. `/aanmelden` is the screen Koen reported.

    `/` is deliberately NOT in this list — that is the landing page, and it names the
    afdelingen on purpose. Asserting "no Raak Millegem" there would test the opposite
    of what the landing is for; it has its own test below.
    """
    from app.domains.mdm.api import platform_tenant_id

    resp = client.get(path, headers={"host": platform_host})

    assert resp.status_code == 200, resp.text[:200]
    assert "Digital Platform" in resp.text, (
        "the platform host does not show the platform name")
    assert "Raak Millegem" not in resp.text, (
        "the shell of an afdeling on a platform host — that is #853")
    assert platform_tenant_id(db=db_session) is not None


def test_the_landing_page_still_lists_the_afdelingen(client, db_session, platform_host):
    """The counterpart, and it is why `/` is not in the list above: on the landing page
    an afdeling name is the point, not the bug."""
    resp = client.get("/", headers={"host": platform_host})

    assert resp.status_code == 200
    assert "Digital Platform" in resp.text
    assert "Raak Millegem" in resp.text, "the landing page lists no afdelingen"


def test_the_login_mail_from_a_platform_host_carries_the_platform_name(
        client, db_session, platform_host, monkeypatch):
    """The name reaches the mail along a different road than the shell, so this is the
    test that goes red again soonest.

    Koen's report was literally an e-mail titled *"Inloglink Raak Millegem"* arriving
    after logging in on the platform.
    """
    verstuurd = {}

    from app.domains.mail import service as mail_service

    # `_send` and not `_dispatch`: the magic-link mail calls `_send` directly, so a
    # patch one layer higher never fires and the test would fail for the wrong reason.
    def _capture(to_email, subject, body_html, **kwargs):
        verstuurd["subject"] = subject
        verstuurd["html"] = body_html

    monkeypatch.setattr(mail_service, "_send", _capture)

    # A KNOWN address: `start_login` stays silent for an unknown one — deliberately,
    # so the screen never reveals who has an account.
    resp = client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL},
                       headers={"host": platform_host})

    assert resp.status_code == 200
    assert verstuurd, "no mail was sent at all"
    assert "Digital Platform" in verstuurd["subject"], verstuurd["subject"]
    assert "Raak Millegem" not in verstuurd["subject"]
    assert "Raak Millegem" not in verstuurd["html"], (
        "the signature still carries the name of an afdeling")


def test_the_tenant_list_survives_the_global_filter(client, db_session, platform_host):
    """The screen that must see everything, while the active tenant sees only itself.

    This is the price of the choice, and the only test that catches it: the failure
    shows no error, the list simply shrinks.
    """
    _operator(client, db_session)

    resp = client.get("/admin/tenants", headers={"host": platform_host})

    assert resp.status_code == 200, resp.text[:300]
    for name in ("Raak Millegem", "Raak Voorbeeldafdeling"):
        assert name in resp.text, (
            f"{name} is missing from the tenant list while the platform is the active "
            f"tenant — the global filter is shrinking the one screen that must see all")
    assert "Digital Platform" in resp.text, (
        "the platform itself is not configurable, while it carries settings like any "
        "tenant")


def test_the_platform_is_not_reachable_as_a_path_prefix(client, db_session):
    """`tenant_lookup` filters on UNIT and must keep doing so: `/platform/` is not an
    afdeling site."""
    from app.domains.mdm.api import tenant_codes

    codes = tenant_codes(db=db_session)

    assert "platform" not in codes, (
        "the platform is in the code→id map, so /platform/… would open a site")


def test_the_platform_settings_page_offers_no_membership_fields(client, db_session,
                                                                platform_host):
    """A platform has no members, so no membership fee. Offer the field and somebody
    eventually fills it in, and then a value sits there that nobody can explain."""
    from app.domains.mdm.api import platform_tenant_id

    _operator(client, db_session)
    platform_id = platform_tenant_id(db=db_session)

    resp = client.get(f"/admin/tenants/{platform_id}", headers={"host": platform_host})

    assert resp.status_code == 200, resp.text[:300]
    assert 'name="membership_price_full"' not in resp.text
    assert 'name="max_registrations_per_email"' not in resp.text
    # The counterproof, in the same response: the fields a platform DOES have.
    assert 'name="display_name"' in resp.text and 'name="gmail_from"' in resp.text


def test_a_unit_keeps_all_its_fields(client, db_session, platform_host):
    """The counterproof to the previous test: hiding is only right where it is right."""
    from app.domains.mdm.api import list_units

    _operator(client, db_session)
    unit = list_units(db_session)[0]

    resp = client.get(f"/admin/tenants/{unit.id}", headers={"host": platform_host})

    assert 'name="membership_price_full"' in resp.text


def test_a_tenant_host_is_unchanged(client, db_session, platform_host):
    """What must not break. An afdeling host has its own name and keeps it."""
    resp = client.get("/", headers={"host": "raakmillegem.be"})

    assert resp.status_code == 200
    assert "Digital Platform" not in resp.text

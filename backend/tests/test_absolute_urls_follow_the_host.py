"""#860 — absolute URLs must follow the host you arrived on.

Found by Koen on UAT, 10 September 2026. He logged in on `/aanmelden` of the **platform
host** and got a mail with a login link to the **afdeling address** of Raak Millegem.
Clicking it puts your session cookie on the wrong host: signed in on the afdeling site,
still anonymous on the platform. A platform administrator never gets in where he was
going.

`tenant_base_url` never looked at the host the request came in on. Two things stacked:

1. **The platform tenant has no address of its own**, so it borrowed one from an
   afdeling — on production too, where the stored value does win.
2. **The brake from #477 had grown too broad.** On non-prod `FRONTEND_URL` always won,
   with the reason spelled out in its own docstring: *"on HDEV/UAT everything runs on one
   origin"*. Since #821 and #854 that is no longer true, and the broad brake made the
   platform flow untestable on UAT.

The brake itself stays. The danger was never a per-tenant address as such but an address
pointing at **another environment** — a production URL that lands in a UAT database after
a restore. So a stored `base_url` is accepted when its host is one this environment
actually serves, and ignored otherwise.

**It is two questions with different answers, not one rule.**

| The question | Where | Answer |
|---|---|---|
| *Where does that other afdeling live?* | landing cards, `sitemap.xml` | her own canonical address |
| *Where do you bring me back?* | login link, Mollie redirect, edit link of a submission | the host you arrived on |

For an afdeling **without** its own host those coincide on `<incoming-host>/<code>`, which
is why it looks like one rule. They diverge for an afdeling **with** its own host: standing
on the platform host, the Millegem card must point at Millegem's own domain and not at
`<platform-host>/raakmillegem` — anything else weakens her canonical address. Hence
`tenant_home_url` next to `tenant_base_url`.

And the source of that canonical address is the routing, not a typed-in field:
`TENANT_HOSTNAMES` already ties a host to an afdeling per environment. Measured on
10 September 2026: Raak Millegem has no `base_url` at all on UAT or PROD — it has that
mapping.

The Mollie redirect is the nastiest of the list — you pay on one host and come back on
another, and you notice after the money moved.

Broken on purpose to check that these tests can go red:

- put a production-looking `base_url` (`https://raakmillegem.be`) in the settings of this
  non-prod environment and asserted it is ignored — that IS the second test, and it is how
  #477 stops being only a story in a docstring. Removing the host check makes it fall over
  with `https://raakmillegem.be` in the login link of a test environment — and it takes the
  derivation test with it, because a stored address then also wins over the platform host.
- `current_origin` left unset in the middleware → four fall over, each with an afdeling
  address where the platform host belongs. Only the ones that do not depend on the incoming
  host stay green: production, and an afdeling with its own domain.
- the `TENANT_HOSTNAMES` lookup in `tenant_home_url` disabled → the card of an afdeling
  with her own host falls back to `<platform-host>/raakmillegem`, which works but weakens
  her canonical address.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


@pytest.fixture
def captured_mail(monkeypatch):
    sent = {}

    from app.domains.mail import service as mail_service

    def _capture(to_email, subject, body_html, **kwargs):
        sent["subject"] = subject
        sent["html"] = body_html

    monkeypatch.setattr(mail_service, "_send", _capture)
    return sent


def test_the_login_link_points_at_the_host_you_arrived_on(client, db_session,
                                                          platform_host, captured_mail):
    """Koen's case, and the test closest to the complaint."""
    resp = client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL},
                       headers={"host": platform_host})

    assert resp.status_code == 200
    assert captured_mail, "no mail was sent"
    assert f"//{platform_host}/login/verify" in captured_mail["html"], (
        f"the login link does not point at the platform host:\n{captured_mail['html']}")


def test_a_base_url_from_another_environment_is_still_ignored(client, db_session,
                                                              platform_host, captured_mail):
    """The brake from #477, and the proof that it still works.

    A production address in a non-prod database — after a restore or a seed — must never
    end up in a test login link or a payment redirect. `raakmillegem.be` is served by no
    setting of this environment, so it is ignored in favour of the host you came in on.
    """
    from app.domains.mdm.api import platform_tenant_id
    from app.kernel.tenant_config import set_setting

    # On the PLATFORM tenant, because that is the tenant this request resolves to.
    # Storing it on another tenant would make this test pass without proving anything —
    # the value would simply never be read.
    set_setting(db_session, "base_url", "https://raakmillegem.be",
                tenant_id=platform_tenant_id(db=db_session))
    db_session.flush()

    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL},
                headers={"host": platform_host})

    assert "raakmillegem.be" not in captured_mail["html"], (
        "a production address from the database leaked into a login link on a test "
        "environment — that is exactly what #477 exists to prevent")
    assert f"//{platform_host}/" in captured_mail["html"]


def test_a_base_url_this_environment_serves_is_accepted(client, db_session,
                                                        captured_mail, monkeypatch):
    """The counterpart, and without it the previous test cannot be told apart from "the
    stored value is never used".

    An afdeling with its own domain keeps its `base_url`, because that IS its canonical
    address. The request arrives on that domain, exactly as a visitor would.
    """
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "tenant_hostnames", "eigen.example.test=raakmillegem")
    set_setting(db_session, "base_url", "https://eigen.example.test")
    db_session.flush()

    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL},
                headers={"host": "eigen.example.test"})

    assert "//eigen.example.test/login/verify" in captured_mail["html"], (
        f"the stored base_url of an afdeling with its own domain was ignored:\n"
        f"{captured_mail['html']}")


def test_on_production_the_stored_base_url_stays_leading(db_session, monkeypatch):
    """Unchanged behaviour: on prod the per-tenant DB value leads, whatever host the
    request came in on."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting, tenant_base_url

    monkeypatch.setattr(settings, "app_env", "prod")
    set_setting(db_session, "base_url", "https://raakmillegem.be")
    db_session.flush()

    assert tenant_base_url(db_session) == "https://raakmillegem.be"


def test_an_afdeling_without_its_own_domain_derives_its_address(client, db_session,
                                                                platform_host):
    """Koen: *"I should not even have to fill that in."* Storing it by hand would put the
    same fact in two places, and then it is not a question whether they drift but when.

    This is the card he saw pointing at the address of a different afdeling.
    """
    html = client.get("/", headers={"host": platform_host}).text

    assert f"//{platform_host}/raakvoorbeeldafdeling" in html, (
        "the card of an afdeling without its own domain does not derive its address from "
        "this platform host")


def test_the_derivation_uses_the_incoming_host_and_not_just_any_platform_host(
        client, db_session, monkeypatch):
    """`PLATFORM_HOSTS` is a list, so "a platform host" and "the host you came in on" can
    differ — and then a card sends you away from the site you are looking at.

    Koen: *"I am browsing on the platform host and the voorbeeldafdeling will
    automatically point at `<platform-host>/raakvoorbeeldafdeling`? That seems the most
    logical to me, it has nothing to do with Millegem."*
    """
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts",
                        f"eerste.example.test,{PLATFORM_HOST}")
    invalidate_tenant_codes()
    try:
        html = client.get("/", headers={"host": PLATFORM_HOST}).text
    finally:
        invalidate_tenant_codes()

    assert f"//{PLATFORM_HOST}/raakvoorbeeldafdeling" in html
    assert "eerste.example.test" not in html, (
        "the derivation took the first host from the configuration instead of the one "
        "this request arrived on")


def test_the_mollie_redirect_comes_back_on_the_same_host(client, db_session, platform_host):
    """The nastiest one on the list: you pay on one host and return on another, and you
    only notice after the money moved."""
    from app.kernel.tenant_config import tenant_base_url

    # Same call the payment flow makes (activities/router.py:909) — through the client so
    # the middleware has set the request context.
    resp = client.get("/robots.txt", headers={"host": platform_host})

    assert platform_host in resp.text, (
        "robots.txt points at another host, so every absolute URL built this way does")
    assert tenant_base_url(db_session) is not None


def test_an_afdeling_with_its_own_host_keeps_her_own_address_on_a_card(
        client, db_session, platform_host, monkeypatch):
    """The two questions diverge here, and this is the one Koen raised.

    Standing on the platform host, the card of an afdeling with her own domain must point
    at that domain. `<platform-host>/raakmillegem` would work, but it weakens her
    canonical address — and the mapping in TENANT_HOSTNAMES already says where she lives.
    """
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "tenant_hostnames", "millegem.example.test=raakmillegem")
    invalidate_tenant_codes()
    try:
        html = client.get("/", headers={"host": platform_host}).text
    finally:
        invalidate_tenant_codes()

    assert "//millegem.example.test" in html, (
        "the card of an afdeling with her own host does not point at her own domain")
    assert f"//{PLATFORM_HOST}/raakmillegem" not in html
    # And the counterpart in the same response: an afdeling WITHOUT its own host still
    # derives from the host you arrived on.
    assert f"//{PLATFORM_HOST}/raakvoorbeeldafdeling" in html


def test_the_return_url_follows_the_incoming_host_even_with_an_own_domain(
        client, db_session, platform_host, captured_mail, monkeypatch):
    """The other half of the split: "where do you bring me back" is not "where does this
    tenant live". You arrived on the platform host, so that is where you return."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "tenant_hostnames", "millegem.example.test=raakmillegem")
    invalidate_tenant_codes()
    try:
        client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL},
                    headers={"host": platform_host})
    finally:
        invalidate_tenant_codes()

    assert f"//{platform_host}/login/verify" in captured_mail["html"], (
        "the login link sent you to a tenant's own domain instead of back to the host you "
        "were on")

"""#889 — from an afdeling on the platform host, *Home* took you to the platform.

Koen: *"If I navigate from the platform to Raak Millegem and I click Photos and then go to
Home (in Millegem), I end up on the platform."*

The cause is one line in `resolve_request`: the tenant cookie keeps you at your afdeling on
**every** path except `/` — and *Home* in the public shell is exactly `href="/"`.

**That exception stays.** It is what keeps the platform findable: typing the bare domain
always gives the landing page, whatever cookie you carry. The bug is that *Home* in the
**afdeling shell** pointed at `/` and so sent you away.

**The fix is the links.** An afdeling reached through a path prefix renders links **with**
that prefix: *Home* becomes `/raakmillegem/`. Three things become right at once, and the
second matters most:

- the URL says where you are — today it reads `/fotos` while you are at Millegem, and only a
  cookie still knows that;
- **a shared link works** — send `/fotos` on and the recipient, without your cookie, ends up
  somewhere else;
- the cookie becomes a safety net instead of the mechanism.

Broken on purpose to check that these tests can go red: `path_for` made to return its
argument unchanged → the first two fall over, with *Home* pointing at `/` again; and the
`/admin` exception removed from `path_for` → the admin test falls over with a prefix on a
screen that is never reached through one.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
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


def test_home_keeps_you_at_the_afdeling(client, db_session, platform_host):
    """Koens geval, letterlijk: via de prefix binnen, dan Foto's, dan Home."""
    eerste = client.get(f"/raakmillegem/", headers={"host": PLATFORM_HOST})
    assert eerste.status_code == 200

    fotos = client.get("/raakmillegem/fotos", headers={"host": PLATFORM_HOST})

    assert fotos.status_code == 200
    # Zonder slotslash, dezelfde vorm als de kaarten op de landingspagina gebruiken
    # (`tenant_home_url`): één schrijfwijze door de hele app, want twee vormen van
    # hetzelfde adres is precies wat #884 met de canonical probeerde te vermijden.
    assert 'href="/raakmillegem"' in fotos.text, (
        "Home wijst naar / en stuurt je dus naar het platform — dat is de bug")
    assert 'href="/raakmillegem/fotos"' in fotos.text, (
        "de Foto's-link draagt de prefix niet")


def test_the_same_route_works_without_a_cookie(client, db_session, platform_host):
    """**De test die dit issue draagt.**

    Zonder cookie dezelfde weg: als de prefix het werk doet, kom je bij dezelfde afdeling
    uit. Werkt het alleen mét cookie, dan is een gedeelde link waardeloos — de ontvanger
    heeft jouw cookie niet.
    """
    client.cookies.clear()

    resp = client.get("/raakmillegem/fotos", headers={"host": PLATFORM_HOST})

    assert resp.status_code == 200
    assert 'href="/raakmillegem"' in resp.text, (
        "zonder cookie dragen de links geen prefix, dus een gedeelde link brengt de "
        "ontvanger ergens anders")


def test_on_an_own_hostname_there_is_no_prefix(client, db_session, platform_host,
                                               monkeypatch):
    """De tegenproef: op de echte site geen lelijke URL's."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "tenant_hostnames", "millegem.example.test=raakmillegem")
    invalidate_tenant_codes()
    try:
        resp = client.get("/fotos", headers={"host": "millegem.example.test"})
    finally:
        invalidate_tenant_codes()

    assert resp.status_code == 200
    assert 'href="/raakmillegem"' not in resp.text, "de eigen site kreeg een prefix"
    assert 'href="/"' in resp.text


def test_the_bare_platform_host_still_gives_the_landing_page(client, db_session,
                                                             platform_host):
    """Ongewijzigd, en het is de reden dat er géén extra knop naar het platform nodig is:
    het bare domein blijft de landingspagina geven, ongeacht welke cookie je draagt."""
    client.get("/raakvoorbeeldafdeling/", headers={"host": PLATFORM_HOST})  # zet de cookie

    resp = client.get("/", headers={"host": PLATFORM_HOST})

    assert resp.status_code == 200
    assert "Digital Platform" in resp.text, (
        "het platform is niet meer bereikbaar door het domein te typen")


def test_an_admin_path_never_gets_a_prefix(client, db_session, platform_host):
    """Beheerschermen worden niet via een prefix bereikt. De uitzondering staat in
    `path_for` zelf en niet bij elke aanroeper — een regel die je op tientallen plaatsen
    moet onthouden, vergeet iemand."""
    from app.ui import path_for
    from app.kernel.tenancy import current_platform_host, current_tenant_code

    host_token = current_platform_host.set(True)
    code_token = current_tenant_code.set("raakmillegem")
    try:
        assert path_for("/admin/werkbank") == "/admin/werkbank"
        assert path_for("/static/app.css") == "/static/app.css"
        assert path_for("/api/v1/media/3") == "/api/v1/media/3"
        # En de tegenproef in dezelfde context, anders bewijst het bovenstaande niets:
        assert path_for("/fotos") == "/raakmillegem/fotos"
        assert path_for("/") == "/raakmillegem"
    finally:
        current_tenant_code.reset(code_token)
        current_platform_host.reset(host_token)

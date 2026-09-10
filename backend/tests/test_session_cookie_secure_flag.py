"""#865 — the Secure flag follows the connection, not the name of the environment.

Until now the session cookie carried `secure=settings.app_env in ("uat", "prod")`. That
looks at the NAME of the environment instead of at the connection, and such a list is
behind by definition: an environment added later runs https and does not get the flag,
and nobody notices, because a cookie without `Secure` simply works.

**Behind the proxy is where this actually gets decided.** The backend sees a connection
from Caddy, not from the browser, so the scheme comes from `X-Forwarded-Proto` and never
from the socket. That is exactly the kind of difference that is green locally and wrong
behind a proxy, so both cases are tested here.

**One deliberate deviation from the issue.** It asks the flag to follow the scheme of the
request. Doing only that would let a supplied `X-Forwarded-Proto: http` strip the flag
from a genuine https session — the backend cannot tell that header apart from one the
proxy set. So the environment's own scheme (`FRONTEND_URL`) is a floor: is this
environment served over https, then the flag stays, whatever a header claims. The gain the
issue asked for is intact — the list of environment names is gone and a new https
environment is right by itself.

Broken on purpose to check that these tests can go red: forced plain http (an environment
on `http://` and no forwarded header) → the flag disappears, which is the first test; and
removing the `X-Forwarded-Proto` read → the proxy test falls over with a cookie that has no
`Secure` while the browser spoke https.
"""
import pytest

from app.domains.auth.api import session_cookie_secure

pytestmark = pytest.mark.ui_agnostisch


class _FakeRequest:
    """Enough of a request for this question: headers and a URL scheme."""

    def __init__(self, scheme="http", headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.url = type("U", (), {"scheme": scheme})()


@pytest.fixture
def http_environment(monkeypatch):
    """An environment served over plain http, like dev and HDEV."""
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_url", "http://localhost:8081")
    monkeypatch.setattr(settings, "app_env", "hdev")


def test_plain_http_gets_no_secure_flag(http_environment):
    """A `Secure` cookie is not stored over http, so the flag must not be there — this is
    what makes local and HDEV logins work at all."""
    assert session_cookie_secure(_FakeRequest("http")) is False


def test_behind_a_proxy_the_forwarded_scheme_decides(http_environment):
    """The case that is green locally and wrong behind a proxy.

    The backend sees Caddy's connection, so `request.url.scheme` says http while the
    browser spoke https. Only the forwarded header knows.
    """
    request = _FakeRequest("http", {"X-Forwarded-Proto": "https"})

    assert session_cookie_secure(request) is True


def test_a_list_of_forwarded_schemes_uses_the_first(http_environment):
    """Several proxies append: the one closest to the client comes first."""
    request = _FakeRequest("http", {"X-Forwarded-Proto": "https, http"})

    assert session_cookie_secure(request) is True


def test_an_https_environment_keeps_the_flag_whatever_a_header_claims(monkeypatch):
    """The deviation, and the reason for it.

    Following only the request would let a supplied `X-Forwarded-Proto: http` strip the
    flag from a real https session. The environment's own scheme is the floor.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_url", "https://raakmillegem.be")
    monkeypatch.setattr(settings, "app_env", "prod")

    assert session_cookie_secure(_FakeRequest("http", {"X-Forwarded-Proto": "http"})) is True
    assert session_cookie_secure(None) is True


def test_the_environment_name_no_longer_decides(monkeypatch):
    """The point of the issue: a new environment served over https is right by itself,
    without anybody adding its name to a list."""
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "een-nieuwe-omgeving")
    monkeypatch.setattr(settings, "frontend_url", "https://nieuw.example.test")

    assert session_cookie_secure(_FakeRequest("http")) is True


def test_the_login_screen_sets_the_flag_behind_a_proxy(client, db_session, monkeypatch):
    """End to end, through the real route: this is where the request has to reach
    `set_session_cookie` at all."""
    from app.config import settings
    from app.domains.auth import login as auth_login
    from app.domains.auth.api import SESSION_COOKIE
    from tests.conftest import SEEDED_ADMIN_EMAIL

    monkeypatch.setattr(settings, "frontend_url", "http://localhost:8081")
    monkeypatch.setattr(settings, "app_env", "hdev")
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "424242")
    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})

    resp = client.post("/aanmelden/code",
                       data={"email": SEEDED_ADMIN_EMAIL, "code": "424242"},
                       headers={"X-Forwarded-Proto": "https"})

    cookie = [h for h in resp.headers.get_list("set-cookie") if SESSION_COOKIE in h]
    assert cookie, resp.headers
    assert "Secure" in cookie[0], (
        f"the browser spoke https but the cookie carries no Secure flag: {cookie[0]}")

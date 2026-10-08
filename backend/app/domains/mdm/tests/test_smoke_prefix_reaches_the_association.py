"""#1530 — the measurement under the deploy smoke's new target.

The smoke test now runs under an association's path prefix on whatever host the
environment gives it. That only works if the prefix resolves the tenant on the
API paths too, and not only on pages: measured here on a platform host, where the
bare API path is the platform's (payment off since #1523) and the prefixed one
is Raak Millegem's: the same payment route — the Mollie webhook, posted without
its `id` — answers 422 under the prefix (the route is there and asks for its
field) and 404 bare. The activities list and the payment records routes that
stood here went with CR-13 phase 4b (#1251); the webhook stays.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.ui_serverrendered

HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", HOST)
    invalidate_tenant_codes()
    yield
    invalidate_tenant_codes()


@pytest.mark.parametrize(
    "method,path,status",
    [
        ("GET", "/raakmillegem/api/health", 200),
        ("POST", "/raakmillegem/api/v1/payment-gateway/webhooks/mollie", 422),
        ("GET", "/api/health", 200),
        ("POST", "/api/v1/payment-gateway/webhooks/mollie", 404),
    ],
)
def test_the_prefix_reaches_the_association_on_the_api(client, platform_host, method, path, status):
    client.cookies.clear()
    assert client.request(method, path, headers={"host": HOST}).status_code == status


# CR-13 phase 4b (#1251): the smoke test checks screens, not JSON routes that have
# no other caller. The same measurement for its new lines: under the prefix the
# public pages answer 200 and a back-office screen sends a visitor without a
# session to the sign-in (303, #1458); on the bare platform host the activities
# page is absent, which is what the platform check asserts.
@pytest.mark.parametrize(
    "path,status",
    [
        ("/raakmillegem/", 200),
        ("/raakmillegem/activiteiten", 200),
        ("/raakmillegem/lid-worden", 200),
        ("/raakmillegem/admin/betalingen", 303),
        ("/raakmillegem/admin/media", 303),
        ("/activiteiten", 404),
    ],
)
def test_the_prefix_reaches_the_association_on_the_screens(client, platform_host, path, status):
    client.cookies.clear()
    answer = client.get(path, headers={"host": HOST}, follow_redirects=False)
    assert answer.status_code == status, (path, answer.status_code)
    if status == 303:
        assert "/aanmelden" in answer.headers["location"], answer.headers["location"]

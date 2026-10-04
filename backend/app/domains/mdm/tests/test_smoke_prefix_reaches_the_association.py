"""#1530 — the measurement under the deploy smoke's new target.

The smoke test now runs under an association's path prefix on whatever host the
environment gives it. That only works if the prefix resolves the tenant on the
API paths too, and not only on pages: measured here on a platform host, where the
bare API path is the platform's (activities off since #1523) and the prefixed one
is Raak Millegem's. The four lines are the smoke checks that failed on HDEV, plus
the health and the platform's own 404 that the platform check asserts.
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
    "path,status",
    [
        ("/raakmillegem/api/health", 200),
        ("/raakmillegem/api/v1/activities", 200),
        ("/raakmillegem/api/v1/payment-status/records", 401),
        ("/api/health", 200),
        ("/api/v1/activities", 404),
    ],
)
def test_the_prefix_reaches_the_association_on_the_api(client, platform_host, path, status):
    client.cookies.clear()
    assert client.get(path, headers={"host": HOST}).status_code == status

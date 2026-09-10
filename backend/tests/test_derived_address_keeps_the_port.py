"""#863 — an address derived from TENANT_HOSTNAMES must keep the port.

Found while checking #860 on HDEV, 10 September 2026. The card of Raak Millegem on the
landing page pointed at her own host **without a port number**. HDEV runs on 8081, so:
port 80 → 308 to `https://` → no answer. A dead link, and it is precisely the card you
click to check whether #860 works.

The other card was fine: the voorbeeldafdeling has no host of its own, so her address is
derived from the running request and keeps `:8081`.

**It goes further than the card.** Every URL built from `TENANT_HOSTNAMES` lost the port —
on the afdeling host `robots.txt` also served `Sitemap: http://<host>/sitemap.xml`, equally
dead.

`TENANT_HOSTNAMES` holds hostnames **without** a port, and that is correct: the tenant
resolution compares against `host.split(":")[0]`. The scheme was taken from `FRONTEND_URL`,
but the port came from nowhere.

**Why this matters while UAT and PROD never notice.** They run on the standard port, so
nothing changes there — which makes it tempting to leave it. But HDEV is where a release is
approved before it is tagged. An environment where the link is dead is an environment where
you cannot establish that *"the cards point at the right place"*; then the validation is a
formality instead of a check.

Broken on purpose to check that these tests can go red: `_omgevingspoort` made to return
`""` always → three fall over with a portless address, exactly the dead link from HDEV,
while the standard-port test stays green (it expects no port); and the fallback to
`FRONTEND_URL` removed → only the background-task test falls over, which is the half that
would otherwise go missing silently.
"""
import pytest

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"
AFDELING_HOST = "millegem.example.test"


@pytest.fixture
def hdev_like(monkeypatch):
    """An environment on a non-standard port, like HDEV on 8081."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "frontend_url", "http://localhost:8081")
    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    monkeypatch.setattr(settings, "tenant_hostnames", f"{AFDELING_HOST}=raakmillegem")
    invalidate_tenant_codes()
    yield
    invalidate_tenant_codes()


def test_the_card_of_an_afdeling_with_its_own_host_keeps_the_port(client, db_session,
                                                                  hdev_like):
    """The measured case: without the port this link is dead, and it is the very card you
    click to check #860."""
    html = client.get("/", headers={"host": f"{PLATFORM_HOST}:8081"}).text

    assert f"//{AFDELING_HOST}:8081" in html, (
        f"the derived address lost the port, so the link is dead on this environment")


def test_robots_and_sitemap_keep_the_port(client, db_session, hdev_like):
    """Same cause, second place: every URL built from TENANT_HOSTNAMES lost the port."""
    robots = client.get("/robots.txt", headers={"host": f"{AFDELING_HOST}:8081"}).text

    assert f"Sitemap: http://{AFDELING_HOST}:8081/sitemap.xml" in robots, robots


def test_without_a_request_the_port_comes_from_frontend_url(db_session, hdev_like):
    """The half that would otherwise be missing silently.

    A sitemap or a mail can come from a background task, and then there is no request. Take
    the port only from the request and such a task builds a portless address again.
    """
    from app.kernel.tenant_config import tenant_home_url

    # No client, so no middleware and no request context — exactly a background task.
    assert tenant_home_url(db_session, code="raakmillegem") == f"http://{AFDELING_HOST}:8081"


def test_a_standard_port_is_not_spelled_out(client, db_session, monkeypatch):
    """Unchanged for UAT and PROD, and deliberately so.

    A canonical address with an explicit `:443` is a second spelling of the same URL, and
    for SEO that is precisely what you do not want.
    """
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes
    from app.kernel.tenant_config import tenant_home_url

    monkeypatch.setattr(settings, "frontend_url", "https://raakmillegem.be")
    monkeypatch.setattr(settings, "tenant_hostnames", f"{AFDELING_HOST}=raakmillegem")
    invalidate_tenant_codes()
    try:
        adres = tenant_home_url(db_session, code="raakmillegem")
    finally:
        invalidate_tenant_codes()

    assert adres == f"https://{AFDELING_HOST}", adres
    assert ":443" not in adres and ":80" not in adres

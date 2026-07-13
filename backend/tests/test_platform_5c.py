"""Fase 5c (#406): pad-prefix-routing + tenant-cookie, platform-landing,
per-tenant robots/sitemap en de demo-seed."""
from app.kernel.tenancy import (
    DEFAULT_TENANT_ID,
    TENANT_MILLEGEM_ID,
    TENANT_VOORBEELD_ID,
    resolve_request,
)


def test_resolve_request_volgorde():
    hosts = {"raakmillegem.be": "raakmillegem"}
    platform = {"renko.be"}
    # pad-prefix wint en herschrijft het pad
    assert resolve_request("renko.be", "/raakvoorbeeldafdeling/activiteiten",
                           None, hosts, platform) == (TENANT_VOORBEELD_ID, "/activiteiten", False)
    assert resolve_request("renko.be", "/raakmillegem", None, hosts, platform) == (
        TENANT_MILLEGEM_ID, "/", False)
    # hostname
    assert resolve_request("www.raakmillegem.be", "/x", None, hosts, platform) == (
        TENANT_MILLEGEM_ID, None, False)
    # cookie houdt navigatie op de tenant (enkel platform-hosts)
    assert resolve_request("renko.be", "/activiteiten", "raakvoorbeeldafdeling",
                           hosts, platform) == (TENANT_VOORBEELD_ID, None, False)
    assert resolve_request("raakmillegem.be", "/activiteiten", "raakvoorbeeldafdeling",
                           hosts, platform) == (TENANT_MILLEGEM_ID, None, False)
    # platform-wortel = landing
    assert resolve_request("renko.be", "/", None, hosts, platform) == (
        DEFAULT_TENANT_ID, None, True)


def test_prefix_navigatie_en_cookie(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "platform_hosts", "renko.be")
    resp = client.get("/raakvoorbeeldafdeling/", headers={"host": "renko.be"})
    assert resp.status_code == 200
    assert "Voorbeeldafdeling" in resp.text  # demo home-intro uit de seed
    assert resp.headers.get("x-robots-tag") == "noindex, nofollow"
    assert "raak_tenant=raakvoorbeeldafdeling" in resp.headers.get("set-cookie", "")


def test_platform_landing(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "platform_hosts", "renko.be")
    resp = client.get("/", headers={"host": "renko.be"})
    assert resp.status_code == 200
    assert "Raak Digital Platform" in resp.text
    assert "Raak Voorbeeldafdeling" in resp.text


def test_robots_en_sitemap_per_tenant(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "platform_hosts", "renko.be")
    # default-tenant: indexeerbaar + sitemap
    robots = client.get("/robots.txt")
    assert "Sitemap:" in robots.text and "Disallow: /admin" in robots.text
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200 and "<urlset" in sitemap.text

    # demo-tenant: alles geblokkeerd, geen sitemap
    client.cookies.clear()
    robots = client.get("/raakvoorbeeldafdeling/robots.txt", headers={"host": "renko.be"})
    assert "Disallow: /\n" in robots.text and "Sitemap:" not in robots.text
    sitemap = client.get("/raakvoorbeeldafdeling/sitemap.xml", headers={"host": "renko.be"})
    assert sitemap.status_code == 404


def test_demo_seed_aanwezig(client, db_session):
    from app.domains.activities.api import Activity
    from app.domains.forms.models import Form

    namen = {a.name for a in (db_session.query(Activity)
                              .execution_options(include_all_tenants=True)
                              .filter(Activity.tenant_id == TENANT_VOORBEELD_ID))}
    assert {"Voorbeeldquiz", "Demowandeling"} <= namen
    demo_form = (db_session.query(Form)
                 .execution_options(include_all_tenants=True)
                 .filter(Form.share_token == "demo-formulier").one())
    assert demo_form.status == "open" and demo_form.tenant_id == TENANT_VOORBEELD_ID

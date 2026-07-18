"""Fase 5 (#406): tenant-fundament — resolutie, mixin-default en de globale
cross-tenant-isolatiefilter (§7)."""
from app.domains.cms.models import CmsPage
from app.kernel.tenancy import (
    DEFAULT_TENANT_ID,
    TENANT_MILLEGEM_ID,
    TENANT_VOORBEELD_ID,
    current_tenant_id,
    parse_hostname_map,
    resolve_tenant,
)


def test_resolve_tenant_volgorde():
    hosts = parse_hostname_map("raakmillegem.be=raakmillegem, demo.example=raakvoorbeeldafdeling")
    # hostname wint (ook met www. en poort)
    assert resolve_tenant("www.raakmillegem.be:443", "/", hosts) == TENANT_MILLEGEM_ID
    assert resolve_tenant("demo.example", "/raakmillegem/x", hosts) == TENANT_VOORBEELD_ID
    # pad-prefix als de hostname niets zegt
    assert resolve_tenant("renko.be", "/raakvoorbeeldafdeling/activiteiten", hosts) == TENANT_VOORBEELD_ID
    assert resolve_tenant("renko.be", "/raakmillegem", hosts) == TENANT_MILLEGEM_ID
    # default: Millegem
    assert resolve_tenant("renko.be", "/", hosts) == DEFAULT_TENANT_ID
    assert resolve_tenant(None, "/activiteiten", {}) == DEFAULT_TENANT_ID


def test_mixin_default_volgt_context(db_session):
    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        demo = CmsPage(title="Demo", slug="tenancy-demo")
        db_session.add(demo)
        db_session.flush()
        assert demo.tenant_id == TENANT_VOORBEELD_ID
    finally:
        current_tenant_id.reset(token)
    # zonder context: default-tenant (Millegem)
    gewoon = CmsPage(title="Gewoon", slug="tenancy-gewoon")
    db_session.add(gewoon)
    db_session.flush()
    assert gewoon.tenant_id == DEFAULT_TENANT_ID


def test_globale_filter_isoleert_tenants(db_session):
    db_session.add(CmsPage(title="Van Millegem", slug="iso-millegem",
                           tenant_id=TENANT_MILLEGEM_ID))
    db_session.add(CmsPage(title="Van demo", slug="iso-demo",
                           tenant_id=TENANT_VOORBEELD_ID))
    db_session.flush()

    def slugs(**opts):
        q = db_session.query(CmsPage).filter(CmsPage.slug.like("iso-%"))
        if opts:
            q = q.execution_options(**opts)
        return {p.slug for p in q}

    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        assert slugs() == {"iso-demo"}
        # operator-opt-out: dwars over tenants
        assert slugs(include_all_tenants=True) == {"iso-millegem", "iso-demo"}
    finally:
        current_tenant_id.reset(token)
    # geen actieve tenant = geen filter (single-tenant-compatibel)
    assert slugs() == {"iso-millegem", "iso-demo"}


def test_request_krijgt_default_tenant(client, db_session):
    db_session.add(CmsPage(title="Demopagina", slug="alleen-demo", is_published=True,
                           show_in_nav=False, tenant_id=TENANT_VOORBEELD_ID))
    db_session.flush()
    # het request loopt als Millegem (default) → de demo-pagina bestaat daar niet
    assert client.get("/api/v1/pages/alleen-demo").status_code == 404


def test_tenant_codes_dynamisch_uit_organizations(db_session):
    """#546: de code→id-map komt dynamisch uit de actieve UNIT-organizations, zodat
    een nieuw aangemaakte tenant zonder codewijziging resolvet."""
    from app.kernel.tenancy import tenant_codes, resolve_tenant
    from app.domains.mdm.models import Organization

    org = Organization(org_type="UNIT", code="raaknieuw", name="Raak Nieuw", is_active=True)
    db_session.add(org)
    db_session.flush()

    codes = tenant_codes(db=db_session)
    assert codes.get("raaknieuw") == org.id
    # Pad-prefix /raaknieuw/... resolvet nu naar de nieuwe tenant.
    assert resolve_tenant("x", "/raaknieuw/activiteiten", {}, codes) == org.id

    # Een inactieve UNIT verdwijnt uit de map (resolvet niet meer).
    org.is_active = False
    db_session.flush()
    assert "raaknieuw" not in tenant_codes(db=db_session)


def test_tenant_codes_fallback_op_hardcoded(monkeypatch):
    """Vangnet (#546): faalt de DB-lezing, dan valt tenant_codes terug op de
    hardgecodeerde map — resolutie mag nooit breken."""
    from app.kernel import tenancy

    tenancy.invalidate_tenant_codes()

    def _boom(db):
        raise RuntimeError("db down")

    monkeypatch.setattr(tenancy, "_query_tenant_codes", _boom)
    assert tenancy.tenant_codes().get("raakmillegem") == tenancy.TENANT_MILLEGEM_ID
    tenancy.invalidate_tenant_codes()

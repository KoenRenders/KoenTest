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

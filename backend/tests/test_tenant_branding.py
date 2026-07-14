"""Branding per tenant (#407): mails, site-schil en lidgeld volgen de
tenant-config; Millegem-waarden blijven de default."""
from decimal import Decimal

from app.domains.mail.models import EmailLog
from app.kernel.tenancy import TENANT_VOORBEELD_ID, current_tenant_id
from app.kernel.tenant_config import set_setting


def test_mail_draagt_tenantnaam(client, db_session):
    from app.domains.mail.service import send_magic_link

    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        send_magic_link("branding@example.com", "https://renko.be/x")
    finally:
        current_tenant_id.reset(token)
    log = (db_session.query(EmailLog)
           .execution_options(include_all_tenants=True)
           .filter(EmailLog.recipient == "branding@example.com")
           .order_by(EmailLog.id.desc()).first())
    assert log is not None
    assert "Raak Voorbeeldafdeling" in log.subject
    assert "Raak Voorbeeldafdeling" in log.body


def test_site_schil_volgt_tenant(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "platform_hosts", "renko.be")
    resp = client.get("/raakvoorbeeldafdeling/", headers={"host": "renko.be"})
    assert resp.status_code == 200
    assert "© " in resp.text and "Raak Voorbeeldafdeling" in resp.text
    # Millegem (default) behoudt zijn eigen branding
    client.cookies.clear()
    resp = client.get("/")
    assert "Beleef meer in Millegem" in resp.text


def test_lidgeld_per_tenant(db_session, monkeypatch):
    from decimal import Decimal

    from app.config import settings
    from app.domains.payment.api import membership_price_for_date
    from app.kernel import tenant_config

    # 1. De config-laag: DB-sleutels winnen, .env blijft de default.
    set_setting(db_session, "membership_price_full", "10.00",
                tenant_id=TENANT_VOORBEELD_ID)
    set_setting(db_session, "membership_price_half", "5.00",
                tenant_id=TENANT_VOORBEELD_ID)
    db_session.flush()
    demo = tenant_config.tenant_membership_config(db_session,
                                                  tenant_id=TENANT_VOORBEELD_ID)
    assert (demo["price_full"], demo["price_half"]) == (Decimal("10.00"), Decimal("5.00"))
    ander = tenant_config.tenant_membership_config(db_session, tenant_id=98)
    assert ander["price_full"] == settings.membership_price_full

    # 2. De prijsfunctie leest die config (gepatcht met een vaste dict — de
    # savepoint-fixture is onzichtbaar voor de eigen SessionLocal van de helper).
    monkeypatch.setattr(tenant_config, "tenant_membership_config",
                        lambda db=None, tenant_id=None: {
                            "price_full": Decimal("10.00"),
                            "price_half": Decimal("5.00"),
                            "half_start_md": settings.membership_half_price_start_md,
                            "half_end_md": settings.membership_half_price_end_md,
                            "next_year_from_md": settings.membership_next_year_from_md,
                            "renewal_start_md": None})
    assert membership_price_for_date() in (Decimal("10.00"), Decimal("5.00"))

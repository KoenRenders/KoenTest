import logging
from decimal import Decimal
from sqlalchemy.orm import Session
from app.config import settings
from .models import GatewayPayment
from .providers.mollie import MollieProvider

logger = logging.getLogger(__name__)


def _get_provider(name: str = "mollie", api_key: str | None = None):
    if name == "mollie":
        return MollieProvider(api_key=api_key)
    raise ValueError(f"Unknown payment provider: {name}")


def create_payment(
    db: Session,
    amount: Decimal,
    description: str,
    redirect_url: str,
    metadata: dict,
    provider_name: str = "mollie",
) -> GatewayPayment:
    from app.kernel.tenant_config import get_setting, tenant_mollie_key

    # Per-tenant Mollie-key en webhook-origin (fase 5b, #406); .env als default.
    provider = _get_provider(provider_name, api_key=tenant_mollie_key(db))
    webhook_base = (get_setting(db, "base_url") or settings.public_url).rstrip("/")
    webhook_url = f"{webhook_base}/api/v1/payment-gateway/webhooks/{provider_name}"

    result = provider.create_payment(
        amount=amount,
        description=description,
        redirect_url=redirect_url,
        webhook_url=webhook_url,
        metadata=metadata,
    )

    gp = GatewayPayment(
        provider=provider_name,
        provider_payment_id=result.provider_payment_id,
        amount=amount,
        status=result.status,
        checkout_url=result.checkout_url,
        description=description,
        payment_metadata=metadata,
    )
    db.add(gp)
    db.flush()
    return gp


def refresh_payment_status(db: Session, gateway_payment_id: str) -> GatewayPayment:
    gp = db.query(GatewayPayment).filter(GatewayPayment.id == gateway_payment_id).first()
    if not gp:
        raise ValueError(f"GatewayPayment {gateway_payment_id} not found")

    from app.kernel.tenant_config import tenant_mollie_key

    provider = _get_provider(gp.provider,
                             api_key=tenant_mollie_key(db, tenant_id=gp.tenant_id))
    details = provider.get_payment_details(gp.provider_payment_id)
    new_status = details.status

    # Defense-in-depth (#92): bevestig bij 'paid' dat het door de provider
    # gerapporteerde bedrag/valuta overeenkomt met wat wij verwachtten
    # (gp.amount, EUR). Bij een mismatch markeren we NIET als betaald, maar
    # zetten we een aparte status zodat de penningmeester het nakijkt. Enkel
    # vergelijken als de provider een bedrag teruggaf (anders ongewijzigd gedrag).
    if new_status == "paid" and details.amount is not None:
        currency_ok = (details.currency or "EUR") == "EUR"
        amount_ok = Decimal(str(details.amount)) == Decimal(str(gp.amount))
        if not (currency_ok and amount_ok):
            logger.error(
                "Bedrag-mismatch voor gateway payment %s: verwacht %s EUR, "
                "provider meldt %s %s. NIET als betaald gemarkeerd.",
                gp.id, gp.amount, details.amount, details.currency,
            )
            gp.status = "needs_review"
            db.flush()
            return gp

    gp.status = new_status
    db.flush()
    return gp

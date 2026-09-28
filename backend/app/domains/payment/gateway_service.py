import logging
from decimal import Decimal
from sqlalchemy.orm import Session
from app.config import settings
from .models import GatewayPayment, PaymentProvider, PaymentStatus
from .providers.mollie import MollieProvider

logger = logging.getLogger(__name__)


class StubRefused(RuntimeError):
    """The stub payment provider was asked for where it may not exist (#1274)."""


def _get_provider(name: PaymentProvider = PaymentProvider.MOLLIE,
                  api_key: str | None = None):
    """The provider object for a stored or chosen provider name.

    Runs for every real payment and every status re-fetch, so the brake on the
    stub sits **inside the stub's branch** and nowhere else: a check in front of
    the whole function would be one typo away from refusing Mollie itself.
    """
    provider = PaymentProvider(name)
    if provider is PaymentProvider.MOLLIE:
        return MollieProvider(api_key=api_key)
    if provider is PaymentProvider.STUB:
        if not settings.payment_stub_allowed:
            raise StubRefused(
                f"The stub payment provider does not exist in APP_ENV={settings.app_env}.")
        from .providers.stub import StubProvider

        return StubProvider(api_key=api_key)
    raise ValueError(f"Unknown payment provider: {name}")


def configured_provider() -> PaymentProvider:
    """The provider new online payments go to — `settings.payment_provider`."""
    return PaymentProvider(settings.payment_provider)


def create_payment(
    db: Session,
    amount: Decimal,
    description: str,
    redirect_url: str,
    metadata: dict,
    provider_name: PaymentProvider | None = None,
) -> GatewayPayment:
    from app.kernel.tenant_config import get_setting, tenant_mollie_key

    provider_name = provider_name or configured_provider()
    # Per-tenant Mollie-key en webhook-origin (fase 5b, #406); .env als default.
    provider = _get_provider(provider_name, api_key=tenant_mollie_key(db))
    webhook_base = (get_setting(db, "base_url") or settings.public_url).rstrip("/")
    # The code, not the member (#1279): since #1178 `provider_name` is a
    # `PaymentProvider` member, and a plain Enum in an f-string reads
    # `PaymentProvider.MOLLIE` — a webhook URL Mollie called and got a 404 on.
    webhook_url = (f"{webhook_base}/api/v1/payment-gateway/webhooks/"
                   f"{PaymentProvider(provider_name).value}")

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
    if PaymentStatus(new_status) is PaymentStatus.PAID and details.amount is not None:
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

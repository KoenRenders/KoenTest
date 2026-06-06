from decimal import Decimal
from sqlalchemy.orm import Session
from app.config import settings
from .models import GatewayPayment
from .providers.mollie import MollieProvider


def _get_provider(name: str = "mollie"):
    if name == "mollie":
        return MollieProvider()
    raise ValueError(f"Unknown payment provider: {name}")


def create_payment(
    db: Session,
    amount: Decimal,
    description: str,
    redirect_url: str,
    metadata: dict,
    provider_name: str = "mollie",
) -> GatewayPayment:
    provider = _get_provider(provider_name)
    webhook_url = f"{settings.public_url}/api/v1/payment-gateway/webhooks/{provider_name}"

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
        metadata=metadata,
    )
    db.add(gp)
    db.flush()
    return gp


def refresh_payment_status(db: Session, gateway_payment_id: str) -> GatewayPayment:
    gp = db.query(GatewayPayment).filter(GatewayPayment.id == gateway_payment_id).first()
    if not gp:
        raise ValueError(f"GatewayPayment {gateway_payment_id} not found")

    provider = _get_provider(gp.provider)
    new_status = provider.get_payment_status(gp.provider_payment_id)
    gp.status = new_status
    db.flush()
    return gp

from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from app.database import get_db
from .models import GatewayPayment
from .gateway_service import refresh_payment_status
from .service import handle_gateway_update
from app.limiter import mollie_webhook_limiter

router = APIRouter(prefix="/payment-gateway", tags=["payment-gateway"])


def process_webhook(db: Session, provider_payment_id: str) -> dict:
    """What a provider's webhook does: look the payment up by the provider's id,
    re-fetch its status from the provider, and act on that.

    The body carries only the id, and nothing else from it is used — the
    re-fetch is the security model (`CLAUDE.md`). One function for every
    provider's route (#1274), so the stub's webhook is this code and not a copy.
    """
    gp = db.query(GatewayPayment).filter(
        GatewayPayment.provider_payment_id == provider_payment_id
    ).first()
    if not gp:
        return {"status": "ignored"}

    gp = refresh_payment_status(db, gp.id)
    handle_gateway_update(db, gateway_payment_id=gp.id, new_status=gp.status)
    db.commit()
    return {"status": "ok"}


@router.post("/webhooks/mollie", status_code=200, dependencies=[Depends(mollie_webhook_limiter)])
def mollie_webhook(id: str = Form(...), db: Session = Depends(get_db)):
    """Mollie calls this when a payment status changes (form-encoded body with 'id')."""
    return process_webhook(db, id)

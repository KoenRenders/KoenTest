from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from .models import GatewayPayment
from .schemas import WebhookPayload
from .service import refresh_payment_status
from app.domains.payment_status.service import handle_gateway_update

router = APIRouter(prefix="/payment-gateway", tags=["payment-gateway"])


@router.get("/payments/{payment_id}")
def get_payment(payment_id: str, db: Session = Depends(get_db)):
    gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"id": gp.id, "status": gp.status, "checkout_url": gp.checkout_url}


@router.post("/webhooks/mollie", status_code=200)
def mollie_webhook(payload: WebhookPayload, db: Session = Depends(get_db)):
    """Mollie calls this when a payment status changes."""
    gp = db.query(GatewayPayment).filter(
        GatewayPayment.provider_payment_id == payload.id
    ).first()
    if not gp:
        return {"status": "ignored"}

    gp = refresh_payment_status(db, gp.id)
    handle_gateway_update(db, gateway_payment_id=gp.id, new_status=gp.status)
    db.commit()
    return {"status": "ok"}

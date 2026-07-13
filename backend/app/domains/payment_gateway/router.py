from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.domains.auth.api import get_current_admin
from app.domains.auth.api import User
from .models import GatewayPayment
from .service import refresh_payment_status
from app.domains.payment_status.service import handle_gateway_update
from app.limiter import mollie_webhook_limiter

router = APIRouter(prefix="/payment-gateway", tags=["payment-gateway"])


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    # Admin-only: dit endpoint wordt niet door de publieke frontend gebruikt; een
    # (geraden) payment-id mag geen betaalstatus prijsgeven (#146).
    gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"id": gp.id, "status": gp.status}


@router.post("/webhooks/mollie", status_code=200, dependencies=[Depends(mollie_webhook_limiter)])
def mollie_webhook(id: str = Form(...), db: Session = Depends(get_db)):
    """Mollie calls this when a payment status changes (form-encoded body with 'id')."""
    gp = db.query(GatewayPayment).filter(
        GatewayPayment.provider_payment_id == id
    ).first()
    if not gp:
        return {"status": "ignored"}

    gp = refresh_payment_status(db, gp.id)
    handle_gateway_update(db, gateway_payment_id=gp.id, new_status=gp.status)
    db.commit()
    return {"status": "ok"}

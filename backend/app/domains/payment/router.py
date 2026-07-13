"""Composer-ingang van het payment-component (fase 3, #401): bundelt de
gateway-router (Mollie, webhook) en de status-router (PaymentRecords, refunds)."""
from fastapi import APIRouter

from app.domains.payment.gateway_router import router as gateway_router
from app.domains.payment.status_router import router as status_router

router = APIRouter()
router.include_router(gateway_router)
router.include_router(status_router)

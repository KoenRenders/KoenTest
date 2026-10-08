"""Composer-ingang van het payment-component (fase 3, #401): de gateway-router
(Mollie, webhook). The status router (payment records, refunds) had no caller
but tests and went with CR-13 phase 4b (#1251)."""

from fastapi import APIRouter

from app.domains.payment.gateway_router import router as gateway_router

router = APIRouter()
router.include_router(gateway_router)

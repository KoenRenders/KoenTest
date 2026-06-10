import httpx
from decimal import Decimal
from app.config import settings
from .base import BaseProvider, PaymentResult

MOLLIE_API_BASE = "https://api.mollie.com/v2"

# Map Mollie statuses to our internal statuses
MOLLIE_STATUS_MAP = {
    "open": "pending",
    "pending": "pending",
    "authorized": "pending",
    "expired": "failed",
    "canceled": "cancelled",
    "failed": "failed",
    "paid": "paid",
}


class MollieProvider(BaseProvider):
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.mollie_api_key}"}

    def create_payment(
        self,
        amount: Decimal,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict,
    ) -> PaymentResult:
        if not settings.mollie_api_key:
            raise ValueError("MOLLIE_API_KEY is niet geconfigureerd.")

        # Mollie can't reach localhost/private URLs — omit webhook in that case
        is_local = any(h in webhook_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))
        payload: dict = {
            "amount": {"currency": "EUR", "value": f"{amount:.2f}"},
            "description": description,
            "redirectUrl": redirect_url,
            "metadata": metadata,
        }
        if not is_local:
            payload["webhookUrl"] = webhook_url

        response = httpx.post(
            f"{MOLLIE_API_BASE}/payments",
            json=payload,
            headers=self._headers(),
            timeout=10,
        )
        if not response.is_success:
            raise ValueError(f"Mollie fout ({response.status_code}): {response.text}")
        response.raise_for_status()
        data = response.json()
        return PaymentResult(
            provider_payment_id=data["id"],
            checkout_url=data["_links"]["checkout"]["href"],
            status=MOLLIE_STATUS_MAP.get(data["status"], "pending"),
        )

    def get_payment_status(self, provider_payment_id: str) -> str:
        response = httpx.get(
            f"{MOLLIE_API_BASE}/payments/{provider_payment_id}",
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        mollie_status = response.json()["status"]
        return MOLLIE_STATUS_MAP.get(mollie_status, "pending")

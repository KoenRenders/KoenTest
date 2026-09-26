import logging
from decimal import Decimal

import httpx

from app.config import settings
from app.domains.payment.models import PaymentStatus
from app.kernel.codes import ExternalVocabulary
from .base import BaseProvider, PaymentResult, PaymentStatusResult

logger = logging.getLogger(__name__)

MOLLIE_API_BASE = "https://api.mollie.com/v2"


class MollieStatus(str, ExternalVocabulary):
    """The payment statuses Mollie reports — **their** list, not ours (§B4.10).

    Marked `ExternalVocabulary` rather than given a code table, and the reason
    is operational: Mollie can add a value without our migration, so a foreign
    key on `gateway_payments.status` would make the webhook fail at exactly the
    moment money is moving. What we owe is a mapping to our own vocabulary and
    an explicit branch for the value we do not know.

    `str` mixin on purpose here, unlike our own lists: this enum is built from
    a raw JSON string that arrives over the wire, and it is compared against
    the API's spelling rather than against our code.
    """

    OPEN = "open"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    EXPIRED = "expired"
    CANCELED = "canceled"
    FAILED = "failed"
    PAID = "paid"


#: Their vocabulary to ours. Typed on both sides, so a new member on either
#: side that nobody mapped is visible here instead of in a dictionary of
#: strings that happens to have a hole in it.
MOLLIE_STATUS_MAP: dict[MollieStatus, PaymentStatus] = {
    MollieStatus.OPEN: PaymentStatus.PENDING,
    MollieStatus.PENDING: PaymentStatus.PENDING,
    MollieStatus.AUTHORIZED: PaymentStatus.PENDING,
    MollieStatus.EXPIRED: PaymentStatus.FAILED,
    MollieStatus.CANCELED: PaymentStatus.CANCELLED,
    MollieStatus.FAILED: PaymentStatus.FAILED,
    MollieStatus.PAID: PaymentStatus.PAID,
}


def our_status(reported: str) -> PaymentStatus:
    """Translate what Mollie reports into our own payment status.

    **An unknown value logs and stays `pending`; it never raises.** That is the
    whole point of not giving this column a code table. Mollie adding a status
    must not turn into a five hundred on the webhook — the record simply stays
    where it was, and the next poll or the next webhook settles it. Raising
    here would mean losing a payment notification over a word we had not seen
    before.
    """
    try:
        return MOLLIE_STATUS_MAP[MollieStatus(reported)]
    except ValueError:
        logger.warning(
            "unknown Mollie status %r — leaving the record pending; add it to "
            "MollieStatus and MOLLIE_STATUS_MAP if it is a real state", reported)
        return PaymentStatus.PENDING


class MollieProvider(BaseProvider):
    def __init__(self, api_key: str | None = None):
        # Per-tenant Mollie-key (fase 5b, #406); default de globale env-key.
        self._api_key = api_key or settings.mollie_api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    def create_payment(
        self,
        amount: Decimal,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict,
    ) -> PaymentResult:
        if not self._api_key:
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
            status=our_status(data["status"]).value,
        )

    def get_payment_details(self, provider_payment_id: str) -> PaymentStatusResult:
        response = httpx.get(
            f"{MOLLIE_API_BASE}/payments/{provider_payment_id}",
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        amount = data.get("amount") or {}
        value = amount.get("value")
        return PaymentStatusResult(
            status=our_status(data["status"]).value,
            amount=Decimal(str(value)) if value is not None else None,
            currency=amount.get("currency"),
        )

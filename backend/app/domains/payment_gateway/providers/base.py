from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class PaymentResult:
    provider_payment_id: str
    checkout_url: str
    status: str


@dataclass
class PaymentStatusResult:
    """Status + (indien gerapporteerd) het bedrag/valuta van de provider, zodat we
    bij 'paid' het werkelijke bedrag kunnen vergelijken met het verwachte (#92)."""
    status: str
    amount: Optional[Decimal] = None
    currency: Optional[str] = None


class BaseProvider(ABC):
    @abstractmethod
    def create_payment(
        self,
        amount: Decimal,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict,
    ) -> PaymentResult:
        ...

    @abstractmethod
    def get_payment_details(self, provider_payment_id: str) -> PaymentStatusResult:
        ...

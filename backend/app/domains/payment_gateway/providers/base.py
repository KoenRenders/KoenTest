from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PaymentResult:
    provider_payment_id: str
    checkout_url: str
    status: str


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
    def get_payment_status(self, provider_payment_id: str) -> str:
        ...

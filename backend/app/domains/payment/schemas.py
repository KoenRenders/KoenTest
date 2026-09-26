from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

from app.domains.mdm.api import PaymentMethod
from app.domains.payment.models import PayableType, PaymentStatus, PaymentType

# CR-12 fase 1: form → router (Pydantic). Deze velden dragen nu de enums, dus
# een onbekende waarde is een 422 met de naam van het veld in plaats van een rij
# die pas op de foreign key struikelt. De JSON blijft identiek: Pydantic
# serialiseert een enum als zijn waarde, en de waarden zijn de codes.


class PaymentRecordCreate(BaseModel):
    payable_type: PayableType
    payable_id: int
    amount: Decimal
    method: PaymentMethod
    redirect_url: Optional[str] = None
    description: Optional[str] = None


class PaymentRecordResponse(BaseModel):
    id: str
    payable_type: PayableType
    payable_id: int
    amount: Decimal
    amount_paid: Optional[Decimal] = None
    method: PaymentMethod
    status: PaymentStatus
    type: PaymentType = PaymentType.CHARGE
    refund_of_id: Optional[str] = None
    note: Optional[str] = None
    paid_at: Optional[datetime] = None
    checkout_url: Optional[str] = None
    structured_communication: Optional[str] = None  # OGM voor overschrijving (#224)
    created_at: datetime

    model_config = {"from_attributes": True}

    # CR-12 §B4.7: een template vergelijkt nooit een code. Deze vier zijn wat
    # de betalingenlijst echt wil weten; ze stonden er als
    # `r.status == "paid"` en waren daar niet te testen. Met een gewone `Enum`
    # zouden ze bovendien stil onwaar geworden zijn — de gevaarlijkste vorm van
    # deze wijziging, want er gaat niets stuk.
    @property
    def is_paid(self) -> bool:
        return self.status is PaymentStatus.PAID

    @property
    def is_refund(self) -> bool:
        return self.type is PaymentType.REFUND

    @property
    def is_online(self) -> bool:
        return self.method is PaymentMethod.ONLINE

    @property
    def is_registration(self) -> bool:
        return self.payable_type is PayableType.REGISTRATION

    @property
    def status_code(self) -> str:
        """De ruwe code, voor een `x-data` die er een formulierwaarde van maakt."""
        return self.status.value


class RefundCreate(BaseModel):
    """Terugbetaling op een charge-record. ``amount`` is het positieve te
    refunden bedrag; de service slaat het op als negatief record."""
    amount: Decimal
    note: Optional[str] = None
    method: PaymentMethod = PaymentMethod.TRANSFER


class RegistrationBalance(BaseModel):
    total_due: Decimal
    total_paid: Decimal
    total_refunded: Decimal
    balance: Decimal


class EnrichedPaymentRecord(PaymentRecordResponse):
    description: Optional[str] = None
    contact_name: Optional[str] = None
    activity_id: Optional[int] = None
    component_id: Optional[int] = None      # voor de penningmeester-filter (#90)
    component_name: Optional[str] = None
    membership_year: Optional[int] = None   # lidgeld-jaar voor de jaarfilter (#308)
    items: list = []


class PaymentRecordUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    amount_paid: Optional[Decimal] = None
    note: Optional[str] = None



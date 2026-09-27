from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

from app.domains.mdm.api import PaymentMethod
from app.domains.payment.models import PayableType, PaymentStatus, PaymentType

# CR-12 phase 1: form → router (Pydantic). These fields now carry the enums, so
# an unknown value is a 422 naming the field instead of a row that only trips
# over the foreign key later. The JSON stays identical: Pydantic serialises an
# enum as its value, and the values are the codes.


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

    # CR-12 §B4.7: a template never compares a code. These four are what the
    # payments list really wants to know; they used to be there as
    # `r.status == "paid"` and could not be tested there. With a plain `Enum`
    # they would moreover have turned silently false — the most dangerous form
    # of this change, because nothing breaks.
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
        """The raw code, for an `x-data` that turns it into a form value."""
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



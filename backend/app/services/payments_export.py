"""ODS-export van betalingen & vorderingen (#307, admin-betalingenpagina).

Eén blad met elk betaalrecord (vordering of terugbetaling) + de 'waarvoor'-context
(inschrijver + activiteit, of hoofdlid + Lidmaatschap <jaar>), met een totaalrij
te betalen / betaald / saldo (netto — refunds zijn negatieve records).

De export **volgt het actieve filter** van de pagina (context + status), zodat de
.ods exact toont wat de penningmeester op het scherm ziet. De filterlogica spiegelt
het pure predicaat in de frontend (@/lib/paymentFilters).

Bevat persoons- en financiële data: enkel admin/penningmeester, nooit in de repo.
"""
from decimal import Decimal
from typing import Optional

from app.domains.payment_status.models import PaymentRecord
from app.services.ods_export import build_ods

_METHOD = {"online": "Online", "transfer": "Overschrijving", "cash": "Cash"}
_STATUS = {"pending": "In afwachting", "paid": "Betaald", "failed": "Mislukt", "cancelled": "Geannuleerd"}
_TYPE = {"charge": "Vordering", "refund": "Terugbetaling"}


def _enrich(db, r) -> tuple[str, Optional[int], Optional[int]]:
    """Geeft (label, membership_year, component_id) voor een betaalrecord.

    Verrijking haalt bewust óók soft-deleted entiteiten op (een betaling is een
    financieel feit; toon de bewaarde naam)."""
    def q(model):
        return db.query(model).execution_options(include_deleted=True)

    if r.payable_type == "registration":
        from app.models.activity import Registration, Activity
        reg = q(Registration).filter(Registration.id == r.payable_id).first()
        if reg:
            act = q(Activity).filter(Activity.id == reg.activity_id).first()
            parts = [reg.contact_name, act.name if act else None]
            label = " — ".join(p for p in parts if p) or f"Inschrijving #{r.payable_id}"
            return label, None, reg.component_id
    elif r.payable_type == "membership":
        from app.models.member import Membership
        from app.domains.mdm.api import MemberPerson, Person
        ms = q(Membership).filter(Membership.id == r.payable_id).first()
        name = None
        year = ms.year if ms else None
        if ms:
            mp = q(MemberPerson).filter(
                MemberPerson.member_id == ms.member_id,
                MemberPerson.relation_type == "HOOFDLID",
            ).first()
            if mp:
                p = q(Person).filter(Person.id == mp.person_id).first()
                if p:
                    name = f"{p.first_name} {p.last_name}"
        period = f"Lidmaatschap {ms.year}" if ms else "Lidmaatschap"
        return " — ".join(x for x in (name, period) if x), year, None
    return f"{r.payable_type} #{r.payable_id}", None, None


def _passes_filter(r, membership_year, component_id, context: str, status: str) -> bool:
    """Spiegelt matchesPaymentFilter (@/lib/paymentFilters): context (#90/#308) + status (#83)."""
    amount = Decimal(str(r.amount or 0))
    paid = Decimal(str(r.amount_paid)) if r.amount_paid is not None else Decimal("0")
    saldo = amount - paid

    # Context: lidmaatschap (alle jaren of één jaar) of één activiteit-onderdeel.
    if context == "membership" and r.payable_type != "membership":
        return False
    if context.startswith("year-"):
        if r.payable_type != "membership" or membership_year != int(context[5:]):
            return False
    if context.startswith("comp-"):
        if r.payable_type != "registration" or component_id != int(context[5:]):
            return False

    # Status: betaald/openstaand uit het saldo (betaald = waarheid, #198).
    if status == "pending":
        return r.status == "pending"
    if status == "paid":
        return r.status == "paid"
    if status == "openstaand":
        return saldo > Decimal("0.001")
    return True


def build_payments_export_ods(db, context: str = "all", status: str = "all") -> bytes:
    """Bouw de .ods met de (gefilterde) betalingen & vorderingen + totaalrij. Bytes terug."""
    records = db.query(PaymentRecord).order_by(PaymentRecord.created_at.desc()).all()

    headers = ["Waarvoor", "Soort", "Type", "Betaalwijze", "Status", "Mededeling (OGM)",
               "Te betalen", "Betaald", "Saldo", "Betaald op", "Notitie"]
    rows = []
    tot_due = Decimal("0")
    tot_paid = Decimal("0")
    for r in records:
        label, membership_year, component_id = _enrich(db, r)
        if not _passes_filter(r, membership_year, component_id, context, status):
            continue
        amount = Decimal(str(r.amount or 0))
        paid = Decimal(str(r.amount_paid)) if r.amount_paid is not None else Decimal("0")
        tot_due += amount
        tot_paid += paid
        rows.append([
            label,
            "Lidgeld" if r.payable_type == "membership" else "Activiteit",
            _TYPE.get(r.type, r.type or ""),
            _METHOD.get(r.method, r.method or ""),
            _STATUS.get(r.status, r.status or ""),
            r.structured_communication or "",
            float(amount),
            float(paid),
            float(amount - paid),
            r.paid_at.date().isoformat() if r.paid_at else "",
            r.note or "",
        ])
    rows.append(["Totaal", "", "", "", "", "",
                 float(tot_due), float(tot_paid), float(tot_due - tot_paid), "", ""])

    col_widths = [6.0, 2.5, 3.0, 3.5, 3.5, 4.5, 3.0, 3.0, 3.0, 3.0, 6.0]
    return build_ods("Betalingen en vorderingen", headers, rows,
                     col_widths=col_widths, bold_last_row=True)

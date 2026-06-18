"""OpenDocument (.ods) export per activiteit-onderdeel (#85/#200).

Genereert per onderdeel (ActivitySubRegistration) één rij per inschrijving: aantallen
per product + financials (verschuldigd, betaald online/overschrijving-cash,
terugbetaald, saldo) zoals ze NU in de DB staan, met een totaalrij. De live DB is de
bron van waarheid.

Bevat persoons- en financiële data: enkel admin, nooit in de repo.
"""
from decimal import Decimal
from typing import Tuple

from app.domains.payment_status.service import get_records_for
from app.services.registration_totals import compute_registration_total
from app.services.ods_export import build_ods

_METHOD_LABELS = {"ONLINE": "Online", "TRANSFER": "Overschrijving", "CASH": "Cash"}


def _registration_financials(db, reg) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """(verschuldigd, betaald_online, betaald_offline, terugbetaald, saldo)."""
    due, _ = compute_registration_total(reg)
    records = get_records_for(db, "registration", reg.id)
    paid_online = Decimal("0")
    paid_offline = Decimal("0")
    refunded = Decimal("0")
    for r in records:
        if r.amount_paid is None:
            continue
        amt = Decimal(str(r.amount_paid))
        if r.type == "refund":
            refunded += -amt  # refund-amount_paid is negatief → terugbetaald positief
        elif r.method == "online":
            paid_online += amt
        else:  # transfer / cash
            paid_offline += amt
    net = paid_online + paid_offline - refunded
    return due, paid_online, paid_offline, refunded, due - net


def _status_label(due: Decimal, saldo: Decimal) -> str:
    if saldo > Decimal("0.005"):
        return "Open"
    if saldo < Decimal("-0.005"):
        return "Te veel betaald"
    return "Vereffend" if due > 0 else "Gratis"


def build_component_export_ods(db, activity, component) -> bytes:
    """Bouw de .ods-export voor één onderdeel en geef de bytes terug."""
    products = list(component.products)
    registrations = [r for r in activity.registrations if r.component_id == component.id]

    headers = (
        ["Naam"]
        + [p.name for p in products]
        + ["Verschuldigd", "Betaald online", "Betaald overschr./cash",
           "Terugbetaald", "Saldo", "Betaalwijze", "Status", "Opmerkingen"]
    )

    product_totals = [0] * len(products)
    money_totals = [Decimal("0")] * 5
    rows = []
    for reg in registrations:
        qty_by_product = {}
        for item in reg.items:
            qty_by_product[item.product_id] = qty_by_product.get(item.product_id, 0) + item.quantity
        due, online, offline, refunded, saldo = _registration_financials(db, reg)

        row = [reg.contact_name or "—"]
        for idx, p in enumerate(products):
            q = qty_by_product.get(p.id, 0)
            product_totals[idx] += q
            row.append(q)
        for i, v in enumerate([due, online, offline, refunded, saldo]):
            money_totals[i] += v
            row.append(float(v))
        row.append(_METHOD_LABELS.get(reg.payment_method or "", reg.payment_method or "—"))
        row.append(_status_label(due, saldo))
        row.append(reg.remarks or "")
        rows.append(row)

    rows.append(["Totaal"] + product_totals + [float(v) for v in money_totals] + ["", "", ""])

    col_widths = [4.5] + [3.0] * len(products) + [3.5, 3.5, 4.0, 3.5, 3.0, 3.5, 3.0, 6.0]
    return build_ods(component.name or "Onderdeel", headers, rows,
                     col_widths=col_widths, bold_last_row=True)

"""OpenDocument (.ods) export per activiteit-onderdeel (#85/#200).

Sheet 1 ("<onderdeel>"): per inschrijving aantallen per product + financials
(verschuldigd, betaald online/overschrijving-cash, terugbetaald, saldo) met een
totaalrij. Sheet 2 ("Betalingen en vorderingen", #307): alle losse betaalrecords
(vorderingen + terugbetalingen) van die inschrijvingen, met een totaalrij
(te betalen / betaald / saldo). De live DB is de bron van waarheid.

Bevat persoons- en financiële data: enkel admin, nooit in de repo.
"""
from decimal import Decimal
from typing import Tuple

from app.domains.activities.totals import compute_registration_total
from app.kernel.ods import build_ods_multi
from app.i18n import _

_METHOD_LABELS = {"ONLINE": "Online", "TRANSFER": "Overschrijving", "CASH": "Cash"}
# Betaalrecords gebruiken kleine letters (PaymentRecord.method/status/type).
_RECORD_METHOD_LABELS = {"online": "Online", "transfer": "Overschrijving", "cash": "Cash"}
_RECORD_STATUS_LABELS = {
    "pending": "In afwachting", "paid": "Betaald", "failed": "Mislukt", "cancelled": "Geannuleerd",
}
_RECORD_TYPE_LABELS = {"charge": "Vordering", "refund": "Terugbetaling"}


def _registration_financials(db, reg) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    # Lazy import: doorbreekt de kringloop payment.api -> ... -> activities.api -> export.
    from app.domains.payment.api import get_records_for
    """(verschuldigd, betaald_online, betaald_offline, terugbetaald, saldo)."""
    due, _extra = compute_registration_total(reg)
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
        return _("Open")
    if saldo < Decimal("-0.005"):
        return _("Te veel betaald")
    return _("Vereffend") if due > 0 else _("Gratis")


def _payments_sheet(db, registrations) -> dict:
    """Sheet 2 (#307): alle betaalrecords (vorderingen + terugbetalingen) van de
    inschrijvingen, gegroepeerd per inschrijver, met een totaalrij (te betalen /
    betaald / saldo). Dit zijn dezelfde 'zichtbare' details als op de admin-
    betalingenpagina, maar gefilterd op dit onderdeel."""
    headers = [_("Inschrijver"), _("Type"), _("Betaalwijze"), _("Status"), _("Mededeling (OGM)"),
               _("Te betalen"), _("Betaald"), _("Saldo"), _("Betaald op"), _("Notitie")]
    rows = []
    tot_due = Decimal("0")
    tot_paid = Decimal("0")
    for reg in registrations:
        from app.domains.payment.api import get_records_for
        for r in get_records_for(db, "registration", reg.id):
            amount = Decimal(str(r.amount or 0))
            paid = Decimal(str(r.amount_paid)) if r.amount_paid is not None else Decimal("0")
            tot_due += amount
            tot_paid += paid
            rows.append([
                reg.contact_name or "—",
                _(_RECORD_TYPE_LABELS.get(r.type, r.type or "")),
                _(_RECORD_METHOD_LABELS.get(r.method, r.method or "")),
                _(_RECORD_STATUS_LABELS.get(r.status, r.status or "")),
                r.structured_communication or "",
                float(amount),
                float(paid),
                float(amount - paid),
                r.paid_at.date().isoformat() if r.paid_at else "",
                r.note or "",
            ])
    rows.append([_("Totaal"), "", "", "", "",
                 float(tot_due), float(tot_paid), float(tot_due - tot_paid), "", ""])
    col_widths = [4.5, 3.0, 3.5, 3.5, 4.5, 3.0, 3.0, 3.0, 3.0, 6.0]
    return {"name": _("Betalingen en vorderingen"), "headers": headers, "rows": rows,
            "col_widths": col_widths, "bold_last_row": True}


def build_component_export_ods(db, activity, component) -> bytes:
    """Bouw de .ods-export voor één onderdeel (2 bladen) en geef de bytes terug."""
    products = list(component.products)
    registrations = [r for r in activity.registrations if r.component_id == component.id]

    headers = (
        [_("Naam"), _("E-mail"), _("Mobiel")]
        + [p.name for p in products]
        + [_("Verschuldigd"), _("Betaald online"), _("Betaald overschr./cash"),
           _("Terugbetaald"), _("Saldo"), _("Betaalwijze"), _("Status"), _("Opmerkingen")]
    )

    product_totals = [0] * len(products)
    money_totals = [Decimal("0")] * 5
    rows = []
    for reg in registrations:
        qty_by_product: dict[int, int] = {}
        for item in reg.items:
            qty_by_product[item.product_id] = qty_by_product.get(item.product_id, 0) + item.quantity
        due, online, offline, refunded, saldo = _registration_financials(db, reg)

        row = [reg.contact_name or "—", reg.contact_email or "", reg.phone or ""]
        for idx, p in enumerate(products):
            q = qty_by_product.get(p.id, 0)
            product_totals[idx] += q
            row.append(q)
        for i, v in enumerate([due, online, offline, refunded, saldo]):
            money_totals[i] += v
            row.append(float(v))
        row.append(_(_METHOD_LABELS.get(reg.payment_method or "", reg.payment_method or "—")))
        row.append(_status_label(due, saldo))
        row.append(reg.remarks or "")
        rows.append(row)

    rows.append([_("Totaal"), "", ""] + product_totals + [float(v) for v in money_totals] + ["", "", ""])

    col_widths = [4.5, 5.0, 3.5] + [3.0] * len(products) + [3.5, 3.5, 4.0, 3.5, 3.0, 3.5, 3.0, 6.0]
    sheet1 = {"name": component.name or "Onderdeel", "headers": headers, "rows": rows,
              "col_widths": col_widths, "bold_last_row": True}
    sheet2 = _payments_sheet(db, registrations)
    return build_ods_multi([sheet1, sheet2])

"""ODS-export van betalingen & vorderingen (#307, admin-betalingenpagina).

Eén blad met elk betaalrecord (vordering of terugbetaling) + de 'waarvoor'-context
(inschrijver + activiteit, of hoofdlid + Lidmaatschap <jaar>), met een totaalrij
te betalen / betaald / saldo (netto — refunds zijn negatieve records).

De export **volgt het actieve filter** van de pagina (context + status + zoekterm),
zodat de .ods exact toont wat de penningmeester op het scherm ziet. Sinds #635 is
dat geen spiegeling meer maar dezelfde functie: `payment.service.matches_filter`.
De vorige twee kopieën waren al uit elkaar gelopen — het scherm kende `failed`,
`cancelled` en vrij zoeken, de export niet.

Bevat persoons- en financiële data: enkel admin/penningmeester, nooit in de repo.
(verhuisd uit app/services/payments_export.py, #444)
"""

from decimal import Decimal

from app.domains.payment.api import PayableType, PaymentRecord
from app.domains.payment.describers import describe_many, describer, in_filter_context
from app.kernel.codes import code_label
from app.kernel.ods import build_ods

# CR-12 phase 1: `_METHOD`, `_STATUS` and `_TYPE` used to stand here — three
# Dutch dictionaries that said the same as the screens next to them, with their
# own deviations. The labels now come from the label tables, so the export and
# the screen show the same word by definition (AC3).


def build_payments_export_ods(
    db,
    context: str = "all",
    status: str = "all",
    q: str = "",
    openstaand: bool = False,
    registration_id: str = "",
    payables=None,
    zicht: str = "alle",
) -> bytes:
    """Bouw de .ods met de (gefilterde) betalingen & vorderingen + totaalrij. Bytes terug.

    De filter is `payment.service.matches_filter` — dezelfde functie die het scherm
    gebruikt (#635). `membership_year` en `component_id` komen hier uit `_enrich`,
    want de rauwe records dragen ze niet.
    """
    from app.domains.payment.service import matches_filter, matches_zicht

    records = db.query(PaymentRecord).order_by(PaymentRecord.created_at.desc()).all()
    # P13 (golf 5, #913): de recordscope geldt ook hier — de exportknop draagt
    # haar mee, anders exporteert een gescopeerd scherm stil álle betalingen.
    scope = (registration_id or "").strip()
    if scope:
        records = [
            r
            for r in records
            if r.payable_type == PayableType.REGISTRATION and str(r.payable_id) == scope
        ]
    if payables is not None:
        records = [r for r in records if (r.payable_type, r.payable_id) in payables]

    headers = [
        "Waarvoor",
        "Soort",
        "Type",
        "Betaalwijze",
        "Status",
        "Mededeling (OGM)",
        "Te betalen",
        "Betaald",
        "Saldo",
        "Betaald op",
        "Notitie",
    ]
    rows = []
    tot_due = Decimal("0")
    tot_paid = Decimal("0")
    # CR-21 phase 0 (#1748): the first two columns and the place in the filter tree
    # come from the payable's describer, as on the screen — one batch per type.
    described = describe_many(db, {(r.payable_type, r.payable_id) for r in records})
    for r in records:
        what = described[(r.payable_type, r.payable_id)]
        if not in_filter_context(r.payable_type, what.filter_context, context):
            continue
        if not matches_filter(r, status=status, q=q, openstaand=openstaand):
            continue
        # Golf 10 (#913): het actieve statustab-zicht geldt ook in de export —
        # anders exporteert "Openstaand" stil alles.
        if not matches_zicht(r, zicht):
            continue
        amount = Decimal(str(r.amount or 0))
        paid = Decimal(str(r.amount_paid)) if r.amount_paid is not None else Decimal("0")
        tot_due += amount
        tot_paid += paid
        rows.append(
            [
                what.export_label,
                describer(r.payable_type).export_kind,
                code_label("payment_type", r.type),
                code_label("payment_method", r.method),
                code_label("payment_status", r.status),
                r.structured_communication or "",
                float(amount),
                float(paid),
                float(amount - paid),
                r.paid_at.date().isoformat() if r.paid_at else "",
                r.note or "",
            ]
        )
    rows.append(
        [
            "Totaal",
            "",
            "",
            "",
            "",
            "",
            float(tot_due),
            float(tot_paid),
            float(tot_due - tot_paid),
            "",
            "",
        ]
    )

    col_widths = [6.0, 2.5, 3.0, 3.5, 3.5, 4.5, 3.0, 3.0, 3.0, 3.0, 6.0]
    return build_ods(
        "Betalingen en vorderingen", headers, rows, col_widths=col_widths, bold_last_row=True
    )

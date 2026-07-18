"""Server-rendered betalingen-scherm (fase 3b, #401 — §21): de matrix
(betalingen & vorderingen met context-/statusfilter), handmatig bevestigen,
refunds (FINANCE) en de .ods-export.

Hergebruikt de bestaande router-/servicefuncties — geen dubbele
businesslogica. Rollen: iedereen met ADMIN of FINANCE mag kijken en
exporteren; bevestigen en terugbetalen is FINANCE-only (financiële
scheiding, #83).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, csrf_token_for, get_user_roles, require_finance_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/betalingen")


def _require_finance(db: Session, email: str) -> None:
    """Betaal-MUTATIES (bevestigen/terugbetalen/bewerken) zijn FINANCE-only —
    financiële scheiding (#83). OPERATOR (platform-superuser) mag alles (#530)."""
    if not ({"FINANCE", "OPERATOR"} & set(get_user_roles(db, email))):
        raise HTTPException(status_code=403,
                            detail=_("Alleen FINANCE mag betalingen wijzigen."))


def _ctx(request: Request, db: Session, email: str) -> dict:
    from app.domains.payment.status_router import list_all_payment_records

    context = (request.query_params.get("context") or "all").strip()
    status = (request.query_params.get("status") or "all").strip()
    records = list_all_payment_records(db=db, _viewer=None)  # type: ignore[arg-type]

    # Filter-opties opbouwen: onderdelen (per activiteit) + lidmaatschapjaren.
    componenten: dict = {}
    jaren: set = set()
    for r in records:
        if r.component_id is not None:
            label = r.description or _("Activiteit")
            if r.component_name:
                label = f"{label} — {r.component_name}"
            componenten.setdefault(r.component_id, label)
        if r.membership_year is not None:
            jaren.add(r.membership_year)

    def _zichtbaar(r) -> bool:
        # Context (zelfde conventie als de export-filter): membership / year-<n> /
        # comp-<id>. Zo werkt de export-link met dezelfde parameters.
        if context == "membership" and r.payable_type != "membership":
            return False
        if context.startswith("year-"):
            if r.payable_type != "membership" or r.membership_year != int(context[5:]):
                return False
        if context.startswith("comp-") and r.component_id != int(context[5:]):
            return False
        # Status: openstaand uit het saldo (betaald = waarheid, #198).
        amount = Decimal(str(r.amount or 0))
        paid = Decimal(str(r.amount_paid or 0))
        if status == "openstaand":
            return (amount - paid) > Decimal("0.001")
        if status in ("pending", "paid", "failed", "cancelled"):
            return r.status == status
        return True

    zichtbaar = [r for r in records if _zichtbaar(r)]

    def _rij(recs) -> dict:
        due = sum((Decimal(str(x.amount or 0)) for x in recs), Decimal("0"))
        paid = sum((Decimal(str(x.amount_paid or 0)) for x in recs), Decimal("0"))
        return {"due": due, "paid": paid, "saldo": due - paid}

    charges = [r for r in zichtbaar if r.type != "refund"]
    refunds = [r for r in zichtbaar if r.type == "refund"]
    m_bet, m_ref = _rij(charges), _rij(refunds)
    m_net = {k: m_bet[k] - m_ref[k] for k in ("due", "paid", "saldo")}

    # Kaarten: elke charge met haar bijhorende refunds (refund_of_id) samen (#455).
    refunds_by_parent: dict = {}
    for r in refunds:
        if r.refund_of_id:
            refunds_by_parent.setdefault(r.refund_of_id, []).append(r)
    charge_ids = {r.id for r in charges}
    kaarten = [(r, refunds_by_parent.get(r.id, [])) for r in charges]
    # Wees-refunds (charge niet zichtbaar door de filter) apart tonen.
    kaarten += [(r, []) for r in refunds
                if not r.refund_of_id or r.refund_of_id not in charge_ids]
    kaarten.sort(key=lambda p: p[0].created_at, reverse=True)

    return {
        "records": zichtbaar, "kaarten": kaarten, "context": context, "status": status,
        "componenten": sorted(componenten.items(), key=lambda kv: kv[1]),
        "jaren": sorted(jaren, reverse=True),
        "matrix": {"betalingen": m_bet, "terugbetalingen": m_ref, "netto": m_net},
        "is_finance": "FINANCE" in get_user_roles(db, email),
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/betalingen", response_class=HTMLResponse)
def betalingen_page(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui)):
    # Role-aware nav (#530): een FINANCE-only gebruiker (geen ADMIN/OPERATOR) ziet
    # enkel de schermen die hij mag openen — anders 403't elke andere nav-link.
    nav = admin_nav("/admin/betalingen", roles=get_user_roles(db, email))
    return templates.TemplateResponse(request, "betalingen.html",
                                      {"nav_items": nav, **_ctx(request, db, email)})


@router.get("/admin/betalingen/lijst", response_class=HTMLResponse)
def betalingen_lijst(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_finance_ui)):
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.get("/admin/betalingen/export")
def betalingen_export(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_finance_ui)):
    from app.domains.payment.exports import build_payments_export_ods

    context = (request.query_params.get("context") or "all").strip()
    status = (request.query_params.get("status") or "all").strip()
    content = build_payments_export_ods(db, context=context, status=status)
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": 'attachment; filename="betalingen-en-vorderingen.ods"'},
    )


@router.post("/admin/betalingen/{record_id}/bevestigen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_bevestigen(record_id: str, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_finance_ui),
                        note: str = Form("")):
    from app.domains.payment.api import confirm_manual_payment

    _require_finance(db, email)
    try:
        confirm_manual_payment(db, record_id, note.strip() or None, actor=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/refund", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_refund(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    amount: str = Form(""), note: str = Form("")):
    from app.domains.payment.api import create_refund

    _require_finance(db, email)
    try:
        bedrag = Decimal(amount.replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))
    try:
        create_refund(db, record_id, bedrag, note=note.strip() or None, actor=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/bijwerken", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_bijwerken(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui),
                       amount_paid: str = Form(""), note: str = Form("")):
    """Betaald bedrag invullen + als betaald bevestigen (#455)."""
    from app.domains.payment.api import confirm_manual_payment

    _require_finance(db, email)
    bedrag = None
    if amount_paid.strip():
        try:
            bedrag = Decimal(amount_paid.replace(",", "."))
        except (InvalidOperation, AttributeError):
            raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))
    try:
        confirm_manual_payment(db, record_id, note.strip() or None,
                               actor=email, amount_paid=bedrag)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/bewerken", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_bewerken(record_id: str, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_finance_ui),
                      status: str = Form(""), amount_paid: str = Form(""),
                      note: str = Form("")):
    """Geünificeerde 'Bewerken' (#515): status + betaald bedrag + opmerking in één
    form, voor charges én refunds (zo registreer je op een refund de effectief
    uitbetaalde som). Hergebruikt de gedeelde service-regel `edit_payment_record`,
    zodat de admin-UI en de JSON-API dezelfde validatie delen."""
    from app.domains.payment.api import edit_payment_record

    _require_finance(db, email)
    bedrag = None
    if amount_paid.strip():
        try:
            bedrag = Decimal(amount_paid.replace(",", "."))
        except (InvalidOperation, AttributeError):
            raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))
    try:
        edit_payment_record(db, record_id, status=status.strip() or None,
                            amount_paid=bedrag, note=note.strip() or None, actor=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/verversen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verversen(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui)):
    """Mollie-status ophalen en toepassen (handmatige tegenhanger van de webhook, #455)."""
    from app.domains.payment.api import refresh_record_status

    _require_finance(db, email)
    try:
        refresh_record_status(db, record_id, actor=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/status", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_status(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    status: str = Form(...), note: str = Form("")):
    """Vrije status-correctie door de penningmeester (#455)."""
    from app.domains.payment.api import set_payment_status

    _require_finance(db, email)
    try:
        set_payment_status(db, record_id, status.strip(), actor=email,
                           note=note.strip() or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.post("/admin/betalingen/{record_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verwijderen(record_id: str, request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_finance_ui),
                         note: str = Form("")):
    """Betaal-/terugbetaalrecord verwijderen (soft-delete, uit het saldo, #455).
    Corrigeert ook een foute refund."""
    from app.domains.payment.api import void_payment_record

    _require_finance(db, email)
    try:
        void_payment_record(db, record_id, actor=email, note=note.strip() or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))

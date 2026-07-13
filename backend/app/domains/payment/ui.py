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
    SESSION_COOKIE, csrf_token_for, get_user_roles, require_admin_ui, require_csrf,
)
from app.ui import templates

router = APIRouter(include_in_schema=False)

NAV = [
    {"href": "/admin/werkbank", "label": "Werkbank", "active": False},
    {"href": "/admin/activiteiten", "label": "Activiteiten", "active": False},
    {"href": "/admin/leden", "label": "Leden", "active": False},
    {"href": "/admin/betalingen", "label": "Betalingen", "active": True},
    {"href": "/admin/e-maillog", "label": "E-maillog", "active": False},
]


def _require_finance(db: Session, email: str) -> None:
    if "FINANCE" not in get_user_roles(db, email):
        raise HTTPException(status_code=403,
                            detail="Alleen FINANCE mag betalingen wijzigen.")


def _ctx(request: Request, db: Session, email: str) -> dict:
    from app.domains.payment.status_router import list_all_payment_records

    context = (request.query_params.get("context") or "all").strip()
    status = (request.query_params.get("status") or "all").strip()
    records = list_all_payment_records(db=db, _viewer=None)  # type: ignore[arg-type]
    if context == "activiteiten":
        records = [r for r in records if r.payable_type == "registration"]
    elif context == "lidmaatschappen":
        records = [r for r in records if r.payable_type == "membership"]
    if status != "all":
        records = [r for r in records if r.status == status]

    totaal = sum((r.amount for r in records), Decimal("0"))
    betaald = sum((r.amount_paid or Decimal("0") for r in records), Decimal("0"))
    return {
        "records": records, "context": context, "status": status,
        "totaal": totaal, "betaald": betaald, "saldo": totaal - betaald,
        "is_finance": "FINANCE" in get_user_roles(db, email),
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/betalingen", response_class=HTMLResponse)
def betalingen_page(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "betalingen.html",
                                      {"nav_items": NAV, **_ctx(request, db, email)})


@router.get("/admin/betalingen/lijst", response_class=HTMLResponse)
def betalingen_lijst(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))


@router.get("/admin/betalingen/export")
def betalingen_export(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.services.payments_export import build_payments_export_ods

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
                        email: str = Depends(require_admin_ui),
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
                    email: str = Depends(require_admin_ui),
                    amount: str = Form(""), note: str = Form("")):
    from app.domains.payment.api import create_refund

    _require_finance(db, email)
    try:
        bedrag = Decimal(amount.replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise HTTPException(status_code=400, detail="Ongeldig bedrag.")
    try:
        create_refund(db, record_id, bedrag, note=note.strip() or None, actor=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _ctx(request, db, email))

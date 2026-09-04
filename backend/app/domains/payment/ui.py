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
from app.domains.payment.api import PaymentRecord

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
    q = (request.query_params.get("q") or "").strip()
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

    term = q.lower()

    def _zichtbaar(r) -> bool:
        # Vrij zoeken (#591) op de drie dingen waarmee je een betaling in de hand
        # terugvindt: de naam op het overschrijvingsformulier, de gestructureerde
        # mededeling en de omschrijving. Het staat vóór de andere filters, zodat
        # een zoekterm binnen het gekozen filter zoekt en niet erbuiten.
        if term and not any(term in (waarde or "").lower() for waarde in
                            (r.contact_name, r.structured_communication,
                             r.description, r.component_name)):
            return False
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

    def _mag_verwijderen(rec) -> bool:
        """Dezelfde regel als de guard in status_router (#218/#617-2c).

        Toon de knop niet wanneer de guard hem toch zou weigeren: nu krijg je een
        foutmelding op een knop die er niet had mogen staan.
        """
        if rec.method == "online" and rec.status == "paid":
            return False
        return rec.amount_paid is None or Decimal(str(rec.amount_paid)) == 0

    def _kaart(rec) -> dict:
        """Per kaart de geldregel én of ze verwijderbaar is (#617-2a).

        `Ontvangen`/`Saldo` vallen weg zolang er niets uitbetaald is — € 0,00 tonen
        suggereert dat er al iets gebeurd is. Wél tonen zodra `amount_paid` gevuld is,
        **ongeacht de status**: in bestaande data staan refunds met status `pending`
        én een uitbetaald bedrag (gevolg van de bug uit §2-0b), en die moeten leesbaar
        blijven. De labels zijn op elke kaart dezelfde drie woorden; het teken doet
        het werk.
        """
        betaald = None if rec.amount_paid is None else Decimal(str(rec.amount_paid))
        return {
            "rec": rec,
            "bedrag": Decimal(str(rec.amount)),
            "ontvangen": betaald,
            "saldo": None if betaald is None else Decimal(str(rec.amount)) - betaald,
            "mag_verwijderen": _mag_verwijderen(rec),
        }

    # Groeperen per PAYABLE, niet per charge (#617-2e). De totaalregel heette
    # "Totaal inschrijving" maar telde één charge met haar refunds. Een inschrijving
    # met meerdere charges — precies wat reconcile_registration_charges produceert bij
    # een bestelwijziging — kreeg dus meerdere regels die elk iets anders beweerden en
    # geen van alle de inschrijving telden. Op HDEV: 16 payables met een refund, 17
    # totaalregels, en één ontbrak.
    groepen: list = []
    volgorde: dict = {}
    for charge, eigen_refunds in kaarten:
        sleutel = (charge.payable_type, charge.payable_id)
        if sleutel not in volgorde:
            volgorde[sleutel] = len(groepen)
            groepen.append({"kaarten": [], "records": []})
        groep = groepen[volgorde[sleutel]]
        groep["kaarten"].append((_kaart(charge), [_kaart(x) for x in eigen_refunds]))
        groep["records"].extend([charge] + eigen_refunds)

    for groep in groepen:
        groep["totaal"] = _rij(groep["records"])
        # Eén regel per inschrijving, en alleen als er iets te tellen valt: twee
        # charges zonder refund verdienen net zo goed een totaal.
        groep["toon_totaal"] = len(groep["records"]) > 1

    # Gegroepeerde context-filter (#549): dezelfde grouped_filter-macro als de
    # Werkbank. Heterogene groepen (jaren/onderdelen) → (value, label)-tuples.
    _comp = sorted(componenten.items(), key=lambda kv: kv[1])
    _jaren = sorted(jaren, reverse=True)
    context_top = [("all", _("Alle betalingen")), ("membership", _("Alle lidmaatschappen"))]
    context_groups: dict = {}
    if _jaren:
        context_groups[_("Lidmaatschap per jaar")] = [
            (f"year-{j}", f"{_('Lidgeld')} {j}") for j in _jaren]
    if _comp:
        context_groups[_("Activiteit / onderdeel")] = [
            (f"comp-{cid}", label) for cid, label in _comp]
    return {
        "records": zichtbaar, "groepen": groepen, "context": context,
        # Eén bron voor de statuslabels (#617-2): de filterbalk én de editors in het
        # fragment lezen hieruit, zodat er nergens nog rauwe codes (pending/paid)
        # op het scherm komen. Het fragment wordt ook los gerenderd, dus een
        # {% set %} in betalingen.html zou daar niet bestaan.
        # §2.12: nooit rauwe DB-waarden op het scherm. Per request opgebouwd, zodat
        # _() de taal van de tenant volgt (#630).
        "method_labels": {
            "online": _("Online"), "transfer": _("Overschrijving"),
            "cash": _("Contant"),
        },
        "status_labels": {
            "all": _("Alle statussen"), "openstaand": _("Openstaand saldo"),
            "pending": _("In afwachting"), "paid": _("Betaald"),
            "failed": _("Mislukt"), "cancelled": _("Geannuleerd"),
        },
        "status": status, "q": q,
        "componenten": _comp, "jaren": _jaren,
        "context_top": context_top, "context_groups": context_groups,
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
        # settled=False (#617-2b): de refund ontstaat met een terug te betalen bedrag
        # en een LEEG uitbetaald bedrag, precies zoals een charge ontstaat met een te
        # betalen bedrag en niets ontvangen. De service-default is True — die blijft,
        # want andere aanroepers gebruiken hem — maar de admin-UI geeft nooit meer
        # True mee: aanmaken en afboeken zijn twee stappen.
        create_refund(db, record_id, bedrag, note=note.strip() or None, actor=email,
                      settled=False)
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
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail=_("Betaling niet gevonden."))

    bedrag = None
    if amount_paid.strip():
        try:
            bedrag = Decimal(amount_paid.replace(",", "."))
        except (InvalidOperation, AttributeError):
            raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))
        if record.type == "refund":
            # Tonen mét teken, invoeren zonder (#617-2c). Het negatieve teken is een
            # boekhoudkundige interne conventie zodat sommen kloppen — dat hoort
            # niemand in te typen. De penningmeester moest letterlijk "-40.00"
            # invoeren, want "40.00" werd geweigerd. De servicelaag en haar grenzen
            # ([amount, 0]) blijven ongewijzigd; de invariant-tests hangen daaraan.
            grens = abs(Decimal(str(record.amount)))
            if abs(bedrag) > grens:
                raise HTTPException(status_code=400, detail=_(
                    "Meer dan het terug te betalen bedrag (€ %(bedrag)s)."
                ) % {"bedrag": f"{grens:.2f}"})
            bedrag = -abs(bedrag)
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

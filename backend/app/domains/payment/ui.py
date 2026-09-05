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
    SESSION_COOKIE, csrf_token_for, get_user_roles, require_csrf,
    require_finance_mutation, require_finance_ui,
)
from app.ui import admin_nav, templates
from app.i18n import _
from app.domains.payment.api import PaymentRecord
from app.domains.payment.service import (
    BetalingFout, bevestig_betaling, bewerk_betaling, registreer_terugbetaling,
    ververs_betaalstatus, verwijder_betaling, zet_betaalstatus,
)
from app.domains.payment.viewmodels import BetalingenView

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/betalingen")


def _uitvoeren(bewerking, db: Session, *args, **kwargs):
    """Voer één schermbewerking uit en vertaal haar fouten naar HTTP.

    De servicelaag kent geen HTTP: ze gooit `BetalingFout` bij een invoerfout en
    `LookupError` als het record niet bestaat. Deze route is de enige plek waar
    dat een statuscode wordt (#635 regel 1: de router is de deurwachter, niet de
    rekenmeester).
    """
    try:
        return bewerking(db, *args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc) or _("Betaling niet gevonden."))
    except BetalingFout as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _view(request: Request, db: Session, email: str,
          nav_items: list | None = None) -> BetalingenView:
    """View-model voor het betalingenscherm.

    Filteren, optellen, groeperen en het afleiden van de status gebeuren in
    `payment.service` (#635 punt 4/9), zodat de export exact dezelfde set toont
    als het scherm. Hier blijft alleen het vormgeven over: bedragen per kaart,
    labels en de filteropties.

    Levert sinds #643 een `BetalingenView` i.p.v. een losse dict: wat het scherm
    krijgt staat daarmee getypeerd op één plek, en de template-variabelen-gate kan
    bewijzen dat de template niets vraagt wat hier niet staat.
    """
    from app.domains.payment.api import (
        aggregate, derived_status, enriched_records, filter_records, group_cards,
        may_delete,
    )

    context = (request.query_params.get("context") or "all").strip()
    status = (request.query_params.get("status") or "all").strip()
    q = (request.query_params.get("q") or "").strip()
    records = enriched_records(db)

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

    zichtbaar = filter_records(records, context=context, status=status, q=q)

    charges = [r for r in zichtbaar if r.type != "refund"]
    refunds = [r for r in zichtbaar if r.type == "refund"]
    m_bet, m_ref = aggregate(charges), aggregate(refunds)
    m_net = {k: m_bet[k] - m_ref[k] for k in ("due", "paid", "saldo")}

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
            "mag_verwijderen": may_delete(rec),
            # Afgeleide status uit de service — de template leidt niets meer af.
            "status": derived_status(rec),
        }

    groepen = group_cards(zichtbaar)
    for groep in groepen:
        groep["kaarten"] = [(_kaart(charge), [_kaart(x) for x in eigen_refunds])
                            for charge, eigen_refunds in groep["kaarten"]]

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
    return BetalingenView(
        records=zichtbaar, groepen=groepen, context=context,
        # Eén bron voor de statuslabels (#617-2): de filterbalk én de editors in het
        # fragment lezen hieruit, zodat er nergens nog rauwe codes (pending/paid)
        # op het scherm komen. Het fragment wordt ook los gerenderd, dus een
        # {% set %} in betalingen.html zou daar niet bestaan.
        # §2.12: nooit rauwe DB-waarden op het scherm. Per request opgebouwd, zodat
        # _() de taal van de tenant volgt (#630).
        method_labels={
            "online": _("Online"), "transfer": _("Overschrijving"),
            "cash": _("Contant"),
        },
        status_labels={
            "all": _("Alle statussen"), "openstaand": _("Openstaand saldo"),
            "pending": _("In afwachting"), "paid": _("Betaald"),
            "failed": _("Mislukt"), "cancelled": _("Geannuleerd"),
        },
        # Badge per afgeleide status (service.derived_status). Label + kleur horen
        # bij de weergave en dus hier; wélke status het is, beslist de service —
        # "Deels betaald" werd vroeger in de template zelf uitgerekend (#635-9).
        kaart_status={
            "paid": (_("Vereffend"), "green"),
            "refund_due": (_("Terug te betalen"), "orange"),
            "partial": (_("Deels betaald"), "orange"),
            "pending": (_("Openstaand"), "yellow"),
            "failed": (_("Mislukt"), "red"),
            "cancelled": (_("Geannuleerd"), "gray"),
        },
        status=status, q=q,
        componenten=_comp, jaren=_jaren,
        context_top=context_top, context_groups=context_groups,
        matrix={"betalingen": m_bet, "terugbetalingen": m_ref, "netto": m_net},
        is_finance="FINANCE" in get_user_roles(db, email),
        csrf_token=csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        nav_items=nav_items or [],
    )


@router.get("/admin/betalingen", response_class=HTMLResponse)
def betalingen_page(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui)):
    # Role-aware nav (#530): een FINANCE-only gebruiker (geen ADMIN/OPERATOR) ziet
    # enkel de schermen die hij mag openen — anders 403't elke andere nav-link.
    nav = admin_nav("/admin/betalingen", roles=get_user_roles(db, email))
    return templates.TemplateResponse(
        request, "betalingen.html",
        _view(request, db, email, nav_items=nav).as_context())


@router.get("/admin/betalingen/lijst", response_class=HTMLResponse)
def betalingen_lijst(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_finance_ui)):
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


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
    require_finance_mutation(db, email)
    _uitvoeren(bevestig_betaling, db, record_id, note=note, actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


@router.post("/admin/betalingen/{record_id}/refund", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_refund(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    amount: str = Form(""), note: str = Form("")):
    require_finance_mutation(db, email)
    _uitvoeren(registreer_terugbetaling, db, record_id, amount=amount, note=note,
               actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


@router.post("/admin/betalingen/{record_id}/bijwerken", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_bijwerken(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui),
                       amount_paid: str = Form(""), note: str = Form("")):
    """Betaald bedrag invullen + als betaald bevestigen (#455)."""
    require_finance_mutation(db, email)
    _uitvoeren(bevestig_betaling, db, record_id, note=note, amount_paid=amount_paid,
               actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


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
    require_finance_mutation(db, email)
    # Het omdraaien van het teken bij een terugbetaling en de bovengrens erop
    # stonden hier; ze bepalen hoeveel geld er terugvloeit en horen dus in de
    # service (#635-I).
    _uitvoeren(bewerk_betaling, db, record_id, status=status,
               amount_paid=amount_paid, note=note, actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


@router.post("/admin/betalingen/{record_id}/verversen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verversen(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui)):
    """Mollie-status ophalen en toepassen (handmatige tegenhanger van de webhook, #455)."""
    require_finance_mutation(db, email)
    _uitvoeren(ververs_betaalstatus, db, record_id, actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


@router.post("/admin/betalingen/{record_id}/status", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_status(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    status: str = Form(...), note: str = Form("")):
    """Vrije status-correctie door de penningmeester (#455)."""
    require_finance_mutation(db, email)
    _uitvoeren(zet_betaalstatus, db, record_id, status, note=note, actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())


@router.post("/admin/betalingen/{record_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verwijderen(record_id: str, request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_finance_ui),
                         note: str = Form("")):
    """Betaal-/terugbetaalrecord verwijderen (soft-delete, uit het saldo, #455).
    Corrigeert ook een foute refund."""
    require_finance_mutation(db, email)
    _uitvoeren(verwijder_betaling, db, record_id, note=note, actor=email)
    return templates.TemplateResponse(request, "_betalingen_lijst.html",
                                      _view(request, db, email).as_context())

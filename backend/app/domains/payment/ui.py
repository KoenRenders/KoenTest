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
from app.ui import admin_nav, filterparams, templates
from app.domains.payment.api import PayableType, PaymentType
from app.i18n import _
from app.kernel.codes import code_labels
from app.domains.payment.service import (
    BetalingFout, bevestig_betaling, bewerk_betaling, registreer_terugbetaling,
    ververs_betaalstatus, verwijder_betaling, zet_betaalstatus,
)
from app.domains.payment.viewmodels import BetalingenView

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/betalingen")


def _uitvoeren(bewerking, request: Request, db: Session, email: str,
               *args, **kwargs) -> HTMLResponse:
    """Voer één schermbewerking uit en geef de lijst terug — met de reden bij een
    weigering.

    De servicelaag kent geen HTTP: ze gooit `BetalingFout` bij een invoerfout en
    `LookupError` als het record niet bestaat. Deze route is de enige plek waar dat
    een statuscode wordt (#635 regel 1: de router is de deurwachter, niet de
    rekenmeester).

    #723: een `BetalingFout` was een 400, en daar hield de uitleg op. htmx swapt niet
    op een 4xx, dus de globale afhandelaar in `_macros.html` nam over — en die toont
    voor élke status behalve 401/403 één vaste zin zonder ooit in het antwoord te
    kijken. De precieze reden ("Kan niet meer terugbetalen (€ 100.00) dan er netto
    ontvangen is (€ 10.00).") werd geschreven, doorgegeven, over de lijn gestuurd en
    op de laatste meter weggegooid.

    Nu gaat de lijst terug met een **200** en de reden in de foutbanner, precies
    zoals `inschrijving_opslaan` het al deed — omdát htmx een 200 wél swapt.

    Een `LookupError` blijft een 404: dat is geen invoerfout maar een verdwenen
    record, en daar is "herlaad de pagina" wél het juiste antwoord.

    Bewust géén `db.rollback()` op de foutweg: de services valideren vóór ze
    muteren, dus er staat niets te herroepen — en een rollback zou in de tests de
    savepoint van de fixture wegnemen.
    """
    fout = None
    try:
        bewerking(db, *args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc) or _("Betaling niet gevonden."))
    except BetalingFout as exc:
        fout = str(exc)
    context = _view(request, db, email).as_context()
    context["error"] = fout
    # Fragmentantwoord: band + tabs reizen out-of-band mee (zie de partial).
    context["oob_boven"] = True
    return templates.TemplateResponse(request, "_betalingen_lijst.html", context)


def _activiteit_scope(db: Session, activiteit_id: int):
    """(naam, inschrijving-ids) van één activiteit — of (None, lege set) als ze
    niet bestaat: de scope blijft dan zichtbaar met een lege lijst, nooit stil
    alles (P13). Lokale import: activities importeert zelf uit payment."""
    from app.domains.activities.api import get_activity, registration_ids_for

    activiteit = get_activity(db, activiteit_id, include_deleted=True)
    return (activiteit.name if activiteit is not None else None,
            {(PayableType.REGISTRATION, i)
             for i in registration_ids_for(db, activiteit_id)})


def _gezin_scope(db: Session, family_id: int):
    """(gezinslabel, payables) — of (None, lege set) als het gezin niet
    bestaat: zichtbare scope met lege lijst, nooit stil alles (P13)."""
    from app.domains.membership.api import family_label, get_family
    from app.domains.payment.api import family_payables

    try:
        gezin = get_family(db, family_id)
    except Exception:
        gezin = None
    return (family_label(gezin) if gezin is not None else None,
            family_payables(db, family_id))


#: Groepen per pagina (#1059). Vijftig, zoals elke andere beheerlijst
#: (`docs/design-system.md` §2.3) — en GROEPEN en geen rijen, want een
#: inschrijving met vier boekingen mag niet over twee pagina's breken.
PER_PAGE = 50


def _paginakeuze(request, stand: dict) -> int:
    """Welke pagina er gevraagd wordt (#1059).

    Twee bronnen, en het verschil is de hele truc. Een **GET** zegt zelf waar hij
    heen wil: de bladerknoppen dragen `page=` in hun URL, een tabwissel en een
    filterwijziging niet — en die horen dan ook op pagina 1 te beginnen, want hun
    selectie is een andere. Zou `page` uit `HX-Current-URL` komen, dan sleepte een
    tabwissel de oude pagina 3 mee naar een tab die er misschien maar één heeft.

    Een **mutatie** (POST) is geen navigatie: bevestig je een betaling op pagina 3,
    dan hoor je daar te blijven staan. Die post draagt geen query-string, dus
    daarvoor is `HX-Current-URL` — via `stand` — juist de goede bron.
    """
    ruw = (request.query_params.get("page") if request.method == "GET"
           else stand.get("page")) or ""
    return max(1, int(ruw)) if ruw.isdigit() else 1


def _raakje_op_dit_scherm(db: Session, email: str) -> bool:
    """Mag hier een Raakje-ingang staan? (#1060)

    Twee voorwaarden, en de tweede is de reden dat deze functie bestaat: de
    beheer-assistent moet aanstaan (omgeving én tenant, CR-07 §6.3), én deze
    gebruiker moet hem mogen aanspreken. Dat laatste valt hier NIET samen met wie
    het scherm mag zien: Betalingen laat FINANCE binnen, de assistent niet. Een
    knop die op een 403 uitkomt is erger dan geen knop.
    """
    from app.domains.auth.api import may_use_admin_assistant
    from app.kernel.tenant_config import tenant_admin_chat_enabled

    return tenant_admin_chat_enabled(db) and may_use_admin_assistant(db, email)


def _stt_mode() -> str:
    """De spraakmodus van de kit, lokaal geïmporteerd zoals de rest van dit
    bestand — `app.config` hoort niet in de modulekop van een scherm."""
    from app.config import settings

    return settings.stt_mode


def _view(request: Request, db: Session, email: str,
          nav_items: list | None = None, *,
          forceer_activiteit: int | None = None,
          forceer_gezin: int | None = None,
          forceer_inschrijving: int | None = None,
          scope_stil: bool = False) -> BetalingenView:
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
        aggregate, apply_zicht, count_zichten, derived_status, enriched_records,
        filter_records, group_cards, may_delete,
    )

    # #671: uit HX-Current-URL als htmx die meestuurt, anders uit de query-string.
    # Eén gedeelde helper voor de vier modules die hun filter zo lezen.
    stand = filterparams(request)
    context = (stand.get("context") or "all").strip()
    status = (stand.get("status") or "all").strip()
    q = (stand.get("q") or "").strip()
    # #669: eigen schakelaar naast de statuskeuzelijst. De oude waarde
    # status=openstaand blijft werken (bestaande links, opgeslagen export-URL's) en
    # zet de schakelaar aan.
    openstaand = stand.get("openstaand") == "1" or status == "openstaand"
    if status == "openstaand":
        status = "all"
    # Golf 10 (#913): de statustabs. Een oude openstaand-link (of -export-URL)
    # landt op het Openstaand-tab, zodat hij hetzelfde blijft tonen; een
    # onbekende waarde valt terug op "alle" en vervalst nooit een tab.
    zicht = (stand.get("zicht") or "").strip()
    if zicht not in ("alle", "openstaand", "betaald", "terugbetaald"):
        zicht = "openstaand" if openstaand else "alle"
    openstaand = False
    # #704: `?record=<id>` toont die ene betaling, ongeacht de andere filters.
    # Zo landt een werkbanktaak op de kaart die ze bedoelt, ook als die buiten
    # het huidige filter valt. Alleen hier en niet in de export: een export van
    # één record is een andere vraag, en niemand stelde ze.
    record_id = (stand.get("record") or "").strip()
    # P13 (golf 5, #913): `?inschrijving=<id>` is een recordSCOPE — de betalingen
    # van één inschrijving, met de gewone filters daarbinnen. Zichtbaar via de
    # scope-regel hieronder; de enige uitgang is haar "Alle bekijken". Alleen
    # cijfers tellen: al het andere is geen id en zou de scope-regel een
    # vervalste tekst laten tonen.
    inschrijving_id = (str(forceer_inschrijving) if forceer_inschrijving
                       else (stand.get("inschrijving") or "").strip())
    if not inschrijving_id.isdigit():
        inschrijving_id = ""
    # Golf 8 (#913): `?activiteit=<id>` — de betalingen van één activiteit, voor
    # de Betalingen-tab op haar recordpagina. Zelfde regels als de
    # inschrijvingscope; de resolutie naar inschrijving-ids gebeurt in
    # _activiteit_scope via de activities-facade.
    activiteit_id = (str(forceer_activiteit) if forceer_activiteit
                     else (stand.get("activiteit") or "").strip())
    if not activiteit_id.isdigit():
        activiteit_id = ""
    # Golf 9 (#913): de gezinsscope — lidmaatschappen én inschrijvingen van één
    # gezin, voor de Betalingen-tab op de gezinspagina. Zelfde regels.
    gezin_id = (str(forceer_gezin) if forceer_gezin
                else (stand.get("gezin") or "").strip())
    if not gezin_id.isdigit():
        gezin_id = ""
    # Golf 8-feedback: op de ingebedde tab zegt de recordkop al waar je bent —
    # de scope-regel zou dat herhalen. De vlag reist als hidden field mee met
    # elke filterwissel, anders dook de regel na de eerste wissel alsnog op.
    stil = scope_stil or stand.get("scope_stil") == "1"
    page = _paginakeuze(request, stand)
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

    scope_naam, scope_payables = (None, None)
    if activiteit_id:
        scope_naam, scope_payables = _activiteit_scope(db, int(activiteit_id))
    elif gezin_id:
        scope_naam, scope_payables = _gezin_scope(db, int(gezin_id))
    # Eerst zónder zicht (de tab-aantallen tellen over deze basis), daarna de
    # doorsnede van het actieve tab — dezelfde apply_zicht die filter_records
    # en de export gebruiken, dus scherm en bestand kunnen niet uiteenlopen.
    zicht_basis = filter_records(records, context=context, status=status, q=q,
                                 openstaand=openstaand, record_id=record_id,
                                 registration_id=inschrijving_id,
                                 payables=scope_payables)
    telling = count_zichten(zicht_basis)
    zichtbaar = zicht_basis if record_id else apply_zicht(zicht_basis, zicht)

    # De scope-regel (P13): benoemt de scope en linkt naar het record zelf, met
    # de weg terug naar deze gescopeerde lijst (P3). De naam komt via de
    # activities-facade — de server hercontroleert het id dus altijd; een
    # onbestaand id houdt de scope (en haar lege lijst) zichtbaar i.p.v. stil
    # alles te tonen. #704's `?record=` krijgt dezelfde zichtbaarheid: dat was
    # tot nu een onzichtbaar voorfilter.
    scope = None
    if gezin_id:
        scope = {
            "soort": _("Voor gezin:"),
            "titel": scope_naam or f"#{gezin_id}",
            "titel_url": f"/admin/leden/gezin/{gezin_id}",
            "alles_url": "/admin/betalingen",
            "param_naam": "gezin", "param_waarde": gezin_id,
            "stil": stil,
        }
    elif activiteit_id:
        scope = {
            "soort": _("Voor activiteit:"),
            "titel": scope_naam or f"#{activiteit_id}",
            "titel_url": f"/admin/activiteiten/{activiteit_id}",
            "alles_url": "/admin/betalingen",
            "param_naam": "activiteit", "param_waarde": activiteit_id,
            "stil": stil,
        }
    elif inschrijving_id:
        from urllib.parse import quote

        from app.domains.activities.api import get_registration

        reg = get_registration(db, int(inschrijving_id), include_deleted=True)
        naam = (reg.contact_name if reg is not None else None) or f"#{inschrijving_id}"
        terug = quote(f"/admin/betalingen?inschrijving={inschrijving_id}", safe="")
        scope = {
            "soort": _("Voor inschrijving:"), "titel": naam,
            "titel_url": f"/admin/inschrijvingen/{inschrijving_id}?terug={terug}",
            "alles_url": "/admin/betalingen",
            "param_naam": "inschrijving", "param_waarde": inschrijving_id,
            "stil": stil,
        }
    elif record_id:
        scope = {
            "soort": _("Eén betaling uitgelicht"), "titel": None, "titel_url": None,
            "alles_url": "/admin/betalingen",
            "param_naam": "record", "param_waarde": record_id,
        }

    charges = [r for r in zichtbaar if r.type != PaymentType.REFUND]
    refunds = [r for r in zichtbaar if r.type == PaymentType.REFUND]
    m_bet, m_ref = aggregate(charges), aggregate(refunds)
    # De KPI-band telt over de zicht-BASIS: de tabs snijden de tabel, niet de
    # kengetallen — anders zegt het tab "Betaald" dat er € 0 openstaat.
    basis_tot = aggregate(zicht_basis)
    kpi = {"due": basis_tot["due"], "paid": basis_tot["paid"],
           "saldo": basis_tot["saldo"],
           "boekingen": len(zicht_basis), "open": telling["openstaand"]}

    # Tab-URLs server-side opgebouwd mét de actieve filterstand: de tabs staan
    # in het fragment (verse aantallen bij elke filterwissel) en een link die
    # zijn stand zelf draagt heeft geen hx-include-samenloop met de filterbalk.
    from urllib.parse import urlencode

    _tabstand: list = [("q", q) if q else None,
                       ("context", context) if context != "all" else None,
                       ("status", status) if status != "all" else None]
    if inschrijving_id:
        _tabstand.append(("inschrijving", inschrijving_id))
    elif activiteit_id:
        _tabstand.append(("activiteit", activiteit_id))
    elif gezin_id:
        _tabstand.append(("gezin", gezin_id))
    if stil:
        _tabstand.append(("scope_stil", "1"))
    zichten = []
    for _zkey, _zlabel in (("alle", _("Alle")), ("openstaand", _("Openstaand")),
                           ("betaald", _("Betaald")),
                           ("terugbetaald", _("Terugbetaald"))):
        _qs = urlencode([("zicht", _zkey)] + [p for p in _tabstand if p])
        zichten.append({"key": _zkey, "label": _zlabel, "count": telling[_zkey],
                        "url": f"/admin/betalingen/lijst?{_qs}",
                        "page_url": f"/admin/betalingen?{_qs}",
                        "actief": _zkey == zicht})
    # Terugbetalingen staan al NEGATIEF in de records (create_refund bewaart
    # -bedrag), dus netto is een OPTELSOM. De oude aftrekking telde ze dubbel:
    # 18 − (−9) = 27, terwijl de totaalregels onderaan (aggregate over alle
    # records van een groep) correct 9 zeiden (HDEV-melding Koen, 15 sep).
    m_net = {k: m_bet[k] + m_ref[k] for k in ("due", "paid", "saldo")}
    # #1059: dezelfde stand als de tabs, plus het actieve zicht. De macro plakt er
    # `&page=N` achter. Bewust zonder `hx-include`: de filterbalk serialiseert
    # geen `page`, dus meesturen zou de knop zijn eigen keuze laten overschrijven.
    pager_url = f"/admin/betalingen/lijst?{urlencode([('zicht', zicht)] + [p for p in _tabstand if p])}"

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
            # CR-12 §B4.7: "staat deze kaart vereffend?" stond als
            # `k.status == "paid"` in de template. Dat is een afgeleide
            # toestand en geen code, maar de vergelijking hoort hier en niet
            # daar: één plek waar de regel staat, en toetsbaar.
            "is_settled": derived_status(rec) == "paid",
        }

    # `records` erbij zodat een gefilterde terugbetaling haar charge als context
    # kan meenemen (#668); die telt niet mee in de totalen.
    groepen = group_cards(zichtbaar, records)
    # #1059: pas hier snijden, en op GROEPEN. Het snijden gebeurt vóór de
    # kaartopmaak hieronder, zodat die alleen het zichtbare deel kost; de
    # tellingen erboven (kpi, tabaantallen, matrix) zijn al berekend over de
    # volledige selectie en blijven dus onaangeroerd.
    totaal_groepen = len(groepen)
    paginas = max(1, -(-totaal_groepen // PER_PAGE))
    # Een verwijdering kan de laatste groep van de laatste pagina weghalen; dan
    # is "pagina 4" van zonet er geen meer.
    page = min(page, paginas)
    groepen = groepen[(page - 1) * PER_PAGE:page * PER_PAGE]
    for groep in groepen:
        groep["kaarten"] = [(_kaart(k["charge"]) | {"is_context": k["is_context"],
                                                    "is_extra": k["is_extra"]},
                             [_kaart(x) for x in k["refunds"]])
                            for k in groep["kaarten"]]

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
        # CR-12 fase 1: deze twee kwamen uit twee woordenboeken in dit bestand.
        # Nu uit de labeltabellen, zodat het scherm, de export en de
        # rapportdimensie per definitie hetzelfde woord tonen (AC3) en een
        # Engelstalige afdeling ze allebei in het Engels ziet (AC2).
        method_labels=dict(code_labels("payment_method")),
        # De twee filteropties bovenaan zijn géén codes: "alle statussen" en
        # "openstaand saldo" zijn manieren van kijken, geen waarden die in de
        # kolom staan. Die blijven dus door `_()` gaan.
        status_labels={
            "all": _("Alle statussen"), "openstaand": _("Openstaand saldo"),
            **dict(code_labels("payment_status")),
        },
        # Badge per afgeleide status (service.derived_status). Label + kleur horen
        # bij de weergave en dus hier; wélke status het is, beslist de service —
        # "Deels betaald" werd vroeger in de template zelf uitgerekend (#635-9).
        kaart_status={
            "paid": (_("Vereffend"), "green"),
            # Geel, gelijk aan "Openstaand" (#660): het is hetzelfde soort
            # toestand — er moet nog geld bewegen, alleen de richting verschilt.
            # Die richting lees je af aan de aparte type-badge "Terugbetaling",
            # die sinds #660 oranje is. Zonder deze stap stonden er twee oranje
            # badges naast elkaar op één kaart. "Deels betaald" blijft oranje;
            # dat is een andere situatie.
            "refund_due": (_("Terug te betalen"), "yellow"),
            "partial": (_("Deels betaald"), "orange"),
            "pending": (_("Openstaand"), "yellow"),
            "failed": (_("Mislukt"), "red"),
            "cancelled": (_("Geannuleerd"), "gray"),
        },
        status=status, openstaand=openstaand, q=q, scope=scope,
        zicht=zicht, zichten=zichten, kpi=kpi,
        page=page, per_page=PER_PAGE, totaal_groepen=totaal_groepen,
        pager_url=pager_url,
        componenten=_comp, jaren=_jaren,
        context_top=context_top, context_groups=context_groups,
        matrix={"betalingen": m_bet, "terugbetalingen": m_ref, "netto": m_net},
        is_finance="FINANCE" in get_user_roles(db, email),
        raakje_scherm=_raakje_op_dit_scherm(db, email),
        stt_mode=_stt_mode(),
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


@router.get("/admin/activiteiten/{activity_id}/betalingen",
            response_class=HTMLResponse)
def activiteit_betalingen_tab(activity_id: int, request: Request,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_finance_ui)):
    """De Betalingen-tab van de activiteit-recordpagina (golf 8-feedback):
    exact het betalingenscherm, gefilterd op dit record, onder de recordkop —
    zonder scope-regel, want de kop zegt al waar je bent. FINANCE-gated zoals
    /admin/betalingen zelf (#544)."""
    from app.domains.activities.api import get_activity_detail, record_kop_ctx

    activiteit = get_activity_detail(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    # Nav-focus (Koen, 15 sep): je zit ín Activiteiten — de linkernavigatie
    # blijft daar staan, ook al rendert het betalingenscherm.
    nav = admin_nav("/admin/activiteiten", roles=get_user_roles(db, email))
    ctx = _view(request, db, email, nav_items=nav,
                forceer_activiteit=activity_id, scope_stil=True).as_context()
    ctx["a"] = activiteit
    # #1070: één bouwer voor de hele recordkop. Stond hier met de hand samengesteld
    # naast dezelfde samenstelling in `activities.admin_ui`; een sleutel erbij ging
    # dan onvermijdelijk op één van de twee plekken ontbreken.
    ctx.update(record_kop_ctx(db, activiteit, email, "betalingen"))
    return templates.TemplateResponse(
        request, "admin_activiteit_betalingen.html", ctx)


@router.get("/admin/leden/gezin/{family_id}/betalingen",
            response_class=HTMLResponse)
def gezin_betalingen_tab(family_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_finance_ui)):
    """De Betalingen-tab van de gezinspagina (golf 9, #913): het gewone
    betalingenscherm, gefilterd op dit gezin, onder de gezins-recordkop.
    FINANCE-gated zoals /admin/betalingen zelf (#544)."""
    from app.domains.membership.api import get_family
    from app.domains.mdm.api import gezin_tabs

    try:
        gezin = get_family(db, family_id)
    except Exception:
        gezin = None
    if gezin is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    nav = admin_nav("/admin/leden", roles=get_user_roles(db, email))
    ctx = _view(request, db, email, nav_items=nav,
                forceer_gezin=family_id, scope_stil=True).as_context()
    ctx["family"] = gezin
    ctx["record_tabs"] = gezin_tabs(db, gezin, email, "betalingen")
    return templates.TemplateResponse(
        request, "admin_gezin_betalingen.html", ctx)


@router.get("/admin/inschrijvingen/{registration_id}/betalingen",
            response_class=HTMLResponse)
def inschrijving_betalingen_tab(registration_id: int, request: Request,
                                terug: str = "",
                                db: Session = Depends(get_db),
                                email: str = Depends(require_finance_ui)):
    """De Betalingen-tab van de inschrijvingspagina (feedback 15 sep): het
    gewone betalingenscherm in de inschrijvingscope, onder de gedeelde
    recordkop — dit verving de P13-chip op dat scherm. FINANCE-gated zoals
    /admin/betalingen zelf (#544)."""
    from app.domains.activities.api import inschrijving_kop_ctx, get_registration

    reg = get_registration(db, registration_id, include_deleted=True)
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    # Nav-focus (Koen, 15 sep): je kwam uit Activiteiten — de navigatie blijft
    # daar staan, ook al rendert het betalingenscherm.
    nav = admin_nav("/admin/activiteiten", roles=get_user_roles(db, email))
    ctx = _view(request, db, email, nav_items=nav,
                forceer_inschrijving=registration_id,
                scope_stil=True).as_context()
    kop = inschrijving_kop_ctx(db, registration_id, email, "betalingen", terug)
    if kop is None:  # kan niet meer na de 404 hierboven; mypy weet dat niet
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    ctx.update(kop)
    ctx["reg"] = reg
    return templates.TemplateResponse(
        request, "admin_inschrijving_betalingen.html", ctx)


@router.get("/admin/betalingen/lijst", response_class=HTMLResponse)
def betalingen_lijst(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_finance_ui)):
    ctx = _view(request, db, email).as_context()
    ctx["oob_boven"] = True
    return templates.TemplateResponse(request, "_betalingen_lijst.html", ctx)


@router.get("/admin/betalingen/export")
def betalingen_export(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_finance_ui)):
    from app.domains.payment.exports import build_payments_export_ods

    # Dezelfde bron als het scherm (#669/#671): de exportknop draagt de filterstand
    # in zijn href, en die wordt hier langs dezelfde helper gelezen. Zonder dat
    # exporteert hij iets anders dan wat je ziet — een stille afwijking tussen
    # beeld en bestand.
    stand = filterparams(request)
    context = (stand.get("context") or "all").strip()
    status = (stand.get("status") or "all").strip()
    openstaand = stand.get("openstaand") == "1" or status == "openstaand"
    if status == "openstaand":
        status = "all"
    # Golf 10 (#913): het tab-zicht reist mee — zelfde afleiding als _view.
    zicht = (stand.get("zicht") or "").strip()
    if zicht not in ("alle", "openstaand", "betaald", "terugbetaald"):
        zicht = "openstaand" if openstaand else "alle"
    openstaand = False
    # P13 (golf 5, #913): de recordscope reist mee, zoals elke filterstand —
    # dezelfde cijfercontrole als in _view.
    inschrijving_id = (stand.get("inschrijving") or "").strip()
    activiteit_id = (stand.get("activiteit") or "").strip()
    gezin_id = (stand.get("gezin") or "").strip()
    paren = None
    if activiteit_id.isdigit():
        _naam, paren = _activiteit_scope(db, int(activiteit_id))
    elif gezin_id.isdigit():
        _naam, paren = _gezin_scope(db, int(gezin_id))
    content = build_payments_export_ods(
        db, context=context, status=status, openstaand=openstaand,
        registration_id=inschrijving_id if inschrijving_id.isdigit() else "",
        payables=paren, zicht=zicht)
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
    return _uitvoeren(bevestig_betaling, request, db, email, record_id, note=note, actor=email)


@router.post("/admin/betalingen/{record_id}/refund", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_refund(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    amount: str = Form(""), note: str = Form("")):
    require_finance_mutation(db, email)
    return _uitvoeren(registreer_terugbetaling, request, db, email, record_id, amount=amount, note=note,
               actor=email)


@router.post("/admin/betalingen/{record_id}/bijwerken", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_bijwerken(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui),
                       amount_paid: str = Form(""), note: str = Form("")):
    """Betaald bedrag invullen + als betaald bevestigen (#455)."""
    require_finance_mutation(db, email)
    return _uitvoeren(bevestig_betaling, request, db, email, record_id, note=note, amount_paid=amount_paid,
               actor=email)


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
    return _uitvoeren(bewerk_betaling, request, db, email, record_id, status=status,
               amount_paid=amount_paid, note=note, actor=email)


@router.post("/admin/betalingen/{record_id}/verversen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verversen(record_id: str, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_finance_ui)):
    """Mollie-status ophalen en toepassen (handmatige tegenhanger van de webhook, #455)."""
    require_finance_mutation(db, email)
    return _uitvoeren(ververs_betaalstatus, request, db, email, record_id, actor=email)


@router.post("/admin/betalingen/{record_id}/status", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_status(record_id: str, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_finance_ui),
                    status: str = Form(...), note: str = Form("")):
    """Vrije status-correctie door de penningmeester (#455)."""
    require_finance_mutation(db, email)
    return _uitvoeren(zet_betaalstatus, request, db, email, record_id, status, note=note, actor=email)


@router.post("/admin/betalingen/{record_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def betaling_verwijderen(record_id: str, request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_finance_ui),
                         note: str = Form("")):
    """Betaal-/terugbetaalrecord verwijderen (soft-delete, uit het saldo, #455).
    Corrigeert ook een foute refund."""
    require_finance_mutation(db, email)
    return _uitvoeren(verwijder_betaling, request, db, email, record_id, note=note, actor=email)

"""Server-rendered betalingen-scherm (fase 3b, #401 — §21): de matrix
(betalingen & vorderingen met context-/statusfilter), handmatig bevestigen,
refunds (FINANCE) en de .ods-export.

Hergebruikt de bestaande router-/servicefuncties — geen dubbele
businesslogica. Rollen: iedereen met ADMIN of FINANCE mag kijken en
exporteren; bevestigen en terugbetalen is FINANCE-only (financiële
scheiding, #83).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    csrf_token_for,
    get_user_roles,
    may,
    require_csrf,
    require_right,
)
from app.domains.payment.api import PayableType
from app.domains.payment.service import (
    BetalingFout,
    bevestig_betaling,
    bewerk_betaling,
    registreer_terugbetaling,
    ververs_betaalstatus,
    verwijder_betaling,
    zet_betaalstatus,
)
from app.domains.payment.viewmodels import BetalingenView, BookingView
from app.i18n import _
from app.kernel.codes import code_labels
from app.kernel.geld import bedrag as geld
from app.ui import (
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    per_page_from,
    register_origin,
    templates,
)

#: The query parameter that names one booking on the payments list, as the origin
#: of a record opened from it (#1557). The list keeps its own state beside it.
BOOKING_PARAM = "boeking"

#: The address of the embedded Betalingen tab per scope (K6, #1560).
_TAB_PATHS = {
    "activiteit": "/admin/activiteiten/{id}/betalingen",
    "gezin": "/admin/leden/gezin/{id}/betalingen",
    "inschrijving": "/admin/inschrijvingen/{id}/betalingen",
}


def _booking_origin(db: Session, url: str) -> str | None:
    """ "Betaling van <naam>" for a way back that leads to one booking: its own
    page (`/admin/betalingen/<id>`, #1574) or its row on the payments list
    (`?boeking=<id>`); None without one, so the list's menu name stands."""
    from urllib.parse import parse_qs, urlsplit

    from app.domains.payment.api import enriched_records

    parts = urlsplit(url)
    booking = parse_qs(parts.query).get(BOOKING_PARAM, [""])[0] or (
        parts.path.removeprefix("/admin/betalingen").strip("/")
    )
    if not booking:
        return None
    # The same enrichment the list shows, so the name is the row's name.
    name = next((r.contact_name for r in enriched_records(db) if str(r.id) == booking), None)
    return _("Betaling van %(name)s") % {"name": name} if name else None


register_origin("/admin/betalingen", _booking_origin)

router = APIRouter(include_in_schema=False)


def _uitvoeren(bewerking, request: Request, db: Session, email: str, *args, **kwargs) -> Response:
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
    # #1574: a form on a booking page says so (`X-Booking-Page`), and gets that
    # page back instead of the list.
    booking_page = request.headers.get("x-booking-page")
    if booking_page:
        return _booking_answer(request, db, email, booking_page, error=fout)
    context = _view(request, db, email, **_scope_from_request(request)).as_context()
    context["error"] = fout
    # Fragmentantwoord: band + tabs reizen out-of-band mee (zie de partial).
    context["oob_boven"] = True
    return templates.TemplateResponse(request, "_betalingen_lijst.html", context)


def _scope_from_request(request: Request) -> dict:
    """The scope the list was in when the mutation was sent (#1247).

    `#betalingen-lijst` sends it as `X-Betalingen-Scope` (`activiteit=12`,
    `gezin=3&scope_stil=1`, …) with every request from inside the list. The
    record tabs force their scope in the route and not in the page URL, and a
    mutation posts to its own endpoint, so without this the list came back
    unscoped: every payment of the association under an activity's tab. One place
    for all seven mutations, since they all return through `_uitvoeren`.
    """
    from urllib.parse import parse_qsl

    raw = dict(parse_qsl(request.headers.get("x-betalingen-scope", "")))
    scope: dict = {}
    for field, argument in (
        ("activiteit", "forceer_activiteit"),
        ("gezin", "forceer_gezin"),
        ("inschrijving", "forceer_inschrijving"),
    ):
        value = (raw.get(field) or "").strip()
        if value.isdigit():
            scope[argument] = int(value)
    if scope and raw.get("scope_stil") == "1":
        scope["scope_stil"] = True
    return scope


def _activiteit_scope(db: Session, activiteit_id: int):
    """(naam, inschrijving-ids) van één activiteit — of (None, lege set) als ze
    niet bestaat: de scope blijft dan zichtbaar met een lege lijst, nooit stil
    alles (P13). Lokale import: activities importeert zelf uit payment."""
    from app.domains.activities.api import get_activity, registration_ids_for

    activiteit = get_activity(db, activiteit_id, include_deleted=True)
    return (
        activiteit.name if activiteit is not None else None,
        {(PayableType.REGISTRATION, i) for i in registration_ids_for(db, activiteit_id)},
    )


def _gezin_scope(db: Session, family_id: int):
    """(gezinslabel, payables) — of (None, lege set) als het gezin niet
    bestaat: zichtbare scope met lege lijst, nooit stil alles (P13)."""
    from app.domains.membership.api import family_label, get_family
    from app.domains.payment.api import family_payables

    try:
        gezin = get_family(db, family_id)
    except Exception:
        gezin = None
    return (family_label(gezin) if gezin is not None else None, family_payables(db, family_id))


#: Groepen per pagina (#1059). Vijftig, zoals elke andere beheerlijst
#: (`docs/design-system.md` §2.3) — en GROEPEN en geen rijen, want een
#: inschrijving met vier boekingen mag niet over twee pagina's breken.
#: Since K1 (#1555) the toolbar offers 25 · 50 · 100 (`app.ui.PER_PAGE_OPTIONS`);
#: this is the default, and still groups.
PER_PAGE = 50

#: The segments of the status filter (CR-11 block 3, Koen, 2 October 2026):
#: *Alle | Openstaand (n)*. A segment is a state the board acts on; Betaald and
#: Terugbetaald are done and get none.
ZICHTEN = ("alle", "openstaand")


def _zicht(stand: dict) -> str:
    """The chosen segment. An unknown value — also "betaald" or "terugbetaald"
    from a link of before K1 — falls back to "alle" and never fakes a segment;
    the old `status=openstaand` and `openstaand=1` still land on Openstaand."""
    zicht = (stand.get("zicht") or "").strip()
    if zicht in ZICHTEN:
        return zicht
    legacy = stand.get("openstaand") == "1" or (stand.get("status") or "") == "openstaand"
    return "openstaand" if legacy and not zicht else "alle"


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
    ruw = (request.query_params.get("page") if request.method == "GET" else stand.get("page")) or ""
    return max(1, int(ruw)) if ruw.isdigit() else 1


def _kaart(rec) -> dict:
    """Per kaart de geldregel én of ze verwijderbaar is (#617-2a).

    `Ontvangen`/`Saldo` vallen weg zolang er niets uitbetaald is — € 0,00 tonen
    suggereert dat er al iets gebeurd is. Wél tonen zodra `amount_paid` gevuld is,
    **ongeacht de status**: in bestaande data staan refunds met status `pending`
    én een uitbetaald bedrag (gevolg van de bug uit §2-0b), en die moeten leesbaar
    blijven. De labels zijn op elke kaart dezelfde drie woorden; het teken doet
    het werk.
    """
    from app.domains.payment.api import derived_status, may_delete

    betaald = None if rec.amount_paid is None else Decimal(str(rec.amount_paid))
    return {
        "rec": rec,
        "bedrag": Decimal(str(rec.amount)),
        "ontvangen": betaald,
        "saldo": None if betaald is None else Decimal(str(rec.amount)) - betaald,
        "mag_verwijderen": may_delete(rec),
        # Afgeleide status uit de service — de template leidt niets meer af.
        "status": derived_status(rec),
        # CR-12 §B4.7: "is this card settled?" used to be
        # `k.status == "paid"` in the template. That is a derived state
        # and not a code, but the comparison belongs here and not there:
        # one place where the rule lives, and testable.
        "is_settled": derived_status(rec) == "paid",
    }


#: The columns the payments table sorts on (K2, #1556): the key in the URL →
#: the value of a group's main row. Amounts sort as numbers, text without case.
SORT_KEYS = {
    "naam": lambda r, badges: (r.contact_name or "").casefold(),
    "context": lambda r, badges: ((r.description or "").casefold(), r.component_name or ""),
    "status": lambda r, badges: badges.get(_kaart(r)["status"], ("",))[0].casefold(),
    "bedrag": lambda r, badges: Decimal(str(r.amount)),
    "saldo": lambda r, badges: Decimal(str(r.amount)) - Decimal(str(r.amount_paid or 0)),
}

#: The optional columns and the priority with which each leaves a narrow list
#: (decision 04, point 6): Ontvangen first, then Context.
OPTIONAL_COLUMNS = {"ontvangen": 1, "context": 2}
COLUMN_MODES = ("auto", "show", "hide")


def _row(
    rec, return_url: str, may_mutate: bool, *, is_context=False, is_extra=False, on_tab=False
) -> dict:
    """One row of the payments table (K2, #1556): the record's figures, where the
    row leads, the context as a reference, the one visible action and the menu.

    The row opens the booking's page with the list as its way back. A record the
    row names — the activity or the household under Context, the registration in
    the menu — is opened with the list AND this booking as its origin
    (`boeking=`), so its way back says "Betaling van <naam>" (#1557).

    `on_tab` (K6, #1560; #1636): on a record's tab the row opens the booking's
    page too — no row unfolds (Q75). The page then leads back to the tab WITH
    the booking named, so the way back lands on the row it left: in view, its
    link focused.
    """
    from urllib.parse import quote

    card = _kaart(rec) | {"is_context": is_context, "is_extra": is_extra}
    back = quote(return_url, safe="/")
    from_booking = quote(
        f"{return_url}{'&' if '?' in return_url else '?'}{BOOKING_PARAM}={rec.id}", safe="/"
    )
    page = f"{BOOKINGS}/{rec.id}?terug={from_booking if on_tab else back}"
    # CR-21 phase 0 (#1748): where the payable hangs is its describer's to say.
    context_href = f"{rec.context_href}?terug={from_booking}" if rec.context_href else None

    action = None
    menu: list[dict] = []
    post = f'hx-target="#betalingen-lijst" hx-swap="innerHTML" hx-post="{BOOKINGS}/{rec.id}'
    if not is_context:
        if may_mutate and not rec.is_paid:
            action = {
                "label": _("Bevestig"),
                "attrs": f'{post}/bevestigen"',
                "confirm": _("Als volledig terugbetaald bevestigen?")
                if rec.is_refund
                else _("Als volledig betaald bevestigen?"),
            }
        if may_mutate and rec.is_paid and not rec.is_refund:
            menu.append({"label": _("Terugbetaling"), "href": f"{page}#terugbetaling"})
        if rec.payable_href:
            menu.append(
                {
                    "label": _("%(what)s openen") % {"what": _(rec.payable_label)},
                    "href": f"{rec.payable_href}?terug={from_booking}",
                }
            )
        if may_mutate and card["mag_verwijderen"]:
            menu.append(
                {
                    "kind": "delete",
                    "label": _("Verwijderen"),
                    "attrs": f'{post}/verwijderen"',
                    "confirm": _("Deze terugbetaling verwijderen?")
                    if rec.is_refund
                    else _("Deze betaling verwijderen?"),
                }
            )
    return card | {
        "href": page,
        "context_href": context_href,
        "action": action,
        "menu": menu,
        "key": str(rec.id),
    }


def _status_badges() -> dict:
    """Label and tone of the badge per derived status (`service.derived_status`).
    One place for the list and the booking page (#1574); built per request, so
    `_()` follows the tenant's language."""
    return {
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
    }


def _status_labels() -> dict:
    """The words for a status, for the editors of the list and of the booking
    page — never a raw code on the screen (§2.12)."""
    return {
        "all": _("Alle statussen"),
        "openstaand": _("Openstaand saldo"),
        **dict(code_labels("payment_status")),
    }


def _view(
    request: Request,
    db: Session,
    email: str,
    nav_items: list | None = None,
    *,
    forceer_activiteit: int | None = None,
    forceer_gezin: int | None = None,
    forceer_inschrijving: int | None = None,
    scope_stil: bool = False,
) -> BetalingenView:
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
        aggregate,
        apply_zicht,
        enriched_records,
        filter_records,
        group_cards,
        open_sides,
    )

    # #671: uit HX-Current-URL als htmx die meestuurt, anders uit de query-string.
    # Eén gedeelde helper voor de vier modules die hun filter zo lezen.
    stand = filterparams(request)
    context = (stand.get("context") or "all").strip()
    q = (stand.get("q") or "").strip()
    # K1 (#1555): the status select is gone (decision 03, point 4), so a
    # `status=` in an old link is ignored — the list would otherwise filter on
    # something no control on the screen shows. A status filter that returns is
    # one more select in the Filters panel and this one line.
    status = "all"
    openstaand = False
    zicht = _zicht(stand)
    per_page = per_page_from(stand.get("per_page"))
    # K2 (#1556): the sort ("naam", or "-naam" for descending; empty is the
    # list's own order, most recent first) and the column chooser's choice per
    # optional column. Anything else falls back to the default.
    sort = (stand.get("sort") or "").strip()
    if sort.lstrip("-") not in SORT_KEYS:
        sort = ""
    column_modes = {
        key: mode if (mode := (stand.get(f"kol_{key}") or "auto")) in COLUMN_MODES else "auto"
        for key in OPTIONAL_COLUMNS
    }
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
    inschrijving_id = (
        str(forceer_inschrijving)
        if forceer_inschrijving
        else (stand.get("inschrijving") or "").strip()
    )
    if not inschrijving_id.isdigit():
        inschrijving_id = ""
    # Golf 8 (#913): `?activiteit=<id>` — de betalingen van één activiteit, voor
    # de Betalingen-tab op haar recordpagina. Zelfde regels als de
    # inschrijvingscope; de resolutie naar inschrijving-ids gebeurt in
    # _activiteit_scope via de activities-facade.
    activiteit_id = (
        str(forceer_activiteit) if forceer_activiteit else (stand.get("activiteit") or "").strip()
    )
    if not activiteit_id.isdigit():
        activiteit_id = ""
    # Golf 9 (#913): de gezinsscope — lidmaatschappen én inschrijvingen van één
    # gezin, voor de Betalingen-tab op de gezinspagina. Zelfde regels.
    gezin_id = str(forceer_gezin) if forceer_gezin else (stand.get("gezin") or "").strip()
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
    zicht_basis = filter_records(
        records,
        context=context,
        status=status,
        q=q,
        openstaand=openstaand,
        record_id=record_id,
        registration_id=inschrijving_id,
        payables=scope_payables,
    )
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
            "param_naam": "gezin",
            "param_waarde": gezin_id,
            "stil": stil,
        }
    elif activiteit_id:
        scope = {
            "soort": _("Voor activiteit:"),
            "titel": scope_naam or f"#{activiteit_id}",
            "titel_url": f"/admin/activiteiten/{activiteit_id}",
            "alles_url": "/admin/betalingen",
            "param_naam": "activiteit",
            "param_waarde": activiteit_id,
            "stil": stil,
        }
    elif inschrijving_id:
        from urllib.parse import quote

        from app.domains.activities.api import get_registration

        reg = get_registration(db, int(inschrijving_id), include_deleted=True)
        naam = (reg.contact_name if reg is not None else None) or f"#{inschrijving_id}"
        terug = quote(f"/admin/betalingen?inschrijving={inschrijving_id}", safe="")
        scope = {
            "soort": _("Voor inschrijving:"),
            "titel": naam,
            "titel_url": f"/admin/inschrijvingen/{inschrijving_id}?terug={terug}",
            "alles_url": "/admin/betalingen",
            "param_naam": "inschrijving",
            "param_waarde": inschrijving_id,
            "stil": stil,
        }
    elif record_id:
        scope = {
            "soort": _("Eén betaling uitgelicht"),
            "titel": None,
            "titel_url": None,
            "alles_url": "/admin/betalingen",
            "param_naam": "record",
            "param_waarde": record_id,
        }

    # De KPI-band telt over de zicht-BASIS: de tabs snijden de tabel, niet de
    # kengetallen — anders zegt het tab "Betaald" dat er € 0 openstaat.
    basis_tot = aggregate(zicht_basis)
    kpi = {
        "due": basis_tot["due"],
        "paid": basis_tot["paid"],
        # #1391 (W1): the tiles "Nog te ontvangen" and "Nog terug te betalen" — two
        # sides with their own counts, never a net.
        **open_sides(zicht_basis),
        "boekingen": len(zicht_basis),
    }

    # Tab-URLs server-side opgebouwd mét de actieve filterstand: de tabs staan
    # in het fragment (verse aantallen bij elke filterwissel) en een link die
    # zijn stand zelf draagt heeft geen hx-include-samenloop met de filterbalk.
    from urllib.parse import parse_qsl, urlencode, urlsplit

    _tabstand: list = [
        ("q", q) if q else None,
        ("context", context) if context != "all" else None,
        ("per_page", str(per_page)) if per_page != PER_PAGE else None,
        *[(f"kol_{k}", m) for k, m in column_modes.items() if m != "auto"],
    ]
    if inschrijving_id:
        _tabstand.append(("inschrijving", inschrijving_id))
    elif activiteit_id:
        _tabstand.append(("activiteit", activiteit_id))
    elif gezin_id:
        _tabstand.append(("gezin", gezin_id))
    if stil:
        _tabstand.append(("scope_stil", "1"))
    # The status filter (K1, #1555). "Openstaand" carries its count, and the
    # count is what the click yields: registration groups, the unit of the
    # toolbar's "x–y van n", counted with the search and the context filter of
    # this moment. "Alle" carries none — the toolbar's count says n.
    segments: list[dict] = [
        {"value": "alle", "label": _("Alle")},
        {
            "value": "openstaand",
            "label": _("Openstaand"),
            "count": len(group_cards(apply_zicht(zicht_basis, "openstaand"), records)),
        },
    ]
    # The scope travels with every request of the toolbar, as hidden fields.
    toolbar_hidden = [p for p in _tabstand if p and p[0] in ("inschrijving", "activiteit", "gezin")]
    if stil:
        toolbar_hidden.append(("scope_stil", "1"))
    # #1059: dezelfde stand als de tabs, plus het actieve zicht. De macro plakt er
    # `&page=N` achter. Bewust zonder `hx-include`: de filterbalk serialiseert
    # geen `page`, dus meesturen zou de knop zijn eigen keuze laten overschrijven.
    _state = [("zicht", zicht)] + [p for p in _tabstand if p]
    pager_url = f"/admin/betalingen/lijst?{urlencode(_state + ([('sort', sort)] if sort else []))}"

    # `records` erbij zodat een gefilterde terugbetaling haar charge als context
    # kan meenemen (#668); die telt niet mee in de totalen.
    groepen = group_cards(zichtbaar, records)
    # K2 (#1556): a sort orders the GROUPS, each by its main row, and a group
    # stays together (decision 04, point 1). Without a sort the order is
    # `group_cards`' own: most recent first.
    if sort:
        badges = _status_badges()
        groepen.sort(
            key=lambda g: SORT_KEYS[sort.lstrip("-")](g["kaarten"][0]["charge"], badges),
            reverse=sort.startswith("-"),
        )
    # #1059: pas hier snijden, en op GROEPEN. Het snijden gebeurt vóór de
    # kaartopmaak hieronder, zodat die alleen het zichtbare deel kost; de
    # tellingen erboven (kpi, tabaantallen, matrix) zijn al berekend over de
    # volledige selectie en blijven dus onaangeroerd.
    totaal_groepen = len(groepen)
    paginas = max(1, -(-totaal_groepen // per_page))
    # Een verwijdering kan de laatste groep van de laatste pagina weghalen; dan
    # is "pagina 4" van zonet er geen meer.
    page = min(page, paginas)
    # The way back from a row's registration (CR-11 B7 test 21, R14): the list
    # as it was left — segment, search, context, page size and page — and that
    # is the address the browser shows, not one rebuilt here. A GET carries it
    # as its own query (the toolbar and the pager push exactly that onto the
    # page path, `main.py:_filter_push_url`); a mutation posts without one, and
    # then `HX-Current-URL` is the address. An embedded tab keeps today's
    # address until K6 (#1560) gives the record its own.
    _query = (
        request.url.query
        if request.method == "GET"
        else urlsplit(request.headers.get("hx-current-url") or "").query
    )
    # K6 (#1560): an embedded tab has its own address — the record's tab path
    # with the list's state — so a row's way back leads to the tab, not to the
    # payments list. The scope is the path there, not a parameter; and the
    # booking a visitor came back to is not part of the list's state (a second
    # `boeking=` would name the wrong row).
    _own = [
        pair
        for pair in parse_qsl(_query, keep_blank_values=True)
        if pair[0] != BOOKING_PARAM
        and not (stil and pair[0] in ("activiteit", "gezin", "inschrijving", "scope_stil"))
    ]
    list_path = "/admin/betalingen"
    if stil and scope is not None:
        tab_path = _TAB_PATHS.get(str(scope.get("param_naam")))
        if tab_path:
            list_path = tab_path.format(id=scope["param_waarde"])
    return_url = list_path + (f"?{urlencode(_own)}" if _own else "")
    groepen = groepen[(page - 1) * per_page : page * per_page]
    may_mutate = may(db, email, Right.PAYMENT_MANAGE)
    for groep in groepen:
        groep["kaarten"] = [
            (
                _row(
                    k["charge"],
                    return_url,
                    may_mutate,
                    is_context=k["is_context"],
                    is_extra=k["is_extra"],
                    on_tab=stil,
                ),
                [_row(x, return_url, may_mutate, on_tab=stil) for x in k["refunds"]],
            )
            for k in groep["kaarten"]
        ]

    # The table's columns (K2): the head's labels, which column sorts and where
    # its link leads, and the two optional ones with their priority — Ontvangen
    # leaves first, then Context.
    def _sort_urls(key: str) -> dict:
        nxt = f"-{key}" if sort == key else key
        query = urlencode(_state + [("sort", nxt)])
        return {
            "sort_url": f"/admin/betalingen/lijst?{query}",
            "sort_page_url": f"/admin/betalingen?{query}",
            "sorted": ("desc" if sort.startswith("-") else "asc")
            if sort.lstrip("-") == key
            else None,
        }

    columns = [
        {"key": "naam", "label": _("Boeking"), "cell": "name", **_sort_urls("naam")},
        {
            "key": "context",
            "label": _("Context"),
            "cell": "context",
            "priority": 2,
            **_sort_urls("context"),
        },
        {
            "key": "status",
            "label": _("Status"),
            "cell": "status",
            **_sort_urls("status"),
        },
        {
            "key": "bedrag",
            "label": _("Bedrag"),
            "cell": "amount",
            "num": True,
            **_sort_urls("bedrag"),
        },
        {
            "key": "ontvangen",
            "label": _("Ontvangen"),
            "cell": "extra",
            "num": True,
            "priority": 1,
        },
        {
            "key": "saldo",
            "label": _("Saldo"),
            "cell": "extra",
            "num": True,
            **_sort_urls("saldo"),
        },
        {"key": "acties", "label": _("Acties"), "cell": "actions"},
    ]

    # Gegroepeerde context-filter (#549): dezelfde grouped_filter-macro als de
    # Werkbank. Heterogene groepen (jaren/onderdelen) → (value, label)-tuples.
    _comp = sorted(componenten.items(), key=lambda kv: kv[1])
    _jaren = sorted(jaren, reverse=True)
    context_top = [("all", _("Alle betalingen")), ("membership", _("Alle lidmaatschappen"))]
    context_groups: dict = {}
    if _jaren:
        context_groups[_("Lidmaatschap per jaar")] = [
            (f"year-{j}", f"{_('Lidgeld')} {j}") for j in _jaren
        ]
    if _comp:
        context_groups[_("Activiteit / onderdeel")] = [
            (f"comp-{cid}", label) for cid, label in _comp
        ]
    return BetalingenView(
        records=zichtbaar,
        groepen=groepen,
        context=context,
        # Eén bron voor de statuslabels (#617-2): de filterbalk én de editors in het
        # fragment lezen hieruit, zodat er nergens nog rauwe codes (pending/paid)
        # op het scherm komen. Het fragment wordt ook los gerenderd, dus een
        # {% set %} in betalingen.html zou daar niet bestaan.
        # §2.12: nooit rauwe DB-waarden op het scherm. Per request opgebouwd, zodat
        # _() de taal van de tenant volgt (#630).
        # CR-12 phase 1: these two came from two dictionaries in this file.
        # Now from the label tables, so the screen, the export and the report
        # dimension show the same word by definition (AC3) and an
        # English-language department sees both of them in English (AC2).
        method_labels=dict(code_labels("payment_method")),
        # The two filter options at the top are *not* codes: "all statuses"
        # and "outstanding balance" are ways of looking, not values that sit
        # in the column. So they keep going through `_()`.
        status_labels=_status_labels(),
        # Badge per afgeleide status (service.derived_status). Label + kleur horen
        # bij de weergave en dus hier; wélke status het is, beslist de service —
        # "Deels betaald" werd vroeger in de template zelf uitgerekend (#635-9).
        kaart_status=_status_badges(),
        status=status,
        openstaand=openstaand,
        q=q,
        scope=scope,
        zicht=zicht,
        segments=segments,
        # The three key figures of the title row (block 2, Koen, 2 October
        # 2026): each one figure, the `warning` tint only on an open amount
        # above zero. Counted over the selection before the status filter, like
        # the band they replace — the filter cuts the table, not the figures.
        figures=[
            {
                "value": f"€ {geld(kpi['due'])}",
                "label": _("Netto te betalen"),
                "title": _("Wat er in deze selectie te betalen is, na terugbetalingen."),
            },
            {
                "value": f"€ {geld(kpi['to_receive'])}",
                "label": _("Nog te ontvangen"),
                "title": _("Wat er in deze selectie nog moet binnenkomen."),
                "warning": kpi["to_receive"] > 0,
            },
            {
                "value": f"€ {geld(kpi['to_refund'])}",
                "label": _("Nog terug te betalen"),
                "title": _("Wat er in deze selectie nog terugbetaald moet worden."),
                "warning": kpi["to_refund"] > 0,
            },
        ],
        page_sizes=list(PER_PAGE_OPTIONS),
        # Under `⋯`: the export of what the list shows — the toolbar's fields
        # travel as its query.
        toolbar_menu=[
            {
                "label": _("Export (.ods)"),
                "href": "/admin/betalingen/export",
                "icon": "download",
                "with_state": True,
            }
        ],
        toolbar_hidden=toolbar_hidden,
        embedded=stil,
        # K6 (#1560): the activity's figures stand on its summary card
        # (Gegevens); the household and the registration keep the band until
        # pilot B gives them a summary.
        show_band=stil and not activiteit_id,
        # The row a visitor came back to, unfolded again.
        open_row=(stand.get(BOOKING_PARAM) or "") if stil else "",
        kpi=kpi,
        page=page,
        per_page=per_page,
        totaal_groepen=totaal_groepen,
        pager_url=pager_url,
        return_url=return_url,
        componenten=_comp,
        jaren=_jaren,
        context_top=context_top,
        context_groups=context_groups,
        may_mutate=may_mutate,
        columns=columns,
        column_modes={priority: column_modes[key] for key, priority in OPTIONAL_COLUMNS.items()},
        column_choices=[
            {"key": "ontvangen", "label": _("Ontvangen"), "mode": column_modes["ontvangen"]},
            {"key": "context", "label": _("Context"), "mode": column_modes["context"]},
        ],
        sort=sort,
        sort_options=[
            ("", _("Recentste eerst")),
            ("naam", _("Naam (A–Z)")),
            ("-naam", _("Naam (Z–A)")),
            ("context", _("Context (A–Z)")),
            ("status", _("Status")),
            ("-bedrag", _("Bedrag (hoog–laag)")),
            ("bedrag", _("Bedrag (laag–hoog)")),
            ("-saldo", _("Saldo (hoog–laag)")),
        ],
        # The one sentence of the empty state: what made the list empty.
        empty_reason=(
            _("Geen betalingen gevonden voor “%(q)s”.") % {"q": q}
            if q
            else _("Geen openstaande betalingen.")
            if zicht == "openstaand"
            else _("Geen betalingen in deze context.")
            if context != "all"
            else _("Geen betalingen voor deze selectie.")
            if scope
            else _("Er zijn nog geen betalingen.")
        ),
        csrf_token=csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        nav_items=nav_items or [],
    )


@router.get("/admin/betalingen", response_class=HTMLResponse)
def betalingen_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    # Role-aware nav (#530): een FINANCE-only gebruiker (geen ADMIN/OPERATOR) ziet
    # enkel de schermen die hij mag openen — anders 403't elke andere nav-link.
    nav = admin_nav("/admin/betalingen", roles=get_user_roles(db, email))
    return templates.TemplateResponse(
        request, "betalingen.html", _view(request, db, email, nav_items=nav).as_context()
    )


@router.get("/admin/activiteiten/{activity_id}/betalingen", response_class=HTMLResponse)
def activiteit_betalingen_tab(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
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
    ctx = _view(
        request, db, email, nav_items=nav, forceer_activiteit=activity_id, scope_stil=True
    ).as_context()
    ctx["a"] = activiteit
    # #1070: één bouwer voor de hele recordkop. Stond hier met de hand samengesteld
    # naast dezelfde samenstelling in `activities.admin_ui`; een sleutel erbij ging
    # dan onvermijdelijk op één van de twee plekken ontbreken.
    ctx.update(record_kop_ctx(db, activiteit, email, "betalingen"))
    from app.ui import record_frame

    ctx.update(record_frame(request, db, "/admin/activiteiten"))  # #1557
    return templates.TemplateResponse(request, "admin_activiteit_betalingen.html", ctx)


@router.get("/admin/leden/gezin/{family_id}/betalingen", response_class=HTMLResponse)
def gezin_betalingen_tab(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    """De Betalingen-tab van de gezinspagina (golf 9, #913): het gewone
    betalingenscherm, gefilterd op dit gezin, onder de gezins-recordkop.
    FINANCE-gated zoals /admin/betalingen zelf (#544)."""
    from app.domains.mdm.api import gezin_tabs
    from app.domains.membership.api import get_family

    try:
        gezin = get_family(db, family_id)
    except Exception:
        gezin = None
    if gezin is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    nav = admin_nav("/admin/leden", roles=get_user_roles(db, email))
    ctx = _view(
        request, db, email, nav_items=nav, forceer_gezin=family_id, scope_stil=True
    ).as_context()
    ctx["family"] = gezin
    ctx["record_tabs"] = gezin_tabs(db, gezin, email, "betalingen")
    return templates.TemplateResponse(request, "admin_gezin_betalingen.html", ctx)


@router.get("/admin/inschrijvingen/{registration_id}/betalingen", response_class=HTMLResponse)
def inschrijving_betalingen_tab(
    registration_id: int,
    request: Request,
    terug: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    """De Betalingen-tab van de inschrijvingspagina (feedback 15 sep): het
    gewone betalingenscherm in de inschrijvingscope, onder de gedeelde
    recordkop — dit verving de P13-chip op dat scherm. FINANCE-gated zoals
    /admin/betalingen zelf (#544)."""
    from app.domains.activities.api import get_registration, inschrijving_kop_ctx

    reg = get_registration(db, registration_id, include_deleted=True)
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    # Nav-focus (Koen, 15 sep): je kwam uit Activiteiten — de navigatie blijft
    # daar staan, ook al rendert het betalingenscherm.
    nav = admin_nav("/admin/activiteiten", roles=get_user_roles(db, email))
    ctx = _view(
        request, db, email, nav_items=nav, forceer_inschrijving=registration_id, scope_stil=True
    ).as_context()
    kop = inschrijving_kop_ctx(db, registration_id, email, "betalingen", terug)
    if kop is None:  # kan niet meer na de 404 hierboven; mypy weet dat niet
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    ctx.update(kop)
    ctx["reg"] = reg
    return templates.TemplateResponse(request, "admin_inschrijving_betalingen.html", ctx)


@router.get("/admin/betalingen/lijst", response_class=HTMLResponse)
def betalingen_lijst(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    ctx = _view(request, db, email).as_context()
    ctx["oob_boven"] = True
    response = templates.TemplateResponse(request, "_betalingen_lijst.html", ctx)
    # K6 (#1560): on a record's tab the address that holds the list's state is
    # the tab's, not the payments list's (`main.py:_filter_push_url` keeps a
    # push that is already set).
    if ctx["embedded"] and request.headers.get("X-Raak-Filter") == "1":
        response.headers["HX-Push-Url"] = ctx["return_url"]
    return response


@router.get("/admin/betalingen/export")
def betalingen_export(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    from app.domains.payment.exports import build_payments_export_ods

    # Dezelfde bron als het scherm (#669/#671): de exportknop draagt de filterstand
    # in zijn href, en die wordt hier langs dezelfde helper gelezen. Zonder dat
    # exporteert hij iets anders dan wat je ziet — een stille afwijking tussen
    # beeld en bestand.
    stand = filterparams(request)
    context = (stand.get("context") or "all").strip()
    # K1 (#1555): the same derivation as `_view` — the status select is gone,
    # the segment travels.
    status = "all"
    openstaand = False
    zicht = _zicht(stand)
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
        db,
        context=context,
        status=status,
        openstaand=openstaand,
        registration_id=inschrijving_id if inschrijving_id.isdigit() else "",
        payables=paren,
        zicht=zicht,
    )
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": 'attachment; filename="betalingen-en-vorderingen.ods"'},
    )


# ── The booking page (#1574, CR-11 pilot A) ────────────────────────────────────
#
# A payments row opens a record page (CR-11 block 4: the row is the way in), and
# that page carries what the unfold under the row carried: the booking's data,
# its edit form, the refund form and the actions of the head. Nothing new: every
# form posts to the route the unfold posted to, with `X-Booking-Page`, so
# `_uitvoeren` answers with this page instead of the list.

BOOKINGS = "/admin/betalingen"


def _page_post(record_id, action: str) -> str:
    """The htmx attributes of a control on a booking page that posts `action`
    for this booking and gets the page back."""
    return (
        f'hx-post="{BOOKINGS}/{record_id}/{action}" hx-target="body" hx-swap="innerHTML" '
        f'hx-headers=\'{{"X-Booking-Page": "{record_id}"}}\''
    )


def _booking_view(
    request: Request,
    db: Session,
    email: str,
    record_id: str,
    *,
    error: str | None = None,
    saved: bool = False,
) -> BookingView | None:
    """The view-model of one booking's page, or None when there is no such
    booking (any more)."""
    from urllib.parse import quote

    from app.domains.payment.api import enriched_records
    from app.ui import record_frame

    # The same enrichment the list shows, so the page names what the row named.
    records = enriched_records(db)
    rec = next((r for r in records if str(r.id) == record_id), None)
    if rec is None:
        return None
    card = _kaart(rec)
    frame = record_frame(request, db, BOOKINGS)
    keep = frame["way_back"]["keep"]
    here = f"{BOOKINGS}/{rec.id}" + (f"?{keep}" if keep else "")
    # A record opened from here leads back to this page, which keeps its own way
    # back (`keep`) — so the origin survives two steps.
    back_here = quote(here, safe="/")
    may_mutate = may(db, email, Right.PAYMENT_MANAGE)
    badges = _status_badges()
    labels = _status_labels()
    name = rec.contact_name or "—"

    def _status_badge(r) -> tuple[str, str]:
        return badges.get(_kaart(r)["status"], (labels.get(str(r.status_code), ""), "gray"))

    def _booking_link(r) -> dict:
        label, tone = _status_badge(r)
        return {
            "label": _("Terugbetaling") if r.is_refund else _("Betaling"),
            "href": f"{BOOKINGS}/{r.id}?terug={back_here}",
            "amount": Decimal(str(r.amount)),
            "status_label": label,
            "status_tone": tone,
        }

    # The facts line: the context as a jump link to its record (CR-11 Q56) — the
    # activity of a registration booking, the household of a membership booking —
    # then the registration itself and the structured communication.
    context = rec.description or _("Betaling")
    if rec.component_name:
        context = f"{context} — {rec.component_name}"
    facts: list[dict] = []
    if rec.context_href:
        facts.append(
            {"text": context, "href": f"{rec.context_href}?terug={back_here}", "kind": "reference"}
        )
    else:
        facts.append({"text": context})
    if rec.payable_href:
        facts.append(
            {
                "text": _(rec.payable_label),
                "href": f"{rec.payable_href}?terug={back_here}",
                "kind": "reference",
            }
        )
    if rec.structured_communication:
        facts.append({"text": rec.structured_communication})

    status_label, status_tone = _status_badge(rec)
    primary = None
    actions: list[dict] = []
    if may_mutate:
        if not rec.is_paid:
            question = (
                _("Als volledig terugbetaald bevestigen?")
                if rec.is_refund
                else _("Als volledig betaald bevestigen?")
            )
            primary = {
                "label": _("Bevestig"),
                "attrs": f'{_page_post(rec.id, "bevestigen")} data-confirm="{question}"',
            }
        if rec.is_online:
            actions.append(
                {
                    "kind": "record",
                    "verb": "state",
                    "label": _("Status verversen"),
                    "attrs": _page_post(rec.id, "verversen"),
                }
            )
        if card["mag_verwijderen"]:
            actions.append(
                {
                    "kind": "delete",
                    "label": _("Verwijderen"),
                    "attrs": _page_post(rec.id, "verwijderen"),
                    "confirm": _("Deze terugbetaling verwijderen?")
                    if rec.is_refund
                    else _("Deze betaling verwijderen?"),
                }
            )

    parent = next((r for r in records if rec.refund_of_id and r.id == rec.refund_of_id), None)
    return BookingView(
        rec=rec,
        card=card,
        record_head={
            "title": (
                _("Terugbetaling aan %(name)s") if rec.is_refund else _("Betaling van %(name)s")
            )
            % {"name": name},
            "badges": [{"label": status_label, "tone": status_tone}],
            "facts": facts,
            "primary": primary,
            "actions": actions,
        },
        way_back=frame["way_back"],
        parent=_booking_link(parent) if parent is not None else None,
        refunds=[_booking_link(r) for r in records if r.refund_of_id == rec.id],
        may_mutate=may_mutate,
        status_labels=labels,
        method_label=dict(code_labels("payment_method")).get(
            str(getattr(rec.method, "value", rec.method)), ""
        ),
        here=here,
        csrf_token=csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        nav_items=admin_nav(BOOKINGS, roles=get_user_roles(db, email)),
        error=error,
        toast_opgeslagen=saved,
    )


def _booking_answer(
    request: Request, db: Session, email: str, record_id: str, *, error: str | None
) -> Response:
    """What a mutation from a booking page answers: the page again, with the
    reason of a refusal — or, when the booking is gone (it was deleted), the way
    back the page had."""
    from app.ui import record_frame

    view = _booking_view(request, db, email, record_id, error=error, saved=error is None)
    if view is None:
        return Response(
            status_code=204,
            headers={"HX-Redirect": record_frame(request, db, BOOKINGS)["way_back"]["href"]},
        )
    return templates.TemplateResponse(request, "betaling.html", view.as_context())


@router.get("/admin/betalingen/{record_id}", response_class=HTMLResponse)
def booking_page(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_VIEW)),
):
    """The record page of one booking (#1574). Who may see the payments list may
    see it; only FINANCE and OPERATOR get its actions."""
    view = _booking_view(request, db, email, record_id)
    if view is None:
        raise HTTPException(status_code=404, detail=_("Betaling niet gevonden."))
    return templates.TemplateResponse(request, "betaling.html", view.as_context())


@router.post(
    "/admin/betalingen/{record_id}/bevestigen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_bevestigen(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    note: str = Form(""),
):
    return _uitvoeren(bevestig_betaling, request, db, email, record_id, note=note, actor=email)


@router.post(
    "/admin/betalingen/{record_id}/refund",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_refund(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    amount: str = Form(""),
    note: str = Form(""),
):
    return _uitvoeren(
        registreer_terugbetaling,
        request,
        db,
        email,
        record_id,
        amount=amount,
        note=note,
        actor=email,
    )


@router.post(
    "/admin/betalingen/{record_id}/bijwerken",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_bijwerken(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    amount_paid: str = Form(""),
    note: str = Form(""),
):
    """Betaald bedrag invullen + als betaald bevestigen (#455)."""
    return _uitvoeren(
        bevestig_betaling,
        request,
        db,
        email,
        record_id,
        note=note,
        amount_paid=amount_paid,
        actor=email,
    )


@router.post(
    "/admin/betalingen/{record_id}/bewerken",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_bewerken(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    status: str = Form(""),
    amount_paid: str = Form(""),
    note: str = Form(""),
):
    """Geünificeerde 'Bewerken' (#515): status + betaald bedrag + opmerking in één
    form, voor charges én refunds (zo registreer je op een refund de effectief
    uitbetaalde som). Hergebruikt de gedeelde service-regel `edit_payment_record`,
    zodat de admin-UI en de JSON-API dezelfde validatie delen."""
    # Het omdraaien van het teken bij een terugbetaling en de bovengrens erop
    # stonden hier; ze bepalen hoeveel geld er terugvloeit en horen dus in de
    # service (#635-I).
    return _uitvoeren(
        bewerk_betaling,
        request,
        db,
        email,
        record_id,
        status=status,
        amount_paid=amount_paid,
        note=note,
        actor=email,
    )


@router.post(
    "/admin/betalingen/{record_id}/verversen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_verversen(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
):
    """Mollie-status ophalen en toepassen (handmatige tegenhanger van de webhook, #455)."""
    return _uitvoeren(ververs_betaalstatus, request, db, email, record_id, actor=email)


@router.post(
    "/admin/betalingen/{record_id}/status",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_status(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    status: str = Form(...),
    note: str = Form(""),
):
    """Vrije status-correctie door de penningmeester (#455)."""
    return _uitvoeren(
        zet_betaalstatus, request, db, email, record_id, status, note=note, actor=email
    )


@router.post(
    "/admin/betalingen/{record_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def betaling_verwijderen(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAYMENT_MANAGE)),
    note: str = Form(""),
):
    """Betaal-/terugbetaalrecord verwijderen (soft-delete, uit het saldo, #455).
    Corrigeert ook een foute refund."""
    return _uitvoeren(verwijder_betaling, request, db, email, record_id, note=note, actor=email)

"""Server-rendered ledenbeheer (fase 2b, #400 — §21): gezinnenlijst met zoeken
en paginering, gezinsdetail (personen, adres, bestuurslid, lidmaatschappen) en
de leden-import-wizard (preview → commit).

De schermen hergebruiken de bestaande admin-API-functies (routers/members.py,
domains/mdm/import_router.py — #444) als servicelaag — geen dubbele businesslogica; deze
module bouwt alleen view-models en kiest templates.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, filterparams, is_fragment_request, templates
from app.domains.mdm.viewmodels import LedenView
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/leden")


def _codes(db: Session) -> dict:
    from app.domains.mdm.api import admin_code_lists

    return admin_code_lists(db)


def _lidmaatschapsjaren(db: Session) -> list[int]:
    from app.domains.membership.api import membership_years

    return membership_years(db)


def _kpi(db: Session) -> dict:
    """De drie kengetallen boven het ledenbeheer (C1-KPI-rij, #582).

    "Nog niet vernieuwd" draagt het doeljaar in zijn label, want dat jaar kantelt
    op de tenant-datum ``membership_next_year_from_md``: vóór die dag gaat de
    campagne over het lopende jaar, erna over het volgende. De logica zelf staat
    in het membership-domein — dit scherm telt niet zelf.
    """
    from app.domains.membership.api import not_renewed_count, renewal_years
    from app.domains.payment.api import current_membership_counts

    gezinnen, personen = current_membership_counts(db)
    # Het referentiejaar (#611): de KPI-kaart noemt het jaar waarin iemand lid wás,
    # zodat duidelijk is dat we naar vorig jaar kijken en niet twee jaar terug. Het
    # kantelt mee met de tenant-datum, dus het mag niet hardgecodeerd zijn.
    referentiejaar, doeljaar = renewal_years()
    return {"kpi_gezinnen": gezinnen, "kpi_personen": personen,
            "kpi_niet_vernieuwd": not_renewed_count(db), "kpi_doeljaar": doeljaar,
            "kpi_referentiejaar": referentiejaar}


def _lijst_view(request: Request, db: Session,
                nav_items: list | None = None) -> LedenView:
    """View-model van het ledenoverzicht (#643): pagina én fragment.

    Het fragment wordt los gerenderd bij zoeken, filteren en pagineren, dus het
    krijgt hetzelfde model — inclusief de KPI-rij, die anders bij een swap zou
    verdwijnen.
    """
    from app.domains.membership.api import list_families

    # #671: uit HX-Current-URL als htmx die meestuurt, anders uit de query-string.
    stand = filterparams(request)
    q = (stand.get("q") or "").strip()
    status = (stand.get("status") or "").strip()
    jaar_raw = (stand.get("jaar") or "").strip()
    jaar = int(jaar_raw) if jaar_raw.isdigit() else None
    try:
        page = max(1, int(stand.get("page", "1")))
    except ValueError:
        page = 1
    data = list_families(db, page=page, page_size=25, q=q or None,
                         status=status or None, membership_year=jaar)
    # total + page_size erbij zodat ui.pager() "x–y van n" kan tonen (#580).
    return LedenView(
        families=data.items, page=data.page, total=data.total,
        per_page=data.page_size, total_pages=data.total_pages,
        q=q, status=status, jaar=jaar,
        jaren=_lidmaatschapsjaren(db),
        gefilterd=bool(q or status or jaar),
        csrf_token=csrf_from_request(request),
        nav_items=nav_items or [],
        **_kpi(db),
    )


def _detail_ctx(request: Request, db: Session, family_id: int) -> dict:
    from app.domains.membership.api import get_family

    family = get_family(db, family_id)
    from app.domains.mdm.api import list_persons, list_postal_codes

    persons = list_persons(db)
    postal_codes = list_postal_codes(db)
    hoofdlid = next((m for m in family.members
                     if (m.relation_type or "").upper() == "HOOFDLID"),
                    family.members[0] if family.members else None)
    overige = [m for m in family.members if hoofdlid is None or m.id != hoofdlid.id]
    from datetime import date
    return {"family": family, "hoofdlid": hoofdlid, "overige": overige,
            "current_year": date.today().year,
            "all_persons": persons, "postal_codes": postal_codes,
            "csrf_token": csrf_from_request(request), **_codes(db)}


def _detail_response(request: Request, db: Session, family_id: int, *,
                     toast: bool = False):
    ctx = _detail_ctx(request, db, family_id)
    ctx["toast_opgeslagen"] = toast
    # Oob-kopverversing (HDEV-melding 15 sep) — zie _aa_detail.html.
    from app.domains.auth.api import SESSION_COOKIE, read_session_value
    from app.domains.mdm.api import gezin_tabs

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email:
        ctx["record_tabs"] = gezin_tabs(db, ctx["family"], email, "overzicht")
        ctx["oob_kop"] = True
    return templates.TemplateResponse(request, "_leden_detail.html", ctx)


def _kaart_response(request: Request, db: Session, family_id: int, *,
                    kaarten: list[str], toast: bool = False, kop: bool = False,
                    bestuurslid: bool = False):
    """The answer to one partial action (#1111): only the card(s) it changed.

    Every action used to answer with the whole block, re-read from the database;
    that wiped whatever the board member had typed in another card and reset the
    Alpine state, so the panel closed and nothing seemed to happen. Now the route
    names its cards; what changes elsewhere travels out-of-band: the record
    header (`kop`, name and address) and the board-member card (`bestuurslid`,
    which lists every person by name).
    """
    ctx = _detail_ctx(request, db, family_id)
    ctx.update(kaarten=kaarten, toast_opgeslagen=toast, oob_bestuurslid=bestuurslid)
    if kop:
        from app.domains.auth.api import SESSION_COOKIE, read_session_value
        from app.domains.mdm.api import gezin_tabs

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
        if email:
            ctx["record_tabs"] = gezin_tabs(db, ctx["family"], email, "overzicht")
            ctx["oob_kop"] = True
    return templates.TemplateResponse(request, "_leden_deel.html", ctx)


# ── Overzicht ──────────────────────────────────────────────────────────────────

@router.get("/admin/leden", response_class=HTMLResponse)
def leden_page(request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(
        request, "leden.html", _lijst_view(request, db, nav_items=NAV).as_context())


@router.get("/admin/leden/lijst", response_class=HTMLResponse)
def leden_lijst(request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Enkel de kaarten: de filterbalk swapt dit fragment, zodat het zoekveld niet
    onder je vingers vervangen wordt."""
    return templates.TemplateResponse(request, "_leden_lijst.html",
                                      _lijst_view(request, db).as_context())


@router.get("/admin/leden/nieuw", response_class=HTMLResponse)
def lid_nieuw(request: Request, db: Session = Depends(get_db),
              email: str = Depends(require_admin_ui)):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    from app.domains.mdm.api import list_postal_codes

    return templates.TemplateResponse(request, "leden_nieuw.html", {
        "nav_items": NAV,
        "csrf_token": csrf_from_request(request),
        "postal_codes": list_postal_codes(db),
        "values": {}, "error": None,
        **_codes(db),
    })


@router.get("/admin/leden/nieuw/persoon-rij", response_class=HTMLResponse)
def lid_nieuw_persoon_rij(request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    """Een lege rij voor een extra gezinslid (#1110).

    Hetzelfde fragment als het publieke formulier, want het zijn dezelfde velden;
    een eigen admin-route omdat dit scherm achter de beheerdeur hoort te zitten.
    Er gaat niets naar de databank en er wordt niets vervangen, dus wat je al
    typte blijft staan.
    """
    try:
        index = max(1, int(request.query_params.get("index", "1")))
    except ValueError:
        index = 1
    return templates.TemplateResponse(request, "_lid_persoon_rij.html", {
        **_codes(db), "i": index, "values": {}})


@router.post("/admin/leden", dependencies=[Depends(require_csrf)])
async def gezin_aanmaken(request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui)) -> Response:
    """Nieuw gezin met hoofdlid, adres, contactgegevens en lidmaatschap (#1110).

    Eén formulier, één opslaan-actie, één transactie — in de vorm van het publieke
    "Word lid" en langs dezelfde schrijfweg. Tot #1110 waren het vier aparte
    opslag-acties en vroeg dit scherm e-mail en gsm van het hoofdlid niet eens,
    terwijl het publieke formulier ze verplicht: je kon via de beheerkant dus een
    lid aanmaken dat publiek geweigerd zou worden. Dezelfde regel op één plek
    (`FamilyCreate`) betekent dat dat niet meer kan.

    #713: de beheerder tekent de auditregels.
    """
    from pydantic import ValidationError

    from app.domains.membership.api import (FamilyCreate, FamilyMemberCreate,
                                            create_family_by_admin, parse_member_rows)
    from app.domains.mdm.api import list_postal_codes

    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}

    def _fout(melding: str):
        """Het formulier opnieuw, mét wat er ingevuld stond en de reden.

        De keuzelijsten worden hier opgehaald en niet bovenaan: een mislukte
        opslag rolt de transactie terug (#1110), en objecten die vóór die rollback
        geladen zijn, bestaan daarna niet meer. Ze alsnog renderen geeft een
        harde fout in plaats van de nette foutpagina.
        """
        return templates.TemplateResponse(
            request, "leden_nieuw.html",
            {"nav_items": NAV, "csrf_token": csrf_from_request(request),
             "postal_codes": list_postal_codes(db), "values": values,
             "error": melding, **_codes(db)}, status_code=422)

    rijen = parse_member_rows(form)
    if not rijen:
        return _fout(_("Vul minstens het hoofdlid in."))
    try:
        data = FamilyCreate(
            street=(values.get("street") or "").strip(),
            house_number=(values.get("house_number") or "").strip(),
            bus_number=(values.get("bus_number") or "").strip() or None,
            postal_code=(values.get("postal_code") or "").strip(),
            members=[FamilyMemberCreate(
                first_name=r["first_name"], last_name=r["last_name"],
                date_of_birth=r["date_of_birth"] or None,
                gender_code=r["gender_code"] or None,
                email=r["email"] or None, phone=r["phone"] or None,
                mobile=r["mobile"] or None,
                relation_type=r["relation_type"] or ("HOOFDLID" if i == 0 else "PARTNER"),
            ) for i, r in enumerate(rijen)],
        )
    except ValidationError as exc:
        return _fout(str(exc.errors()[0].get("msg", _("Ongeldige invoer."))))

    try:
        gezin = create_family_by_admin(db, data, actor=email)
    except HTTPException as exc:
        return _fout(str(exc.detail))

    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/leden/gezin/{gezin.id}"})


@router.get("/admin/leden/gezin/{family_id}", response_class=HTMLResponse)
def gezin_detail(family_id: int, request: Request, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    """Een kaart opent de paginabrede gezinseditor (C1, #582); de bewerkingen
    daarbinnen blijven htmx-fragmenten die in #leden-detail landen."""
    if is_fragment_request(request):
        return _detail_response(request, db, family_id)
    from app.domains.mdm.api import gezin_tabs

    ctx = _detail_ctx(request, db, family_id)
    return templates.TemplateResponse(request, "leden_gezin.html", {
        "nav_items": NAV, **ctx,
        "record_tabs": gezin_tabs(db, ctx["family"], email, "overzicht")})


@router.get("/admin/leden/gezin/{family_id}/inschrijvingen",
            response_class=HTMLResponse)
def gezin_inschrijvingen_tab(family_id: int, request: Request,
                             sort: str = "datum", richting: str = "asc",
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    """De Inschrijvingen-tab van de gezinspagina (Koen, 15 sep — verving de
    Wijzigingen-tab): wat dit gezin ingeschreven heeft, per activiteit
    gegroepeerd, op basis van de personen van het gezin (person_id én de
    e-mail-terugval voor gastinschrijvingen — dezelfde ene bron als de
    Betalingen-tab)."""
    from urllib.parse import quote

    from app.domains.activities.api import INSCHRIJVING_SORT_VELDEN
    from app.domains.membership.api import get_family
    from app.domains.mdm.api import family_registrations, gezin_tabs

    try:
        family = get_family(db, family_id)
    except Exception:
        family = None
    if family is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    # Normaliseren vóór de URL-bouw: een vervalste sort/richting mag nooit
    # rauw in sorteer_urls of de terugweg belanden (zelfde regel als de
    # activiteitstab, die de gevalideerde waarden uit de helper terugkrijgt).
    if sort not in INSCHRIJVING_SORT_VELDEN:
        sort = "datum"
    richting = "desc" if richting == "desc" else "asc"
    groepen = family_registrations(db, family_id, sort, richting)
    # Zelfde sorteer- en terug-machinerie als de activiteitstab: het gedeelde
    # sjabloon verwacht exact hetzelfde contract.
    basis = f"/admin/leden/gezin/{family_id}/inschrijvingen"
    sorteer_urls = {
        naam: (f"{basis}?sort={naam}&richting="
               + ("desc" if sort == naam and richting == "asc" else "asc"))
        for naam in INSCHRIJVING_SORT_VELDEN}
    return templates.TemplateResponse(
        request, "admin_gezin_inschrijvingen.html", {
            "nav_items": NAV, "family": family,
            "record_tabs": gezin_tabs(db, family, email, "inschrijvingen"),
            "groepen": groepen, "toon_onderdeel": True,
            "totaal": sum(g["aantal"] for g in groepen),
            "sort": sort, "richting": richting, "sorteer_urls": sorteer_urls,
            "terug": quote(f"{basis}?sort={sort}&richting={richting}",
                           safe=""),
            "csrf_token": csrf_from_request(request),
        })


# ── Mutaties (allemaal: sessie + CSRF; herrenderen het detail) ─────────────────

@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def persoon_opslaan(family_id: int, person_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    first_name: str = Form(""), last_name: str = Form(""),
                    date_of_birth: str = Form(""), gender_code: str = Form(""),
                    contact_email: str = Form("", alias="email"), phone: str = Form(""),
                    mobile: str = Form(""), relation_type: str = Form("")):
    from app.domains.membership.api import update_person, update_person_contacts
    from app.domains.membership.api import PersonUpdate
    from app.domains.membership.api import ContactsUpdate

    update_person(db, person_id, PersonUpdate(
        first_name=first_name.strip(), last_name=last_name.strip(),
        date_of_birth=date_of_birth or None, gender_code=gender_code or None,
    ), admin=admin_user_by_email(db, email))
    update_person_contacts(db, person_id, ContactsUpdate(
        email=contact_email.strip() or None, phone=phone.strip() or None,
        mobile=mobile.strip() or None,
    ), admin=admin_user_by_email(db, email))
    # Relatietype op de MemberPerson-junctie (#498). De regel — nooit promoveren
    # tot HOOFDLID, nooit een bestaand HOOFDLID overschrijven — staat sinds #635-F
    # in de service, met een rauwe query minder in dit scherm.
    from app.domains.membership.api import set_relation_type

    set_relation_type(db, family_id, person_id, relation_type)
    # #742: een afsluitende "Opslaan", dus mét bevestiging. Een persoon toevoegen of
    # verwijderen is een deelactie en krijgt er géén — dezelfde grens als bij #717.
    # #1111: alleen deze kaart; de naam staat ook in de kop en in de
    # bestuurslidlijst, dus die twee reizen oob mee.
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"],
                           toast=True, kop=True, bestuurslid=True)


# ── E-mailadressen van één persoon (#1174) ───────────────────────────────────
#
# Drie aparte acties en geen veld in het Opslaan-formulier. Een adres toevoegen of
# weghalen is een deelactie op één rij, net als een persoon toevoegen of een
# bijlage verwijderen: die krijgen géén bevestigingstoast (#742/#717). Het
# e-mailVELD in dat formulier blijft wat het was — het hoofdadres — zodat de
# gewone weg onveranderd is voor wie maar één adres heeft.

@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}/email",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def email_toevoegen(family_id: int, person_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    extra_email: str = Form("")):
    from app.domains.mdm.api import add_email_address

    add_email_address(db, person_id, extra_email, actor=email)
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"])


@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/hoofd",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def email_hoofdadres(family_id: int, person_id: int, contact_id: int,
                     request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    from app.domains.mdm.api import make_email_primary

    make_email_primary(db, person_id, contact_id, actor=email)
    # Ook de kop en de bestuurslidlijst: die noemen het adres van de persoon.
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"],
                           kop=True)


@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def email_verwijderen(family_id: int, person_id: int, contact_id: int,
                      request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.mdm.api import remove_email_address

    remove_email_address(db, person_id, contact_id, actor=email)
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"],
                           kop=True)


@router.post("/admin/leden/gezin/{family_id}/adres", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def adres_opslaan(family_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui),
                  street: str = Form(""), house_number: str = Form(""),
                  bus_number: str = Form(""), postal_code: str = Form("")):
    from app.domains.membership.api import get_family, update_person_address
    from app.domains.membership.api import AddressUpdate

    family = get_family(db, family_id)
    hoofdlid = next((m for m in family.members
                     if (m.relation_type or "").upper() == "HOOFDLID"),
                    family.members[0] if family.members else None)
    if hoofdlid is None:
        raise HTTPException(status_code=400, detail=_("Gezin zonder personen."))
    update_person_address(db, hoofdlid.id, AddressUpdate(
        street=street.strip(), house_number=house_number.strip(),
        bus_number=bus_number.strip() or None, postal_code=postal_code.strip(),
    ), admin=admin_user_by_email(db, email))
    # #1111: alleen de adreskaart; het adres staat ook in de kop.
    return _kaart_response(request, db, family_id, kaarten=["adres"], toast=True,
                           kop=True)


@router.post("/admin/leden/gezin/{family_id}/personen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def persoon_toevoegen(family_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      first_name: str = Form(""), last_name: str = Form(""),
                      date_of_birth: str = Form(""), gender_code: str = Form(""),
                      contact_email: str = Form("", alias="email"), phone: str = Form(""),
                      mobile: str = Form(""), relation_type: str = Form("PARTNER")):
    from app.domains.membership.api import add_person_to_family, get_family
    from app.domains.membership.api import PersonAddToFamily

    # `add_person_to_family` geeft het hele gezin terug; de nieuwe persoon is de
    # enige die er vóór de toevoeging niet in zat (#1111: zijn kaart is het antwoord).
    voorheen = {m.id for m in get_family(db, family_id).members}
    gezin = add_person_to_family(db, family_id, PersonAddToFamily(
        first_name=first_name.strip(), last_name=last_name.strip(),
        date_of_birth=date_of_birth or None, gender_code=gender_code or None,
        email=contact_email.strip() or None, phone=phone.strip() or None,
        mobile=mobile.strip() or None, relation_type=relation_type,
    ), admin=admin_user_by_email(db, email))
    # #1111: de nieuwe persoonkaart plus een verse toevoegkaart, in de plaats van
    # de toevoegkaart die postte; de bestuurslidlijst krijgt de nieuwe naam oob.
    (nieuw_id,) = {m.id for m in gezin.members} - voorheen
    return _kaart_response(request, db, family_id,
                           kaarten=[f"persoon:{nieuw_id}", "toevoegen"],
                           bestuurslid=True)


@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def persoon_verwijderen(family_id: int, person_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_person

    delete_person(db, person_id, admin=admin_user_by_email(db, email))
    # #1111: de kaart verdwijnt (leeg antwoord op haar eigen outerHTML-doel); de
    # bestuurslidlijst noemde deze persoon en reist oob mee.
    return _kaart_response(request, db, family_id, kaarten=[], bestuurslid=True)


@router.post("/admin/leden/gezin/{family_id}/bestuurslid", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def bestuurslid_zetten(family_id: int, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       person_id: str = Form("")):
    from app.domains.membership.api import assign_board_member
    from app.domains.membership.api import BoardMemberAssign

    assign_board_member(db, family_id, BoardMemberAssign(
        person_id=int(person_id) if person_id else None,
    ), admin=admin_user_by_email(db, email))
    return _kaart_response(request, db, family_id, kaarten=["bestuurslid"])


@router.post("/admin/leden/gezin/{family_id}/lidmaatschappen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def lidmaatschap_toevoegen(family_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui),
                           year: int = Form(...)):
    from app.domains.membership.api import create_membership_for_family
    from app.domains.membership.api import MembershipCreate

    create_membership_for_family(db, family_id, MembershipCreate(year=year, is_active=True),
                                 admin=admin_user_by_email(db, email))
    return _kaart_response(request, db, family_id, kaarten=["lidmaatschappen"])


@router.post("/admin/leden/gezin/{family_id}/lidmaatschappen/{membership_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def lidmaatschap_verwijderen(family_id: int, membership_id: int, request: Request,
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_membership

    delete_membership(db, membership_id, admin=admin_user_by_email(db, email))
    return _kaart_response(request, db, family_id, kaarten=["lidmaatschappen"])


@router.post("/admin/leden/gezin/{family_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def gezin_verwijderen(family_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_family

    delete_family(db, family_id, admin=admin_user_by_email(db, email))
    # Verwijderen gebeurt vanuit de gezinseditor; die pagina bestaat daarna niet
    # meer, dus terug naar de lijst (#582).
    return Response(status_code=204, headers={"HX-Redirect": "/admin/leden"})


# ── Leden-import-wizard ────────────────────────────────────────────────────────

@router.get("/admin/leden-import", response_class=HTMLResponse)
def import_page(request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    nav = [dict(item, active=False) for item in NAV]
    return templates.TemplateResponse(request, "leden_import.html", {
        "csrf_token": csrf_from_request(request), "nav_items": nav,
    })


@router.post("/admin/leden-import/preview", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def import_preview(request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         file: UploadFile = File(...)):
    from app.domains.mdm.api import import_preview

    try:
        data = await import_preview(db, file, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
            "error": exc.detail, "stap": "preview"})
    return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
        "error": None, "stap": "preview", "data": data, "report": data["report"]})


@router.post("/admin/leden-import/commit", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def import_commit(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui), token: str = Form(...)):
    from app.domains.mdm.api import import_commit

    try:
        data = import_commit(db, token, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
            "error": exc.detail, "stap": "commit"})
    return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
        "error": None, "stap": "commit", "data": data, "report": data["report"]})

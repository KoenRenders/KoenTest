"""Server-rendered ledenbeheer (fase 2b, #400 — §21): gezinnenlijst met zoeken
en paginering, gezinsdetail (personen, adres, bestuurslid, lidmaatschappen) en
de leden-import-wizard (preview → commit).

De schermen hergebruiken de bestaande admin-API-functies (routers/members.py,
domains/mdm/import_router.py — #444) als servicelaag — geen dubbele businesslogica; deze
module bouwt alleen view-models en kiest templates.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    admin_user_by_email,
    csrf_from_request,
    require_admin_ui,
    require_csrf,
)
from app.domains.mdm.api import RelationType
from app.domains.mdm.viewmodels import LedenView
from app.i18n import _
from app.ui import admin_nav, filterparams, is_fragment_request, refusal_response, templates

router = APIRouter(include_in_schema=False)

NAV = "/admin/leden"


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
    from app.domains.membership.api import (
        current_membership_counts,
        not_renewed_count,
        renewal_years,
    )

    gezinnen, personen = current_membership_counts(db)
    # Het referentiejaar (#611): de KPI-kaart noemt het jaar waarin iemand lid wás,
    # zodat duidelijk is dat we naar vorig jaar kijken en niet twee jaar terug. Het
    # kantelt mee met de tenant-datum, dus het mag niet hardgecodeerd zijn.
    referentiejaar, doeljaar = renewal_years()
    return {
        "kpi_gezinnen": gezinnen,
        "kpi_personen": personen,
        "kpi_niet_vernieuwd": not_renewed_count(db),
        "kpi_doeljaar": doeljaar,
        "kpi_referentiejaar": referentiejaar,
    }


def _lijst_view(request: Request, db: Session, nav_items: list | None = None) -> LedenView:
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
    data = list_families(
        db, page=page, page_size=25, q=q or None, status=status or None, membership_year=jaar
    )
    # total + page_size erbij zodat ui.pager() "x–y van n" kan tonen (#580).
    return LedenView(
        families=data.items,
        page=data.page,
        total=data.total,
        per_page=data.page_size,
        total_pages=data.total_pages,
        q=q,
        status=status,
        jaar=jaar,
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
    hoofdlid = next(
        (m for m in family.members if m.relation_type == RelationType.PRIMARY_MEMBER),
        family.members[0] if family.members else None,
    )
    overige = [m for m in family.members if hoofdlid is None or m.id != hoofdlid.id]
    from datetime import date

    return {
        "family": family,
        "hoofdlid": hoofdlid,
        "overige": overige,
        "current_year": date.today().year,
        "all_persons": persons,
        "postal_codes": postal_codes,
        "csrf_token": csrf_from_request(request),
        **_codes(db),
    }


def _detail_response(request: Request, db: Session, family_id: int, *, toast: bool = False):
    ctx = _detail_ctx(request, db, family_id)
    ctx["toast_opgeslagen"] = toast
    # Oob-kopverversing (HDEV-melding 15 sep) — zie _aa_detail.html.
    from app.domains.auth.api import read_session_value
    from app.domains.mdm.api import gezin_tabs

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email:
        ctx["record_tabs"] = gezin_tabs(db, ctx["family"], email, "overzicht")
        ctx["oob_kop"] = True
    return templates.TemplateResponse(request, "_leden_detail.html", ctx)


def _kaart_response(
    request: Request,
    db: Session,
    family_id: int,
    *,
    kaarten: list[str],
    toast: bool = False,
    kop: bool = False,
    bestuurslid: bool = False,
):
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
def leden_page(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    return templates.TemplateResponse(
        request, "leden.html", _lijst_view(request, db, nav_items=admin_nav(NAV)).as_context()
    )


@router.get("/admin/leden/lijst", response_class=HTMLResponse)
def leden_lijst(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """Enkel de kaarten: de filterbalk swapt dit fragment, zodat het zoekveld niet
    onder je vingers vervangen wordt."""
    return templates.TemplateResponse(
        request, "_leden_lijst.html", _lijst_view(request, db).as_context()
    )


@router.get("/admin/leden/nieuw", response_class=HTMLResponse)
def lid_nieuw(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    from app.domains.mdm.api import list_postal_codes

    return templates.TemplateResponse(
        request,
        "leden_nieuw.html",
        {
            "nav_items": admin_nav(NAV),
            "csrf_token": csrf_from_request(request),
            "postal_codes": list_postal_codes(db),
            "values": {},
            "error": None,
            **_codes(db),
        },
    )


@router.get("/admin/leden/nieuw/persoon-rij", response_class=HTMLResponse)
def lid_nieuw_persoon_rij(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
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
    return templates.TemplateResponse(
        request, "_lid_persoon_rij.html", {**_codes(db), "i": index, "values": {}}
    )


@router.post("/admin/leden", dependencies=[Depends(require_csrf)])
async def gezin_aanmaken(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
) -> Response:
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

    from app.domains.mdm.api import list_postal_codes
    from app.domains.membership.api import (
        FamilyCreate,
        FamilyMemberCreate,
        create_family_by_admin,
        parse_member_rows,
    )

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
            request,
            "leden_nieuw.html",
            {
                "nav_items": admin_nav(NAV),
                "csrf_token": csrf_from_request(request),
                "postal_codes": list_postal_codes(db),
                "values": values,
                "error": melding,
                **_codes(db),
            },
            status_code=422,
        )

    rijen = parse_member_rows(form)
    if not rijen:
        return _fout(_("Vul minstens het hoofdlid in."))
    try:
        data = FamilyCreate(
            street=(values.get("street") or "").strip(),
            house_number=(values.get("house_number") or "").strip(),
            bus_number=(values.get("bus_number") or "").strip() or None,
            postal_code=(values.get("postal_code") or "").strip(),
            members=[
                FamilyMemberCreate(
                    first_name=r["first_name"],
                    last_name=r["last_name"],
                    date_of_birth=r["date_of_birth"] or None,
                    gender_code=r["gender_code"] or None,
                    email=r["email"] or None,
                    phone=r["phone"] or None,
                    mobile=r["mobile"] or None,
                    relation_type=r["relation_type"] or ("HOOFDLID" if i == 0 else "PARTNER"),
                )
                for i, r in enumerate(rijen)
            ],
        )
    except ValidationError as exc:
        return _fout(str(exc.errors()[0].get("msg", _("Ongeldige invoer."))))

    try:
        gezin = create_family_by_admin(db, data, actor=email)
    except HTTPException as exc:
        return _fout(str(exc.detail))

    return Response(status_code=204, headers={"HX-Redirect": f"/admin/leden/gezin/{gezin.id}"})


@router.get("/admin/leden/gezin/{family_id}", response_class=HTMLResponse)
def gezin_detail(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    """Een kaart opent de paginabrede gezinseditor (C1, #582); de bewerkingen
    daarbinnen blijven htmx-fragmenten die in #leden-detail landen."""
    if is_fragment_request(request):
        return _detail_response(request, db, family_id)
    from app.domains.mdm.api import gezin_tabs

    ctx = _detail_ctx(request, db, family_id)
    return templates.TemplateResponse(
        request,
        "leden_gezin.html",
        {
            "nav_items": admin_nav(NAV),
            **ctx,
            "record_tabs": gezin_tabs(db, ctx["family"], email, "overzicht"),
        },
    )


@router.get("/admin/leden/gezin/{family_id}/inschrijvingen", response_class=HTMLResponse)
def gezin_inschrijvingen_tab(
    family_id: int,
    request: Request,
    sort: str = "datum",
    richting: str = "",
    rij: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    """The Inschrijvingen tab of the household's page (Koen, 15 September — it
    replaced the Wijzigingen tab): what this household registered for, grouped
    per activity, from the household's persons (person_id and the e-mail
    fallback for guest registrations — the same one source as the Betalingen
    tab). The table is the one of the activity's tab (K6, #1560); the toolbar
    and the rest of the household's page are pilot B."""
    from app.domains.activities.api import parse_registration_sort, registration_table
    from app.domains.mdm.api import family_registrations, gezin_tabs
    from app.domains.membership.api import get_family

    try:
        family = get_family(db, family_id)
    except Exception:
        family = None
    if family is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    table = registration_table(
        db,
        family_registrations(db, family_id),
        page_url=f"/admin/leden/gezin/{family_id}/inschrijvingen",
        # A forged sort never reaches a link: the builder validates it.
        sort=parse_registration_sort(sort, richting),
        open_row=rij,
        sub_is_component=True,
    )
    return templates.TemplateResponse(
        request,
        "admin_gezin_inschrijvingen.html",
        {
            "nav_items": admin_nav(NAV),
            "family": family,
            "record_tabs": gezin_tabs(db, family, email, "inschrijvingen"),
            **table,
            # No list fragment of its own: a sort link is the page.
            "reg_target": "",
            "csrf_token": csrf_from_request(request),
        },
    )


# ── Mutaties (allemaal: sessie + CSRF; herrenderen het detail) ─────────────────


@router.post(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def persoon_opslaan(
    family_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    first_name: str = Form(""),
    last_name: str = Form(""),
    date_of_birth: str = Form(""),
    gender_code: str = Form(""),
    contact_email: str = Form("", alias="email"),
    phone: str = Form(""),
    mobile: str = Form(""),
    relation_type: str = Form(""),
):
    from app.domains.membership.api import (
        ContactsUpdate,
        PersonUpdate,
        update_person,
        update_person_contacts,
    )

    update_person(
        db,
        person_id,
        PersonUpdate(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            date_of_birth=date_of_birth or None,
            gender_code=gender_code or None,
        ),
        admin=admin_user_by_email(db, email),
    )
    # #1219: het e-mailveld zit niet meer in de veldenset van een BESTAANDE
    # persoon — de adressen zijn rijen geworden. `email` dus alleen meegeven als
    # het formulier het droeg: `ContactsUpdate` laat een niet-meegegeven veld met
    # rust, en een lege waarde zou het hoofdadres verwijderen.
    contacten: dict = {"phone": phone.strip() or None, "mobile": mobile.strip() or None}
    if contact_email.strip():
        contacten["email"] = contact_email.strip()
    update_person_contacts(
        db, person_id, ContactsUpdate(**contacten), admin=admin_user_by_email(db, email)
    )
    # De adresrijen uit ditzelfde formulier — één opslaan, één transactie (#1110).
    from app.domains.mdm.api import apply_email_rows

    apply_email_rows(db, person_id, await request.form(), actor=email)
    # Relatietype op de MemberPerson-junctie (#498). De regel — nooit promoveren
    # tot HOOFDLID, nooit een bestaand HOOFDLID overschrijven — staat sinds #635-F
    # in de service, met een rauwe query minder in dit scherm.
    from app.domains.membership.api import set_relation_type

    set_relation_type(db, family_id, person_id, relation_type)
    # #742: een afsluitende "Opslaan", dus mét bevestiging. Een persoon toevoegen of
    # verwijderen is een deelactie en krijgt er géén — dezelfde grens als bij #717.
    # #1111: alleen deze kaart; de naam staat ook in de kop en in de
    # bestuurslidlijst, dus die twee reizen oob mee.
    return _kaart_response(
        request,
        db,
        family_id,
        kaarten=[f"persoon:{person_id}"],
        toast=True,
        kop=True,
        bestuurslid=True,
    )


# ── E-mailadressen van één persoon (#1174) ───────────────────────────────────
#
# Drie aparte acties en geen veld in het Opslaan-formulier. Een adres toevoegen of
# weghalen is een deelactie op één rij, net als een persoon toevoegen of een
# bijlage verwijderen: die krijgen géén bevestigingstoast (#742/#717). Het
# e-mailVELD in dat formulier blijft wat het was — het hoofdadres — zodat de
# gewone weg onveranderd is voor wie maar één adres heeft.


@router.get(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}/email-rij", response_class=HTMLResponse
)
def email_rij(
    family_id: int,
    person_id: int,
    request: Request,
    index: str = "",
    nummer: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    """Een lege e-mailrij om onderaan te plakken (#1219).

    Zelfde vorm als `/admin/leden/nieuw/persoon-rij` (#1110): niets naar de
    databank, niets vervangen, dus wat er al getypt staat blijft staan. De rij
    krijgt nog geen id — pas bij Opslaan van het lid ontstaat er een rij — en
    draagt daarom geen knop die er een nodig heeft.
    """
    return templates.TemplateResponse(
        request,
        "_email_rij.html",
        {
            "rij": None,
            "index": index or "0",
            "nummer": nummer or "1",
            "basis_url": f"/admin/leden/gezin/{family_id}/persoon/{person_id}/email",
            "doel": f"#persoon-{person_id}",
            "swap": "outerHTML",
        },
    )


@router.post(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}/email",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def email_toevoegen(
    family_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    extra_email: str = Form(""),
):
    from app.domains.mdm.api import add_email_address

    add_email_address(db, person_id, extra_email, actor=email)
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"])


@router.post(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/hoofd",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def email_hoofdadres(
    family_id: int,
    person_id: int,
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    from app.domains.mdm.api import make_email_primary

    make_email_primary(db, person_id, contact_id, actor=email)
    # Ook de kop en de bestuurslidlijst: die noemen het adres van de persoon.
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"], kop=True)


@router.post(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def email_verwijderen(
    family_id: int,
    person_id: int,
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    from app.domains.mdm.api import remove_email_address

    remove_email_address(db, person_id, contact_id, actor=email)
    return _kaart_response(request, db, family_id, kaarten=[f"persoon:{person_id}"], kop=True)


@router.post(
    "/admin/leden/gezin/{family_id}/adres",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def adres_opslaan(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    street: str = Form(""),
    house_number: str = Form(""),
    bus_number: str = Form(""),
    postal_code: str = Form(""),
):
    from app.domains.membership.api import AddressUpdate, get_family, update_person_address

    family = get_family(db, family_id)
    hoofdlid = next(
        (m for m in family.members if m.relation_type == RelationType.PRIMARY_MEMBER),
        family.members[0] if family.members else None,
    )
    if hoofdlid is None:
        raise HTTPException(status_code=400, detail=_("Gezin zonder personen."))
    update_person_address(
        db,
        hoofdlid.id,
        AddressUpdate(
            street=street.strip(),
            house_number=house_number.strip(),
            bus_number=bus_number.strip() or None,
            postal_code=postal_code.strip(),
        ),
        admin=admin_user_by_email(db, email),
    )
    # #1111: alleen de adreskaart; het adres staat ook in de kop.
    return _kaart_response(request, db, family_id, kaarten=["adres"], toast=True, kop=True)


@router.post(
    "/admin/leden/gezin/{family_id}/personen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def persoon_toevoegen(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    first_name: str = Form(""),
    last_name: str = Form(""),
    date_of_birth: str = Form(""),
    gender_code: str = Form(""),
    contact_email: str = Form("", alias="email"),
    phone: str = Form(""),
    mobile: str = Form(""),
    relation_type: str = Form("PARTNER"),
):
    from app.domains.membership.api import PersonAddToFamily, add_person_to_family, get_family

    # `add_person_to_family` geeft het hele gezin terug; de nieuwe persoon is de
    # enige die er vóór de toevoeging niet in zat (#1111: zijn kaart is het antwoord).
    voorheen = {m.id for m in get_family(db, family_id).members}
    gezin = add_person_to_family(
        db,
        family_id,
        PersonAddToFamily(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            date_of_birth=date_of_birth or None,
            gender_code=gender_code or None,
            email=contact_email.strip() or None,
            phone=phone.strip() or None,
            mobile=mobile.strip() or None,
            relation_type=relation_type,
        ),
        admin=admin_user_by_email(db, email),
    )
    # #1111: de nieuwe persoonkaart plus een verse toevoegkaart, in de plaats van
    # de toevoegkaart die postte; de bestuurslidlijst krijgt de nieuwe naam oob.
    (nieuw_id,) = {m.id for m in gezin.members} - voorheen
    return _kaart_response(
        request, db, family_id, kaarten=[f"persoon:{nieuw_id}", "toevoegen"], bestuurslid=True
    )


@router.post(
    "/admin/leden/gezin/{family_id}/persoon/{person_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def persoon_verwijderen(
    family_id: int,
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    from app.domains.membership.api import delete_person

    delete_person(db, person_id, admin=admin_user_by_email(db, email))
    # #1111: de kaart verdwijnt (leeg antwoord op haar eigen outerHTML-doel); de
    # bestuurslidlijst noemde deze persoon en reist oob mee.
    return _kaart_response(request, db, family_id, kaarten=[], bestuurslid=True)


@router.post(
    "/admin/leden/gezin/{family_id}/bestuurslid",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def bestuurslid_zetten(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    person_id: str = Form(""),
):
    from app.domains.membership.api import BoardMemberAssign, assign_board_member

    assign_board_member(
        db,
        family_id,
        BoardMemberAssign(
            person_id=int(person_id) if person_id else None,
        ),
        admin=admin_user_by_email(db, email),
    )
    return _kaart_response(request, db, family_id, kaarten=["bestuurslid"])


@router.post(
    "/admin/leden/gezin/{family_id}/lidmaatschappen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def lidmaatschap_toevoegen(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    year: int = Form(...),
):
    from app.domains.membership.api import MembershipCreate, create_membership_for_family

    create_membership_for_family(
        db,
        family_id,
        MembershipCreate(year=year, is_active=True),
        admin=admin_user_by_email(db, email),
    )
    return _kaart_response(request, db, family_id, kaarten=["lidmaatschappen"])


@router.post(
    "/admin/leden/gezin/{family_id}/lidmaatschappen/{membership_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def lidmaatschap_verwijderen(
    family_id: int,
    membership_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    from app.domains.membership.api import delete_membership

    delete_membership(db, membership_id, admin=admin_user_by_email(db, email))
    return _kaart_response(request, db, family_id, kaarten=["lidmaatschappen"])


@router.post(
    "/admin/leden/gezin/{family_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def gezin_verwijderen(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    from app.domains.membership.api import delete_family

    delete_family(db, family_id, admin=admin_user_by_email(db, email))
    # Verwijderen gebeurt vanuit de gezinseditor; die pagina bestaat daarna niet
    # meer, dus terug naar de lijst (#582).
    return Response(status_code=204, headers={"HX-Redirect": "/admin/leden"})


# ── Leden-import-wizard ────────────────────────────────────────────────────────


@router.get("/admin/leden-import", response_class=HTMLResponse)
def import_page(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    nav = [dict(item, active=False) for item in admin_nav(NAV)]
    return templates.TemplateResponse(
        request,
        "leden_import.html",
        {
            "csrf_token": csrf_from_request(request),
            "nav_items": nav,
        },
    )


@router.post(
    "/admin/leden-import/preview", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def import_preview(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    file: UploadFile = File(...),
):
    from app.domains.mdm.api import import_preview

    try:
        data = await import_preview(db, file, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "_leden_import_resultaat.html", {"error": exc.detail, "stap": "preview"}
        )
    return templates.TemplateResponse(
        request,
        "_leden_import_resultaat.html",
        {"error": None, "stap": "preview", "data": data, "report": data["report"]},
    )


@router.post(
    "/admin/leden-import/commit", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def import_commit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    token: str = Form(...),
):
    from app.domains.mdm.api import import_commit

    try:
        data = import_commit(db, token, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "_leden_import_resultaat.html", {"error": exc.detail, "stap": "commit"}
        )
    return templates.TemplateResponse(
        request,
        "_leden_import_resultaat.html",
        {"error": None, "stap": "commit", "data": data, "report": data["report"]},
    )


# ── The family portal: a member changes a person of their household ──────────
#
# CR-13 phase 3 (#1250): the household and its persons are master data (Koen, 27
# September 2026: *"gezin en personen is mdm"*), so the doors that change them are
# `mdm`'s. The portal itself stays `membership`'s screen; these routes ask it who is
# logged in and for the page to answer with, both reads through `membership.api`.
# Since #1590 there is one door: the page's one "Opslaan". The three row routes
# (a person saved, added, removed on their own) are gone; the JSON API under
# `/api/v1/member/household/…` keeps its own doors on the same cores.


#: Where a refused save of the household is shown: the page's message line.
HOUSEHOLD_MESSAGE = "#gezin-melding"


@router.post("/leden/gezin", response_class=HTMLResponse)
async def portal_household_save(request: Request, db: Session = Depends(get_db)):
    """The one "Opslaan" of the household (#1590): its persons, their e-mail
    addresses and the address, written in one transaction by
    `mdm.household_save.save_household`.

    The form is read by name (`household_form`), because its rows are not a fixed
    list of parameters. A refusal writes nothing and leaves the form as it was
    typed: the answer is the banner alone, for the page's message line, with every
    refused field or row named (`app.ui.refusal_response`, the frame's one way).
    A good save answers the page in read mode.
    """
    from app.domains.mdm.api import (
        HouseholdSaveRefused,
        actor_of,
        household_from_form,
        household_of,
        household_refusals_as_http,
        save_household,
    )
    from app.domains.membership.api import family_portal_page, portal_member

    person = portal_member(request, db)
    payload = household_from_form(await request.form())
    with household_refusals_as_http():
        household = household_of(db, person)
    try:
        save_household(db, household, payload, by=person, actor=actor_of(person))
    except HouseholdSaveRefused as refusal:
        return refusal_response(request, refusal.errors, HOUSEHOLD_MESSAGE)
    # The page is back in read mode and says so (§2.6: "Opgeslagen ✓").
    return family_portal_page(request, db, person)

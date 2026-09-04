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
    SESSION_COOKIE, User, csrf_token_for, require_admin_ui, require_csrf,
)
from app.domains.mdm.models import GenderCode, Person, RelationTypeCode, PostalCode
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/leden")


def _codes(db: Session) -> dict:
    genders = (db.query(GenderCode).filter(GenderCode.language == "nl").all()
               or db.query(GenderCode).all())
    relations = (db.query(RelationTypeCode).filter(RelationTypeCode.language == "nl").all()
                 or db.query(RelationTypeCode).all())
    # Ontdubbel op code (codes bestaan per taal).
    def _uniq(rows):
        seen, out = set(), []
        for r in rows:
            if r.code not in seen:
                seen.add(r.code)
                out.append(r)
        return out
    return {"gender_codes": _uniq(genders), "relation_types": _uniq(relations)}


def _lidmaatschapsjaren(db: Session) -> list[int]:
    """De jaren die écht in de data zitten (#582): de dropdown is data-gedreven,
    net als op Betalingen — geen hardgecodeerde reeks die na nieuwjaar niet klopt."""
    from app.domains.membership.api import Membership

    return [j for (j,) in db.query(Membership.year).distinct()
            .order_by(Membership.year.desc()).all() if j]


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


def _lijst_ctx(request: Request, db: Session) -> dict:
    from app.domains.membership.api import list_families

    q = (request.query_params.get("q") or "").strip()
    status = (request.query_params.get("status") or "").strip()
    jaar_raw = (request.query_params.get("jaar") or "").strip()
    jaar = int(jaar_raw) if jaar_raw.isdigit() else None
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    data = list_families(page=page, page_size=25, q=q or None,
                         status=status or None, membership_year=jaar,
                         db=db, _admin=None)
    # total + page_size erbij zodat ui.pager() "x–y van n" kan tonen (#580).
    return {"families": data.items, "page": data.page, "total": data.total,
            "per_page": data.page_size, "total_pages": data.total_pages,
            "q": q, "status": status, "jaar": jaar,
            "jaren": _lidmaatschapsjaren(db),
            "gefilterd": bool(q or status or jaar)}


def _detail_ctx(request: Request, db: Session, family_id: int) -> dict:
    from app.domains.membership.api import get_family

    family = get_family(family_id, db=db, _admin=None)
    persons = (db.query(Person)
               .order_by(Person.last_name, Person.first_name).all())
    postal_codes = db.query(PostalCode).order_by(PostalCode.postal_code).all()
    hoofdlid = next((m for m in family.members
                     if (m.relation_type or "").upper() == "HOOFDLID"),
                    family.members[0] if family.members else None)
    overige = [m for m in family.members if hoofdlid is None or m.id != hoofdlid.id]
    from datetime import date
    return {"family": family, "hoofdlid": hoofdlid, "overige": overige,
            "current_year": date.today().year,
            "all_persons": persons, "postal_codes": postal_codes,
            "csrf_token": csrf_from_request(request), **_codes(db)}


def _detail_response(request: Request, db: Session, family_id: int):
    return templates.TemplateResponse(request, "_leden_detail.html",
                                      _detail_ctx(request, db, family_id))


# ── Overzicht ──────────────────────────────────────────────────────────────────

@router.get("/admin/leden", response_class=HTMLResponse)
def leden_page(request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    ctx = {"csrf_token": csrf_from_request(request), "nav_items": NAV,
           **_kpi(db), **_lijst_ctx(request, db)}
    return templates.TemplateResponse(request, "leden.html", ctx)


@router.get("/admin/leden/lijst", response_class=HTMLResponse)
def leden_lijst(request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Enkel de kaarten: de filterbalk swapt dit fragment, zodat het zoekveld niet
    onder je vingers vervangen wordt."""
    return templates.TemplateResponse(request, "_leden_lijst.html",
                                      _lijst_ctx(request, db))


@router.get("/admin/leden/nieuw", response_class=HTMLResponse)
def lid_nieuw(request: Request, db: Session = Depends(get_db),
              email: str = Depends(require_admin_ui)):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    return templates.TemplateResponse(request, "leden_nieuw.html", {
        "nav_items": NAV,
        "csrf_token": csrf_from_request(request),
    })


@router.post("/admin/leden", dependencies=[Depends(require_csrf)])
def gezin_aanmaken(request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui),
                   first_name: str = Form(""), last_name: str = Form("")) -> Response:
    """Nieuw gezin met zijn hoofdlid (#582).

    De modal vraagt enkel de naam; adres, contactgegevens en lidmaatschappen vul
    je aan in de editor waar je meteen op uitkomt — dezelfde vorm als de andere
    records-lijsten.
    """
    from app.domains.membership.api import MemberCreate, PersonCreate, create_member

    if not first_name.strip() or not last_name.strip():
        raise HTTPException(status_code=400,
                            detail=_("Voornaam en achternaam zijn verplicht."))
    gezin = create_member(MemberCreate(persons=[PersonCreate(
        first_name=first_name.strip(), last_name=last_name.strip(),
        relation_type="HOOFDLID")]), db=db, _admin=None)
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/leden/gezin/{gezin.id}"})


@router.get("/admin/leden/gezin/{family_id}", response_class=HTMLResponse)
def gezin_detail(family_id: int, request: Request, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    """Een kaart opent de paginabrede gezinseditor (C1, #582); de bewerkingen
    daarbinnen blijven htmx-fragmenten die in #leden-detail landen."""
    if request.headers.get("hx-request"):
        return _detail_response(request, db, family_id)
    return templates.TemplateResponse(request, "leden_gezin.html", {
        "nav_items": NAV, **_detail_ctx(request, db, family_id)})


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

    update_person(person_id, PersonUpdate(
        first_name=first_name.strip(), last_name=last_name.strip(),
        date_of_birth=date_of_birth or None, gender_code=gender_code or None,
    ), db=db, admin=admin_user_by_email(db, email))
    update_person_contacts(person_id, ContactsUpdate(
        email=contact_email.strip() or None, phone=phone.strip() or None,
        mobile=mobile.strip() or None,
    ), db=db, admin=admin_user_by_email(db, email))
    # Relatietype op de MemberPerson-junctie (#498) — enkel wijzigen naar een
    # niet-hoofdrol, en nooit de hoofdlid-rol overschrijven.
    if relation_type and relation_type.upper() != "HOOFDLID":
        from app.domains.mdm.api import MemberPerson

        mp = (db.query(MemberPerson)
              .filter(MemberPerson.member_id == family_id,
                      MemberPerson.person_id == person_id).first())
        if mp is not None and (mp.relation_type or "").upper() != "HOOFDLID":
            mp.relation_type = relation_type
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/adres", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def adres_opslaan(family_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui),
                  street: str = Form(""), house_number: str = Form(""),
                  bus_number: str = Form(""), postal_code: str = Form("")):
    from app.domains.membership.api import get_family, update_person_address
    from app.domains.membership.api import AddressUpdate

    family = get_family(family_id, db=db, _admin=None)
    hoofdlid = next((m for m in family.members
                     if (m.relation_type or "").upper() == "HOOFDLID"),
                    family.members[0] if family.members else None)
    if hoofdlid is None:
        raise HTTPException(status_code=400, detail=_("Gezin zonder personen."))
    update_person_address(hoofdlid.id, AddressUpdate(
        street=street.strip(), house_number=house_number.strip(),
        bus_number=bus_number.strip() or None, postal_code=postal_code.strip(),
    ), db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/personen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def persoon_toevoegen(family_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      first_name: str = Form(""), last_name: str = Form(""),
                      date_of_birth: str = Form(""), gender_code: str = Form(""),
                      contact_email: str = Form("", alias="email"), phone: str = Form(""),
                      mobile: str = Form(""), relation_type: str = Form("PARTNER")):
    from app.domains.membership.api import add_person_to_family
    from app.domains.membership.api import PersonAddToFamily

    add_person_to_family(family_id, PersonAddToFamily(
        first_name=first_name.strip(), last_name=last_name.strip(),
        date_of_birth=date_of_birth or None, gender_code=gender_code or None,
        email=contact_email.strip() or None, phone=phone.strip() or None,
        mobile=mobile.strip() or None, relation_type=relation_type,
    ), db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/persoon/{person_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def persoon_verwijderen(family_id: int, person_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_person

    delete_person(person_id, db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/bestuurslid", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def bestuurslid_zetten(family_id: int, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       person_id: str = Form("")):
    from app.domains.membership.api import assign_board_member
    from app.domains.membership.api import BoardMemberAssign

    assign_board_member(family_id, BoardMemberAssign(
        person_id=int(person_id) if person_id else None,
    ), db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/lidmaatschappen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def lidmaatschap_toevoegen(family_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui),
                           year: int = Form(...)):
    from app.domains.membership.api import create_membership_for_family
    from app.domains.membership.api import MembershipCreate

    create_membership_for_family(family_id, MembershipCreate(year=year, is_active=True),
                                 db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/lidmaatschappen/{membership_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def lidmaatschap_verwijderen(family_id: int, membership_id: int, request: Request,
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_membership

    delete_membership(membership_id, db=db, admin=admin_user_by_email(db, email))
    db.commit()
    return _detail_response(request, db, family_id)


@router.post("/admin/leden/gezin/{family_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def gezin_verwijderen(family_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.membership.api import delete_family

    delete_family(family_id, db=db, admin=admin_user_by_email(db, email))
    db.commit()
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
    from app.domains.mdm.import_router import preview

    try:
        data = await preview(file=file, db=db, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
            "error": exc.detail, "stap": "preview"})
    return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
        "error": None, "stap": "preview", "data": data, "report": data["report"]})


@router.post("/admin/leden-import/commit", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def import_commit(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui), token: str = Form(...)):
    from app.domains.mdm.import_router import commit, CommitRequest

    try:
        data = commit(CommitRequest(token=token), db=db, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
            "error": exc.detail, "stap": "commit"})
    return templates.TemplateResponse(request, "_leden_import_resultaat.html", {
        "error": None, "stap": "commit", "data": data, "report": data["report"]})

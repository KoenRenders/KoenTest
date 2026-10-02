"""Server-rendered "Word lid"-formulier (React-exit #405, §21).

Meerdere gezinsleden via htmx (rij-fragment per index — geen client-side
state), postcode altijd een dropdown (vaste UI-beslissing), betaalwijze met
Mollie-redirect via HX-Redirect. Hergebruikt register_family integraal
(dedup, prijsregels, mail, audit).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.mdm.api import PaymentMethod
from app.i18n import _
from app.limiter import registration_limiter
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


def _codes(db: Session) -> dict:
    """De keuzelijsten voor de formulieren — inclusief de ontdubbeling per code,
    die in de service woont omdat ze uit de tenant-scheiding volgt (#635 I)."""
    from app.domains.mdm.api import form_code_lists

    return form_code_lists(db)


@router.get("/lid-worden", response_class=HTMLResponse)
def lid_worden(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "lid_worden.html",
        {
            **site_context(db, request),
            **_codes(db),
            "error": None,
            "values": {},
            "extra_rows": [],
            **_lidgeld(),
        },
    )


def _lidgeld() -> dict:
    """Tarief en geldigheid voor het Word-lid-scherm (F3, #996): dezelfde
    helpers als de inzending zelf gebruikt, dus scherm en aanrekening kunnen
    niet uiteenlopen."""
    from app.domains.payment.api import membership_price_for_date, membership_valid_period

    _van, tot = membership_valid_period()
    return {"lidgeld": {"prijs": membership_price_for_date(), "tot": tot}}


@router.get("/lid-worden/persoon-rij", response_class=HTMLResponse)
def persoon_rij(request: Request, db: Session = Depends(get_db)):
    from app.domains.membership.api import default_relation

    try:
        index = max(1, int(request.query_params.get("index", "1")))
    except ValueError:
        index = 1
    # #1321: the relations already on the form, so the new row starts with the one
    # rule's default — partner while there is none, child after that.
    earlier = [r for r in request.query_params.get("relations", "").split(",") if r]
    return templates.TemplateResponse(
        request,
        "_lid_persoon_rij.html",
        {**_codes(db), "i": index, "values": {}, "default_relation": default_relation(earlier)},
    )


@router.get("/lid-worden/email-rij", response_class=HTMLResponse)
def email_row(request: Request):
    """One extra e-mail row for member `member` of the Word lid form (#1246).

    The same fragment as the family portal (#1219). A row added here is never the
    first one, so it is never the primary address and can be removed again; the
    family does not exist yet, so the row has no id and no server actions.
    """

    def _int(name: str, default: int, minimum: int) -> int:
        try:
            return max(minimum, int(request.query_params.get(name, default)))
        except ValueError:
            return default

    from app.domains.membership.viewmodels import EmailRowView

    view = EmailRowView(
        index=_int("index", 1, 1),
        nummer=_int("nummer", 2, 2),
        name_prefix=f"m{_int('member', 0, 0)}_",
    )
    return templates.TemplateResponse(request, "_email_rij.html", view.as_context())


def _parse_members(form) -> list[dict]:
    """Doorgeefluik naar de gedeelde ontleding (#1110) — het beheerscherm gebruikt
    dezelfde veldnamen en dus dezelfde functie."""
    from app.domains.membership.service import parse_member_rows

    return parse_member_rows(form)


@router.post(
    "/lid-worden", response_class=HTMLResponse, dependencies=[Depends(registration_limiter)]
)
async def lid_worden_submit(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    from pydantic import ValidationError

    from app.domains.membership.api import register_family
    from app.domains.membership.schemas_family import FamilyCreate, FamilyMemberCreate

    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    # Elk foutpad hieronder rendert hetzelfde sjabloon; het lidgeldblok (F3)
    # hoort er dus ook hier bij, anders valt StrictUndefined over `lidgeld`.
    ctx = {**site_context(db, request), **_codes(db), "values": values, **_lidgeld()}

    members = _parse_members(form)
    # #1327: after a refusal the form shows every person again, not only the head
    # of household — their rows come back from `values`, relation and extra
    # addresses included. A person the visitor removed is not in the form.
    ctx["extra_rows"] = [m["index"] for m in members if m["index"] > 0]
    if not members:
        ctx["error"] = "Vul minstens het hoofdlid in."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)
    if not (values.get("postal_code") or "").strip():
        ctx["error"] = "Selecteer een geldige postcode uit de lijst."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    # #1321: a person without a relation gets the one rule's default, given the
    # relations before them — head of household, then partner, then child.
    from app.domains.membership.api import default_relation

    relations: list[str] = []
    for m in members:
        relations.append(m["relation_type"] or default_relation(relations))

    try:
        data = FamilyCreate(
            street=(values.get("street") or "").strip(),
            house_number=(values.get("house_number") or "").strip(),
            bus_number=(values.get("bus_number") or "").strip() or None,
            postal_code=(values.get("postal_code") or "").strip(),
            payment_method=(values.get("payment_method") or "online").strip(),
            members=[
                FamilyMemberCreate(
                    first_name=m["first_name"],
                    last_name=m["last_name"],
                    date_of_birth=m["date_of_birth"] or None,
                    gender_code=m["gender_code"] or None,
                    email=m["email"] or None,
                    extra_emails=m["extra_emails"],
                    phone=m["phone"] or None,
                    mobile=m["mobile"] or None,
                    relation_type=relation,
                )
                for m, relation in zip(members, relations)
            ],
        )
    except ValidationError as exc:
        eerste = exc.errors()[0]
        ctx["error"] = str(eerste.get("msg", "Ongeldige invoer."))
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    try:
        result = register_family(db, data, background_tasks)
    except HTTPException as exc:
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    checkout_url = getattr(result, "checkout_url", None)
    response = templates.TemplateResponse(
        request,
        "lid_worden_klaar.html",
        {
            **site_context(db, request),
            "checkout": bool(checkout_url),
            "amount": getattr(result, "amount", None),
        },
    )
    if checkout_url:
        response.headers["HX-Redirect"] = checkout_url
    return response


# ── Ledenportaal (React-exit 405-b): /leden/gezin + login-pariteit ─────────────


def _session_member(request: Request, db: Session):
    """Ingelogd lid via de HttpOnly-sessie, of None."""
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return None
    return login_person_for_email(db, email)


def _portal_ctx(request: Request, db: Session, person) -> dict:
    from datetime import date

    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for
    from app.domains.membership.api import (
        household_view,
        membership_coverage_until,
        renewal_available,
    )

    household = household_view(db, person)
    # Dekking t/m (incl. een al betaald volgend jaar) i.p.v. enkel 'geldig vandaag' (#496).
    valid_until = membership_coverage_until(person)
    ctx = {
        **site_context(db, request),
        **_codes(db),
        "household": household,
        "person_id": person.id,
        "valid_until": valid_until,
        "renewal_available": renewal_available(valid_until, date.today()),
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }
    ctx.update(_lopende_vernieuwing(db, person))
    return ctx


def _lopende_vernieuwing(db: Session, person) -> dict:
    """Toont de stand van een openstaande vernieuwing i.p.v. het formulier (#618).

    Zonder dit bouwde alleen het POST-antwoord `renew_transfer` op: na één keer
    navigeren stond het vernieuwformulier er weer, en de knop liep gegarandeerd op de
    guard ("Je vernieuwing loopt nog"). Het scherm nodigde dus uit tot een handeling
    die niet kon slagen.

    Bedrag en OGM komen **uit de PaymentRecord zelf**, niet opnieuw uit
    membership_price_for_date(): wijzigt de prijs tussen twee bezoeken, dan zou het
    scherm een ander bedrag tonen dan wat er te betalen valt.

    Geeft ALTIJD beide sleutels terug, desnoods als None (#643): de template vraagt
    `renew_transfer` en `renew_online`, dus hoort het view-model ze te beloven. Een
    ontbrekende sleutel rendert onder StrictUndefined niet stil leeg maar faalt —
    en dat is precies de bedoeling, want zo'n gat is niet van een typo te
    onderscheiden.
    """
    leeg = {"renew_transfer": None, "renew_online": None}
    from app.domains.membership.api import household_member_for, open_renewal_payment

    try:
        member = household_member_for(db, person)
    except Exception:
        return leeg
    record = open_renewal_payment(db, member) if member is not None else None
    if record is None:
        return leeg

    if record.method == PaymentMethod.TRANSFER:
        from app.kernel.tenant_config import tenant_payment_beneficiary, tenant_payment_iban

        return {
            **leeg,
            "renew_transfer": {
                "amount": record.amount,
                "ogm": record.structured_communication,
                "iban": tenant_payment_iban(db),
                "beneficiary": tenant_payment_beneficiary(db),
            },
        }

    # Online afgebroken bij Mollie (#618-3): even doodlopend als de overschrijving.
    # Met een checkout-URL kan het lid de betaling hervatten; zonder blijft enkel de
    # uitleg dat ze nog loopt.
    from app.domains.payment.api import checkout_url_for

    checkout_url = checkout_url_for(db, record)
    return {**leeg, "renew_online": {"amount": record.amount, "checkout_url": checkout_url}}


@router.get("/leden/gezin", response_class=HTMLResponse)
def gezin_portaal(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        from urllib.parse import quote

        from fastapi.responses import RedirectResponse

        # #1437: remember the page, so the sign-in comes back here — whatever
        # the role (a board member who is also a member lands in the portal).
        here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/aanmelden?terug={quote(here, safe='/')}", status_code=302)
    return templates.TemplateResponse(
        request, "gezin_portaal.html", _portal_ctx(request, db, person)
    )


def render_family_portal(request: Request, db: Session, person) -> HTMLResponse:
    """The family portal as it stands now — the answer of every portal mutation.

    Also the answer of the three person mutations whose doors are `mdm`'s since
    CR-13 phase 3 (#1250): the screen stays `membership`'s, so `mdm` asks it for the
    page through `membership.api.family_portal_page`.
    """
    return templates.TemplateResponse(
        request, "gezin_portaal.html", _portal_ctx(request, db, person)
    )


def _require_member_csrf(request: Request, db: Session):
    from app.domains.auth.api import require_csrf

    person = _session_member(request, db)
    if person is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    return person


# ── E-mailadressen, door het lid zelf (#1174) ────────────────────────────────
#
# Drie schermacties die het portaal opnieuw renderen, net als de andere
# bewerkingen hier. De gezinsgrens en de audit zitten in de domeinlaag; dit
# scherm geeft alleen door wie er klikte.


@router.get("/leden/gezin/personen/{person_id}/email-rij", response_class=HTMLResponse)
def gezin_email_rij(
    person_id: int,
    request: Request,
    index: str = "",
    nummer: str = "",
    db: Session = Depends(get_db),
):
    """Een lege e-mailrij om onderaan te plakken (#1219).

    Leest de sessie mee zodat een niet-aangemelde bezoeker hier niets ophaalt;
    er gaat niets naar de databank, dus wat er al getypt staat blijft staan.
    """
    _require_member_csrf(request, db)
    return templates.TemplateResponse(
        request,
        "_email_rij.html",
        {
            "rij": None,
            "index": index or "0",
            "nummer": nummer or "1",
            "basis_url": f"/leden/gezin/personen/{person_id}/email",
            "doel": "body",
            "swap": "innerHTML",
        },
    )


@router.post("/leden/gezin/personen/{person_id}/email", response_class=HTMLResponse)
async def gezin_email_toevoegen(person_id: int, request: Request, db: Session = Depends(get_db)):
    from app.domains.membership.api import household_add_email

    person = _require_member_csrf(request, db)
    form = await request.form()
    waarde = form.get("extra_email")
    household_add_email(db, person, person_id, waarde.strip() if isinstance(waarde, str) else "")
    return templates.TemplateResponse(
        request, "gezin_portaal.html", _portal_ctx(request, db, person)
    )


@router.post(
    "/leden/gezin/personen/{person_id}/email/{contact_id}/hoofd", response_class=HTMLResponse
)
def gezin_email_hoofdadres(
    person_id: int, contact_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.domains.membership.api import household_make_email_primary

    person = _require_member_csrf(request, db)
    household_make_email_primary(db, person, person_id, contact_id)
    return templates.TemplateResponse(
        request, "gezin_portaal.html", _portal_ctx(request, db, person)
    )


@router.post(
    "/leden/gezin/personen/{person_id}/email/{contact_id}/verwijderen", response_class=HTMLResponse
)
def gezin_email_verwijderen(
    person_id: int, contact_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.domains.membership.api import household_remove_email

    person = _require_member_csrf(request, db)
    household_remove_email(db, person, person_id, contact_id)
    return templates.TemplateResponse(
        request, "gezin_portaal.html", _portal_ctx(request, db, person)
    )


@router.post("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def gezin_vernieuwen(
    request: Request, db: Session = Depends(get_db), payment_method: str = Form("online")
):
    from app.domains.membership.api import household_renew_membership

    person = _require_member_csrf(request, db)
    method = payment_method if payment_method in ("online", "transfer") else "online"
    try:
        result = household_renew_membership(db, person, payment_method=method)
    except HTTPException as exc:
        ctx = _portal_ctx(request, db, person)
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "gezin_portaal.html", ctx)
    ctx = _portal_ctx(request, db, person)
    checkout_url = result.get("checkout_url") if isinstance(result, dict) else None
    if checkout_url:
        response = templates.TemplateResponse(request, "gezin_portaal.html", ctx)
        response.headers["HX-Redirect"] = checkout_url
        return response
    # Overschrijving (#497): toon de betaalinstructies (bedrag + OGM + IBAN) op het scherm.
    from app.kernel.tenant_config import tenant_payment_beneficiary, tenant_payment_iban

    ctx["renew_transfer"] = {
        "amount": result.get("amount"),
        "ogm": result.get("structured_communication"),
        "iban": tenant_payment_iban(db),
        "beneficiary": tenant_payment_beneficiary(db),
    }
    return templates.TemplateResponse(request, "gezin_portaal.html", ctx)

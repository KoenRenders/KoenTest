"""Het scherm voor organisaties (#971) — gegroepeerd per tabel.

**Waarom dit naast `/admin/tenants` staat en niet erin.** Een tenant is een SITE:
mail, Umami, taal, lidgeld, sleutels. Een organisatie is een RECHTSPERSOON: naam,
rechtsvorm, adres, rekening, ondernemingsnummer. Meestal vallen ze samen — Raak
Millegem is allebei — maar niet altijd, en dat uitzonderingsgeval is precies het
belangrijke: **de ACCOUNT-organisatie (Raak vzw) is geen tenant.** Ze stond dus in
geen enkel scherm, terwijl zij nu net degene is met een ondernemingsnummer en een
rekening. Dit scherm is het enige dat bij haar kán.

De velden staan hier en **niet meer** op `/admin/tenants`. Blijven ze op allebei,
dan is er twee plaatsen voor één feit — nu in schermen in plaats van in kolommen,
en dat is precies het patroon dat #924 en #945 net opgeruimd hebben.

**Het scherm groepeert per tabel, en dat is geen opmaakkeuze.** Tot nu toe liep er
één vlakke lijst van dertien invoervelden onder één kopje, waarin het rekeningnummer,
het btw-nummer en Facebook onder elkaar stonden alsof ze hetzelfde soort ding waren.
Ze zijn dat niet: sinds #924/#945 zijn het rijen in vier verschillende tabellen. Het
scherm hoort te laten zien hoe het model in elkaar zit, want dat is wat je moet
begrijpen om het goed in te vullen.

| Groep | Tabel |
|---|---|
| Naam, rechtsvorm | `mdm.organizations` (kolommen) |
| Adres | `mdm.addresses` |
| Contactgegevens, inclusief de sociale links | `mdm.contact_details` |
| Rekening | `mdm.bank_accounts` |
| Nummers | `mdm.organization_identifications` |

**Het adres is LETTERLIJK dat van het hoofdlid.** Vier kolommen, straat over twee,
huisnummer en bus ernaast, postcode als dropdown over de volle breedte. Dat is een
vastgelegde UI-beslissing (`CLAUDE.md`) en geen keuze die hier opnieuw gemaakt is.
Koen: *"ik zou het organisatie-scherm zo consistent met de leden willen behouden."*
De gelijkenis loopt één kant op: aan de ledenschermen verandert niets.

**De contactgegevens zijn één groep** — e-mail, telefoon, mobiel, website, Facebook,
Instagram, TikTok. Koen: *"niet als aparte groep, maar een grotere groep."* Dat is
ook het eerlijkste beeld van het model: het zijn allemaal rijen in dezelfde tabel
met een ander type.

**Eén rij per soort op het scherm, meer in het model.** Staat er ooit een tweede
rekening of een tweede btw-nummer, dan bewerkt dit de eerste en laat het de rest met
rust — nooit stilzwijgend overschrijven of verwijderen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    csrf_from_request,
    require_admin_ui,
    require_csrf,
    require_platform_operator_ui,
    require_tenant_workspace,
)
from app.domains.mdm.api import ORGANIZATION_TYPE, OrganizationType
from app.i18n import _
from app.kernel.codes import code_labels, register_tones
from app.ui import admin_nav, filterparams, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

NAV = "/admin/organisaties"

# Per groep: (veldnaam, label, hulptekst). De volgorde op het scherm is de volgorde
# hier — één plek, zodat een veld niet in de ene helft van de code bestaat en in de
# andere niet.
CONTACTGROEP = [
    ("email", "E-mailadres", "Contactadres van de organisatie; komt in de footer."),
    ("phone", "Telefoon", "Optioneel; komt in de footer."),
    ("mobile", "Mobiel", "Optioneel."),
    ("website", "Website", "Optioneel."),
    ("facebook_url", "Facebook", "Footer-icoon. Leeg = niet tonen."),
    ("instagram_url", "Instagram", "Footer-icoon. Leeg = niet tonen."),
    ("tiktok_url", "TikTok", "Footer-icoon. Leeg = niet tonen."),
]

REKENINGGROEP = [
    (
        "payment_iban",
        "Rekeningnummer (IBAN)",
        "Voor de overschrijvingsinstructies in de bevestigingsmail.",
    ),
    ("payment_bic", "BIC", "Optioneel; staat bij het rekeningnummer in de footer."),
    ("payment_beneficiary", "Begunstigde", "Naam op de overschrijving."),
]

NUMMERGROEP = [
    ("enterprise_number", "Ondernemingsnummer", "Bv. 0123.456.789."),
    ("vat_number", "Btw-nummer", "Optioneel."),
]

# CR-12 phase 2: the words of the organisation kind come from its label table;
# the dictionary that stood here became its seed. The badge tone stays here,
# next to the screen that draws it (§B4.5): the legal entity blue, the rest gray.
register_tones(
    ORGANIZATION_TYPE.name,
    {
        OrganizationType.ACCOUNT: "blue",
        OrganizationType.UNIT: "gray",
        OrganizationType.PLATFORM: "gray",
    },
)


def _lijst_ctx(request: Request, db: Session) -> dict:
    """Lijst-index (design-system C1): zoeken op naam of code, filter op soort."""
    from app.domains.mdm.api import organization_options

    stand = filterparams(request)
    zoek = (stand.get("q") or "").strip()
    soort = (stand.get("org_type") or "").strip()

    organisaties = organization_options(db)
    if zoek:
        naald = zoek.lower()
        organisaties = [
            o
            for o in organisaties
            if naald in (o["name"] or "").lower() or naald in (o["code"] or "").lower()
        ]
    soorten = code_labels(ORGANIZATION_TYPE.name, db=db)
    if soort in dict(soorten):
        organisaties = [o for o in organisaties if o["org_type"] == soort]

    return {
        "nav_items": admin_nav(NAV),
        "organisaties": organisaties,
        "q": zoek,
        "org_type": soort,
        "soort_options": soorten,
        "gefilterd": bool(zoek or soort),
        "csrf_token": csrf_from_request(request),
    }


def _editor_ctx(request: Request, db: Session, organization_id: int, *, own=False) -> dict:
    """The organisation editor's context. `own` (#1535) is a tenant workspace's
    "Onze organisatie": the same fields and the same save, for this workspace's
    own organisation only; only where it posts and leads differs."""
    from app.domains.mdm.api import (
        legal_form_options,
        list_postal_codes,
        organization_address,
        organization_details,
        organization_options,
    )

    organisaties = organization_options(db)
    organisatie = next((o for o in organisaties if o["id"] == organization_id), None)
    if organisatie is None:
        raise HTTPException(status_code=404, detail=_("Onbekende organisatie"))

    # De tenant-editor bestaat alleen voor organisaties die een site draaien; een
    # ACCOUNT heeft er geen, en een link daarheen zou op een 404 uitkomen.
    heeft_site = organisatie["org_type"] in ("UNIT", "PLATFORM")

    return {
        "nav_items": admin_nav("/admin/organisatie" if own else NAV),
        "organisatie": organisatie,
        "organization_id": organization_id,
        "heeft_site": heeft_site,
        # #1535: where this editor posts and leads, per scope.
        "own": own,
        "back_href": None if own else "/admin/organisaties",
        "cancel_href": "/admin/organisatie" if own else f"/admin/organisaties/{organization_id}",
        "site_href": "/admin/instellingen" if own else f"/admin/tenants/{organization_id}",
        "velden": organization_details(db, organization_id),
        "adres": organization_address(db, organization_id),
        "postal_codes": list_postal_codes(db),
        "rechtsvormen": legal_form_options(db),
        "contactgroep": CONTACTGROEP,
        "rekeninggroep": REKENINGGROEP,
        "nummergroep": NUMMERGROEP,
        "error": None,
        "toast_opgeslagen": False,
        "csrf_token": csrf_from_request(request),
    }


@router.get("/admin/organisaties", response_class=HTMLResponse)
def organisaties(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    require_platform_operator_ui(db, email)
    sjabloon = "_org_kaarten.html" if is_fragment_request(request) else "admin_organisaties.html"
    return templates.TemplateResponse(request, sjabloon, _lijst_ctx(request, db))


def _new_account_ctx(request: Request, *, name: str = "", code: str = "", error=None) -> dict:
    return {
        "nav_items": admin_nav(NAV),
        "name": name,
        "code": code,
        "error": error,
        "csrf_token": csrf_from_request(request),
    }


# Declared before `/{organization_id}`: FastAPI matches in declaration order.
@router.get("/admin/organisaties/nieuw", response_class=HTMLResponse)
def new_account_form(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """ "Nieuw account" (CR-19, #1495): OPERATOR only, on GET as on POST."""
    require_platform_operator_ui(db, email)
    return templates.TemplateResponse(
        request, "admin_organisatie_nieuw.html", _new_account_ctx(request)
    )


@router.post(
    "/admin/organisaties", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def create_account_route(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    name: str = Form(""),
    code: str = Form(""),
):
    """Creates the account and lands on its organisation screen, where the rest
    is filled in. A refusal shows the form again with what was typed."""
    from app.domains.mdm.api import TenantFout, create_account

    require_platform_operator_ui(db, email)
    try:
        account = create_account(db, name=name, code=code)
    except TenantFout as fout:
        # 200, not 422: htmx swaps no 4xx answer, and the banner would not show.
        ctx = _new_account_ctx(request, name=name, code=code, error=_(str(fout)))
        return templates.TemplateResponse(request, "admin_organisatie_nieuw.html", ctx)
    target = f"/admin/organisaties/{account.id}"
    # As in meetings: a boosted form is an htmx request, and `HX-Redirect` makes
    # the browser really navigate, so the address bar follows.
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


@router.get("/admin/organisaties/{organization_id}", response_class=HTMLResponse)
def organisatie_editor(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    require_platform_operator_ui(db, email)
    return templates.TemplateResponse(
        request, "admin_organisatie.html", _editor_ctx(request, db, organization_id)
    )


@router.post(
    "/admin/organisaties/{organization_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def organisatie_opslaan(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    require_platform_operator_ui(db, email)
    return await _save(request, db, organization_id, own=False)


@router.get("/admin/organisatie", response_class=HTMLResponse)
def own_organisation(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """ "Onze organisatie" (#1535): the tenant workspace's own organisation, for
    its ADMIN and the operator — and nothing of another organisation."""
    return templates.TemplateResponse(
        request,
        "admin_organisatie.html",
        _editor_ctx(request, db, require_tenant_workspace(db), own=True),
    )


@router.post(
    "/admin/organisatie", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def own_organisation_save(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    return await _save(request, db, require_tenant_workspace(db), own=True)


async def _save(request: Request, db: Session, organization_id: int, *, own: bool):
    """One save path for both scopes (#1535): `save_organization`, one
    transaction for the whole form (#1244)."""
    from app.domains.mdm.api import OngeldigeInstelling, save_organization

    form = await request.form()
    try:
        # #1244: one transaction for the whole form — see `save_organization`.
        save_organization(db, organization_id, form)
    except OngeldigeInstelling as fout:
        # #797: het formulier terug tonen mét de ingetypte waarden. Ze wegwerpen zou
        # betekenen dat één tikfout het hele scherm leegveegt, en dan is de melding
        # erger dan de fout.
        ctx = _editor_ctx(request, db, organization_id, own=own)
        labels = {key: label for key, label, _h in (*CONTACTGROEP, *REKENINGGROEP, *NUMMERGROEP)}
        labels.update(
            {
                "name": _("Naam"),
                "legal_form": _("Rechtsvorm"),
                "street": _("Straat"),
                "house_number": _("Huisnummer"),
                "postal_code": _("Postcode"),
            }
        )
        ctx["error"] = " ".join(f"{labels.get(k, k)}: {m}" for k, m in fout.fouten.items())
        ctx["velden"] = {**ctx["velden"], **{k: v for k, v in form.items() if k in ctx["velden"]}}
        ctx["adres"] = {**ctx["adres"], **{k: v for k, v in form.items() if k in ctx["adres"]}}
        # 422 is the right status; since #1515 the shells swap an HTML 422
        # (`ui.htmx_ux`), so the form with its banner reaches the screen.
        return templates.TemplateResponse(request, "admin_organisatie.html", ctx, status_code=422)

    ctx = _editor_ctx(request, db, organization_id, own=own)
    ctx["toast_opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_organisatie.html", ctx)

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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    csrf_from_request,
    require_admin_ui,
    require_csrf,
    require_operator_ui,
)
from app.i18n import _
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
    ("payment_iban", "Rekeningnummer (IBAN)",
     "Voor de overschrijvingsinstructies in de bevestigingsmail."),
    ("payment_bic", "BIC", "Optioneel; staat bij het rekeningnummer in de footer."),
    ("payment_beneficiary", "Begunstigde", "Naam op de overschrijving."),
]

NUMMERGROEP = [
    ("enterprise_number", "Ondernemingsnummer", "Bv. 0123.456.789."),
    ("vat_number", "Btw-nummer", "Optioneel."),
]

SOORT_LABELS = {"ACCOUNT": "Rechtspersoon", "UNIT": "Afdeling",
                "PLATFORM": "Platform"}


def _lijst_ctx(request: Request, db: Session) -> dict:
    """Lijst-index (design-system C1): zoeken op naam of code, filter op soort."""
    from app.domains.mdm.api import organization_options

    stand = filterparams(request)
    zoek = (stand.get("q") or "").strip()
    soort = (stand.get("org_type") or "").strip()

    organisaties = organization_options(db)
    if zoek:
        naald = zoek.lower()
        organisaties = [o for o in organisaties
                        if naald in (o["name"] or "").lower()
                        or naald in (o["code"] or "").lower()]
    if soort in SOORT_LABELS:
        organisaties = [o for o in organisaties if o["org_type"] == soort]

    return {"nav_items": admin_nav(NAV), "organisaties": organisaties,
            "q": zoek, "org_type": soort,
            "soort_labels": SOORT_LABELS,
            "soort_options": list(SOORT_LABELS.items()),
            "gefilterd": bool(zoek or soort),
            "csrf_token": csrf_from_request(request)}


def _editor_ctx(request: Request, db: Session, organization_id: int) -> dict:
    from app.domains.mdm.api import (legal_form_options, list_postal_codes,
                                     organization_address, organization_details,
                                     organization_options)

    organisaties = organization_options(db)
    organisatie = next((o for o in organisaties if o["id"] == organization_id), None)
    if organisatie is None:
        raise HTTPException(status_code=404, detail=_("Onbekende organisatie"))

    # De tenant-editor bestaat alleen voor organisaties die een site draaien; een
    # ACCOUNT heeft er geen, en een link daarheen zou op een 404 uitkomen.
    heeft_site = organisatie["org_type"] in ("UNIT", "PLATFORM")

    return {"nav_items": admin_nav(NAV), "organisatie": organisatie,
            "organization_id": organization_id,
            "soort_labels": SOORT_LABELS,
            "heeft_site": heeft_site,
            "velden": organization_details(db, organization_id),
            "adres": organization_address(db, organization_id),
            "postal_codes": list_postal_codes(db),
            "rechtsvormen": legal_form_options(db),
            "contactgroep": CONTACTGROEP,
            "rekeninggroep": REKENINGGROEP,
            "nummergroep": NUMMERGROEP,
            "error": None, "toast_opgeslagen": False,
            "csrf_token": csrf_from_request(request)}


@router.get("/admin/organisaties", response_class=HTMLResponse)
def organisaties(request: Request, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    require_operator_ui(db, email)
    sjabloon = ("_org_kaarten.html" if is_fragment_request(request)
                else "admin_organisaties.html")
    return templates.TemplateResponse(request, sjabloon, _lijst_ctx(request, db))


@router.get("/admin/organisaties/{organization_id}", response_class=HTMLResponse)
def organisatie_editor(organization_id: int, request: Request,
                       db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)):
    require_operator_ui(db, email)
    return templates.TemplateResponse(request, "admin_organisatie.html",
                                      _editor_ctx(request, db, organization_id))


@router.post("/admin/organisaties/{organization_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def organisatie_opslaan(organization_id: int, request: Request,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui)):
    from app.domains.mdm.api import (OngeldigeInstelling,
                                     update_organization_address,
                                     update_organization_details)

    require_operator_ui(db, email)
    form = await request.form()
    try:
        update_organization_details(db, organization_id, form)
        update_organization_address(db, organization_id, form)
    except OngeldigeInstelling as fout:
        # #797: het formulier terug tonen mét de ingetypte waarden. Ze wegwerpen zou
        # betekenen dat één tikfout het hele scherm leegveegt, en dan is de melding
        # erger dan de fout.
        ctx = _editor_ctx(request, db, organization_id)
        labels = {key: label for key, label, _h in
                  (*CONTACTGROEP, *REKENINGGROEP, *NUMMERGROEP)}
        labels.update({"name": _("Naam"), "legal_form": _("Rechtsvorm"),
                       "street": _("Straat"), "house_number": _("Huisnummer"),
                       "postal_code": _("Postcode")})
        ctx["error"] = " ".join(f"{labels.get(k, k)}: {m}"
                                for k, m in fout.fouten.items())
        ctx["velden"] = {**ctx["velden"],
                         **{k: v for k, v in form.items() if k in ctx["velden"]}}
        ctx["adres"] = {**ctx["adres"],
                        **{k: v for k, v in form.items() if k in ctx["adres"]}}
        return templates.TemplateResponse(request, "admin_organisatie.html", ctx,
                                          status_code=422)

    ctx = _editor_ctx(request, db, organization_id)
    ctx["toast_opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_organisatie.html", ctx)

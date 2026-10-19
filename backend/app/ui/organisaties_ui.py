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

**Het scherm groepeert per tabel, en dat is geen opmaakkeuze.** Sinds #924/#945 zijn
de velden rijen in verschillende tabellen; het scherm hoort te laten zien hoe het
model in elkaar zit, want dat is wat je moet begrijpen om het goed in te vullen.

| Kaart | Tabel |
|---|---|
| Organisatie: naam, rechtsvorm, contactgegevens (ook de sociale links) | `mdm.organizations`, `mdm.contact_details` |
| Adres | `mdm.addresses` |
| Rekening | `mdm.bank_accounts` |
| Nummers | `mdm.party_identifications` |

**Het adres is LETTERLIJK dat van het hoofdlid.** Straat over de helft, huisnummer en
bus een kwart elk, postcode als dropdown over de volle breedte. Dat is een
vastgelegde UI-beslissing (`CLAUDE.md`) en geen keuze die hier opnieuw gemaakt is.

**Eén rij per soort op het scherm, meer in het model.** Staat er ooit een tweede
rekening of een tweede btw-nummer, dan bewerkt dit de eerste en laat het de rest met
rust — nooit stilzwijgend overschrijven of verwijderen.

**Lijst en record op de kit (#1932).** De lijst is een `list_page` met de soorten als
segmenten; het record leest eerst (`?bewerken=1` is de bewerkmodus met ÉÉN
"Opslaan"), in vier kaarten op het bewerkraster. Eén opslag, één transactie
(`save_organization`); een weigering laat het formulier zoals het getypt was en
komt als banner terug (`refusal_response`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    csrf_from_request,
    may,
    require_csrf,
    require_platform_right,
    require_right,
    require_tenant_workspace,
)
from app.i18n import _
from app.kernel.codes import code_of
from app.kernel.refusals import FieldError
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    is_fragment_request,
    list_return,
    per_page_from,
    record_frame,
    refusal_response,
    templates,
)
from app.ui.viewmodel import ViewModel

router = APIRouter(include_in_schema=False)

NAV = "/admin/organisaties"
OWN = "/admin/organisatie"
#: A department's Organisaties (CR-26 F9, Koen, 19 October 2026: "weg 2"): an address
#: family of its own beside the platform's, on the same templates. The one constant;
#: the three literal form targets in the templates (the rules gate walks them to their
#: routes) follow it.
DEPARTMENT_NAV = "/admin/relaties"


@dataclass(frozen=True)
class Scope:
    """Whose Organisaties this is: the platform's (every organisation, the operator's
    rights) or a department's (the ones with a fact there, `PARTY_VIEW`, edit by
    `PARTY_MASTERDATA`). The base address is where the list lives and the record hangs."""

    base: str
    department: bool


PLATFORM = Scope(NAV, False)
DEPARTMENT = Scope(DEPARTMENT_NAV, True)
RECORD_MESSAGE = "#org-melding"

SORTS = ("naam", "-naam")
SORT_DEFAULT = SORTS[0]

# ── The list ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class OrganisationsView(ViewModel):
    """`admin_organisaties.html` and its fragment `_org_kaarten.html`."""

    #: One dict per row: id, name, href, legal_form, inactive.
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    q: str
    sort: str
    sort_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    #: The fragment carries the toolbar's count out-of-band.
    oob: bool = False
    #: Where the list lives, and whether "Nieuwe organisatie" is offered (CR-26 F9).
    base: str = NAV
    can_create: bool = True
    #: The column "Gebruikt door" is the platform's (which tenants name a party).
    show_use: bool = True


def _list_view(
    request: Request,
    db: Session,
    *,
    oob: bool = False,
    scope: Scope = PLATFORM,
    can_create: bool = True,
) -> OrganisationsView:
    """The list Organisaties (#1932): the parties only since CR-20 — a tenant is
    no organisation any more, so the kinds (account, afdeling, platform) that
    were the segments are gone with the column that held them (CR-20 F5). The
    search on name, the sort by name. The state is in the URL; the toolbar asks
    this same address for the fragment."""
    from app.domains.mdm.api import legal_form_options, organization_options, tenants_naming_each

    state = filterparams(request)
    q = (state.get("q") or "").strip()
    sort = (state.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORT_DEFAULT
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1

    legal_forms = dict(legal_form_options(db))
    shown = organization_options(db)
    if scope.department:
        # CR-26 F9: the organisations with a fact at this tenant, and the ones with a
        # fact nowhere (every department of the account sees those).
        from app.domains.mdm.api import organisation_ids_here

        here = organisation_ids_here(db)
        shown = [o for o in shown if here is None or o["id"] in here]
    if q:
        needle = q.lower()
        shown = [o for o in shown if needle in (o["name"] or "").lower()]
    shown = sorted(
        shown, key=lambda o: ((o["name"] or "").casefold(), o["id"]), reverse=sort[0] == "-"
    )
    total = len(shown)
    page = min(page, max(1, -(-total // per_page)))
    shown = shown[(page - 1) * per_page : page * per_page]

    way_back = list_return(
        scope.base,
        q=q,
        sort=sort if sort != SORT_DEFAULT else "",
        page=page if page > 1 else "",
        per_page=per_page if per_page != PER_PAGE_DEFAULT else "",
    )
    # CR-20 F5: how many tenants name each party — what makes it "in use", from
    # the one place that rule stands (`tenants_naming_each`).
    naming = tenants_naming_each(db)

    def used_by(o) -> str:
        n = len(naming.get(o["id"], []))
        if not n:
            return ""
        return _("1 tenant") if n == 1 else _("%(n)s tenants") % {"n": n}

    rows = [
        {
            "id": o["id"],
            "name": o["name"],
            "used_by": used_by(o),
            "href": f"{scope.base}/{o['id']}?terug={quote(way_back, safe='/')}",
            # The code, not the member: `organization_options` hands over the
            # column as it is, an enum member that equals no string.
            "legal_form": legal_forms.get(code_of(o["legal_form"]) or "", ""),
            "inactive": not o["is_active"],
        }
        for o in shown
    ]

    def _query(**more: Any) -> str:
        return urlencode(
            {k: v for k, v in {"q": q, "per_page": per_page, **more}.items() if v != ""}
        )

    turned = "-naam" if sort == "naam" else "naam"
    return OrganisationsView(
        rows=rows,
        columns=[
            {
                "key": "naam",
                "label": _("Organisatie"),
                "cell": "name",
                "sort_url": f"{scope.base}?{_query(sort=turned)}",
                "sort_page_url": f"{scope.base}?{_query(sort=turned)}",
                "sorted": "asc" if sort == "naam" else "desc",
            },
            *(
                []
                if scope.department
                else [
                    {
                        "key": "gebruik",
                        "label": _("Gebruikt door"),
                        "cell": "extra",
                        "priority": 1,
                        "width": 140,
                    }
                ]
            ),
            {
                "key": "rechtsvorm",
                "label": _("Rechtsvorm"),
                "cell": "extra",
                "priority": 2,
                "width": 200,
            },
            {"key": "status", "label": _("Status"), "cell": "status"},
        ],
        q=q,
        sort=sort,
        sort_options=[("naam", _("Naam"))],
        page=page,
        per_page=per_page,
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{scope.base}?{_query(sort=sort)}",
        empty_reason=_("Geen organisaties gevonden.") if q else _("Nog geen organisaties."),
        csrf_token=csrf_from_request(request),
        nav_items=[] if oob else admin_nav(scope.base, request),
        oob=oob,
        base=scope.base,
        can_create=can_create,
        show_use=not scope.department,
    )


@router.get("/admin/organisaties", response_class=HTMLResponse)
def organisations(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    fragment = is_fragment_request(request)
    view = _list_view(request, db, oob=fragment)
    template = "_org_kaarten.html" if fragment else "admin_organisaties.html"
    return templates.TemplateResponse(request, template, view.as_context())


# ── A new organisation ────────────────────────────────────────────────────────


def _new_organisation_ctx(
    request: Request, *, name: str = "", error=None, scope: Scope = PLATFORM
) -> dict:
    return {
        "nav_items": admin_nav(scope.base, request),
        "base": scope.base,
        "department": scope.department,
        "name": name,
        "error": error,
        "csrf_token": csrf_from_request(request),
    }


# Declared before `/{organization_id}`: FastAPI matches in declaration order.
@router.get("/admin/organisaties/nieuw", response_class=HTMLResponse)
def new_organisation_form(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """ "Nieuwe organisatie" (CR-20 F5; "Nieuw account" until then, CR-19 #1495):
    OPERATOR only, on GET as on POST."""
    return templates.TemplateResponse(
        request, "admin_organisatie_nieuw.html", _new_organisation_ctx(request)
    )


@router.post(
    "/admin/organisaties", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def create_organisation_route(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
    name: str = Form(""),
):
    """Creates the organisation — a party, no code (CR-20 C4.7) — and lands on
    its screen, where the rest is filled in. A refusal shows the form again with
    what was typed."""
    return _create(request, db, name, PLATFORM)


def _create(request: Request, db: Session, name: str, scope: Scope):
    """One create path for both scopes: a department's organisation lies in the
    department's account, so that the department that made it sees it (F9)."""
    from app.domains.mdm.api import TenantFout, create_organization, current_account_id

    try:
        organisation = create_organization(
            db, name=name, account_id=current_account_id(db) if scope.department else None
        )
    except TenantFout as fout:
        # 200, not 422: htmx swaps no 4xx answer, and the banner would not show.
        ctx = _new_organisation_ctx(request, name=name, error=_(str(fout)), scope=scope)
        return templates.TemplateResponse(request, "admin_organisatie_nieuw.html", ctx)
    target = f"{scope.base}/{organisation.id}"
    # As in meetings: a boosted form is an htmx request, and `HX-Redirect` makes
    # the browser really navigate, so the address bar follows.
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


# ── The record ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class OrganisationRecordView(ViewModel):
    """`admin_organisatie.html`: the organisation's record, read first."""

    organization_id: int
    organization: dict[str, Any]
    own: bool
    #: Another organisation's data on this site (#1550): read only, with a line
    #: that says where it is edited.
    read_only: bool
    edit: bool
    saved: bool
    record_head: dict[str, Any]
    way_back: dict[str, Any] | None
    summary: dict[str, Any]
    values: dict[str, str]
    legal_form_label: str
    address: dict[str, str]
    address_line: str
    legal_forms: list[tuple[str, str]]
    postal_options: list[tuple[str, str]]
    save_url: str
    cancel_href: str
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    #: The card Personen (CR-26): who is linked to the organisation, and how.
    people: list[dict[str, Any]] = field(default_factory=list)
    #: A department's record (CR-26 F9): the form posts to the department's address.
    department: bool = False
    base: str = NAV


def _address_line(address: dict[str, str], postal: dict[str, str]) -> str:
    """The address in one line: street and number, bus, postal code and municipality."""
    street = " ".join(part for part in (address["street"], address["house_number"]) if part)
    if street and address["bus_number"]:
        street += " " + _("bus %(bus)s") % {"bus": address["bus_number"]}
    place = postal.get(address["postal_code"], "") if address["postal_code"] else ""
    return ", ".join(part for part in (street, place) if part)


def _record_view(
    request: Request,
    db: Session,
    email: str,
    organization_id: int,
    *,
    own: bool = False,
    scope: Scope = PLATFORM,
    read_only: bool = False,
    edit: bool | None = None,
    saved: bool = False,
) -> OrganisationRecordView:
    """The record of an organisation (#1932; end state §2.2, §5.2): the head with
    Bewerken and Acties, the summary beside the form column, four cards — Organisatie,
    Adres, Rekening, Nummers — read first, and `?bewerken=1` the editor with ONE
    save. `own` (#1535) is a tenant workspace's "Onze organisatie": the same record
    for this workspace's own organisation only; only where it posts and leads
    differs."""
    from app.domains.mdm.api import (
        legal_form_options,
        list_postal_codes,
        organization_address,
        organization_details,
        organization_options,
        people_of_organisation,
        tenants,
    )

    everyone = organization_options(db)
    organisation = next((o for o in everyone if o["id"] == organization_id), None)
    if organisation is None:
        raise HTTPException(status_code=404, detail=_("Onbekende organisatie"))

    base = OWN if own else f"{scope.base}/{organization_id}"
    frame = record_frame(request, db, scope.base)
    way_back = None if own else frame["way_back"]
    keep = way_back["keep"] if way_back else ""
    can_edit = not read_only and may(
        db, email, Right.PARTY_MASTERDATA if own or scope.department else Right.PLATFORM_MANAGE
    )
    editing = frame["head_editing"] if edit is None else edit
    editing = editing and can_edit

    legal_forms = legal_form_options(db)
    values = organization_details(db, organization_id)
    legal_form_label = dict(legal_forms).get(values["legal_form"], "")
    postal = {pc.postal_code: f"{pc.postal_code} {pc.municipality}" for pc in list_postal_codes(db)}
    address = organization_address(db, organization_id)

    # The tenant editor of the site that shows this organisation (CR-20: a
    # tenant is its own record now, so the link goes to the tenant that shows
    # it, not to an editor of the same id). Several tenants may show one
    # organisation; the first is linked — the list of them is CR-20 phase 2's.
    showing = [t for t in tenants(db) if t.organization_id == organization_id]
    # A department's record has no site settings of another tenant to lead to, and
    # no Verwijderen: deleting a party is the platform's (CR-20 F6).
    platform_links = not scope.department
    # CR-26 T12: *Klant* is read from the facts (an order names the party at this
    # tenant), never stored — only where there is a tenant to have orders.
    klant = []
    if scope.department:
        from app.domains.sales.api import has_orders

        if has_orders(db, organisation["party_id"]):
            klant = [{"label": _("Klant"), "tone": "blue"}]
    facts: list[dict[str, str]] = []
    if legal_form_label:
        facts.append({"text": legal_form_label})
    record_head = {
        "title": organisation["name"],
        "badges": klant,
        "facts": facts,
        "primary": {
            "label": _("Bewerken"),
            "href": f"{base}?bewerken=1" + (f"&{keep}" if keep else ""),
        }
        if can_edit
        else None,
        "actions": (
            [
                {
                    "kind": "record",
                    "label": _("Instellingen van de site"),
                    "href": "/admin/instellingen" if own else f"/admin/tenants/{showing[0].id}",
                }
            ]
            if showing and platform_links
            else []
        )
        # CR-20 F5, C4.4: the platform deletes a party; one a tenant names refuses
        # with the tenants' names, on the record's banner.
        + (
            [
                {
                    "kind": "delete",
                    "label": _("Verwijderen"),
                    "attrs": f'hx-post="{base}/verwijderen"',
                    "confirm": _("De organisatie en haar gegevens verdwijnen uit de lijsten."),
                    "confirm_ok": _("Definitief verwijderen"),
                }
            ]
            if can_edit and not own and platform_links
            else []
        ),
    }
    summary = {
        "state": {
            "label": _("Actief") if organisation["is_active"] else _("Inactief"),
            "tone": "green" if organisation["is_active"] else "red",
        },
        "figures": [
            {"label": _("Rechtsvorm"), "value": legal_form_label or "—"},
        ],
    }
    return OrganisationRecordView(
        organization_id=organization_id,
        organization=organisation,
        own=own,
        read_only=read_only,
        edit=editing,
        saved=saved,
        record_head=record_head,
        way_back=way_back,
        summary=summary,
        values=values,
        legal_form_label=legal_form_label,
        address=address,
        address_line=_address_line(address, postal),
        legal_forms=legal_forms,
        postal_options=[("", _("— Kies een postcode —"))] + list(postal.items()),
        save_url=base,
        cancel_href=base + (f"?{keep}" if keep else ""),
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(OWN if own else scope.base, request),
        people=people_of_organisation(db, organization_id),
        department=scope.department,
        base=scope.base,
    )


def _record_page(request: Request, db: Session, email: str, organization_id: int, **kwargs):
    view = _record_view(request, db, email, organization_id, **kwargs)
    return templates.TemplateResponse(request, "admin_organisatie.html", view.as_context())


@router.get("/admin/organisaties/{organization_id}", response_class=HTMLResponse)
def organisation_record(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    return _record_page(request, db, email, organization_id)


@router.post(
    "/admin/organisaties/{organization_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def organisation_save(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
):
    return await _save(request, db, email, organization_id, own=False)


@router.post(
    "/admin/organisaties/{organization_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def organisation_delete(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
):
    """Delete an organisation (CR-20 F5, C4.4): back to the list, or the reason
    on the record's banner — the tenants that name it."""
    from app.domains.mdm.api import OngeldigeInstelling, delete_organization

    try:
        delete_organization(db, organization_id, actor=email)
    except OngeldigeInstelling as refusal:
        return refusal_response(
            request,
            [FieldError(name, message) for name, message in refusal.fouten.items()],
            RECORD_MESSAGE,
        )
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": NAV})
    return RedirectResponse(NAV, status_code=303)


@router.get("/admin/organisatie", response_class=HTMLResponse)
def own_organisation(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """ "Onze organisatie" (#1535): the tenant workspace's own organisation, for
    its ADMIN and the operator — and nothing of another organisation.

    #1550: the organisation behind the site. When the operator pointed the site
    at another organisation of its account, that one is shown, read-only, with
    the line that says where it is edited: its data is never copied here."""
    org_id, editable = _own_organisation(db)
    return _record_page(request, db, email, org_id, own=True, read_only=not editable)


def _own_organisation(db: Session) -> tuple[int, bool]:
    """The organisation "Onze organisatie" shows (#1550), and whether this
    workspace may edit it (CR-20 F5, test 16): when its party is nobody's
    account — this tenant's own included — and no other tenant shows it. An
    account's record is edited in the platform's Organisaties only; a party two
    sites show, by neither."""
    from app.domains.mdm.api import organisation_editable_here
    from app.kernel.tenant_config import site_organization_id

    tenant = require_tenant_workspace(db)
    org_id = site_organization_id(db, tenant)
    return org_id, organisation_editable_here(db, org_id, tenant)


@router.post(
    "/admin/organisatie", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def own_organisation_save(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
):
    org_id, editable = _own_organisation(db)
    if not editable:
        raise HTTPException(
            status_code=403,
            detail=_("Deze gegevens komen van een andere organisatie; je bewerkt ze daar."),
        )
    return await _save(request, db, email, org_id, own=True)


async def _save(
    request: Request,
    db: Session,
    email: str,
    organization_id: int,
    *,
    own: bool,
    scope: Scope = PLATFORM,
):
    """One save path for both scopes (#1535): `save_organization`, one transaction
    for the whole form (#1244). A refusal writes nothing and leaves the form as it
    was typed: the answer is the banner alone, each refused field named (#1932)."""
    from app.domains.mdm.api import OngeldigeInstelling, save_organization

    form = await request.form()
    try:
        # #1885: who saved stands in the history of the address and the contact details.
        save_organization(db, organization_id, form, actor=email)
    except OngeldigeInstelling as refusal:
        # 422 is the right status; the headers send the banner to the message
        # line of the record, so what was typed stays where it is.
        return refusal_response(
            request,
            [FieldError(name, message) for name, message in refusal.fouten.items()],
            RECORD_MESSAGE,
        )
    response = _record_page(
        request, db, email, organization_id, own=own, scope=scope, edit=False, saved=True
    )
    response.headers["HX-Push-Url"] = OWN if own else f"{scope.base}/{organization_id}"
    return response


# ── A department's Organisaties (CR-26 F9) ────────────────────────────────────
#
# The same screens on the department's address family, behind the invoices module
# (R13: "Organisaties is aan of uit") and only in a department's workspace. What the
# department sees is what has a fact at it (`mdm.facts.organisations_of_tenant`); a record
# by id that has none answers 404 as an id that is not yours. Look: `PARTY_VIEW`; create
# and edit: `PARTY_MASTERDATA`. Included in `main.py` under `require_module(INVOICES)`.

department_router = APIRouter(include_in_schema=False)
# The decorators below carry the address as a literal — the rules gate reads them as
# text — and `test_the_department_address_is_one_constant` holds them to `DEPARTMENT_NAV`.


def _department_workspace(db: Session = Depends(get_db)) -> None:
    """A department's address family answers 404 in the platform workspace, which has
    its own Organisaties."""
    require_tenant_workspace(db)


def _party_here(db: Session, organization_id: int) -> None:
    """404 for an organisation the department has no fact with (F9)."""
    from app.domains.mdm.api import organisation_at_tenant

    if not organisation_at_tenant(db, organization_id):
        raise HTTPException(status_code=404, detail=_("Onbekende organisatie"))


def _editable_here(db: Session, organization_id: int) -> bool:
    """The rule of Q14 for this department: the one function "Onze organisatie" reads."""
    from app.domains.mdm.api import organisation_editable_here

    return organisation_editable_here(db, organization_id, require_tenant_workspace(db))


@department_router.get("/admin/relaties", response_class=HTMLResponse)
def department_organisations(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
    _workspace: None = Depends(_department_workspace),
):
    fragment = is_fragment_request(request)
    view = _list_view(
        request,
        db,
        oob=fragment,
        scope=DEPARTMENT,
        can_create=may(db, email, Right.PARTY_MASTERDATA),
    )
    template = "_org_kaarten.html" if fragment else "admin_organisaties.html"
    return templates.TemplateResponse(request, template, view.as_context())


# Declared before `/{organization_id}`: FastAPI matches in declaration order.
@department_router.get("/admin/relaties/nieuw", response_class=HTMLResponse)
def department_new_organisation_form(
    request: Request,
    db: Session = Depends(get_db),
    # A GET asks its screen's viewing right (C4.3a, as the platform's form does); the
    # POST that creates asks the changing one.
    email: str = Depends(require_right(Right.PARTY_VIEW)),
    _workspace: None = Depends(_department_workspace),
):
    return templates.TemplateResponse(
        request, "admin_organisatie_nieuw.html", _new_organisation_ctx(request, scope=DEPARTMENT)
    )


@department_router.post(
    "/admin/relaties", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def department_create_organisation(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
    _workspace: None = Depends(_department_workspace),
    name: str = Form(""),
):
    return _create(request, db, name, DEPARTMENT)


@department_router.get("/admin/relaties/{organization_id}", response_class=HTMLResponse)
def department_organisation_record(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
    _workspace: None = Depends(_department_workspace),
):
    _party_here(db, organization_id)
    return _record_page(
        request,
        db,
        email,
        organization_id,
        scope=DEPARTMENT,
        read_only=not _editable_here(db, organization_id),
    )


@department_router.post(
    "/admin/relaties/{organization_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def department_organisation_save(
    organization_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
    _workspace: None = Depends(_department_workspace),
):
    _party_here(db, organization_id)
    if not _editable_here(db, organization_id):
        # The refusal on the record's banner, as every other refusal of this screen; a 403
        # would read as "no right", and the person holds it — the party is not his to edit.
        return refusal_response(
            request,
            [
                FieldError(
                    "", _("Deze gegevens komen van een andere organisatie; je bewerkt ze daar.")
                )
            ],
            RECORD_MESSAGE,
        )
    return await _save(request, db, email, organization_id, own=False, scope=DEPARTMENT)

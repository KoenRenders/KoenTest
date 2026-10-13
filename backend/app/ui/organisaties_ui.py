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
| Nummers | `mdm.organization_identifications` |

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
from app.domains.mdm.api import ORGANIZATION_TYPE, OrganizationType
from app.i18n import _
from app.kernel.codes import code_labels, register_tones, tone
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
RECORD_MESSAGE = "#org-melding"

SORTS = ("naam", "-naam", "soort", "-soort")
SORT_DEFAULT = SORTS[0]

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


# ── The list ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class OrganisationsView(ViewModel):
    """`admin_organisaties.html` and its fragment `_org_kaarten.html`."""

    #: One dict per row: id, name, code, href, kind_label, kind_tone, parent
    #: ({name, href} or None), legal_form, inactive.
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    kind: str
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
    #: The fragment carries the toolbar's count and segment counts out-of-band.
    oob: bool = False


def _sorted(organisations: list[dict], sort: str, order: dict[str, int]) -> list[dict]:
    """The list in the chosen order: by name, or by kind and then name."""

    def by_name(o: dict) -> tuple:
        return ((o["name"] or "").casefold(),)

    def by_kind(o: dict) -> tuple:
        return (order.get(o["org_type"], 99), (o["name"] or "").casefold())

    return sorted(
        organisations,
        key=by_kind if sort in ("soort", "-soort") else by_name,
        reverse=sort[0] == "-",
    )


def _list_view(request: Request, db: Session, *, oob: bool = False) -> OrganisationsView:
    """The list Organisaties (#1932): the kinds as the segments with their counts,
    the search on name and code, the sort by name or by kind. The state is in the
    URL; the toolbar asks this same address for the fragment."""
    from app.domains.mdm.api import legal_form_options, organization_options

    state = filterparams(request)
    q = (state.get("q") or "").strip()
    kinds = code_labels(ORGANIZATION_TYPE.name, db=db)
    kind = (state.get("org_type") or "").strip()
    if kind not in dict(kinds):
        kind = ""
    sort = (state.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORT_DEFAULT
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1

    everyone = organization_options(db)
    by_id = {o["id"]: o for o in everyone}
    kind_labels = dict(kinds)
    legal_forms = dict(legal_form_options(db))
    order = {code: at for at, (code, _label) in enumerate(kinds)}

    shown = everyone
    if q:
        needle = q.lower()
        shown = [
            o
            for o in shown
            if needle in (o["name"] or "").lower() or needle in (o["code"] or "").lower()
        ]
    if kind:
        shown = [o for o in shown if o["org_type"] == kind]
    shown = _sorted(shown, sort, order)
    total = len(shown)
    page = min(page, max(1, -(-total // per_page)))
    shown = shown[(page - 1) * per_page : page * per_page]

    way_back = list_return(
        NAV,
        org_type=kind,
        q=q,
        sort=sort if sort != SORT_DEFAULT else "",
        page=page if page > 1 else "",
        per_page=per_page if per_page != PER_PAGE_DEFAULT else "",
    )
    rows = []
    for o in shown:
        parent = by_id.get(o["parent_id"]) if o["parent_id"] else None
        rows.append(
            {
                "id": o["id"],
                "name": o["name"],
                "code": o["code"],
                "href": f"{NAV}/{o['id']}?terug={quote(way_back, safe='/')}",
                "kind_label": kind_labels.get(o["org_type"], o["org_type"]),
                "kind_tone": tone(ORGANIZATION_TYPE.name, o["org_type"]),
                "parent": {"name": parent["name"], "href": f"{NAV}/{parent['id']}"}
                if parent
                else None,
                "legal_form": legal_forms.get(o["legal_form"], "") if o["legal_form"] else "",
                "inactive": not o["is_active"],
            }
        )

    link_state = {"org_type": kind, "q": q}

    def _query(**more: Any) -> str:
        return urlencode(
            {k: v for k, v in {**link_state, "per_page": per_page, **more}.items() if v != ""}
        )

    def _head(
        key: str, label: str, cell: str, ascending: str, descending: str, **extra: Any
    ) -> dict[str, Any]:
        turned = descending if sort == ascending else ascending
        head: dict[str, Any] = {
            "key": key,
            "label": label,
            "cell": cell,
            "sort_url": f"{NAV}?{_query(sort=turned)}",
            "sort_page_url": f"{NAV}?{_query(sort=turned)}",
            **extra,
        }
        if sort in (ascending, descending):
            head["sorted"] = "asc" if sort == ascending else "desc"
        return head

    counts = {code: sum(1 for o in everyone if o["org_type"] == code) for code, _label in kinds}
    segments = [{"value": "", "label": _("Alle"), "count": len(everyone)}] + [
        {"value": code, "label": label, "count": counts[code]} for code, label in kinds
    ]
    return OrganisationsView(
        rows=rows,
        columns=[
            _head("naam", _("Organisatie"), "name", "naam", "-naam"),
            _head("soort", _("Soort"), "context", "soort", "-soort", width=150),
            {"key": "onder", "label": _("Onder"), "cell": "extra", "priority": 1, "width": 200},
            {
                "key": "rechtsvorm",
                "label": _("Rechtsvorm"),
                "cell": "extra",
                "priority": 2,
                "width": 200,
            },
            {"key": "status", "label": _("Status"), "cell": "status"},
        ],
        segments=segments,
        kind=kind,
        q=q,
        sort=sort,
        sort_options=[("naam", _("Naam")), ("soort", _("Soort, dan naam"))],
        page=page,
        per_page=per_page,
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{NAV}?{_query(sort=sort)}",
        empty_reason=(
            _("Geen organisaties gevonden.") if (q or kind) else _("Nog geen organisaties.")
        ),
        csrf_token=csrf_from_request(request),
        nav_items=[] if oob else admin_nav(NAV, request),
        oob=oob,
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


# ── A new account ─────────────────────────────────────────────────────────────


def _new_account_ctx(request: Request, *, name: str = "", code: str = "", error=None) -> dict:
    return {
        "nav_items": admin_nav(NAV, request),
        "name": name,
        "code": code,
        "error": error,
        "csrf_token": csrf_from_request(request),
    }


# Declared before `/{organization_id}`: FastAPI matches in declaration order.
@router.get("/admin/organisaties/nieuw", response_class=HTMLResponse)
def new_account_form(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """ "Nieuw account" (CR-19, #1495): OPERATOR only, on GET as on POST."""
    return templates.TemplateResponse(
        request, "admin_organisatie_nieuw.html", _new_account_ctx(request)
    )


@router.post(
    "/admin/organisaties", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def create_account_route(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
    name: str = Form(""),
    code: str = Form(""),
):
    """Creates the account and lands on its organisation screen, where the rest
    is filled in. A refusal shows the form again with what was typed."""
    from app.domains.mdm.api import TenantFout, create_account

    try:
        account = create_account(db, name=name, code=code)
    except TenantFout as fout:
        # 200, not 422: htmx swaps no 4xx answer, and the banner would not show.
        ctx = _new_account_ctx(request, name=name, code=code, error=_(str(fout)))
        return templates.TemplateResponse(request, "admin_organisatie_nieuw.html", ctx)
    target = f"{NAV}/{account.id}"
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
    )

    everyone = organization_options(db)
    organisation = next((o for o in everyone if o["id"] == organization_id), None)
    if organisation is None:
        raise HTTPException(status_code=404, detail=_("Onbekende organisatie"))

    base = OWN if own else f"{NAV}/{organization_id}"
    frame = record_frame(request, db, NAV)
    way_back = None if own else frame["way_back"]
    keep = way_back["keep"] if way_back else ""
    can_edit = not read_only and may(
        db, email, Right.PARTY_MASTERDATA if own else Right.PLATFORM_MANAGE
    )
    editing = frame["head_editing"] if edit is None else edit
    editing = editing and can_edit

    kinds = dict(code_labels(ORGANIZATION_TYPE.name, db=db))
    kind_label = kinds.get(organisation["org_type"], organisation["org_type"])
    legal_forms = legal_form_options(db)
    legal_form_label = dict(legal_forms).get(organisation["legal_form"], "")
    parent = next((o for o in everyone if o["id"] == organisation["parent_id"]), None)
    postal = {pc.postal_code: f"{pc.postal_code} {pc.municipality}" for pc in list_postal_codes(db)}
    address = organization_address(db, organization_id)

    # The tenant editor exists only for organisations that run a site; an ACCOUNT
    # has none, and a link there would end on a 404.
    has_site = organisation["org_type"] in ("UNIT", "PLATFORM")
    facts: list[dict[str, str]] = [{"text": organisation["code"]}]
    if legal_form_label:
        facts.append({"text": legal_form_label})
    if parent is not None:
        under = _("Onder %(naam)s") % {"naam": parent["name"]}
        # Platform administration answers in the platform workspace only.
        facts.append(
            {"text": under, "kind": "reference", "href": f"{NAV}/{parent['id']}"}
            if not own
            else {"text": under}
        )
    record_head = {
        "title": organisation["name"],
        "badges": [{"label": kind_label, "tone": "gray"}],
        "facts": facts,
        "primary": {
            "label": _("Bewerken"),
            "href": f"{base}?bewerken=1" + (f"&{keep}" if keep else ""),
        }
        if can_edit
        else None,
        "actions": [
            {
                "kind": "record",
                "label": _("Instellingen van de site"),
                "href": "/admin/instellingen" if own else f"/admin/tenants/{organization_id}",
            }
        ]
        if has_site
        else [],
    }
    summary = {
        "state": {
            "label": _("Actief") if organisation["is_active"] else _("Inactief"),
            "tone": "green" if organisation["is_active"] else "red",
        },
        "figures": [
            {"label": _("Soort"), "value": kind_label},
            {"label": _("Code"), "value": organisation["code"]},
            {"label": _("Onder"), "value": parent["name"] if parent else "—"},
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
        values=organization_details(db, organization_id),
        legal_form_label=legal_form_label,
        address=address,
        address_line=_address_line(address, postal),
        legal_forms=legal_forms,
        postal_options=[("", _("— Kies een postcode —"))] + list(postal.items()),
        save_url=base,
        cancel_href=base + (f"?{keep}" if keep else ""),
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(OWN if own else NAV, request),
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
    workspace may edit it: only its own row."""
    from app.kernel.tenant_config import site_organization_id

    tenant = require_tenant_workspace(db)
    org_id = site_organization_id(db, tenant)
    return org_id, org_id == tenant


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


async def _save(request: Request, db: Session, email: str, organization_id: int, *, own: bool):
    """One save path for both scopes (#1535): `save_organization`, one transaction
    for the whole form (#1244). A refusal writes nothing and leaves the form as it
    was typed: the answer is the banner alone, each refused field named (#1932)."""
    from app.domains.mdm.api import OngeldigeInstelling, save_organization

    form = await request.form()
    try:
        save_organization(db, organization_id, form)
    except OngeldigeInstelling as refusal:
        # 422 is the right status; the headers send the banner to the message
        # line of the record, so what was typed stays where it is.
        return refusal_response(
            request,
            [FieldError(name, message) for name, message in refusal.fouten.items()],
            RECORD_MESSAGE,
        )
    response = _record_page(request, db, email, organization_id, own=own, edit=False, saved=True)
    response.headers["HX-Push-Url"] = OWN if own else f"{NAV}/{organization_id}"
    return response

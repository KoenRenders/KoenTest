"""Server-rendered mediabeheer (React-exit 405-d, #405 — §21).

Sponsors en activiteitenfoto's: uploaden (multipart via htmx), metadata
bewerken (titel, link, volgorde, actief) en verwijderen. Hergebruikt de
media-routerfuncties als servicelaag.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    csrf_from_request,
    require_csrf,
    require_right,
)
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

NAV = "/admin/media"


# #708: activiteitenfoto's zijn wat er dagelijks bijkomt; sponsorlogo's zet je
# eens per jaar. De standaard hoort de gewone handeling te zijn.
#
# Alle DRIE de plekken moeten mee — de lijst, het uploadscherm en de terugval in
# `_lijst_ctx`. "+ Uploaden" geeft de huidige filterstand door in de URL, dus
# verander je alleen het uploadscherm, dan overschrijft de lijst hem meteen weer en
# lijkt de wijziging niet te werken.
STANDAARD_KIND = "activity_photo"  # the code; see MediaKind.ACTIVITY_PHOTO

# #1527: "Alles" at the top of the tree — the whole library, as a choice and not
# where you land (#891: landing on a big list of photos is pointless). In pages,
# like the picker, and without the arrows: an order holds within one album only.
ALL = "alles"

# CR-15 #1471: the "in gebruik" filter. A list with an explicit empty value and
# not a checkbox: the filter is read through `filterparams`, which keeps a value
# from the current URL unless the request sends its own — an unticked box sends
# nothing, so it could never be switched off again.
IN_USE = "in_gebruik"


def _activity_filter(kind: str, activity_id: Optional[int]) -> Optional[int]:
    """The activity filter, where it applies: only for activity photos (#1291).

    Sponsors, pages and component info hang off no activity, so an activity
    filter on them empties the list — Koen saw no sponsors because an activity
    from before was still selected. The one place of the rule: the list, the
    count of filters and the address of "where I was" (`_filterstand`) all ask
    here.
    """
    from app.domains.media.api import MediaKind

    # #1470: posters hang off an activity too — their own branch in the tree.
    # #1527: and design pictures, under Ontwerpbeelden.
    met_activiteit = {
        MediaKind.ACTIVITY_PHOTO.value,
        MediaKind.ACTIVITY_POSTER.value,
        MediaKind.DESIGN_IMAGE.value,
    }
    return activity_id if kind in met_activiteit else None


def _filterstand(
    kind: str,
    q: str = "",
    activity_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    year: Optional[int] = None,
) -> str:
    """ "Waar ik was", als query-string. De enige plek die dat adres samenstelt (#962).

    Soort, zoekterm en activiteit vormen samen de plek waar je stond, en die plek
    moet drie overgangen overleven: van de lijst naar het uploadscherm, van het
    uploadscherm terug, en van een mislukte upload terug naar hetzelfde scherm. Tot
    nu toe bouwde elk van die drie zijn eigen adres — de knop in het sjabloon, een
    verborgen veld en de redirect — en dat is precies hoe ze uit elkaar liepen: de
    foutafhandeling nam de filterstand wél mee, het geslaagde pad niet. De
    uitzondering zat dus op het pad dat je elke keer neemt.

    **Een activiteit reist alleen mee bij activiteitenfoto's.** Bij een sponsorlogo
    betekent ze niets — er is daar geen activiteitenfilter — en meesturen zou een
    parameter achterlaten die bij de volgende overgang weer opduikt. De regel staat
    hier en niet bij de drie aanroepers, want een regel die je op drie plaatsen moet
    onthouden is de fout die dit issue is.
    """
    from urllib.parse import urlencode

    # #1527: no kind is a place too — the landing, or a tag across kinds.
    params: list[tuple[str, str]] = [("kind", kind)] if kind else []
    if q:
        params.append(("q", q))
    activity_id = _activity_filter(kind, activity_id)
    # `is not None`: 0 is a place too — "Zonder activiteit" (#1527).
    if activity_id is not None:
        params.append(("activity_id", str(activity_id)))
    # #1470: the chosen tag and year are part of "where I was" too.
    if tag_id:
        params.append(("tag", str(tag_id)))
    if year:
        params.append(("year", str(year)))
    return urlencode(params)


def _int(raw) -> Optional[int]:
    return int(raw) if raw and str(raw).isdigit() else None


def _tree(
    alle_activiteiten: list[dict],
    year: Optional[int],
    *,
    by_kind: dict,
    tags: list,
    href: "Callable[[str, int | str], str]",
    chosen: "Callable[[str, int | str], bool]",
    kind_labels: dict[str, str],
) -> dict:
    """The library's tree (CR-15 §C4.2, #1470): two branches derived from the
    activity — its album photos and, apart, its posters (Q10) — and the board's
    tags.

    No tag row stands behind the activity branches: an activity's photos already
    have their place. Within the year filter, only that year's activities. Every
    node carries its address and whether it is the one shown, so the template
    composes no URL and compares nothing.

    One builder for two screens (#1472): the library and the picker show the same
    tree and differ only in where a node leads. `href(node_kind, id)` and
    `chosen(node_kind, id)` say that, with `node_kind` "photos", "posters", "tag"
    or "kind" (its id then the kind's code).

    #1527: the kinds that hang off no activity — Logo's, Paginabeelden — are
    branches too, from `media.api.KIND_GROUPS`, the one source both trees read. A
    branch of one kind is one link with the branch's name; a branch of several
    lists them by their kind's word. Ontwerpbeelden is a branch per year and
    activity, like Affiches, with "Zonder activiteit" for the ones of none
    (Koen's addition to #1527).
    """
    from app.domains.media.api import MediaKind

    deleted = _("Verwijderd")

    def branch(soort: MediaKind, node_kind: str) -> list[dict]:
        met = by_kind.get(soort, set())
        per_jaar: dict[int | str, list[dict]] = {}
        for a in alle_activiteiten:
            # #1527: a deleted activity (no date left) under "Verwijderd", last.
            jaar = deleted if a.get("verwijderd") else a["jaar"]
            if a["id"] in met and jaar and (year is None or jaar == year):
                per_jaar.setdefault(jaar, []).append(
                    {
                        "naam": a["naam"],
                        "href": href(node_kind, a["id"]),
                        "actief": chosen(node_kind, a["id"]),
                    }
                )
        jaren = sorted((j for j in per_jaar if j != deleted), reverse=True)
        if deleted in per_jaar:
            jaren.append(deleted)
        met_keuze = next((j for j in jaren if any(a["actief"] for a in per_jaar[j])), None)
        open_jaar = met_keuze if met_keuze is not None else (jaren[0] if jaren else None)
        return [
            {
                "jaar": jaar,
                "open": jaar == open_jaar,
                "activiteiten": sorted(per_jaar[jaar], key=lambda x: x["naam"]),
            }
            for jaar in jaren
        ]

    def tag_node(node) -> dict:
        return {
            "naam": node.name,
            "aantal": node.pictures,
            "href": href("tag", node.id),
            "actief": chosen("tag", node.id),
            "kinderen": [tag_node(child) for child in node.children],
        }

    from app.domains.media.api import KIND_GROUPS, WITHOUT_ACTIVITY

    group_names = {"logos": _("Logo's"), "pages": _("Paginabeelden")}

    def kind_link(name: str, code: str) -> dict:
        return {"naam": name, "href": href("kind", code), "actief": chosen("kind", code)}

    soorten: list[dict] = []
    for key, kinds in KIND_GROUPS:
        if len(kinds) == 1:
            soorten.append({"naam": None, "links": [kind_link(group_names[key], kinds[0].value)]})
        else:
            soorten.append(
                {
                    "naam": group_names[key],
                    "links": [kind_link(kind_labels.get(k.value, k.value), k.value) for k in kinds],
                }
            )

    return {
        "activiteiten": branch(MediaKind.ACTIVITY_PHOTO, "photos"),
        "affiches": branch(MediaKind.ACTIVITY_POSTER, "posters"),
        # #1527 (Koen): design pictures per year and activity, like posters, and
        # those of no activity apart.
        "ontwerpen": branch(MediaKind.DESIGN_IMAGE, "designs"),
        "ontwerpen_los": {
            "naam": _("Zonder activiteit"),
            "href": href("designs", WITHOUT_ACTIVITY),
            "actief": chosen("designs", WITHOUT_ACTIVITY),
        },
        "soorten": soorten,
        "tags": [tag_node(node) for node in tags],
    }


def _library_href(year: Optional[int]):
    """Where a node of the library's tree leads: the library, on that branch."""
    from app.domains.media.api import MediaKind

    kinds = {
        "photos": MediaKind.ACTIVITY_PHOTO.value,
        "posters": MediaKind.ACTIVITY_POSTER.value,
        "designs": MediaKind.DESIGN_IMAGE.value,
    }

    def href(node_kind: str, node_id: int | str) -> str:
        if node_kind == "tag":
            return "/admin/media?" + _filterstand("", tag_id=int(node_id), year=year)
        if node_kind == "kind":
            return "/admin/media?" + _filterstand(str(node_id), year=year)
        return "/admin/media?" + _filterstand(kinds[node_kind], activity_id=int(node_id), year=year)

    return href


def _library_chosen(kind: str, activity_id: Optional[int], tag_id: Optional[int]):
    from app.domains.media.api import MediaKind

    kinds = {
        "photos": MediaKind.ACTIVITY_PHOTO.value,
        "posters": MediaKind.ACTIVITY_POSTER.value,
        "designs": MediaKind.DESIGN_IMAGE.value,
    }

    def chosen(node_kind: str, node_id: int | str) -> bool:
        if node_kind == "tag":
            return node_id == tag_id
        if node_kind == "kind":
            return tag_id is None and kind == node_id
        return tag_id is None and kind == kinds[node_kind] and activity_id == node_id

    return chosen


def _find_tag(tree: list, tag_id: int):
    """The chosen tag as a tree node — its own name and its parent."""
    todo = list(tree)
    while todo:
        node = todo.pop()
        if node.id == tag_id:
            return node
        todo.extend(node.children)
    return None


def _lijst_ctx(
    request: Request,
    db: Session,
    kind: str,
    q: str = "",
    activity_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    year: Optional[int] = None,
    refused: Optional[int] = None,
    page: int = 1,
) -> dict:
    from app.domains.activities.api import activity_names, activity_options
    from app.domains.media.api import (
        MEDIA_KIND,
        PICK_PAGE_SIZE,
        VALID_KINDS,
        MediaKind,
        activities_by_kind,
        list_media,
        list_media_with_tag,
        tag_index,
        uses_by_asset,
    )
    from app.kernel.codes import code_labels
    from app.ui import filterparams

    # #1470: posters can be LOOKED at here — their branch in the tree — but are
    # not uploaded here: they belong to the activity's own screen. #1527: design
    # pictures have their branch now too. An unknown kind is no branch: the
    # landing, "Kies een tak".
    soorten = {k.value for k in VALID_KINDS} | {
        MediaKind.ACTIVITY_POSTER.value,
        MediaKind.DESIGN_IMAGE.value,
    }
    actief_kind = kind if kind in soorten | {ALL} else ""
    if activity_id is None:
        # GET: het filter staat in de querystring. Bij een mutatie (POST) geeft de
        # kaart hem als verborgen veld mee, zodat het filter niet wegvalt.
        raw = request.query_params.get("activity_id")
        activity_id = int(raw) if raw and raw.isdigit() else None
    # #1470: the tag and the year travel the same way — the query string on a
    # GET, a hidden field on a card's POST.
    if tag_id is None:
        tag_id = _int(request.query_params.get("tag"))
    if year is None:
        year = _int(request.query_params.get("year"))
    # The server decides, not the filter bar: a URL with `kind=sponsor&activity_id=…`
    # shows every sponsor too (#1291).
    activity_id = _activity_filter(actief_kind, activity_id)

    # Álle activiteiten (naam + jaar) voor de upload-dropdown (#476): je moet
    # foto's aan om het even welke activiteit kunnen koppelen, ook zonder foto's.
    #
    # `activity_options` en niet `list_activities` (#645): die laatste laadt datums,
    # onderdelen én producten eager en berekent de bezetting per onderdeel — een
    # lijstbewerking, hergebruikt om drie velden in een <select> te zetten. Dat
    # kostte dit scherm p95 578 ms tegen 9–122 ms voor de andere adminroutes.
    alle_activiteiten = [
        {
            "id": optie.id,
            "naam": optie.name,
            "jaar": optie.first_date.year if optie.first_date else None,
        }
        for optie in activity_options(db)
    ]
    # Filter-dropdown: enkel activiteiten die al media hebben (#459), mét jaar.
    # #1470: one query for the activities per kind; the filter list, the
    # tree's branches and the year choices all read it (query budget 6).
    by_kind = activities_by_kind(db)
    aids = set().union(*by_kind.values()) if by_kind else set()
    activiteiten = [a for a in alle_activiteiten if a["id"] in aids]
    # CR-15 §C4.7 (#1471): the photos of a deleted activity stay, so the filter
    # still offers that activity — the only way to reach its album here.
    levend = {a["id"] for a in activiteiten}
    activiteiten += [
        {
            "id": aid,
            "naam": _("%(naam)s (verwijderd)") % {"naam": naam.name},
            "jaar": None,
            "verwijderd": True,
        }
        for aid, naam in sorted(activity_names(db, aids - levend).items())
        if naam.is_deleted
    ]
    in_use_only = (filterparams(request).get("gebruik") or "").strip() == IN_USE

    # #891: bij activiteitenfoto's toont het scherm niets tot er een activiteit gekozen
    # is. Ongefilterd stond hier een lijst van alle albums door elkaar, met pijltjes die
    # iets doen wat je op dat scherm niet kán zien: de volgorde van een foto geldt binnen
    # HAAR album, en over activiteiten heen bestaat er geen volgorde.
    #
    # Dat is dezelfde tegenstrijdigheid die bij #882 opdook, waar de groepsgrens bewust
    # aan het asset zelf moest hangen en niet aan de getoonde lijst — juist omdát die
    # lijst ongefilterd geen bruikbare groep is. Dit haalt ze weg in plaats van ze te
    # omzeilen.
    #
    # ALLEEN voor deze soort: sponsors en component-info hangen niet aan een activiteit,
    # en daar is de volle lijst juist de bedoeling.
    # #1470: a chosen tag shows every picture with that tag or a tag below it,
    # of whatever kind — a tag gathers across kinds, which is its point.
    # #1470: the tags in two queries — tree, paths and each card's tags.
    index = tag_index(db)
    tag_paden = index.paths
    if tag_id is not None and tag_id not in {t for t, _ in tag_paden}:
        tag_id = None
    # #1471: "In gebruik" spans the albums too: the pictures in use are few, and
    # the question is "which ones", not "which ones of this album".
    kies_eerst = (
        tag_id is None
        and actief_kind == MediaKind.ACTIVITY_PHOTO.value
        and activity_id is None
        and not in_use_only
    )
    # #1527: landing on the library shows no list until a branch is chosen; "In
    # gebruik" is a choice too, and then spans every kind.
    kies_tak = tag_id is None and actief_kind == "" and not in_use_only
    if tag_id is not None:
        assets = list_media_with_tag(db, tag_id)
    elif kies_eerst or kies_tak:
        assets = []
    elif actief_kind in (ALL, ""):
        assets = [a for a in list_media(db) if a["kind"] in soorten]
    else:
        assets = list_media(db, kind=actief_kind, activity_id=activity_id)
    # #1470: the year filter keeps the pictures of that year's activities; a
    # picture of no activity (a sponsor, a page picture) is not dated by it.
    jaar_van = {a["id"]: a["jaar"] for a in alle_activiteiten}
    if year is not None:
        assets = [
            a for a in assets if a["activity_id"] is None or jaar_van.get(a["activity_id"]) == year
        ]
    jaren = sorted({j for aid, j in jaar_van.items() if j and aid in aids}, reverse=True)
    # Vrij zoeken op titel (C1, #588). Media zonder titel valt weg zodra er
    # gezocht wordt — dat is de bedoeling van een zoekterm.
    term = q.strip().lower()
    if term:
        # admin_list_media levert lichte metadata-dicts (_meta), geen ORM-objecten.
        assets = [a for a in assets if term in (a.get("title") or "").lower()]

    # CR-15 #1471: where each card is used, derived from the consumers, and the
    # origin of a photo whose activity was deleted.
    uses = uses_by_asset(db, [a["id"] for a in assets])
    for asset in assets:
        asset["uses"] = [{"label": u.label, "href": u.href} for u in uses[asset["id"]]]
        asset["uses_open"] = asset["id"] == refused
    if in_use_only:
        assets = [a for a in assets if a["uses"]]
    # #1527: "Alles" in pages of 60, like the picker — the whole library is
    # hundreds of pictures.
    total = len(assets)
    pages = max(1, -(-total // PICK_PAGE_SIZE))
    page = min(max(1, page), pages)
    if actief_kind == ALL:
        assets = assets[(page - 1) * PICK_PAGE_SIZE : page * PICK_PAGE_SIZE]
    herkomst = activity_names(db, {a["activity_id"] for a in assets if a["activity_id"]})
    for asset in assets:
        naam = herkomst.get(asset["activity_id"])
        asset["origin_deleted"] = bool(naam and naam.is_deleted)

    # CR-12 phase 4: the words of the kinds come from the label table of
    # `media_kind`, one name per kind. The short chip label "Pagina" of #1173 is
    # gone with #1194: the filter is a list now, so the row no longer runs out of
    # room and the kind carries its one name again. Order: the label table's.
    # #1527: design pictures can be uploaded here too — from their branch.
    toonbaar = {k.value for k in VALID_KINDS} | {MediaKind.DESIGN_IMAGE.value}
    alle_labels = code_labels(MEDIA_KIND.name)
    upload_kind_options = [(k, w) for k, w in alle_labels if k in toonbaar]
    # #882: de pijltjes moeten weten of dit item het eerste of laatste van ZIJN GROEP
    # is — niet van de lijst. Ongefilterd staan de foto's van alle activiteiten door
    # elkaar, dus de buur in de lijst hoort vaak bij een ander album.
    for groep_key in {(a["kind"], a["activity_id"], a["component_id"]) for a in assets}:
        groep = [a for a in assets if (a["kind"], a["activity_id"], a["component_id"]) == groep_key]
        for positie, asset in enumerate(groep):
            asset["is_first"] = positie == 0
            asset["is_last"] = positie == len(groep) - 1
            asset["is_sponsor"] = asset["kind"] == MediaKind.SPONSOR.value

    # #1470: the tags each card carries, in one query for the page.
    for asset in assets:
        asset["tag_ids"] = [str(t) for t in index.per_asset.get(asset["id"], [])]
    tag_naam = dict(tag_paden)
    gekozen = _find_tag(index.tree, tag_id) if tag_id is not None else None

    return {
        "assets": assets,
        "q": q,
        "gefilterd": bool(term or activity_id or tag_id or year or in_use_only),
        "gebruik": IN_USE if in_use_only else "",
        "gebruik_options": [("", _("In gebruik of niet")), (IN_USE, _("Alleen in gebruik"))],
        "kies_eerst": kies_eerst,
        "kies_tak": kies_tak,
        "kind": actief_kind,
        "upload_kind_options": upload_kind_options,
        # Decided here, so the templates compare no code with a literal.
        "is_activity_photo": actief_kind == MediaKind.ACTIVITY_PHOTO.value,
        "activity_id": activity_id,
        "alle_activiteiten": alle_activiteiten,
        # Waar je stond, als één waarde (#962). Het sjabloon plakt er een pad
        # voor en stelt niets zelf samen — de knop die hem vergat, is de reden
        # dat je de activiteit drie keer moest kiezen.
        "filterstand": _filterstand(actief_kind, q, activity_id, tag_id, year),
        "csrf_token": csrf_from_request(request),
        # #1470: the tree, the chosen tag and year, and the tags as choices.
        # #1527: the tree is the only way to an album now, so it carries the
        # activities that were deleted too (CR-15 §C4.7, #1471).
        "boom": _tree(
            alle_activiteiten + [a for a in activiteiten if a.get("verwijderd")],
            year,
            by_kind=by_kind,
            tags=index.tree,
            href=_library_href(year),
            chosen=_library_chosen(actief_kind, activity_id, tag_id),
            kind_labels=dict(alle_labels),
        ),
        # #1527: "Alles" above the tree, and its pages.
        "alles_href": "/admin/media?" + _filterstand(ALL, year=year),
        "alles_actief": actief_kind == ALL,
        "page": page,
        "per_page": PICK_PAGE_SIZE,
        "pages": pages if actief_kind == ALL else 1,
        "total": total,
        "pager_url": "/admin/media?" + _filterstand(ALL, q, year=year),
        # #1527: "+ Uploaden" starts from the chosen branch — on Affiches at the
        # activity's own poster screen, the one place that replaces a poster.
        "upload_href": (
            f"/admin/activiteiten/{activity_id}"
            if tag_id is None and actief_kind == MediaKind.ACTIVITY_POSTER.value and activity_id
            else "/admin/media/nieuw?" + _filterstand(actief_kind, q, activity_id, tag_id, year)
        ),
        "tag": tag_id,
        "tag_naam": tag_naam.get(tag_id, "") if tag_id else "",
        "tag_eigen_naam": gekozen.name if gekozen else "",
        "tag_ouder": str(gekozen.parent_id) if gekozen and gekozen.parent_id else "",
        "year": year,
        "jaar_opties": jaren,
        "tag_opties": [(str(t), pad) for t, pad in tag_paden],
        "tag_ouder_opties": [(str(t), pad) for t, pad in tag_paden if t != tag_id],
        "is_poster_lijst": tag_id is None and actief_kind == MediaKind.ACTIVITY_POSTER.value,
    }


def _lijst_response(
    request: Request,
    db: Session,
    kind: str,
    error: str | None = None,
    q: str = "",
    activity_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    year: Optional[int] = None,
    refused: Optional[int] = None,
    page: int = 1,
):
    """Enkel de kaarten (C1, #588): kop, knop en filterbalk staan op de pagina.
    `refused`: the card whose delete was refused opens its list of uses (#1471)."""
    ctx = _lijst_ctx(request, db, kind, q, activity_id, tag_id, year, refused, page)
    ctx["error"] = error
    # #1138: de uploadknop staat buiten dit fragment en reist out-of-band mee.
    # Alleen hier en niet in de paginaroute: daar rendert het sjabloon hem zelf.
    ctx["oob_uploadknop"] = True
    return templates.TemplateResponse(request, "_me_lijst.html", ctx)


@router.get("/admin/media", response_class=HTMLResponse)
def admin_media(
    request: Request,
    kind: str = "",
    q: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_VIEW)),
):
    # #1527: no kind is the landing — "Kies een tak in de boom" (#891).
    # htmx (de filterbalk) krijgt enkel de kaarten terug: een pagina-swap zou het
    # zoekveld tijdens het typen vervangen.
    if is_fragment_request(request):
        return _lijst_response(request, db, kind, q=q, page=page)
    return templates.TemplateResponse(
        request,
        "admin_media.html",
        {
            "nav_items": admin_nav(NAV, request),
            "error": None,
            **_lijst_ctx(request, db, kind, q, page=page),
        },
    )


@router.get("/admin/media/nieuw", response_class=HTMLResponse)
def media_nieuw(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_VIEW)),
):
    """Uploaden als volledige pagina (#627, §2.8) i.p.v. een modal.

    Hergebruikt de contextbouwer van de lijst: de dropdown met álle activiteiten en
    de huidige filterstand komen daaruit, zodat je na het uploaden terugkeert in
    dezelfde filtering.
    """
    # #1527: the branch you came from is the form's starting point — the kind,
    # the activity, the tag — visible and changeable. Without a kind of its own
    # (the landing, "Alles", a year, a tag) the kind starts at activity photo.
    ctx = _lijst_ctx(request, db, kind=(request.query_params.get("kind") or "").strip())
    ctx["tak"] = _branch_of(ctx)
    ctx["upload_kind"] = _upload_kind(ctx["kind"], ctx["upload_kind_options"])
    ctx["nav_items"] = admin_nav(NAV, request)
    return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)


def _branch_of(ctx: dict) -> dict:
    """The branch the library showed, to return to after an upload (#1527)."""
    return {
        "kind": ctx["kind"],
        "activity_id": ctx["activity_id"] or "",
        "tag": ctx["tag"] or "",
        "year": ctx["year"] or "",
    }


def _upload_kind(kind: str, options: list) -> str:
    """The kind the upload form starts with: the branch's, if it can be uploaded
    here; else activity photo, the everyday one (#708)."""
    return kind if kind in {k for k, _w in options} else STANDAARD_KIND


@router.post("/admin/media", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def media_uploaden(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    # #1831: not required here. A post without a file is refused by the service's
    # own rule, in the page's banner — required on the route, the framework
    # answered a bare JSON 422 and the page showed the kit's general message.
    # `str`: a file input nobody filled arrives as an empty text field.
    files: List[UploadFile | str] = File([]),
    kind: str = Form("sponsor"),
    activity_id: Optional[int] = Form(None),
    title: str = Form(""),
    link_url: str = Form(""),
    q: str = Form(""),
    filter_kind: str = Form(""),
    filter_activity_id: Optional[int] = Form(None),
    filter_tag: Optional[int] = Form(None),
    filter_year: Optional[int] = Form(None),
    tag_ids: List[int] = Form([]),
):
    from app.domains.media.api import MediaFout, set_asset_tags, upload_media

    try:
        stored = await upload_media(
            db,
            files=[given for given in files if not isinstance(given, str)],
            kind=kind,
            activity_id=activity_id,
            title=title.strip() or None,
            link_url=link_url.strip() or None,
        )
        # #1470: an upload can carry one or more tags at once.
        for asset in stored:
            if tag_ids:
                set_asset_tags(db, asset["id"], tag_ids)
    except (LookupError, MediaFout) as exc:
        # Op het aanmaakscherm blijven mét de fout (#627): een fragment terugsturen
        # naar een pagina die geen lijst toont, laat de gebruiker in het ongewisse.
        ctx = _lijst_ctx(
            request,
            db,
            kind=filter_kind,
            q=q,
            activity_id=filter_activity_id,
            tag_id=filter_tag,
            year=filter_year,
        )
        ctx["tak"] = _branch_of(ctx)
        ctx["upload_kind"] = _upload_kind(kind, ctx["upload_kind_options"])
        ctx["nav_items"] = admin_nav(NAV, request)
        ctx["error"] = str(exc)
        return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)
    # Media is met één handeling compleet, dus terug naar de lijst (#627) — en naar
    # DEZELFDE lijst (#962). Hier stond een kaal `/admin/media`, dus je kwam terug in
    # de ongefilterde lijst en koos je activiteit een derde keer, terwijl het typische
    # gebruik nu juist is: foto's van één activiteit, in meerdere keren.
    #
    # `kind` is dat van de UPLOAD en niet van het filter waar je vandaan kwam: schakel
    # je op dit scherm om naar een sponsorlogo, dan hoort de lijst te tonen wat je net
    # toevoegde en niet de filtering waarin het onzichtbaar is.
    terug = _back_after_upload(
        kind, activity_id, tag_ids, q, filter_kind, filter_activity_id, filter_tag, filter_year
    )
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/media?{terug}"})


def _back_after_upload(
    kind: str,
    activity_id: Optional[int],
    tag_ids: List[int],
    q: str,
    filter_kind: str,
    filter_activity_id: Optional[int],
    filter_tag: Optional[int],
    filter_year: Optional[int],
) -> str:
    """Where an upload returns (#1527): the branch it started from, when the new
    picture is in it — a tag it carries, "Alles", or the same kind (and the same
    activity, for an album). Changed on the form to a place outside that branch,
    the upload returns to its own place, where it can be seen (#962)."""
    in_branch = (
        (filter_tag is not None and filter_tag in tag_ids)
        or filter_kind == ALL
        or (
            filter_tag is None
            and filter_kind == kind
            # "Zonder activiteit" (0) is the place of a picture with none.
            and (_activity_filter(kind, filter_activity_id) or None)
            == (_activity_filter(kind, activity_id) or None)
        )
    )
    if in_branch:
        return _filterstand(filter_kind, q, filter_activity_id, filter_tag, filter_year)
    return _filterstand(kind, q, activity_id)


# ── Tags (CR-15 §C4.2, #1470) ────────────────────────────────────────────────
# Create, rename, move and delete. Done: back to the library with that tag
# chosen, so the tree shows it. Refused: the reason above the cards.


def _to_tag(tag_id: Optional[int]) -> Response:
    adres = f"/admin/media?tag={tag_id}" if tag_id else "/admin/media"
    return Response(status_code=204, headers={"HX-Redirect": adres})


@router.post("/admin/media/tags", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def create_tag_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    name: str = Form(""),
    parent_id: Optional[int] = Form(None),
):
    from app.domains.media.api import MediaFout, create_tag

    try:
        tag = create_tag(db, name, parent_id)
    except (LookupError, MediaFout) as exc:
        return _lijst_response(request, db, STANDAARD_KIND, str(exc), tag_id=parent_id)
    return _to_tag(tag.id)


@router.post(
    "/admin/media/tags/{tag_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def update_tag_submit(
    tag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    name: str = Form(""),
    parent_id: Optional[int] = Form(None),
):
    """Rename and move in one form: the name, and the tag it hangs under (none = top)."""
    from app.domains.media.api import MediaFout, move_tag, rename_tag

    try:
        rename_tag(db, tag_id, name)
        move_tag(db, tag_id, parent_id)
    except (LookupError, MediaFout) as exc:
        return _lijst_response(request, db, STANDAARD_KIND, str(exc), tag_id=tag_id)
    return _to_tag(tag_id)


@router.post(
    "/admin/media/tags/{tag_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def delete_tag_submit(
    tag_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
):
    from app.domains.media.api import MediaFout, delete_tag

    try:
        delete_tag(db, tag_id)
    except (LookupError, MediaFout) as exc:
        return _lijst_response(request, db, STANDAARD_KIND, str(exc), tag_id=tag_id)
    return _to_tag(None)


# The tag routes stand BEFORE `/admin/media/{asset_id}`: that pattern would
# take "tags" as an asset id and answer 422.


@router.post(
    "/admin/media/{asset_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def media_bijwerken(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    kind: str = Form("sponsor"),
    title: str = Form(""),
    link_url: str = Form(""),
    is_active: str = Form(""),
    show_in_footer: str = Form(""),
    q: str = Form(""),
    filter_activity_id: Optional[int] = Form(None),
    filter_tag: Optional[int] = Form(None),
    filter_year: Optional[int] = Form(None),
    tag_ids: List[int] = Form([]),
    tags_on_card: str = Form(""),
):
    """Titel, link en zichtbaarheid. NIET de volgorde (#882).

    `sort_order` stond hier tot #882 als formulierveld met default "0". Nu de pijltjes
    de volgorde bepalen, stuurt het formulier dat veld niet meer mee — en dan zou die
    default bij élke keer opslaan de volgorde op 0 zetten. Vandaar: `sort_order` staat
    niet in de payload, en `update_media` raakt alleen aan wat er wél in staat.
    """
    from app.domains.media.api import MediaFout, set_asset_tags, update_media

    try:
        update_media(
            db,
            asset_id,
            {
                "title": title.strip() or None,
                "link_url": link_url.strip() or None,
                "is_active": bool(is_active),
                # #1057: een niet-aangevinkt vakje stuurt niets mee, dus dit is altijd
                # de stand van het formulier — voor élke soort. Buiten een sponsorlogo
                # betekent de kolom niets en leest niemand haar.
                "show_in_footer": bool(show_in_footer),
            },
        )
        # #1470: the card's tags. Only when the card sent its tag field: an
        # unticked list sends nothing, and that must mean "none", not "untouched".
        if tags_on_card:
            set_asset_tags(db, asset_id, tag_ids)
    except (LookupError, MediaFout) as exc:
        return _lijst_response(
            request, db, kind, str(exc), q, filter_activity_id, tag_id=filter_tag, year=filter_year
        )
    return _lijst_response(
        request, db, kind, q=q, activity_id=filter_activity_id, tag_id=filter_tag, year=filter_year
    )


@router.post(
    "/admin/media/{asset_id}/verplaats",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def media_verplaatsen(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    kind: str = Form("sponsor"),
    richting: str = Form("omhoog"),
    q: str = Form(""),
    filter_activity_id: Optional[int] = Form(None),
    filter_tag: Optional[int] = Form(None),
    filter_year: Optional[int] = Form(None),
):
    """Media omhoog/omlaag herordenen (#882) — dezelfde vorm als de vier andere
    schermen met `ui.reorder`."""
    from app.domains.media.api import move_media

    try:
        move_media(db, asset_id, richting)
    except LookupError as exc:
        return _lijst_response(
            request, db, kind, str(exc), q, filter_activity_id, tag_id=filter_tag, year=filter_year
        )
    return _lijst_response(
        request, db, kind, q=q, activity_id=filter_activity_id, tag_id=filter_tag, year=filter_year
    )


@router.post(
    "/admin/media/{asset_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def media_verwijderen(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_MANAGE)),
    kind: str = Form("sponsor"),
    q: str = Form(""),
    filter_activity_id: Optional[int] = Form(None),
    filter_tag: Optional[int] = Form(None),
    filter_year: Optional[int] = Form(None),
):
    from app.domains.media.api import MediaInUse, delete_media

    try:
        delete_media(db, asset_id)
    except LookupError as exc:
        return _lijst_response(
            request, db, kind, str(exc), q, filter_activity_id, tag_id=filter_tag, year=filter_year
        )
    except MediaInUse as exc:
        # #1471: refused, with the uses open on the card as links.
        return _lijst_response(
            request,
            db,
            kind,
            str(exc),
            q,
            filter_activity_id,
            tag_id=filter_tag,
            year=filter_year,
            refused=asset_id,
        )
    return _lijst_response(
        request, db, kind, q=q, activity_id=filter_activity_id, tag_id=filter_tag, year=filter_year
    )


# ── The picker (CR-15 §C4.3, #1472) ──────────────────────────────────────────
# `ui.media_picker` opens a kit modal and loads this fragment into it: the tree
# at the left, search and the year above, the thumbnails in pages of 60. Every
# link inside reloads the fragment in place; choosing sets the hidden field the
# macro owns. The offer itself is `media.api.pick_options`.


def _picker_url(field: str, for_activity_id: Optional[int], **state) -> str:
    """The fragment's own address with the state that travels: one place."""
    from urllib.parse import urlencode

    pairs = [("field", field)]
    if for_activity_id:
        pairs.append(("for_activity_id", str(for_activity_id)))
    for key in ("q", "year", "tag", "photos_of", "posters_of", "designs_of", "kind"):
        value = state.get(key)
        if value not in (None, ""):
            pairs.append((key, str(value)))
    return "/admin/media/kiezer?" + urlencode(pairs)


@router.get("/admin/media/kiezer", response_class=HTMLResponse)
def media_picker(
    request: Request,
    field: str = "",
    for_activity_id: Optional[int] = None,
    q: str = "",
    # Read like the library's (`_int`): the "Alle jaren" chip sends `year=`, which
    # an `Optional[int]` refuses with a 422 — every search in the picker failed
    # (measured with #1474, the picker's own e2e did not see it).
    year: str = "",
    tag: Optional[int] = None,
    photos_of: Optional[int] = None,
    posters_of: Optional[int] = None,
    designs_of: Optional[int] = None,
    kind: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.MEDIA_VIEW)),
):
    from app.domains.activities.api import activity_options
    from app.domains.media.api import (
        KIND_BRANCHES,
        MEDIA_KIND,
        PICK_PAGE_SIZE,
        activities_by_kind,
        pick_options,
        tag_index,
    )
    from app.i18n import _
    from app.kernel.codes import code_labels

    # Only a kind with its own branch; anything else in the address is no branch.
    branch_kind = next((k for k in KIND_BRANCHES if k.value == kind), None)
    chosen_year = _int(year)

    options = pick_options(
        db,
        for_activity_id=for_activity_id,
        q=q,
        year=chosen_year,
        tag_id=tag,
        photos_of=photos_of,
        posters_of=posters_of,
        designs_of=designs_of,
        kind=branch_kind,
        page=page,
    )
    alle_activiteiten = [
        {"id": o.id, "naam": o.name, "jaar": o.first_date.year if o.first_date else None}
        for o in activity_options(db)
    ]
    by_kind = activities_by_kind(db)
    branch_state = {
        "photos": "photos_of",
        "posters": "posters_of",
        "designs": "designs_of",
        "tag": "tag",
        "kind": "kind",
    }
    current = {
        "photos_of": photos_of,
        "posters_of": posters_of,
        "designs_of": designs_of,
        "tag": tag,
        "kind": branch_kind.value if branch_kind else None,
    }

    def href(node_kind: str, node_id: int | str) -> str:
        return _picker_url(
            field, for_activity_id, q=q, year=chosen_year, **{branch_state[node_kind]: node_id}
        )

    def chosen(node_kind: str, node_id: int | str) -> bool:
        return current[branch_state[node_kind]] == node_id

    labels = dict(code_labels(MEDIA_KIND.name))

    met_media = set().union(*by_kind.values()) if by_kind else set()
    jaren = sorted(
        {a["jaar"] for a in alle_activiteiten if a["jaar"] and a["id"] in met_media}, reverse=True
    )
    return templates.TemplateResponse(
        request,
        "_media_picker.html",
        {
            "field": field,
            "for_activity_id": for_activity_id or "",
            "q": q,
            "year": str(chosen_year) if chosen_year else "",
            "jaar_keuzes": [("", _("Alle jaren"))] + [(str(j), str(j)) for j in jaren],
            "groups": options.groups,
            "total": options.total,
            "page": options.page,
            "per_page": PICK_PAGE_SIZE,
            "boom": _tree(
                alle_activiteiten,
                chosen_year,
                by_kind=by_kind,
                tags=tag_index(db).tree,
                href=href,
                chosen=chosen,
                # #1527: the kind branches from the same builder as the library.
                kind_labels=labels,
            ),
            "alles_href": _picker_url(field, for_activity_id, q=q, year=chosen_year),
            "branch_chosen": any(v is not None for v in current.values()),
            "pager_url": _picker_url(field, for_activity_id, q=q, year=chosen_year, **current),
            "target": f"#mp-{field}",
        },
    )

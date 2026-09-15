"""Server-rendered Wijzigingen-scherm (React-exit 405-d, #405 — §21).

Eén primaire weergave over de append-only history (#512, v1.4-pariteit): het
uniforme audit-logboek met groep-/actorfilter. De ledendata-wijzigingen voor
manuele overname in Raak Nationaal blijven beschikbaar als .ods-export (aparte
route), niet meer als altijd-zichtbare tabel. Composer-module: leest via de
audit-facade (`app.domains.audit.api`, #444), geen domein-internals.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/ledenwijzigingen")


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today() - timedelta(days=30)


PER_PAGE = 50  # §2.5: server-side, 50 per pagina zodra een lijst kan groeien.


# Sorteerbare kolommen (golf 3, #913): sleutel → veld van de feed-rij. De feed
# is een in Python samengevoegde lijst dicts (±10 history-tabellen), dus hier
# wordt in Python gesorteerd — de whitelist blijft om dezelfde reden bestaan
# als bij SQL: een sleutel van buiten wordt nooit blind een veldnaam.
_SORT_VELDEN = {
    "wanneer": "recorded_at",
    "wijziging": "operation_label",
    "groep": "group",
    "persoon": "person_name",
    "object": "entity",
    "actor": "actor",
}


def wijzigingen_ctx(request: Request, db: Session, since: str, group: str, actor: str,
                    page: int = 1, sort: str = "wanneer", richting: str = "desc",
                    member_id: int | None = None,
                    basis: str = "/admin/ledenwijzigingen") -> dict:
    from app.domains.audit.api import GROUPS, all_changes_since

    vanaf = _since(since)
    # #512 (v1.4-pariteit): één algemeen audit-logboek als primaire, gefilterde
    # tabel. De ledendata-mutaties voor Raak Nationaal blijven als .ods-export
    # (aparte route), niet meer als altijd-zichtbare tabel bovenaan.
    # Golf 9 (#913): member_id scoopt de feed op één gezin (de tab op de
    # gezinspagina); basis laat de sorteerlinks binnen die tab blijven.
    alle = all_changes_since(db, vanaf, group=group or None, actor=actor or None,
                             member_id=member_id)

    # Paginering (#620). Bewust ná het sorteren en in Python: all_changes_since()
    # verenigt ~10 history-tabellen in Python, dus een server-side LIMIT/OFFSET op
    # één query bestaat niet. De "Vanaf"-datum blijft de echte begrenzing en bij
    # deze volumes volstaat dit. Groeit het logboek fors, dan is een echte UNION ALL
    # in SQL de duurzame oplossing — dat is opvolging, niet iets om nu te bouwen.
    if sort not in _SORT_VELDEN:
        sort = "wanneer"
    richting = "asc" if richting == "asc" else "desc"
    veld = _SORT_VELDEN[sort]

    def _sleutel(r: dict):
        w = r.get(veld)
        # None-veilig: lege waarden achteraan bij asc; sorted() is stabiel en de
        # feed komt al nieuw→oud binnen, dus gelijke waarden houden een vaste
        # volgorde — de paging-tegenhanger van de #761-tiebreaker.
        if veld == "recorded_at":
            return w
        return (w is None or w == "", str(w).lower(), r.get("entity_id") or 0)

    alle = sorted(alle, key=_sleutel, reverse=(richting == "desc"))

    from urllib.parse import quote, urlencode

    def _sorteer_url(key: str) -> str:
        params = {k: v for k, v in (("since", since), ("group", group),
                                    ("actor", actor)) if v}
        if sort == key:
            volgende = "asc" if richting == "desc" else "desc"
        else:
            volgende = "desc" if key == "wanneer" else "asc"
        params.update({"sort": key, "richting": volgende})
        return f"{basis}?" + urlencode(params)

    totaal = len(alle)
    page = max(1, page)
    feed_rows = alle[(page - 1) * PER_PAGE:page * PER_PAGE]

    # P13-spronglinks (golf 5, #913): de object-cel linkt naar de canonieke
    # pagina van het record — alleen voor entiteiten die er een hébben; de rest
    # blijft tekst. De inschrijvingspagina kent P3, dus alleen die sprong draagt
    # de weg terug naar dit scherm mét zijn filter- en sorteerstand.
    terug = quote(f"{basis}?" + urlencode(
        {k: v for k, v in (("since", since), ("group", group), ("actor", actor),
                           ("sort", sort), ("richting", richting),
                           ("page", page if page > 1 else "")) if v}), safe="")
    _OBJECT_URLS = {
        "Gezin": "/admin/leden/gezin/{id}",
        "Activiteit": "/admin/activiteiten/{id}",
        "Inschrijving": "/admin/inschrijvingen/{id}?terug=" + terug,
    }
    for r in feed_rows:
        sjabloon = _OBJECT_URLS.get(r["entity"])
        r["object_url"] = (sjabloon.format(id=r["entity_id"])
                           if sjabloon and r.get("entity_id") else None)
    return {
        "since": vanaf.isoformat(),
        "group": group, "actor": actor,
        "sort": sort, "richting": richting,
        "sorteer_urls": {key: _sorteer_url(key) for key in _SORT_VELDEN},
        "groups": GROUPS, "feed_rows": feed_rows,
        "page": page, "per_page": PER_PAGE, "totaal": totaal,
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/ledenwijzigingen", response_class=HTMLResponse)
def admin_ledenwijzigingen(request: Request, since: str = "", group: str = "",
                           actor: str = "", page: int = 1,
                           sort: str = "wanneer", richting: str = "desc",
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    ctx = wijzigingen_ctx(request, db, since, group, actor, page, sort, richting)
    template = ("_lw_inhoud.html" if is_fragment_request(request)
                else "admin_ledenwijzigingen.html")
    if template == "admin_ledenwijzigingen.html":
        ctx["nav_items"] = NAV
    return templates.TemplateResponse(request, template, ctx)


@router.get("/admin/ledenwijzigingen/export")
def ledenwijzigingen_export(request: Request, since: str = "",
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.audit.api import build_member_changes_ods, member_changes_since

    vanaf = _since(since)
    content = build_member_changes_ods(member_changes_since(db, vanaf))
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="ledenwijzigingen-vanaf-{vanaf}.ods"'},
    )

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
from app.i18n import _
from app.ui import (PER_PAGE_OPTIONS, admin_nav, is_fragment_request,
                    per_page_from, sort_description, templates)

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/ledenwijzigingen")


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today() - timedelta(days=30)


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


def _sorteer_labels() -> dict[str, str]:
    """De zichtbare kolomnaam per sorteersleutel.

    Per request en niet als moduleconstante: `_()` volgt de taal van de tenant.
    Hier en niet in het sjabloon, omdat de meta-regel dezelfde woorden gebruikt
    als de kolomkop — twee plekken zouden na de eerste hernoeming uiteenlopen.
    """
    return {"wanneer": _("Wanneer"), "wijziging": _("Wijziging"),
            "groep": _("Groep"), "persoon": _("Persoon"),
            "object": _("Object"), "actor": _("Actor")}


def wijzigingen_ctx(request: Request, db: Session, since: str, group: str, actor: str,
                    page: int = 1, sort: str = "wanneer",
                    richting: str = "desc", per_page: str = "") -> dict:
    from app.domains.audit.api import GROUPS, all_changes_since

    vanaf = _since(since)
    # #512 (v1.4-pariteit): één algemeen audit-logboek als primaire, gefilterde
    # tabel. De ledendata-mutaties voor Raak Nationaal blijven als .ods-export
    # (aparte route), niet meer als altijd-zichtbare tabel bovenaan.
    alle = all_changes_since(db, vanaf, group=group or None, actor=actor or None)

    # Paginering (#620). Bewust ná het sorteren en in Python: all_changes_since()
    # verenigt ~10 history-tabellen in Python, dus een server-side LIMIT/OFFSET op
    # één query bestaat niet. De "Vanaf"-datum blijft de echte begrenzing en bij
    # deze volumes volstaat dit. Groeit het logboek fors, dan is een echte UNION ALL
    # in SQL de duurzame oplossing — dat is opvolging, niet iets om nu te bouwen.
    if sort not in _SORT_VELDEN:
        sort = "wanneer"
    richting = "asc" if richting == "asc" else "desc"
    veld = _SORT_VELDEN[sort]
    labels = _sorteer_labels()

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

    # Standaard 50, met de keuze 25/50/100 in de meta-regel (#1083). De whitelist
    # staat in `app.ui`: de keuzelijst wordt uit diezelfde reeks gevuld, zodat er
    # geen maat te kiezen valt die deze route weigert.
    rijen_per_pagina = per_page_from(per_page)

    def _sorteer_url(key: str) -> str:
        params = {k: v for k, v in (("since", since), ("group", group),
                                    ("actor", actor)) if v}
        if sort == key:
            volgende = "asc" if richting == "desc" else "desc"
        else:
            volgende = "desc" if key == "wanneer" else "asc"
        params.update({"sort": key, "richting": volgende})
        # De paginagrootte reist mee met een kop-klik: die gaat langs de link en
        # niet langs de filterbalk, dus zonder dit valt de keuze daar terug op 50.
        params["per_page"] = str(rijen_per_pagina)
        return "/admin/ledenwijzigingen?" + urlencode(params)

    totaal = len(alle)
    page = max(1, page)
    feed_rows = alle[(page - 1) * rijen_per_pagina:page * rijen_per_pagina]

    # P13-spronglinks (golf 5, #913): de object-cel linkt naar de canonieke
    # pagina van het record — alleen voor entiteiten die er een hébben; de rest
    # blijft tekst. De inschrijvingspagina kent P3, dus alleen die sprong draagt
    # de weg terug naar dit scherm mét zijn filter- en sorteerstand.
    terug = quote("/admin/ledenwijzigingen?" + urlencode(
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
        "sorteer_labels": labels,
        "groups": GROUPS, "feed_rows": feed_rows,
        "page": page, "per_page": rijen_per_pagina, "totaal": totaal,
        "per_page_options": PER_PAGE_OPTIONS,
        # De meta-regel boven de tabel (§2.3): hoeveel regels, en in welke
        # volgorde. `totaal` telt de HELE selectie en niet deze pagina — dat is
        # hier eerlijk, want de datumfilter begrenst al wat er opgehaald wordt.
        "meta_telling": _("%(aantal)s wijzigingen") % {"aantal": totaal},
        "meta_volgorde": sort_description(labels[sort], richting,
                                          is_date=(sort == "wanneer")),
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/ledenwijzigingen", response_class=HTMLResponse)
def admin_ledenwijzigingen(request: Request, since: str = "", group: str = "",
                           actor: str = "", page: int = 1,
                           sort: str = "wanneer", richting: str = "desc",
                           per_page: str = "",
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    ctx = wijzigingen_ctx(request, db, since, group, actor, page, sort, richting,
                          per_page)
    template = ("_lw_inhoud.html" if is_fragment_request(request)
                else "admin_ledenwijzigingen.html")
    if template == "admin_ledenwijzigingen.html":
        ctx["nav_items"] = NAV
    else:
        # #1141: de exportknop staat buiten het swap-doel en reist out-of-band
        # mee. Alleen hier en niet op de paginaroute: daar rendert de kop hem
        # zelf, en twee knoppen met dezelfde id overschrijven elkaar.
        ctx["oob_exportknop"] = True
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

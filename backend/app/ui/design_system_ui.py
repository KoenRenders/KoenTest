"""Live design-system-pagina (#783): `/admin/design-system`.

De ontwerpnorm is sinds 9 september 2026 tweedelig — prose in
`docs/design-system.md`, en de componenten uit de app zelf. Dit is dat tweede deel:
één scherm dat elke kit-macro rendert met de ECHTE `_macros.html` en de ECHTE
`app.css`. Verander een macro en dit scherm verandert mee.

Wat het vervangt was een nabouw: `docs/design-system.html` had een eigen `<style>`
met 53 kleuren waar `build-css.sh` er 36 kent, en geen enkele kit-macro. GitHub
rendert het bestand niet, dus je moest het downloaden om het te zien — en het liep
uit de pas zonder dat iemand het merkte. Gemeten: de zes conventiewijzigingen van
8 september belandden alle zes in `ui-conventies.md` en geen enkele in die gids.

**Wat deze pagina wél en niet garandeert.** Het uiterlijk van een macro kan niet
afdrijven: een knop hier ís de knop. Representativiteit is een andere zaak — de
demo kiest zelf zijn argumenten en staat in zijn eigen omgeving, en een macro in een
smalle kolom of binnen een kaart kan er anders uitzien. Daarom roept het sjabloon
elke macro aan met argumenten zoals een echt scherm ze geeft, en staan er links naar
die echte schermen. De volledigheidsgate toetst aanwezigheid, niet getrouwheid; dat
verschil hoort iemand met zijn ogen te controleren.

**Toegang: `require_admin_ui`, dus ADMIN of OPERATOR, op elke omgeving.** Dat is
bewust niet OPERATOR-only. `require_operator_ui(db, email)` heeft een sessie nodig,
en dan zou deze route `db` moeten aannemen — precies de eigenschap die dit scherm
moet bewijzen: het toont geen data en heeft geen databank nodig. Er valt hier ook
niets te beschermen dat verder gaat dan "niet publiek": alle demo-waarden staan
hieronder in de broncode. De route bestaat dus op elke omgeving en de rooktest
(strikt alleen-lezen, publieke paden) raakt haar niet.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.domains.auth.api import require_admin_ui
from app.ui import admin_nav, templates
from app.ui.viewmodels import DesignSystemView

router = APIRouter(include_in_schema=False)

_STATIC = Path(__file__).resolve().parent.parent / "static"
_MACROS = Path(__file__).resolve().parent / "templates" / "_macros.html"


@lru_cache(maxsize=1)
def _tokens() -> list[tuple[str, str]]:
    """De kleurtokens uit de GEGENEREERDE css, niet opnieuw ingetypt.

    Dat is het hele punt van dit scherm: een lijst die met de hand wordt
    bijgehouden is precies wat er in `docs/design-system.html` misging.
    """
    try:
        css = (_STATIC / "app.css").read_text()
    except OSError:
        return []
    root = re.search(r":root\s*\{(.*?)\}", css, re.S)
    if not root:
        return []
    alles = re.findall(r"--([a-z0-9-]+):\s*([^;]+);", root.group(1))
    # Enkel de KLEUREN: `--brand-font` is ook een token maar geen vlak, en als
    # kleurstaal getoond zou hij een leeg vierkant met een lettertypenaam ernaast
    # zijn. Die hoort bij de typografie, niet bij het palet.
    return [(naam, waarde.strip()) for naam, waarde in alles
            if re.fullmatch(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)", waarde.strip())]


@lru_cache(maxsize=1)
def _iconen() -> list[str]:
    """De namen uit de `paths`-tabel van `ui.icon()`."""
    try:
        bron = _MACROS.read_text()
    except OSError:
        return []
    blok = bron[bron.index("{% macro icon("):]
    blok = blok[:blok.index("{%- endmacro %}")]
    return sorted(set(re.findall(r"^\s{2}\"([a-z0-9-]+)\":", blok, re.M)))


def _voorbeeldvelden() -> list:
    """Eén voorbeeld per soort uit `FIELD_TYPES` (#811).

    De formuliersoorten zijn géén kit-macro, dus de volledigheidsgate — die
    macronamen telt — zag ze niet. Gemeten op de eerste versie van deze pagina:
    geen radio-optielijst, geen "anders"-optie, en `rating` stond er alleen als
    woord. Ze worden hieronder gerenderd door dezelfde `veld()`-macro als het
    publieke formulier, niet nagebouwd; wat je hier ziet is dus letterlijk wat een
    bezoeker ziet.
    """
    from types import SimpleNamespace as N

    def optie(i, label, anders=False):
        return N(id=i, label=label, is_other=anders)

    return [
        N(id=1, field_type="text", label="Naam", required=True, help_text=None,
          options=[], rating_max=None, rating_low_label=None, rating_high_label=None),
        N(id=2, field_type="textarea", label="Opmerking", required=False,
          help_text="Zoveel of zo weinig als je wil.", options=[], rating_max=None,
          rating_low_label=None, rating_high_label=None),
        N(id=3, field_type="number", label="Aantal deelnemers", required=False,
          help_text=None, options=[], rating_max=None, rating_low_label=None,
          rating_high_label=None),
        N(id=4, field_type="email", label="E-mailadres", required=True,
          help_text=None, options=[], rating_max=None, rating_low_label=None,
          rating_high_label=None),
        N(id=5, field_type="phone", label="Gsm-nummer", required=False,
          help_text=None, options=[], rating_max=None, rating_low_label=None,
          rating_high_label=None),
        N(id=6, field_type="select", label="Afdeling", required=False, help_text=None,
          options=[optie(1, "Millegem"), optie(2, "Miloheem")], rating_max=None,
          rating_low_label=None, rating_high_label=None),
        N(id=7, field_type="radio", label="Hoe kom je?", required=False,
          help_text=None,
          options=[optie(3, "Te voet"), optie(4, "Met de fiets"),
                   optie(5, "Anders", anders=True)],
          rating_max=None, rating_low_label=None, rating_high_label=None),
        N(id=8, field_type="checkbox", label="Wat neem je mee?", required=False,
          help_text=None,
          options=[optie(6, "Regenjas"), optie(7, "Picknick"),
                   optie(8, "Iets anders", anders=True)],
          rating_max=None, rating_low_label=None, rating_high_label=None),
        N(id=9, field_type="rating", label="Hoe was het?", required=False,
          help_text=None, options=[], rating_max=5,
          rating_low_label="slecht", rating_high_label="top"),
        N(id=10, field_type="info", label="Let op", required=False,
          help_text="Een informatieblok vraagt niets; het vertelt alleen iets.",
          options=[], rating_max=None, rating_low_label=None, rating_high_label=None),
    ]


@router.get("/admin/design-system", response_class=HTMLResponse)
def design_system(request: Request, email: str = Depends(require_admin_ui)):
    view = DesignSystemView(
        nav_items=admin_nav("/admin/design-system"),
        tokens=_tokens(),
        iconen=_iconen(),
        velden=_voorbeeldvelden(),
        # A real date, because the date format is the one that cannot be written
        # as a literal in the template (#875).
        demo_datum=date(2026, 9, 12),
    )
    return templates.TemplateResponse(request, "design_system.html",
                                      view.as_context())

"""View-models van het activities-component (#643).

Zie `app/ui/viewmodel.py` voor het waarom: een dict is geen belofte.
"""
from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class AdminActiviteitenView(ViewModel):
    """`admin_activiteiten.html` en haar fragment `_aa_kaarten.html`.

    De filterbalk vraagt enkel de kaarten op — zou ze de pagina vervangen, dan
    sneuvelt het zoekveld (en de focus) bij elke aanslag. Beide krijgen daarom
    hetzelfde model.
    """

    activities: list[Any]
    scope: str
    q: str
    # Kengetallen (#528). Ze tellen wat er openstaat, niet wat er toevallig
    # gefilterd is: een zoekterm mag "Open inschrijvingen" niet doen dalen.
    kpi_open: int
    kpi_vol: int
    kpi_onderdelen: int

    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AdminInschrijvingView(ViewModel):
    """`admin_inschrijving.html` — de inschrijving als volwaardige pagina (golf 4,
    #913, B2). De pagina wikkelt `_inschrijving_detail.html`, dus dit model draagt
    naast de paginakop precies wat dat gedeelde fragment belooft te krijgen
    (`_detail_ctx` + de error/toast-vlaggen die `_render_detail` altijd zet)."""

    # Fragmentcontract (_inschrijving_detail.html)
    reg: dict[str, Any]
    products: list[dict[str, Any]]
    totaal: Any
    toon_ploegnaam: bool
    ploegnaam_verplicht: bool
    editable: bool
    edit_open: bool
    csrf_token: str
    error: str | None
    toast_bericht: str | None

    # Paginakop + de weg terug (A7)
    activiteit_id: int
    activiteit_titel: str
    component_naam: str | None
    terug: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)

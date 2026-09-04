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

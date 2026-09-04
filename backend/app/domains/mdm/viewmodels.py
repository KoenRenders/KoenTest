"""View-models van het mdm-component (#643).

Wat het ledenscherm van zijn route krijgt, getypeerd en op één plek. Zie
`app/ui/viewmodel.py` voor het waarom.
"""
from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class LedenView(ViewModel):
    """`leden.html` en haar fragment `_leden_lijst.html`.

    Het fragment wordt los gerenderd bij zoeken, filteren en pagineren, dus alles
    wat het nodig heeft staat hier — ook de pagineervelden, want `ui.pager()` toont
    "x–y van n".
    """

    families: list[Any]
    # Paginering (#580).
    page: int
    total: int
    per_page: int
    total_pages: int
    # Actieve filterstand; de balk leest ze terug.
    q: str
    status: str
    jaar: int | None
    jaren: list[int]
    gefilterd: bool
    # KPI-rij (#582/#611). `kpi_doeljaar` en `kpi_referentiejaar` staan in de
    # labels: het campagnejaar kantelt op een tenant-datum en mag dus nergens
    # hardgecodeerd staan.
    kpi_gezinnen: int
    kpi_personen: int
    kpi_niet_vernieuwd: int
    kpi_doeljaar: int
    kpi_referentiejaar: int

    csrf_token: str
    # Alleen de volledige pagina draagt de navigatie; het fragment niet.
    nav_items: list[dict[str, Any]] = field(default_factory=list)

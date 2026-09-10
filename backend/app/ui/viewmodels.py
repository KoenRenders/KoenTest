"""View-models van de cross-cutting beheerschermen in `app/ui/`.

Zie `app/ui/viewmodel.py` voor het waarom van een view-model boven een dict.
"""
from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class DesignSystemView(ViewModel):
    """`design_system.html` (#783).

    Bevat geen data uit de databank en kan die ook niet bevatten: het scherm toont
    de kit, niet de inhoud. De demo-waarden staan in het sjabloon zelf, zodat je bij
    elke component meteen ziet met welke argumenten hij is aangeroepen.
    """

    #: (naam, waarde) uit de `:root`-blok van de gegenereerde app.css.
    tokens: list[tuple[str, str]]
    #: De namen uit de `paths`-tabel van `ui.icon()`.
    iconen: list[str]
    #: Eén voorbeeldveld per soort uit `FIELD_TYPES` (#811), gerenderd door dezelfde
    #: `veld()`-macro als het publieke formulier.
    velden: list[Any]
    #: De macro `veld()` leest de ingevulde waarden uit `values`. Die moet in de
    #: context staan op het moment van importeren, niet pas in het sjabloon: Jinja
    #: bindt de context bij `{% from … with context %}`.
    values: dict[str, Any] = field(default_factory=dict)
    nav_items: list[dict[str, Any]] = field(default_factory=list)

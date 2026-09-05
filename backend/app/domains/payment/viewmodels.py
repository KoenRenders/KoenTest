"""View-models van het payment-component (#643).

Wat het betalingenscherm van zijn route krijgt, staat hier — één plek, getypeerd.
Voorheen was dat een dict van twintig sleutels die alleen bij het renderen bleek te
kloppen. Nu is een verkeerde of vergeten sleutel een fout in de route, en kan de
gate (`tests/test_template_variables_gate.py`) bewijzen dat de template niets
vraagt wat hier niet staat.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class BetalingenView(ViewModel):
    """`betalingen.html` en haar fragment `_betalingen_lijst.html`.

    Het fragment wordt óók los gerenderd (bij zoeken en filteren), dus alles wat
    het nodig heeft staat hier en niet in een `{% set %}` op de pagina — anders
    bestaat het in het fragment niet. Dat was precies de reden dat `status_labels`
    hier terechtkwam (#617).
    """

    # De gefilterde records en hun kaartgroepering (payment.service).
    records: list[Any]
    groepen: list[dict[str, Any]]
    matrix: dict[str, dict[str, Decimal]]

    # Actieve filterstand — de balk leest ze terug, de export-link geeft ze door.
    context: str
    status: str
    # #669: staat los van `status` — de statuskolom en de afgeleide "staat er nog
    # iets open" zijn twee verschillende vragen, en je wil ze kunnen combineren.
    openstaand: bool
    q: str

    # Filteropties, opgebouwd uit de zichtbare records.
    componenten: list[tuple[int, str]]
    jaren: list[int]
    context_top: list[tuple[str, str]]
    context_groups: dict[str, list[tuple[str, str]]]

    # Labels: §2.12 verbiedt rauwe DB-waarden op het scherm. Per request
    # opgebouwd zodat _() de taal van de tenant volgt (#630).
    method_labels: dict[str, str]
    status_labels: dict[str, str]
    kaart_status: dict[str, tuple[str, str]]

    # Rol en beveiliging.
    is_finance: bool
    csrf_token: str

    # Alleen de volledige pagina draagt de navigatie; het fragment niet.
    nav_items: list[dict[str, Any]] = field(default_factory=list)

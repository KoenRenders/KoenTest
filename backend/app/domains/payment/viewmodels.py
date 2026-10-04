"""View-models van het payment-component (#643).

Wat het betalingenscherm van zijn route krijgt, staat hier — één plek, getypeerd.
Voorheen was dat een dict van twintig sleutels die alleen bij het renderen bleek te
kloppen. Nu is een verkeerde of vergeten sleutel een fout in de route, en kan de
gate (`tests/test_template_variables_gate.py`) bewijzen dat de template niets
vraagt wat hier niet staat.
"""

from dataclasses import dataclass, field
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

    # Actieve filterstand — de balk leest ze terug, de export-link geeft ze door.
    context: str
    status: str
    # #669: staat los van `status` — de statuskolom en de afgeleide "staat er nog
    # iets open" zijn twee verschillende vragen, en je wil ze kunnen combineren.
    openstaand: bool
    q: str
    # P13 (golf 5, #913): actieve recordscope (?inschrijving= of ?record=), of
    # None. Draagt de tekst en uitgang voor ui.scope_regel plus het hidden field
    # waarmee de scope filterwijzigingen overleeft.
    scope: dict[str, Any] | None
    # Golf 10 (#913): het actieve statustab-zicht, de tabs zelf (label, aantal,
    # fragment-URL, actief) en de kengetallenband boven de tabel.
    zicht: str
    # K1 (#1555): the list kit. The status filter's segments (value, label and,
    # where the state is acted on, a count), the key figures of the title row,
    # the page sizes on offer, the actions under `⋯`, the hidden fields that
    # carry a scope with every toolbar request, and whether this is the
    # embedded rendering inside a record (no title row, no Filters).
    segments: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    page_sizes: list[int]
    toolbar_menu: list[dict[str, Any]]
    toolbar_hidden: list[tuple[str, str]]
    embedded: bool
    kpi: dict[str, Any]
    # #996: band + tabs (#bt-boven) reizen alleen op fragmentantwoorden
    # out-of-band mee; de volledige pagina rendert ze zelf.
    oob_boven: bool = False
    # #1059: de paginering telt GROEPEN, niet rijen — een inschrijving mag nooit
    # over twee pagina's breken. `records` blijft de volledige selectie, want de
    # meta-regel, de totaalregel en het financieel overzicht tellen daarover.
    page: int = 1
    per_page: int = 50
    totaal_groepen: int = 0
    # De bladerknoppen dragen hun eigen filterstand in de URL, zoals de tabs —
    # geen `hx-include` op de filterbalk, want die zou de paginakeuze overschrijven
    # met wat er toevallig in het formulier staat.
    pager_url: str = ""
    # K1 (#1555): the address of this list with its state, for the way back
    # from a row's registration (`?terug=`).
    return_url: str = "/admin/betalingen"
    # #1060: staat de beheer-assistent aan én mag deze gebruiker hem aanspreken?
    # Twee vragen, één antwoord: een ingang die op een 403 uitkomt is erger dan
    # geen ingang. Het betalingenscherm laat FINANCE binnen, de assistent niet.
    raakje_scherm: bool = False
    #: Welke spraakmodus de kit mag tonen (CR-07): de overlay deelt haar
    #: invoerregel met de andere Raakje-ingangen.
    stt_mode: str = ""

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
    # K2 (#1556): may this user change payments (FINANCE or OPERATOR)? The
    # rows carry their action and menu already decided by it; the template
    # asks nothing itself.
    may_mutate: bool
    # The table: the head's columns, the column chooser's choice per priority
    # and per optional column, the sort and its options for a phone, and the
    # sentence of the empty state.
    columns: list[dict[str, Any]]
    column_modes: dict[int, str]
    column_choices: list[dict[str, Any]]
    sort: str
    sort_options: list[tuple[str, str]]
    empty_reason: str
    csrf_token: str

    # Alleen de volledige pagina draagt de navigatie; het fragment niet.
    nav_items: list[dict[str, Any]] = field(default_factory=list)

    # #723: de reden waarom een mutatie geweigerd is. De servicelaag schrijft een
    # precieze zin ("Kan niet meer terugbetalen (€ 100.00) dan er netto ontvangen
    # is (€ 10.00).") en die reisde tot vlak vóór het scherm, waar ze vervangen werd
    # door "Er ging iets mis" — htmx swapt geen 4xx, dus de globale afhandelaar nam
    # over en die kijkt nooit in het antwoord. Nu gaat de lijst terug mét de reden,
    # als 200, precies zoals het inschrijvingenpaneel het al deed.
    error: str | None = None


@dataclass(frozen=True, kw_only=True)
class BookingView(ViewModel):
    """`betaling.html` — the record page of one booking (#1574).

    The row of the payments list opens it (CR-11 block 4: the row is the way in),
    and it carries what the unfold under the row carried: the booking's data, its
    edit form, the refund form and the two actions of the head.
    """

    #: The enriched record, and its figures as the list shows them (amount,
    #: received, balance, derived status, may it be deleted).
    rec: Any
    card: dict[str, Any]
    #: The head: `ui.record_header`'s title, badges, facts, primary and actions.
    record_head: dict[str, Any]
    way_back: dict[str, Any]
    head_editing: bool = False
    #: The charge this refund belongs to, and the refunds of this charge — each a
    #: {label, href, amount, status_label, status_tone}.
    parent: dict[str, Any] | None = None
    refunds: list[dict[str, Any]] = field(default_factory=list)
    #: May this user change payments (FINANCE or OPERATOR)? Without it the page
    #: is read-only: no primary, no actions, no forms.
    may_mutate: bool = False
    status_labels: dict[str, str]
    method_label: str
    #: This page's own address with its way back, where its forms return to.
    here: str
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    #: A full-page answer after a save shows the toast itself (#748).
    toast_opgeslagen: bool = False

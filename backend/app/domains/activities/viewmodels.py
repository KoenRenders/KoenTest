"""View-models van het activities-component (#643).

Zie `app/ui/viewmodel.py` voor het waarom: een dict is geen belofte.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

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
    # #1557: this list as it stands, for the way back of the record a card opens.
    list_url: str
    # Kengetallen (#528). Ze tellen wat er openstaat, niet wat er toevallig
    # gefilterd is: een zoekterm mag "Open inschrijving" niet doen dalen.
    kpi_open: int
    kpi_vol: int
    kpi_onderdelen: int
    # #1428: status and audience per activity id — not on the cards' schema,
    # which is also the public JSON answer.
    publication: dict[int, Any] = field(default_factory=dict)

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
    #: Every product of the component as a counter row (#1494): id, name,
    #: unit_price, quantity — 0 is "not chosen", as on the registration form.
    product_rows: list[dict[str, Any]]
    totaal: Any
    toon_ploegnaam: bool
    ploegnaam_verplicht: bool
    editable: bool
    edit_open: bool
    # Golf 8-feedback: op de eigen pagina draagt het cluster ook Verwijderen.
    op_pagina: bool
    csrf_token: str
    error: str | None
    toast_bericht: str | None
    # CR-14 phase 2 (§B4.4): (label, value) per question, and the moment the
    # answers were asked while the link is open.
    antwoorden: list[tuple[str, str]]
    antwoorden_gevraagd_op: Any
    link_actie: str | None
    # CR-14 phase 3 (§B4.7): the questions to correct the answers in, the answers as
    # the field partial reads them, and the question a refusal names.
    vragen: list[Any]
    vraagformulier: Any
    vraag_groepen: list[dict[str, Any]]
    vraag_los: list[Any]
    values: dict[str, Any]
    vraag_fout: int | None

    # Paginakop + de weg terug (A7)
    activiteit_id: int
    activiteit_titel: str
    component_naam: str | None
    terug: str
    terug_label: str
    # Feedback 15 sep: tabs (Overzicht · Betalingen) i.p.v. de P13-chips.
    record_tabs: list[dict[str, Any]]
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ActivityRegistrationsListView(ViewModel):
    """`_aa_inschrijvingen_lijst.html` — the registrations table of the
    activity's tab (CR-11 K6, #1560), everything from
    `activities.api.registration_table`."""

    # Groups with their rows: per row the badge, the answers and the payment are
    # decided by the builder; the template shows them.
    reg_groups: list[dict[str, Any]]
    reg_columns: list[dict[str, Any]]
    reg_total: int
    reg_per_page: int
    # The one unfolded row, from `rij=` in the URL: the way back from a
    # registration's page lands on the row it left.
    reg_open_row: str
    reg_view: str
    reg_q: str
    reg_sort: str
    reg_segments: list[dict[str, Any]]
    reg_sort_options: list[tuple[str, str]]
    reg_empty: str
    # The list holder a sort link swaps.
    reg_target: str
    # True on a fragment answer: the toolbar's count and sort travel along.
    reg_oob: bool = False


@dataclass(frozen=True, kw_only=True)
class AdminActiviteitInschrijvingenView(ActivityRegistrationsListView):
    """`admin_activiteit_inschrijvingen.html` — the Inschrijvingen tab of the
    record page (golf 8, #913; K6, #1560): the record's head and tabs, the
    embedded toolbar and the registrations table."""

    a: Any
    record_tabs: list[dict[str, Any]]
    # CR-11 block 5 (#1557): the head as data for `ui.record_header` — title,
    # badges, facts, the primary and the actions — from `record_kop_ctx`; the way
    # back and the edit state from `app.ui.record_frame`.
    record_head: dict[str, Any]
    way_back: dict[str, str]
    head_editing: bool
    # The per-screen assistant overlay in the head and its speech path (#975,
    # #1075), from `record_kop_ctx`; both go with the shell's panel (#1562).
    raakje_admin: bool
    stt_mode: str
    # #1428: "Concept" on the summary card, from `record_kop_ctx`.
    publication: Any
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CopyActivityView(ViewModel):
    """`admin_activiteit_kopieren.html`: the step before a copy (#1397).

    `first_date` is None for an activity without dates; then there is nothing to
    move and the step only confirms.
    """

    activity: Any
    first_date: Optional[date]
    same_weekday: Optional[date]
    same_date: Optional[date]
    error: Optional[str] = None
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)

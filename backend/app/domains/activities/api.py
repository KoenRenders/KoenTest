"""Publieke facade van het activities-component (fase 4a, #402).

Activiteiten, onderdelen, producten en registraties (3-level, alle
reg_form_types). De totaalberekening (`compute_registration_total`) leeft
uitsluitend hier — server-side, één plek (§19.3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:  # #1305: types for the annotations only, not a new import order
    from datetime import date

    from fastapi import BackgroundTasks
    from sqlalchemy.orm import Session

    from app.domains.mdm.api import Person
    from app.schemas.activity import ActivityResponse, RegistrationCreate

# Volgorde bewust: eerst de modellen binden, dan pas de services — zo kan een
# component dat middenin deze import (indirect) terugverwijst de modelnamen al
# vinden (zelfde patroon als payment.api).
from app.domains.activities.codes import (  # noqa: F401
    ACTIVITY_STATUS,
    INDIVIDUAL,
    REGISTRATION_STATE,
    REGISTRATION_TYPE,
    TARGET_AUDIENCE,
    TARGET_AUDIENCE_CODES,
)
from app.domains.activities.export import build_component_export_ods  # noqa: F401
from app.domains.activities.fiche import NEW_ACTIVITY_STATUS  # noqa: F401
from app.domains.activities.models import (  # noqa: F401
    Activity,
    ActivityDate,
    ActivityDateHistory,
    ActivityHistory,
    ActivityProduct,
    ActivityStatus,
    ActivitySubRegistration,
    ComponentHistory,
    ProductHistory,
    Registration,
    RegistrationHistory,
    RegistrationItem,
    RegistrationItemHistory,
)
from app.domains.activities.proposer import ProposerError, no_answer_text  # noqa: F401
from app.domains.activities.registration_form import (  # noqa: F401
    Channel,
    Outcome,
    OutcomeKind,
    board_channel,
    contact_refusals,
    form_context,
    form_quantities,
    form_values,
    is_member,
    opening_quantity,
    public_channel,
    question_block_context,
    submit,
    total_context,
)
from app.domains.activities.service import (  # noqa: F401
    INSCHRIJVING_SORT_VELDEN,
    ActivityDateSpan,
    ActivityOption,
    ActivitySpan,
    OrganiserView,
    RegistrationState,
    activities_active_between,
    activities_from,
    activity_by_key,
    activity_dates_active_between,
    activity_dates_from,
    activity_names,
    activity_options,
    add_organiser,
    answer_link_action,
    answer_path,
    answer_questions,
    board_notes,
    booked_per_component,
    check_publicly_bookable,
    component_book,
    copy_activity,
    copy_suggestions,
    edit_answers,
    first_date_of,
    get_activity,
    get_component,
    get_registration,
    inschrijving_kop_ctx,
    inschrijving_tabs,
    is_published,
    members_only_refusal,
    move_organiser,
    organisers_for,
    predecessors_of,
    publication,
    publication_of,
    publicly_bookable_products,
    published_only,
    question_form,
    question_forms,
    record_kop_ctx,
    record_registration_history,
    record_tabs,
    registration_answers,
    registration_awaiting_answers,
    registration_contact_names,
    registration_count_for,
    registration_counts,
    registration_ids_for,
    registration_refusal,
    registration_state,
    registrations_for,
    registrations_without_component_count,
    remove_organiser,
    send_answer_link,
    set_activity_status,
    slug_is_vrij,
    slugify,
    sorteer_inschrijvingen,
    update_organiser,
)
from app.domains.activities.totals import (  # noqa: F401
    compute_registration_total,
    quote_lines,
    quote_registration,
    quote_registration_products,
)

# ── Facade-doorgangen naar de registratieflow ────────────────────────────────
# De implementatie van deze drie blijft in `router.py`. Dat is een bewuste keuze:
# #635 noemt `inschrijf_submit → register_for_activity` expliciet als voorbeeld
# van hoe het hóórt ("niet aanraken") — het scherm doet niets zelf, het roept één
# domeinbewerking aan. Wat wél moest veranderen is de weg ernaartoe: een
# UI-module importeert uit een domein enkel `api.py`, nooit rechtstreeks de
# router. Vandaar deze doorgangen, met `db` vooraan zoals elders in de service.


def list_activities(
    db: Session, scope: str = "upcoming", *, include_drafts: bool = False
) -> list[ActivityResponse]:
    """Publieke activiteitenlijst (upcoming/archived/all) — facade-doorgang
    voor andere componenten (o.a. de homepage, #405).

    #1428: without drafts unless the caller asks — only the board's own list
    does. A public place that forgets the argument stays safe.
    """
    from app.domains.activities.router import activities_for as _impl

    return _impl(db, scope, include_drafts=include_drafts)


def get_activity_detail(db: Session, activity_id: int) -> ActivityResponse | None:
    """Eén activiteit met de verrijking van de lijst (#651) — facade-doorgang.

    Het beheerdetail haalde hiervoor de hele lijst op en filterde in Python; dat
    maakte het detail van één activiteit trager dan de lijst van allemaal.
    """
    from app.domains.activities.router import get_activity_detail as _impl

    return _impl(db, activity_id)


def _standing(activity: Activity, form: Any) -> Any:
    """The fiche as it stands in the page (#1659), or None when the request
    carried no form: the form's texts and date rows, the stored components."""
    from app.domains.activities import proposer
    from app.domains.activities.fiche_form import proposal_fields

    read = proposal_fields(form) if form is not None else None
    if read is None:
        return None
    texts, rows = read
    return proposer.Standing(
        dates=list(rows), sub_registrations=list(activity.sub_registrations), **texts
    )


def propose_for_activity(
    db: Session, activity_id: int, *, request: str, actor: str, form: Any = None
) -> Any:
    """Raakje's proposal for this activity's fiche (#1604), or None when the
    activity does not exist. `form` (#1659): the fiche's form as the panel sent
    it along — its unsaved values are the record for this request. Raises
    `ProposerError` with a line for the screen."""
    from app.domains.activities import proposer
    from app.domains.activities.service import _activity_met_boom

    activity = _activity_met_boom(db, activity_id)
    if activity is None:
        return None
    return proposer.propose(
        db, activity, request=request, actor=actor, standing=_standing(activity, form)
    )


def propose_for_new_activity(db: Session, *, request: str, actor: str, form: Any = None) -> Any:
    """Raakje's proposal for the fiche of an activity that does not exist yet
    (#1649): the same proposer on an activity that holds nothing, so its sources
    are the request and what the form already holds (`form`, #1659). Nothing is
    added to the session."""
    from app.domains.activities import proposer

    activity = Activity(name="")
    return proposer.propose(
        db, activity, request=request, actor=actor, standing=_standing(activity, form)
    )


def proposal_vals() -> str:
    """Which fields of the fiche the Assistent's panel sends along with a
    request for a proposal (#1659), as an `hx-vals` expression."""
    from app.domains.activities.fiche_form import PROPOSAL_VALS

    return PROPOSAL_VALS


#: Where the Assistent's panel asks a proposal for a new activity (#1649).
NEW_PROPOSER_URL = "/admin/activiteiten/nieuw/raakje/voorstel"


def proposer_url(activity_id: int) -> str:
    """Where the Assistent's panel asks a proposal for this activity (#1604)."""
    return f"/admin/activiteiten/{activity_id}/raakje/voorstel"


def open_deadlines(activity: Activity) -> list[date]:
    """De uiterste inschrijfdatums van deze activiteit, zonder dubbels (#1053)."""
    from app.domains.activities.service import open_deadlines as _impl

    return _impl(activity)


def shared_deadline(activity: Activity) -> date | None:
    """De ene uiterste datum die voor élk onderdeel geldt, of None (#1053)."""
    from app.domains.activities.service import shared_deadline as _impl

    return _impl(activity)


def card_deadline(activity: Activity) -> date | None:
    """De ene uiterste datum die de publieke kaart toont, of None (#1053)."""
    from app.domains.activities.service import card_deadline as _impl

    return _impl(activity)


def deadline_is_near(deadline: date | None) -> bool:
    """Valt de uiterste inschrijfdatum binnen de laatste week? (#1051)"""
    from app.domains.activities.service import deadline_is_near as _impl

    return _impl(deadline)


def registration_table(db: Session, groups: list[dict], **kwargs: Any) -> dict:
    """The registrations table of a record's tab (CR-11 K6, #1560) — see
    `registration_table.registration_table`."""
    from app.domains.activities.registration_table import registration_table as _impl

    return _impl(db, groups, **kwargs)


def parse_registration_sort(sort: str, direction: str = "") -> str:
    """The sort of the registrations table as its toolbar carries it."""
    from app.domains.activities.registration_table import parse_sort as _impl

    return _impl(sort, direction)


def enrich_registration(registration: Registration, activity: Activity) -> dict:
    """Een inschrijving met haar activiteit- en productcontext, zoals het
    beheerscherm ze toont. Implementatie in de service (#679, batch 6)."""
    from app.domains.activities.service import enrich_registration as _impl

    return _impl(registration, activity)


def move_within(
    db: Session, siblings: Sequence[Any], item_id: int, richting: str, attr: str = "sort_order"
) -> None:
    """Herorden broers/zussen en leg het vast.

    De kernel-helper commit bewust niet (hij weet niets van transacties); dat
    gebeurt hier, zodat de transactiegrens in het domein ligt en niet in het
    scherm (#635 regel 2).
    """
    from app.kernel.ordering import move_sibling

    move_sibling(siblings, item_id, richting, attr=attr)
    db.commit()


def public_registrations(db: Session, activity_id: int, component_id: int) -> list[dict]:
    """De deelnemers van één onderdeel, zoals de publieke kaart ze toont (#451)."""
    from app.domains.activities.router import get_public_registrations as _impl

    return _impl(activity_id, component_id=component_id, db=db)


def register_for_activity(
    db: Session,
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    current_member: Person | None = None,
) -> dict:
    """De inschrijfflow: volzet-controle, regelitems, totaal, betaalrecord en
    bevestigingsmail. Eén domeinbewerking; het scherm vult alleen het formulier in."""
    from app.domains.activities.router import register_for_activity as _impl

    return _impl(activity_id, data, background_tasks, db=db, current_member=current_member)


def board_register_for_activity(
    db: Session,
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    *,
    actor: str,
    person_id: int | None,
) -> dict:
    """The board adds a registration for somebody else (#1192, #1284).

    The same implementation as the public way (`router.create_registration`).
    `person_id` is the person found by the e-mail address typed into the form —
    never the board member who sends it; `actor` is the board member's e-mail,
    for the audit trail only. The back office may book products that are not
    publicly bookable, and Mollie returns the board to the registration in the
    back office instead of the public page.
    """
    from app.domains.activities.router import create_registration

    return create_registration(
        db,
        activity_id,
        data,
        background_tasks,
        person_id=person_id,
        actor=actor,
        backoffice_products=True,
        return_path="/admin/inschrijvingen/{registration_id}",
    )


__all__ = [
    "Channel",
    "Outcome",
    "OutcomeKind",
    "board_channel",
    "contact_refusals",
    "form_context",
    "form_quantities",
    "is_member",
    "opening_quantity",
    "public_channel",
    "submit",
    "total_context",
    "RegistrationState",
    "registration_refusal",
    "registration_state",
    "INDIVIDUAL",
    "REGISTRATION_STATE",
    "REGISTRATION_TYPE",
    "ActivityOption",
    "activity_names",
    "activity_options",
    "get_activity",
    "get_component",
    "INSCHRIJVING_SORT_VELDEN",
    "booked_per_component",
    "get_registration",
    "inschrijving_kop_ctx",
    "sorteer_inschrijvingen",
    "inschrijving_tabs",
    "record_tabs",
    "record_kop_ctx",
    "registration_contact_names",
    "registration_count_for",
    "registration_ids_for",
    "registrations_for",
    "registrations_without_component_count",
    "publicly_bookable_products",
    "check_publicly_bookable",
    "Activity",
    "ActivityDate",
    "ActivityDateHistory",
    "ActivityHistory",
    "ActivityProduct",
    "ActivitySubRegistration",
    "ComponentHistory",
    "ProductHistory",
    "Registration",
    "RegistrationItem",
    "RegistrationHistory",
    "RegistrationItemHistory",
    "build_component_export_ods",
    "compute_registration_total",
    "quote_registration",
    "quote_registration_products",
    "enrich_registration",
    "registration_table",
    "parse_registration_sort",
    "get_activity_detail",
    "propose_for_activity",
    "propose_for_new_activity",
    "NEW_PROPOSER_URL",
    "NEW_ACTIVITY_STATUS",
    "proposal_vals",
    "proposer_url",
    "ProposerError",
    "no_answer_text",
    "list_activities",
    "move_within",
    "public_registrations",
    "register_for_activity",
    "OrganiserView",
    "add_organiser",
    "organisers_for",
    "board_notes",
    "move_organiser",
    "remove_organiser",
    "update_organiser",
    "ActivitySpan",
    "activities_active_between",
    "activities_from",
    "ActivityDateSpan",
    "activity_dates_active_between",
    "activity_dates_from",
    "registration_counts",
    "copy_activity",
    "copy_suggestions",
    "first_date_of",
    "predecessors_of",
    "is_published",
    "members_only_refusal",
    "published_only",
    "publication",
    "publication_of",
    "set_activity_status",
]

"""The one save of the activity fiche (CR-11 pilot A, #1559).

The fiche edits as a whole (#1558): its sections, its dates, its components with
their products and its organisers are one form, and one "Opslaan" writes them in
**one transaction**. Until #1559 every row had a route of its own — seventeen of
them — and each committed by itself. `save_fiche` replaces them for the screen.

It writes nothing the row functions did not write, and refuses everything they
refused: it calls the same non-committing cores (`insert_date`,
`apply_component_update`, `remove_product`, …) that the committing doors — still
used by the JSON API — call. What is new is said where it stands:

- a row that did not change is not written and gets no history row (a save of
  the whole fiche would otherwise log an update for every row at every save);
- the order of components and products is their place in the form;
- four inputs that came back as a 500 are refused with a message (`_checked`);
- a component with registrations and a product on a registration cannot go
  (`service.remove_component`, `service.remove_product` — Koen, 4 October 2026);
- the confirmation for leaving the posters without a contact person was a rule
  of the route; it is a rule here.

A refusal anywhere rolls the whole save back: nothing is half written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from app.domains.activities import service
from app.domains.activities.models import (
    ActiviteitFout,
    Activity,
    ActivityOrganiser,
)

#: The fields of a row, in the order they are compared and written.
DATE_FIELDS = ("start_date", "end_date", "start_time", "end_time")
COMPONENT_FIELDS = (
    "name",
    "team_name_required",
    "max_participants",
    "registration_closes_on",
    "form_id",
)
COMPONENT_LINKS = ("external_register_url", "external_registrations_url", "info_url")
PRODUCT_FIELDS = (
    "name",
    "price",
    "member_price",
    "is_free",
    "pay_on_site",
    "is_active",
    "max_participants",
)
ORGANISER_FIELDS = ("is_contact", "show_email", "show_mobile", "email_override", "mobile_override")


@dataclass
class DateRow:
    """One date of the fiche. `key` is the row's id, or anything else for a new row."""

    key: str
    start_date: date
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


@dataclass
class ProductRow:
    key: str
    name: str
    price: Decimal = Decimal("0")
    member_price: Optional[Decimal] = None
    is_free: bool = False
    pay_on_site: bool = False
    is_active: bool = True
    max_participants: Optional[int] = None


@dataclass
class ComponentRow:
    key: str
    name: str
    team_name_required: bool = False
    max_participants: Optional[int] = None
    registration_closes_on: Optional[date] = None
    form_id: Optional[int] = None
    #: The three external addresses; None when the form did not send them (a new
    #: component has no place for them yet in the closed last section).
    links: Optional[dict[str, Optional[str]]] = None
    products: list[ProductRow] = field(default_factory=list)
    #: Remove the info attachment.
    drop_info: bool = False


@dataclass
class OrganiserRow:
    key: str
    person_id: Optional[int] = None
    is_contact: bool = False
    show_email: bool = True
    show_mobile: bool = True
    email_override: Optional[str] = None
    mobile_override: Optional[str] = None


@dataclass
class FicheSave:
    """Everything one "Opslaan" of the fiche carries."""

    fields: dict[str, Any]
    dates: list[DateRow] = field(default_factory=list)
    components: list[ComponentRow] = field(default_factory=list)
    organisers: list[OrganiserRow] = field(default_factory=list)
    #: Remove the uploaded poster.
    drop_poster: bool = False
    #: The board confirmed that the posters go without a contact person.
    confirmed_no_contact: bool = False
    #: Which groups the form carried. A group the form did not send is left
    #: alone — a caller that saves only the sections removes no rows.
    groups: frozenset[str] = frozenset({"dates", "components", "organisers"})


class ContactConfirmation(ActiviteitFout):
    """The save would leave the posters without a contact person: not an error
    but a question. The same save with `confirmed_no_contact` goes through."""


def _(text: str) -> str:
    from app.i18n import _ as translate

    return translate(text)


def _gone(what: str) -> ActiviteitFout:
    """A row the form names no longer exists: someone else removed it meanwhile."""
    return ActiviteitFout(
        _("%(what)s bestaat niet meer. Herlaad de pagina en probeer opnieuw.") % {"what": what}
    )


def _changed(row: Any, values: dict) -> dict:
    """The fields of `values` that differ from the row."""
    return {name: value for name, value in values.items() if getattr(row, name) != value}


def _checked(
    kind: str, name: str, max_participants: Optional[int], *prices: Optional[Decimal]
) -> None:
    """The refusals that were a 500 through the row routes: an empty name passed
    (and a nameless row is unfindable), a maximum of zero or less hit the CHECK
    of the database, and a negative price failed a schema built by hand."""
    if not name.strip():
        raise ActiviteitFout(
            _("Een onderdeel heeft een naam nodig.")
            if kind == "component"
            else _("Een product heeft een naam nodig.")
        )
    if max_participants is not None and max_participants <= 0:
        raise ActiviteitFout(
            _("Het maximum van “%(name)s” moet groter zijn dan nul.") % {"name": name}
        )
    if any(price is not None and price < 0 for price in prices):
        raise ActiviteitFout(_("De prijs van “%(name)s” mag niet negatief zijn.") % {"name": name})


async def save_fiche(
    db: Session,
    activity_id: int,
    fiche: FicheSave,
    *,
    actor: str | None = None,
    poster: Any = None,
    component_files: dict[str, Any] | None = None,
    background_tasks: Any = None,
) -> Optional[Activity]:
    """Write the whole fiche in one transaction. None when the activity does not
    exist; `ActiviteitFout` with nothing written when any part is refused.

    `poster` and `component_files` (by the component row's key) are uploads; they
    are stored in the same transaction, so a refused file refuses the save.
    """
    activity = service._activity_met_boom(db, activity_id)
    if activity is None:
        return None
    # A savepoint around the whole save: a refusal — a rule, a refused file, the
    # coherence rule of a date in the flush — takes back exactly what this save
    # wrote and nothing else, and the session stays usable for the answer that
    # says why. Nothing is half written.
    savepoint = db.begin_nested()
    try:
        changed = _changed(activity, fiche.fields)
        if changed:
            service.apply_activity_update(db, activity, changed, actor=actor)
        if "dates" in fiche.groups:
            _save_dates(db, activity, fiche.dates, actor)
        component_ids: dict[str, int] = {}
        if "components" in fiche.groups:
            component_ids = _save_components(db, activity, fiche.components, actor)
        if "organisers" in fiche.groups:
            _save_organisers(db, activity, fiche.organisers, fiche.confirmed_no_contact)
        db.flush()  # the coherence rule of a date row fires here (#792)
        await _store_files(
            db, activity, fiche, component_ids, poster, component_files or {}, background_tasks
        )
    except Exception:
        # Also after a failed flush: the savepoint is then deactivated, not closed,
        # and the session refuses everything until it is rolled back.
        try:
            savepoint.rollback()
        except InvalidRequestError:
            pass  # already closed
        raise
    savepoint.commit()
    db.commit()
    db.refresh(activity)
    return activity


# ── Dates ────────────────────────────────────────────────────────────────────


def _save_dates(db: Session, activity: Activity, rows: list[DateRow], actor: str | None) -> None:
    existing = {str(d.id): d for d in activity.dates}
    kept = set()
    for row in rows:
        values = {name: getattr(row, name) for name in DATE_FIELDS}
        if row.key in existing:
            kept.add(row.key)
            changed = _changed(existing[row.key], values)
            if changed:
                service.apply_date_update(db, existing[row.key], changed, actor=actor)
        elif row.key.isdigit():
            raise _gone(_("Een datum"))
        else:
            service.insert_date(db, activity.id, SimpleNamespace(**values), actor=actor)
    for key, ad in existing.items():
        if key not in kept:
            service.remove_date(db, ad, actor=actor)


# ── Components and their products ────────────────────────────────────────────


def _save_components(
    db: Session, activity: Activity, rows: list[ComponentRow], actor: str | None
) -> dict[str, int]:
    """Returns {row key: component id} for the components that stay, so an upload
    finds the component a new row became."""
    existing = {str(c.id): c for c in activity.sub_registrations}
    ids: dict[str, int] = {}
    # Removals first: a refusal names its component before anything is added.
    kept = {row.key for row in rows}
    for key, component in existing.items():
        if key not in kept:
            service.remove_component(db, component, actor=actor)
    for place, row in enumerate(rows):
        _checked("component", row.name, row.max_participants)
        values: dict[str, Any] = {name: getattr(row, name) for name in COMPONENT_FIELDS}
        values["name"] = row.name.strip()
        if row.links is not None:
            values.update({name: row.links.get(name) for name in COMPONENT_LINKS})
        if row.key in existing:
            component = existing[row.key]
            changed = _changed(component, values)
            if changed:
                service.apply_component_update(db, component, changed, actor=actor)
            products = {str(p.id): p for p in component.products}
        elif row.key.isdigit():
            raise _gone(_("Een onderdeel"))
        else:
            form_id = values.pop("form_id")
            links = {name: values.pop(name, None) for name in COMPONENT_LINKS}
            component = service.new_component(
                activity.id, SimpleNamespace(**values, **links, sort_order=place)
            )
            service._insert_component(db, component, actor=actor, action="component_created")
            if form_id is not None:
                # The row routes could attach a form only on an update; a new row
                # of the fiche has the select, so the same check runs here.
                service._check_questions(db, component, form_id)
                component.form_id = form_id
            products = {}
        if component.sort_order != place:
            component.sort_order = place  # a reorder writes no history, as before
        ids[row.key] = component.id
        _save_products(db, component, products, row.products, actor)
    return ids


def _save_products(
    db: Session, component: Any, existing: dict, rows: list[ProductRow], actor: str | None
) -> None:
    kept = {row.key for row in rows}
    for key, product in existing.items():
        if key not in kept:
            service.remove_product(db, product, actor=actor)
    for place, row in enumerate(rows):
        _checked("product", row.name, row.max_participants, row.price, row.member_price)
        values = {name: getattr(row, name) for name in PRODUCT_FIELDS}
        values["name"] = row.name.strip()
        if row.key in existing:
            product = existing[row.key]
            changed = _changed(product, values)
            if changed:
                service.apply_product_update(db, product, changed, actor=actor)
        elif row.key.isdigit():
            raise _gone(_("Een product"))
        else:
            product = service.new_product(component.id, SimpleNamespace(**values, sort_order=place))
            service._insert_product(db, product, actor=actor, action="product_created")
        if product.sort_order != place:
            product.sort_order = place


# ── Organisers ───────────────────────────────────────────────────────────────


def _save_organisers(
    db: Session, activity: Activity, rows: list[OrganiserRow], confirmed: bool
) -> None:
    from app.domains.mdm.api import Person, is_member

    existing = {str(r.id): r for r in service._organiser_rows(db, activity.id)}
    had_contact = any(r.is_contact for r in existing.values())
    before = [str(r.id) for r in existing.values()]

    kept = {row.key for row in rows}
    removed = [rij for key, rij in existing.items() if key not in kept]
    for rij in removed:
        service.drop_organiser(db, rij)

    final: list[ActivityOrganiser] = []
    people = {r.person_id for key, r in existing.items() if key in kept}
    for row in rows:
        if row.key in existing:
            rij = existing[row.key]
        elif row.key.isdigit():
            raise _gone(_("Een organisator"))
        else:
            # The rules of `service.add_organiser`, in the same words.
            if row.person_id in people:
                raise ActiviteitFout(_("Die persoon staat er al bij."))
            if (
                row.person_id is None
                or db.query(Person).filter(Person.id == row.person_id).first() is None
            ):
                raise _gone(_("Die persoon"))
            if not is_member(db, row.person_id):
                raise ActiviteitFout(_("Alleen leden kunnen organisator zijn."))
            people.add(row.person_id)
            rij = ActivityOrganiser(activity_id=activity.id, person_id=row.person_id)
        # As `service.update_organiser`: an empty override means "the member's own".
        for flag in ("is_contact", "show_email", "show_mobile"):
            if getattr(rij, flag) != bool(getattr(row, flag)):
                setattr(rij, flag, bool(getattr(row, flag)))
        for name in ("email_override", "mobile_override"):
            value = (getattr(row, name) or "").strip() or None
            if getattr(rij, name) != value:
                setattr(rij, name, value)
        final.append(rij)

    if had_contact and not any(r.is_contact for r in final) and not confirmed:
        # This was a rule of the route (and only for unticking, not for removing
        # the last contact person); it is a rule of the save now.
        raise ContactConfirmation(
            _(
                "Zonder contactpersoon tonen de affiches de website, het e-mailadres en het "
                "gsm-nummer van Raak. Bevestig om door te gaan."
            )
        )

    new_rows = [rij for rij in final if rij.id is None]
    if not removed and not new_rows and [str(r.id) for r in final] == before:
        return
    # The order, in two steps inside the one transaction, as `move_organiser`: the
    # UNIQUE on (activity_id, sort_order) is checked per row, so first every row
    # to a free place above all current ones, then to its final place 0..n-1.
    db.flush()  # the removals free their places
    # Above every current place AND above every final one: with rows added, the
    # final places 0..n-1 can reach past the highest current place.
    free = max(max((r.sort_order for r in existing.values()), default=-1), len(final)) + 1
    for index, rij in enumerate(final):
        rij.sort_order = free + index
        if rij.id is None:
            db.add(rij)
    db.flush()
    for index, rij in enumerate(final):
        rij.sort_order = index


# ── Uploads ──────────────────────────────────────────────────────────────────


async def _store_files(
    db: Session,
    activity: Activity,
    fiche: FicheSave,
    component_ids: dict[str, int],
    poster: Any,
    component_files: dict[str, Any],
    background_tasks: Any,
) -> None:
    """The poster and the info attachments, stored in the open transaction. A
    refused file (its type, an empty file) refuses the save with media's words."""
    from fastapi import HTTPException

    from app.domains.media.api import (
        drop_activity_poster,
        drop_component_info,
        store_activity_poster,
        store_component_info,
    )

    try:
        if poster is not None and getattr(poster, "filename", None):
            await store_activity_poster(db, activity.id, poster, background_tasks)
        elif fiche.drop_poster:
            drop_activity_poster(db, activity.id)
        for row in fiche.components:
            component_id = component_ids.get(row.key)
            if component_id is None:
                continue
            upload = component_files.get(row.key)
            if upload is not None and getattr(upload, "filename", None):
                await store_component_info(db, component_id, upload, background_tasks)
            elif row.drop_info:
                drop_component_info(db, component_id)
    except HTTPException as exc:
        raise ActiviteitFout(upload_refusal(exc)) from exc
    except LookupError as exc:
        raise ActiviteitFout(str(exc)) from exc


def upload_refusal(exc: Exception) -> str:
    """What the screen says about a refused upload, instead of failing in silence.
    A type that is not supported — on an iPhone usually a HEIC photo — gets the
    way out with it. Takes media's `HTTPException` as well as a plain error."""
    detail = str(getattr(exc, "detail", exc))
    if "bestandstype" in detail.lower():
        return (
            detail
            + " — "
            + _("gebruik een PNG, JPG, WEBP, GIF of PDF (een iPhone-HEIC-foto werkt niet).")
        )
    return detail

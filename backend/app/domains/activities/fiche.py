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

Since #1561 a refusal names its **place** and the save names **all of them at
once** (`FicheRefusal`): a field (`slug`, `c.<key>.max_participants`), a row
(`c.<key>`, also a row the form removed) or the fiche as a whole (``""``). The
place is the address the form uses (`fiche_form`). The rules themselves stay
where they were — on the object, in the service — and are called, not copied:
the save keeps going after a refused row to hear the next one, and the
savepoint takes everything back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
    ActivityDate,
    ActivityOrganiser,
    ActivityStatus,
)
from app.kernel.refusals import FieldError, Refusals

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


class FicheRefusal(ActiviteitFout):
    """The save is refused; `errors` says why and where, all of them."""

    def __init__(self, errors: list[FieldError]) -> None:
        self.errors = list(errors)
        super().__init__(" ".join(error.message for error in self.errors))


@dataclass
class DateRow:
    """One date of the fiche. `key` is the row's id, or anything else for a new row."""

    key: str
    #: None only when the form's value was no date; the row then carries an error.
    start_date: Optional[date] = None
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
    #: False: the form did not carry the price fields (#1608: they are switched
    #: off while the product is free or paid on the spot) — the prices a product
    #: has are then left as they are.
    prices_sent: bool = True


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
    #: What the form's reader already refused (a date that is no date, an amount
    #: that is none): the save reports them together with its own.
    errors: list[FieldError] = field(default_factory=list)


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


def _errors(found: list[FieldError]) -> Refusals:
    """The refusals of one save of the fiche (`kernel.refusals`): a rule's
    `ActiviteitFout` is noted at its place; the question about the contact person
    is not a refusal and passes through, like the save's own verdict."""
    return Refusals(found, kinds=(ActiviteitFout,), passing=(ContactConfirmation, FicheRefusal))


def _changed(row: Any, values: dict) -> dict:
    """The fields of `values` that differ from the row."""
    return {name: value for name, value in values.items() if getattr(row, name) != value}


def _checked(
    errors: Refusals,
    row: str,
    kind: str,
    name: str,
    max_participants: Optional[int],
    **prices: Optional[Decimal],
) -> None:
    """The refusals that were a 500 through the row routes: an empty name passed
    (and a nameless row is unfindable), a maximum of zero or less hit the CHECK
    of the database, and a negative price failed a schema built by hand."""
    if not name.strip():
        errors.add(
            f"{row}.name",
            _("Een onderdeel heeft een naam nodig.")
            if kind == "component"
            else _("Een product heeft een naam nodig."),
        )
    if max_participants is not None and max_participants <= 0:
        errors.add(
            f"{row}.max_participants",
            _("Het maximum van “%(name)s” moet groter zijn dan nul.") % {"name": name},
        )
    for price_field, price in prices.items():
        if price is not None and price < 0:
            errors.add(
                f"{row}.{price_field}",
                _("De prijs van “%(name)s” mag niet negatief zijn.") % {"name": name},
            )


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
    return await _write(
        db,
        activity,
        fiche,
        actor=actor,
        poster=poster,
        component_files=component_files,
        background_tasks=background_tasks,
    )


#: What a new activity starts as when the board makes it on the fiche (#1649):
#: a draft — an empty fiche saved with a name must not stand on the site unseen;
#: publishing is its own act. (The JSON API creates as before.)
NEW_ACTIVITY_STATUS = ActivityStatus.DRAFT
#: The fields `service._add_activity` takes at the creation itself, so they are
#: part of the one history row "created".
_AT_CREATION = (
    "location",
    "poster_url",
    "description",
    "members_only",
    "board_notes",
    "target_audience",
)


async def create_fiche(
    db: Session,
    fiche: FicheSave,
    *,
    actor: str | None = None,
    poster: Any = None,
    component_files: dict[str, Any] | None = None,
    background_tasks: Any = None,
) -> Activity:
    """Create an activity from the fiche (#1649, CR-11 Q84): the same one save
    as `save_fiche`, on a record that does not exist yet. One transaction — the
    activity, its dates, components, products, organisers and files — and a
    refusal leaves NOTHING: the activity is added inside the save's savepoint,
    so no row, no history and no file outlives it. There is no row before
    Opslaan either: the page that asks is a form, not a record.

    The rules are the fiche's own (a name, the rules of a date, a component, a
    product), plus the one the start screen and the JSON API always asked: **a
    new activity has a first date.** The friendly URL is proposed from the name
    when the form gives none, as every creation does (#884)."""
    errors = _errors(fiche.errors)
    fields = fiche.fields
    if not fields.get("name") and not errors.touches("name"):
        errors.add("name", _("De activiteit heeft een naam nodig."))
    if not fiche.dates:
        errors.add("", _("Een nieuwe activiteit heeft een eerste datum nodig."))
    slug = fields.get("slug") or None
    if slug:
        with errors.at("slug"):
            slug = service._controleer_slug(db, slug)
    with errors.at("target_audience"):
        service._check_audience(fields.get("target_audience") or None)
    if errors.found:
        raise FicheRefusal(errors.found)

    def add() -> Activity:
        return service._add_activity(
            db,
            name=fields["name"],
            dates=(),
            actor=actor,
            slug=slug,
            action="activity_created",
            status=NEW_ACTIVITY_STATUS,
            **{name: fields.get(name) or None for name in _AT_CREATION if name != "members_only"},
            members_only=bool(fields.get("members_only")),
        )

    written = await _write(
        db,
        add,
        fiche,
        actor=actor,
        poster=poster,
        component_files=component_files,
        background_tasks=background_tasks,
        errors=errors,
    )
    assert written is not None
    return written


async def _write(
    db: Session,
    target: Any,
    fiche: FicheSave,
    *,
    actor: str | None,
    poster: Any,
    component_files: dict[str, Any] | None,
    background_tasks: Any,
    errors: Refusals | None = None,
) -> Activity:
    """The one write of the fiche. `target` is the activity, or — for a
    creation — the function that adds it, called INSIDE the savepoint."""
    # A savepoint around the whole save: a refusal — a rule, a refused file, the
    # coherence rule of a date in the flush — takes back exactly what this save
    # wrote and nothing else, and the session stays usable for the answer that
    # says why. Nothing is half written.
    savepoint = db.begin_nested()
    errors = errors if errors is not None else _errors(fiche.errors)
    try:
        if callable(target):
            activity = target()
            changed = {}
        else:
            activity = target
            changed = _changed(activity, fiche.fields)
        if changed:
            _save_fields(db, activity, changed, actor, errors)
        if "dates" in fiche.groups:
            _save_dates(db, activity, fiche.dates, actor, errors)
        component_ids: dict[str, int] = {}
        if "components" in fiche.groups:
            component_ids = _save_components(db, activity, fiche.components, actor, errors)
        if "organisers" in fiche.groups:
            _save_organisers(db, activity, fiche.organisers, fiche.confirmed_no_contact, errors)
        if errors.found:
            raise FicheRefusal(errors.found)
        with errors.at(""):
            db.flush()  # the object rules fire here once more, at the write itself (#792)
        if not errors.found:
            await _store_files(
                db,
                activity,
                fiche,
                component_ids,
                poster,
                component_files or {},
                background_tasks,
                errors,
            )
        if errors.found:
            raise FicheRefusal(errors.found)
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


def _save_fields(
    db: Session, activity: Activity, changed: dict, actor: str | None, errors: Refusals
) -> None:
    """The activity's own fields. The two rules of `apply_activity_update` each
    have their field: the friendly URL is asked first, so what is left is the
    audience's."""
    if "slug" in changed:
        with errors.at("slug"):
            service._controleer_slug(db, changed["slug"], behalve_id=activity.id)
        if errors.touches("slug"):
            return
    with errors.at("target_audience"):
        service.apply_activity_update(db, activity, changed, actor=actor)


# ── Dates ────────────────────────────────────────────────────────────────────


def _coherent(errors: Refusals, row: str, values: dict) -> None:
    """The object's own rule (`ActivityDate.validate_coherence`, #792), asked
    before the write so the refusal names its field and the flush stays whole:
    first the two dates alone — what refuses then is the end date — then with the
    hours, where it is the end hour."""
    dates_only = {**values, "start_time": None, "end_time": None}
    with errors.at(f"{row}.end_date"):
        ActivityDate(**dates_only).validate_coherence()
    if not errors.touches(row):
        with errors.at(f"{row}.end_time"):
            ActivityDate(**values).validate_coherence()


def _save_dates(
    db: Session, activity: Activity, rows: list[DateRow], actor: str | None, errors: Refusals
) -> None:
    existing = {str(d.id): d for d in activity.dates}
    kept = set()
    for row in rows:
        place = f"d.{row.key}"
        values = {name: getattr(row, name) for name in DATE_FIELDS}
        if row.key in existing:
            kept.add(row.key)
        if not errors.touches(place):
            _coherent(errors, place, values)
        if errors.touches(place):
            continue
        if row.key in existing:
            changed = _changed(existing[row.key], values)
            if changed:
                service.apply_date_update(db, existing[row.key], changed, actor=actor)
        elif row.key.isdigit():
            errors.add(place, str(_gone(_("Een datum"))))
        else:
            service.insert_date(db, activity.id, SimpleNamespace(**values), actor=actor)
    for key, ad in existing.items():
        if key not in kept:
            service.remove_date(db, ad, actor=actor)


# ── Components and their products ────────────────────────────────────────────


def _save_components(
    db: Session, activity: Activity, rows: list[ComponentRow], actor: str | None, errors: Refusals
) -> dict[str, int]:
    """Returns {row key: component id} for the components that stay, so an upload
    finds the component a new row became."""
    existing = {str(c.id): c for c in activity.sub_registrations}
    ids: dict[str, int] = {}
    # Removals first: a refusal names its component before anything is added. Its
    # place is the row the form removed, so the screen can put it back.
    kept = {row.key for row in rows}
    for key, component in existing.items():
        if key not in kept:
            with errors.at(f"c.{key}"):
                service.remove_component(db, component, actor=actor)
    for place, row in enumerate(rows):
        at = f"c.{row.key}"
        _checked(errors, at, "component", row.name, row.max_participants)
        for product in row.products:
            _checked(
                errors,
                f"p.{product.key}",
                "product",
                product.name,
                product.max_participants,
                price=product.price,
                member_price=product.member_price,
            )
        if row.key not in existing and row.key.isdigit():
            errors.add(at, str(_gone(_("Een onderdeel"))))
        if errors.touches(at):
            continue
        values: dict[str, Any] = {name: getattr(row, name) for name in COMPONENT_FIELDS}
        values["name"] = row.name.strip()
        if row.links is not None:
            values.update({name: row.links.get(name) for name in COMPONENT_LINKS})
        if row.key in existing:
            component = existing[row.key]
            changed = _changed(component, values)
            if changed:
                # The one rule of this update is the question form's.
                with errors.at(f"{at}.form_id"):
                    service.apply_component_update(db, component, changed, actor=actor)
            products = {str(p.id): p for p in component.products}
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
                with errors.at(f"{at}.form_id"):
                    service._check_questions(db, component, form_id)
                    component.form_id = form_id
            products = {}
        if component.sort_order != place:
            component.sort_order = place  # a reorder writes no history, as before
        ids[row.key] = component.id
        _save_products(db, component, products, row.products, actor, errors)
    return ids


def _save_products(
    db: Session,
    component: Any,
    existing: dict,
    rows: list[ProductRow],
    actor: str | None,
    errors: Refusals,
) -> None:
    kept = {row.key for row in rows}
    for key, product in existing.items():
        if key not in kept:
            with errors.at(f"p.{key}"):
                service.remove_product(db, product, actor=actor)
    for place, row in enumerate(rows):
        at = f"p.{row.key}"
        if row.key not in existing and row.key.isdigit():
            errors.add(at, str(_gone(_("Een product"))))
        if errors.touches(at):
            continue
        values = {name: getattr(row, name) for name in PRODUCT_FIELDS}
        values["name"] = row.name.strip()
        if not row.prices_sent and row.key in existing:
            del values["price"], values["member_price"]
        # The one rule of a product's write: free and pay-on-site exclude each other.
        with errors.at(f"{at}.pay_on_site"):
            if row.key in existing:
                product = existing[row.key]
                changed = _changed(product, values)
                if changed:
                    service.apply_product_update(db, product, changed, actor=actor)
            else:
                product = service.new_product(
                    component.id, SimpleNamespace(**values, sort_order=place)
                )
                service._insert_product(db, product, actor=actor, action="product_created")
            if product.sort_order != place:
                product.sort_order = place


# ── Organisers ───────────────────────────────────────────────────────────────


def _save_organisers(
    db: Session,
    activity: Activity,
    rows: list[OrganiserRow],
    confirmed: bool,
    errors: Refusals,
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
        at = f"o.{row.key}"
        if errors.touches(at):
            continue
        if row.key in existing:
            rij = existing[row.key]
        elif row.key.isdigit():
            errors.add(at, str(_gone(_("Een organisator"))))
            continue
        else:
            # The rules of `service.add_organiser`, in the same words.
            if row.person_id in people:
                errors.add(at, _("Die persoon staat er al bij."))
                continue
            if (
                row.person_id is None
                or db.query(Person).filter(Person.id == row.person_id).first() is None
            ):
                errors.add(at, str(_gone(_("Die persoon"))))
                continue
            if not is_member(db, row.person_id):
                errors.add(at, _("Alleen leden kunnen organisator zijn."))
                continue
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

    if errors.found:
        return  # refused already; the question below is for a save that would go through
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
    errors: Refusals,
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

    @contextmanager
    def stored(place: str) -> Iterator[None]:
        try:
            yield
        except HTTPException as exc:
            errors.add(place, upload_refusal(exc))
        except LookupError as exc:
            errors.add(place, str(exc))

    with stored("file"):
        if poster is not None and getattr(poster, "filename", None):
            await store_activity_poster(db, activity.id, poster, background_tasks)
        elif fiche.drop_poster:
            drop_activity_poster(db, activity.id)
    for row in fiche.components:
        component_id = component_ids.get(row.key)
        if component_id is None:
            continue
        with stored(f"c.{row.key}.file"):
            upload = component_files.get(row.key)
            if upload is not None and getattr(upload, "filename", None):
                await store_component_info(db, component_id, upload, background_tasks)
            elif row.drop_info:
                drop_component_info(db, component_id)


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

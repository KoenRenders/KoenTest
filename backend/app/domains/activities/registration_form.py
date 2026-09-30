"""The registration form, once, for the public and for the board (#1284).

The saving was already one (`router.create_registration`). The screen was not:
the board's "add a registration" page rebuilt the public form's fields, its
context and its processing by hand, and so it showed no prices, no total, no
member price, and offered no online payment (#1192 → #1284). Koen, 28 September
2026: the board's form is the public one, "met uitzondering van de
terugroutering en de producten die enkel in de backoffice zichtbaar zijn".

So this module is the one form: one context builder, one total, one processing
of a submitted form. A `Channel` carries what differs, and nothing else does:

| | public | board |
|---|---|---|
| who registers (member price, `person_id`) | the signed-in person | the person of the **typed** e-mail address |
| which products | publicly bookable | also the back-office-only ones, badged |
| after a free or transfer registration | the confirmation fragment | the registration in the back office |
| after Mollie | the public return page | the registration in the back office |

**The public way never looks up the typed address.** Doing so would give anyone
the member price by typing a member's address; its person comes from the
session. The board's does, because the board member is not the one registering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from sqlalchemy.orm import Session

from app.domains.activities.service import publicly_bookable_products
from app.domains.activities.totals import has_payable_products, quote_lines
from app.kernel.codes import TechnicalEnum

if TYPE_CHECKING:  # #1305
    from fastapi import BackgroundTasks

    from app.domains.activities.models import Activity, ActivityProduct, ActivitySubRegistration
    from app.domains.mdm.api import Person


@dataclass(frozen=True)
class Channel:
    """What differs between the public form and the board's — and only that."""

    #: The board's channel: back-office-only products, the back office after saving.
    backoffice: bool
    #: Who registers: prices the form and becomes the registration's `person_id`.
    person: Any
    #: Where the form posts, and where it asks for a recalculated total.
    form_url: str
    total_url: str
    #: Where the price block (rows and total) is refreshed when the e-mail
    #: address changes — the board's member price follows the typed address
    #: (#1284, Koen: "ja"). None on the public form: it prices by the session.
    prices_url: str | None = None


def public_channel(
    db: Session, activity: Activity, component: ActivitySubRegistration, session_email: str
) -> Channel:
    from app.domains.auth.api import login_person_for_email

    base = f"/activiteiten/{activity.id}/inschrijven/{component.id}"
    return Channel(
        backoffice=False,
        person=login_person_for_email(db, session_email) if session_email else None,
        form_url=base,
        total_url=f"{base}/totaal",
    )


def board_channel(
    db: Session, activity: Activity, component: ActivitySubRegistration, typed_email: str
) -> Channel:
    from app.domains.auth.api import login_person_for_email

    typed = (typed_email or "").strip()
    base = f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw"
    return Channel(
        backoffice=True,
        person=login_person_for_email(db, typed) if "@" in typed else None,
        form_url=base,
        total_url=f"{base}/totaal",
        prices_url=f"{base}/prijzen",
    )


def is_member(person: Person | None) -> bool:
    """Is this person a member today? Decides the member price on the screen.

    "Today" is right here: the form shows what you would pay now.
    `compute_registration_total` prices by the registration date after saving,
    so the price is fixed from then on (#635 point 1).
    """
    from app.domains.membership.api import has_valid_membership

    return has_valid_membership(person)


def contact_refusal(values: Mapping[str, Any]) -> str | None:
    """Why a registration form's contact fields are refused, or None (#1192).

    The same three fields on every way in — Koen: "bestuur moet dezelfde velden
    invullen". The registration itself repeats name and phone (its validators,
    CR-13 phase 1) and the schema the e-mail address; this is the screen's own, friendlier,
    refusal before either is reached.
    """
    naam = (values.get("contact_name") or "").strip()
    email = (values.get("contact_email") or "").strip()
    gsm = (values.get("phone") or "").strip()
    if not naam or "@" not in email or not gsm:
        return "Vul naam, e-mailadres en mobiel nummer in."
    return None


def form_quantities(form: Mapping[str, Any]) -> dict[int, int]:
    out: dict[int, int] = {}
    for key, value in form.items():
        if key.startswith("product_"):
            try:
                out[int(key.removeprefix("product_"))] = max(0, int(value or 0))
            except ValueError:
                continue
    return out


def opening_quantity(products: Iterable[ActivityProduct]) -> int:
    """The quantity the form OPENS with (#1172): 1 with exactly one product.

    With several, prefilling would choose for the visitor. Never above the
    maximum — today a safety net, since `ck_activity_products_max_participants_positive`
    (migration 040) already keeps a maximum of 0 out of the database. Takes the
    PRODUCT LIST the form shows, not the component (#1191): one active product
    next to one inactive one is "one" on the public form.
    """
    products = list(products or [])
    if len(products) != 1:
        return 0
    maximum = products[0].max_participants
    if maximum is not None and maximum < 1:
        return 0
    return 1


def form_products(component: ActivitySubRegistration, channel: Channel) -> list:
    """The products the form shows: publicly bookable, or all of them for the board."""
    if channel.backoffice:
        return list(component.products)
    return publicly_bookable_products(component)


def form_context(
    channel: Channel,
    activity: Activity,
    component: ActivitySubRegistration,
    *,
    values: dict | None = None,
    quantities: dict[int, int] | None = None,
    error: str | None = None,
) -> dict:
    """The one context of the form's fields, for either channel.

    Rows, opening quantity and total come from one product list, through
    `quote_lines` — the same function as the recalculation and the saving
    (§19.3): a second way of pricing here is exactly the drift that path exists
    to prevent.
    """
    products = form_products(component, channel)
    member = is_member(channel.person)
    opening = opening_quantity(products)
    if quantities is None:
        quantities = {p.id: opening for p in products}
    total, _lines = quote_lines(component, quantities, member)
    values = values or {}
    return {
        **questions_context(component, values),
        "activity": activity,
        "component": component,
        "is_member": member,
        "person": channel.person,
        "error": error,
        "totaal": total,
        "values": values,
        "heeft_prijs": has_payable_products(component, member),
        "standaard_aantal": opening,
        "producten": products,
        "form_url": channel.form_url,
        "totaal_url": channel.total_url,
        "prijzen_url": channel.prices_url,
    }


def questions_context(component: ActivitySubRegistration, values: Mapping[str, Any]) -> dict:
    """The component's questions on the page (CR-14 §B4.8): the fields, rendered by
    the form builder's own partial, behind one choice — "nu" (the default, on both
    pages) or "later, via de link in de bevestigingsmail". `vraag_fout` marks the
    question a refusal names."""
    from sqlalchemy.orm import object_session

    from app.domains.activities.service import question_form

    # A soft reference (#396), read through `forms.api`: a form deleted in the
    # builder is None, and then the component asks nothing.
    form = question_form(object_session(component), component)
    return {
        **question_block_context(form),
        "vragen_nu": values.get("questions", "now") != "later",
        "vraag_fout": None,
    }


def question_block_context(form: Any) -> dict:
    """What the form's own question block needs (#1380, `_formulier_vragen.html`):
    the form (its title and description), its sections with their fields, and the
    fields in no section — grouped by `forms.api.question_groups`, as the form's own
    page groups them. `vragen` is every question in order, empty when the component
    asks none. For the registration page, the answer link and the detail alike."""
    from app.domains.forms.api import question_groups

    grouped, loose = question_groups(form) if form is not None else ([], [])
    return {
        "vraagformulier": form,
        "vraag_groepen": grouped,
        "vraag_los": loose,
        "vragen": [f for g in grouped for f in g["fields"]] + list(loose),
    }


def form_values(form: Mapping[str, Any]) -> dict:
    """The posted form as the page shows it again: a checkbox question keeps all its
    ticks (a list), every other field its one value."""
    getlist = getattr(form, "getlist", None)
    out: dict = {}
    for key in form.keys():
        many = getlist(key) if getlist is not None else [form[key]]
        if len(many) > 1:
            out[key] = [v for v in many if isinstance(v, str)]
        else:
            value = form.get(key)
            out[key] = value if isinstance(value, str) else ""
    return out


def total_context(
    channel: Channel, component: ActivitySubRegistration, form: Mapping[str, Any]
) -> dict:
    """What `_inschrijf_totaal.html` needs after a change (§19.3 — no drift)."""
    member = is_member(channel.person)
    total, _lines = quote_lines(component, form_quantities(form), member)
    return {
        "totaal": total,
        "is_member": member,
        "heeft_prijs": has_payable_products(component, member),
    }


class OutcomeKind(TechnicalEnum):
    """What a submitted form came to. `TechnicalEnum` (CR-12 §B4.9): the two
    screens branch on it; it is never stored and never shown."""

    REFUSED = "refused"
    CHECKOUT = "checkout"
    DONE = "done"


@dataclass
class Outcome:
    """What one submitted form came to. Each channel only decides how to show it."""

    kind: OutcomeKind
    #: The form again, with the refusal in it (`REFUSED`).
    context: dict = field(default_factory=dict)
    #: Mollie's page (`CHECKOUT`); empty otherwise.
    checkout_url: str = ""
    registration_id: int | None = None
    name: str = ""


def submit(
    db: Session,
    channel: Channel,
    activity: Activity,
    component: ActivitySubRegistration,
    form: Mapping[str, Any],
    background_tasks: BackgroundTasks,
    *,
    actor: str = "",
) -> Outcome:
    """Process one submitted form — the same steps for both channels.

    `actor` is the board member's address, for the audit trail; the public way
    records the signed-in person as it always did (`register_for_activity`).
    """
    from fastapi import HTTPException
    from pydantic import ValidationError

    from app.domains.mdm.api import PaymentMethod
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    values = form_values(form)
    quantities = form_quantities(form)
    ctx = form_context(channel, activity, component, values=values, quantities=quantities)

    def refused(message: str) -> Outcome:
        ctx["error"] = message
        return Outcome(kind=OutcomeKind.REFUSED, context=ctx)

    refusal = contact_refusal(values)
    if refusal:
        return refused(refusal)
    # #1191: the rows on screen, not `component.products`: with every product of a
    # component hidden there is no row, and this requirement could not be met.
    if ctx["producten"] and not any(q > 0 for q in quantities.values()):
        return refused("Selecteer minstens één product.")

    name = values.get("contact_name", "").strip()
    # CR-14 §B4.3: the questions post `f<field id>` keys, parsed by the form
    # builder's own parser. "Later" posts no answers at all: None, and the
    # registration gets the answer link.
    answers = None
    from app.domains.activities.service import question_form

    questions = question_form(db, component)
    if questions is not None and ctx["vragen_nu"]:
        from app.domains.forms.api import answers_from_form

        answers = answers_from_form(questions, form)
    try:
        data = RegistrationCreate(
            contact_name=name,
            contact_email=values.get("contact_email", "").strip(),
            phone=values.get("phone", "").strip(),
            team_name=(values.get("team_name") or "").strip() or None,
            payment_method=(
                (values.get("payment_method") or PaymentMethod.ONLINE.value)
                if ctx["totaal"] > 0
                else None
            ),
            component_id=component.id,
            items=[
                RegistrationItemCreate(product_id=pid, quantity=qty)
                for pid, qty in quantities.items()
                if qty > 0
            ],
            remarks=(values.get("remarks") or "").strip() or None,
            answers=answers,
        )
    except ValidationError:
        # `contact_refusal` checked that there is an address; the schema checks
        # that it IS one.
        return refused("Dat e-mailadres is niet geldig.")

    from app.domains.activities.api import board_register_for_activity, register_for_activity

    try:
        if channel.backoffice:
            person_id = channel.person.id if channel.person is not None else None
            result = board_register_for_activity(
                db, activity.id, data, background_tasks, actor=actor, person_id=person_id
            )
        else:
            result = register_for_activity(
                db, activity.id, data, background_tasks, current_member=channel.person
            )
    except HTTPException as exc:
        # A refused answer names its question (`VeldFout`): mark it on the page.
        ctx["vraag_fout"] = getattr(exc, "veld_id", None)
        return refused(str(exc.detail))

    registration_id = result.get("id")
    checkout_url = result.get("checkout_url") or ""
    if checkout_url:
        return Outcome(
            kind=OutcomeKind.CHECKOUT,
            checkout_url=checkout_url,
            registration_id=registration_id,
            name=name,
        )
    return Outcome(kind=OutcomeKind.DONE, registration_id=registration_id, name=name)

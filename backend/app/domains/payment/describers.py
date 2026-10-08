"""What a payment is for, told by the domain that owns it (CR-21 Q48, #1748).

A payment record points at its payable with `(payable_type, payable_id)` and no foreign
key: the ledger serves several domains and depends on none. Until CR-21 phase 0
`payment` nevertheless knew what a registration and a membership look like — it
branched on the type at every place that names a payment: the payments screen, its
filter, its export, the jump links on a booking's page, the subject of a change line.
A third payable (the webshop's order) would have been a third branch at each.

So the rule: **`payment` never branches on a payable type to describe it.** A domain
that becomes payable registers a `Describer` for its type, and every screen, export and
audit line asks here. The registration happens in `app/main.py`, beside the event
subscribers — a script that calls into `payment` without importing the app gets a clear
error from `describer()`, not an empty name.

Batch by design: `describe(db, ids)` answers for many payables at once, so the payments
list stays one round of queries per type, not one per row.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.orm import Session

from app.domains.payment.models import PayableType


@dataclass(frozen=True)
class PayableDescription:
    """One payable, in the words and links a payment needs. Everything is optional: a
    payable that no longer exists is described by what is left of it."""

    #: Who it concerns — the registrant, the head of the household.
    contact_name: Optional[str] = None
    #: What it is — the activity's name, "Lidmaatschap 2026".
    description: Optional[str] = None
    #: The back-office page of what the payable hangs on (an activity, a household);
    #: `payment` adds the way back (`?terug=`).
    context_href: Optional[str] = None
    #: The payable's own back-office page and what the link says — filled in by
    #: `describe_many` from the type's `Describer`, also for a payable that is gone.
    payable_href: Optional[str] = None
    payable_label: Optional[str] = None
    #: Its place in the filter tree of the payments screen: the value of `context`
    #: that selects it ("comp-12", "year-2026").
    filter_context: Optional[str] = None
    #: The first column of the export ("who — what").
    export_label: Optional[str] = None
    #: The household and the person behind it, for a change line's subject.
    household_id: Optional[int] = None
    person_id: Optional[int] = None
    contact_email: Optional[str] = None
    #: The fields of `EnrichedPaymentRecord` this payable fills besides the two names
    #: (`component_id`, `component_name`, `membership_year`, `items`): the screen's
    #: record carries them as it did.
    record_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Describer:
    """How one payable type describes itself."""

    #: Many payables at once: `{payable_id: PayableDescription}`. An id it does not
    #: return is described by `unknown()`.
    describe: Callable[[Session, Iterable[int]], dict[int, PayableDescription]]
    #: The ids of this type that belong to a household (the household's payments tab).
    of_household: Callable[[Session, int], Iterable[int]]
    #: The export's second column, "Soort".
    export_kind: str
    #: The payable's own back-office page, by id, and what the link to it says
    #: ("Inschrijving"); None for a type that has no page of its own.
    payable_page: Optional[Callable[[int], str]] = None
    payable_label: Optional[str] = None
    #: The filter tree: the `context` that selects every payable of this type (""
    #: when the tree has no such entry), and the prefix of the contexts that select
    #: some of them ("year-", "comp-").
    filter_group: str = ""
    filter_prefix: str = ""


_describers: dict[PayableType, Describer] = {}


def register_describer(payable_type: PayableType, describer: Describer) -> None:
    """Register the describer of a payable type. Called once, from `app/main.py`."""
    _describers[PayableType(payable_type)] = describer


def registered_describers() -> dict[PayableType, Describer]:
    return dict(_describers)


def describer(payable_type: PayableType | str) -> Describer:
    key = PayableType(payable_type)
    try:
        return _describers[key]
    except KeyError:
        raise LookupError(
            f"no describer registered for payable type {key.value!r} — describe a payable "
            "through its describer (CR-21 Q48); they are registered in app/main.py"
        ) from None


def unknown(payable_type: PayableType | str, payable_id: int) -> PayableDescription:
    """A payable its owner no longer knows: named by its type and id in the export."""
    return PayableDescription(export_label=f"{PayableType(payable_type).value} #{payable_id}")


def describe_many(
    db: Session, payables: Iterable[tuple[PayableType | str, int]]
) -> dict[tuple[PayableType, int], PayableDescription]:
    """Describe every `(type, id)` pair — one call to each type's describer."""
    by_type: dict[PayableType, set[int]] = {}
    for payable_type, payable_id in payables:
        by_type.setdefault(PayableType(payable_type), set()).add(payable_id)
    found: dict[tuple[PayableType, int], PayableDescription] = {}
    for payable_type, ids in by_type.items():
        one = describer(payable_type)
        described = one.describe(db, ids)
        for payable_id in ids:
            what = described.get(payable_id) or unknown(payable_type, payable_id)
            if one.payable_page is not None:
                what = replace(
                    what, payable_href=one.payable_page(payable_id), payable_label=one.payable_label
                )
            found[(payable_type, payable_id)] = what
    return found


def describe_one(
    db: Session, payable_type: PayableType | str, payable_id: int
) -> PayableDescription:
    return describe_many(db, [(payable_type, payable_id)])[(PayableType(payable_type), payable_id)]


def payables_of_household(db: Session, household_id: int) -> set[tuple[PayableType, int]]:
    """Every payable of a household, over all types."""
    return {
        (payable_type, payable_id)
        for payable_type, one in _describers.items()
        for payable_id in one.of_household(db, household_id)
    }


def in_filter_context(
    payable_type: PayableType | str, filter_context: Optional[str], context: str
) -> bool:
    """Does a payable with this place in the filter tree belong under `context`?

    A context that is no describer's group or prefix selects nothing in particular
    ("all"), so it lets every payable through.
    """
    key = PayableType(payable_type)
    for one_type, one in _describers.items():
        if one.filter_group and context == one.filter_group and key is not one_type:
            return False
        if one.filter_prefix and context.startswith(one.filter_prefix):
            if key is not one_type or filter_context != context:
                return False
    return True

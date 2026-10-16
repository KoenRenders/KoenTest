"""The history of an activity: the snapshots that write a row of this domain's
history tables (`docs/architecture.md` §5.8 — a history table per component,
written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). A helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.

#1885: what is logged is declared here, beside the history models, and the
row is written by the one snapshot (`kernel.logged.snapshot`) — every column of
the object but the technical moments. The registration's two secrets are not
logged (Koen, 16 October 2026, "3a, de sleutel moet niet in wijzigingen terecht
komen"): whoever reads Wijzigingen must not be able to answer for somebody else.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityDateHistory,
    ActivityHistory,
    ActivityProduct,
    ActivitySubRegistration,
    ComponentHistory,
    ProductHistory,
    Registration,
    RegistrationHistory,
    RegistrationItem,
    RegistrationItemHistory,
)
from app.kernel.logged import declare, snapshot

declare(Activity, ActivityHistory, key="activity_id")
declare(ActivityDate, ActivityDateHistory, key="activity_date_id")
_ORDER = (
    "its place in the list of the activity's record: a reorder writes no hi"
    "story (#1559), the order is the record's, not a fact of the row"
)
declare(
    ActivitySubRegistration,
    ComponentHistory,
    key="component_id",
    not_logged={"sort_order": _ORDER},
)
declare(ActivityProduct, ProductHistory, key="product_id", not_logged={"sort_order": _ORDER})
declare(RegistrationItem, RegistrationItemHistory, key="registration_item_id")
declare(
    Registration,
    RegistrationHistory,
    key="registration_id",
    not_logged={
        "answer_token": "a secret: the link that answers for this registration (Koen, "
        "16 October 2026, 3a)",
        "submission_key": "a secret: the random part of the form's token it came from "
        "(#1987), of the same kind as the answer link's",
    },
)


def snapshot_registration_item(
    db: Session,
    item: RegistrationItem,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    snapshot(
        db,
        item,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=RegistrationItem,
    )


def snapshot_activity(
    db: Session,
    activity: Activity,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    snapshot(
        db, activity, operation=operation, action=action, source=source, actor=actor, model=Activity
    )


def snapshot_activity_date(
    db: Session,
    ad: ActivityDate,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    snapshot(
        db, ad, operation=operation, action=action, source=source, actor=actor, model=ActivityDate
    )


def snapshot_component(
    db: Session,
    comp: ActivitySubRegistration,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    snapshot(
        db,
        comp,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=ActivitySubRegistration,
    )


def snapshot_product(
    db: Session,
    product: ActivityProduct,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    snapshot(
        db,
        product,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=ActivityProduct,
    )

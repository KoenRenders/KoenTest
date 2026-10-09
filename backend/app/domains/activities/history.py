"""The history of an activity: the snapshots that write a row of this domain's
history tables (`docs/architecture.md` §5.8 — a history table per component,
written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). A helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.
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
    RegistrationItem,
    RegistrationItemHistory,
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
    db.add(
        RegistrationItemHistory(
            registration_item_id=item.id,
            registration_id=item.registration_id,
            product_id=item.product_id,
            quantity=item.quantity,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
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
    db.add(
        ActivityHistory(
            activity_id=activity.id,
            name=activity.name,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
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
    db.add(
        ActivityDateHistory(
            activity_date_id=ad.id,
            activity_id=ad.activity_id,
            start_date=ad.start_date,
            end_date=ad.end_date,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
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
    db.add(
        ComponentHistory(
            component_id=comp.id,
            activity_id=comp.activity_id,
            name=comp.name,
            price=comp.price,
            member_price=comp.member_price,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
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
    db.add(
        ProductHistory(
            product_id=product.id,
            component_id=product.component_id,
            name=product.name,
            price=product.price,
            member_price=product.member_price,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )

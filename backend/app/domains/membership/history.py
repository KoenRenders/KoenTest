"""The history of a membership: the snapshots that write a row of this domain's
history tables (`docs/architecture.md` §5.8 — a history table per component,
written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). A helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.membership.models import MembershipHistory


def snapshot_membership(
    db: Session,
    membership,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    db.add(
        MembershipHistory(
            membership_id=membership.id,
            member_id=membership.member_id,
            year=membership.year,
            is_active=membership.is_active,
            valid_from=membership.valid_from,
            valid_to=membership.valid_to,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )

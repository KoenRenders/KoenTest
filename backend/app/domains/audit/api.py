"""Publieke facade van het audit-domein (#444, §6).

Snapshot-helpers voor de append-only history-tabellen. Andere domeinen en de
(krimpende) oude wereld importeren ALLEEN dit bestand.
"""
from app.domains.audit.service import (
    snapshot_activity,
    snapshot_activity_date,
    snapshot_address,
    snapshot_component,
    snapshot_contact_detail,
    snapshot_member,
    snapshot_member_person,
    snapshot_membership,
    snapshot_payment_record,
    snapshot_person,
    snapshot_product,
    snapshot_registration_item,
)

__all__ = [
    "snapshot_activity", "snapshot_activity_date", "snapshot_address",
    "snapshot_component", "snapshot_contact_detail", "snapshot_member",
    "snapshot_member_person", "snapshot_membership", "snapshot_payment_record",
    "snapshot_person", "snapshot_product", "snapshot_registration_item",
]

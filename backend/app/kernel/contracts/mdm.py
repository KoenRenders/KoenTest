"""Events die het MDM-component publiceert (contract, zie mdm/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class EntityMerged(KernelEvent):
    """Twee masterdata-entiteiten zijn samengevoegd (synchroon, in-transactie).
    Consumenten die id's cachen kunnen hun verwijzing omleggen; soft-refs die
    via ``mdm.api.resolve()`` lezen hoeven niets te doen."""

    entity_type: str  # bv. "person"
    source_id: int  # de opgeslokte entiteit (blijft bestaan, superseded)
    target_id: int  # de overlever


@dataclass(frozen=True)
class TenantCreated(KernelEvent):
    """A tenant was created (CR-19, #1478). Published by `create_tenant` in
    its transaction, after the organisation and its modules are flushed. `cms`
    subscribes and seeds the two site blocks a new site starts with; a
    subscriber that raises undoes the creation."""

    tenant_id: int
    name: str

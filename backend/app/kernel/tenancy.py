"""Tenant-context + mixin (§7). Adoptie gebeurt bewust per component (fase 5),
nooit "dark" — maar de mixin is vanaf dag één RLS-klaar: NOT NULL + index."""
from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_mixin

# Actieve tenant voor dit request (gezet door de resolutie-middleware in fase 5:
# hostname -> pad-prefix). None = single-tenant-gedrag (huidige toestand).
current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


@declarative_mixin
class TenantMixin:
    """Rij-niveau tenancy: elke tenant-tabel draagt een verplichte, geïndexeerde
    ``tenant_id`` (RLS aanzetten wordt zo later een migratieregel, geen verbouwing)."""

    tenant_id = Column(Integer, nullable=False, index=True)

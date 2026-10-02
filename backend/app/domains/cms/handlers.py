"""What the CMS does when another domain says something happened (CR-13 §B4.9).

Registered by importing this module in `main.py`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.kernel.contracts.mdm import TenantCreated
from app.kernel.events import subscribe


@subscribe(TenantCreated)
def seed_blocks_of_new_tenant(event: TenantCreated, db: Session) -> None:
    """A new tenant's site starts with a home intro and a footer (#1478)."""
    from app.domains.cms.service import seed_site_blocks

    seed_site_blocks(db, event.tenant_id, event.name)

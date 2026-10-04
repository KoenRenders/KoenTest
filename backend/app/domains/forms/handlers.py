"""What forms does when another domain says something happened (CR-13 §B4.9).

Registered by importing this module in `main.py` (and in a script that creates
tenants outside the app, such as `seed_e2e.py` — #1492).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.kernel.contracts.mdm import TenantCreated
from app.kernel.events import subscribe


@subscribe(TenantCreated)
def seed_contact_form_of_new_tenant(event: TenantCreated, db: Session) -> None:
    """A new tenant starts with a contact form, as the first one did (#1509)."""
    from app.domains.forms.service import seed_contact_form

    seed_contact_form(db, event.tenant_id)

"""Give every tenant its contact form and the task it starts (#1509).

A new tenant gets both when it is created (the forms and workflow handlers on
`TenantCreated`). A tenant created before that — raakvoorbeeldafdeling on PROD,
every tenant made through the editor since the tenancy — had a "Contacteer ons"
that led nowhere: the `berichten` form and the `bericht` definition were seeded
once, by migrations 073 and 082, for the first tenant only.

This fills that gap at every start of the backend, next to the other startup
seeds, through the domains' facades and never as SQL. Idempotent: a tenant that
has the form and the definition is left as it is, so a second start changes
nothing. Not in the migration that made both keys per tenant: a migration that
imports service code breaks on a fresh database once that code changes.

One consequence, chosen: a tenant that deleted its contact form gets it back at
the next start. A site without contact switches the forms module off instead.

#1567: the platform too. This seed walked the UNITs only — written when the
platform "had no site of an association" — so the platform, a PLATFORM
organisation, was the one tenant left without a form on every environment. It
is a tenant with the modules Forms and Workflow since #1523, with its own home
and its own Werkbank, so it takes a message like any other. The list is the one
/admin/tenants manages: the platform first, then the units.
"""

from app.database import SessionLocal
from app.domains.registry import load_all_models

load_all_models()


def seed_contact_forms(db) -> list[str]:
    """Seed what each tenant lacks; the lines of what was added, one per tenant.

    Every tenant /admin/tenants manages: the platform and every UNIT (#1567).
    One transaction: either every tenant is filled in, or none.
    """
    from app.domains.forms.api import seed_contact_form
    from app.domains.mdm.api import list_manageable_tenants
    from app.domains.workflow.api import seed_message_workflow

    added = []
    for unit in list_manageable_tenants(db):
        parts = []
        if seed_contact_form(db, unit.id):
            parts.append("contactformulier")
        if seed_message_workflow(db, unit.id):
            parts.append("werkbankdefinitie")
        if parts:
            added.append(f"{unit.code}: {' + '.join(parts)}")
    db.commit()
    return added


if __name__ == "__main__":
    db = SessionLocal()
    try:
        lines = seed_contact_forms(db)
    finally:
        db.close()
    print("  " + ("; ".join(lines) if lines else "elke tenant heeft zijn contactformulier al"))

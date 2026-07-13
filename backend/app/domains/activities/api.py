"""Publieke facade van het activities-component (fase 4a, #402).

Activiteiten, onderdelen, producten en registraties (3-level, alle
reg_form_types). De totaalberekening (`compute_registration_total`) leeft
uitsluitend hier — server-side, één plek (§19.3).
"""
# Volgorde bewust: eerst de modellen binden, dan pas de services — zo kan een
# component dat middenin deze import (indirect) terugverwijst de modelnamen al
# vinden (zelfde patroon als payment.api).
from app.domains.activities.models import (  # noqa: F401
    Activity,
    ActivityDate,
    ActivityDateHistory,
    ActivityHistory,
    ActivityProduct,
    ActivitySubRegistration,
    ComponentHistory,
    ProductHistory,
    Registration,
    RegistrationItem,
    RegistrationItemHistory,
)
from app.domains.activities.totals import compute_registration_total  # noqa: F401


def list_activities(db, scope: str = "upcoming"):
    """Publieke activiteitenlijst (upcoming/archived/all) — facade-doorgang
    voor andere componenten (o.a. de homepage, #405)."""
    from app.domains.activities.router import list_activities as _impl

    return _impl(scope=scope, db=db)
from app.domains.activities.export import build_component_export_ods  # noqa: F401

__all__ = [
    "Activity", "ActivityDate", "ActivityDateHistory", "ActivityHistory",
    "ActivityProduct", "ActivitySubRegistration", "ComponentHistory",
    "ProductHistory", "Registration", "RegistrationItem",
    "RegistrationItemHistory", "build_component_export_ods", "compute_registration_total",
    "list_activities",
]

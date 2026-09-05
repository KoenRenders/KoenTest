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
    RegistrationHistory,
    RegistrationItemHistory,
)
from app.domains.activities.totals import compute_registration_total  # noqa: F401


# ── Facade-doorgangen naar de registratieflow ────────────────────────────────
# De implementatie van deze drie blijft in `router.py`. Dat is een bewuste keuze:
# #635 noemt `inschrijf_submit → register_for_activity` expliciet als voorbeeld
# van hoe het hóórt ("niet aanraken") — het scherm doet niets zelf, het roept één
# domeinbewerking aan. Wat wél moest veranderen is de weg ernaartoe: een
# UI-module importeert uit een domein enkel `api.py`, nooit rechtstreeks de
# router. Vandaar deze doorgangen, met `db` vooraan zoals elders in de service.

def list_activities(db, scope: str = "upcoming"):
    """Publieke activiteitenlijst (upcoming/archived/all) — facade-doorgang
    voor andere componenten (o.a. de homepage, #405)."""
    from app.domains.activities.router import list_activities as _impl

    return _impl(scope=scope, db=db)


def public_registrations(db, activity_id: int, component_id: int):
    """De deelnemers van één onderdeel, zoals de publieke kaart ze toont (#451)."""
    from app.domains.activities.router import get_public_registrations as _impl

    return _impl(activity_id, component_id=component_id, db=db)


def register_for_activity(db, activity_id: int, data, background_tasks,
                          current_member=None):
    """De inschrijfflow: volzet-controle, regelitems, totaal, betaalrecord en
    bevestigingsmail. Eén domeinbewerking; het scherm vult alleen het formulier in."""
    from app.domains.activities.router import register_for_activity as _impl

    return _impl(activity_id, data, background_tasks, db=db,
                 current_member=current_member)
from app.domains.activities.export import build_component_export_ods  # noqa: F401

from app.domains.activities.service import (  # noqa: F401
    get_activity,
    get_component,
    get_registration,
)

__all__ = [
    "get_activity", "get_component", "get_registration",
    "Activity", "ActivityDate", "ActivityDateHistory", "ActivityHistory",
    "ActivityProduct", "ActivitySubRegistration", "ComponentHistory",
    "ProductHistory", "Registration", "RegistrationItem",
    "RegistrationHistory", "RegistrationItemHistory", "build_component_export_ods", "compute_registration_total",
    "list_activities", "public_registrations", "register_for_activity",
]

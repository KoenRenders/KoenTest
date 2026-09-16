"""Publieke facade van het MDM-component (fase 2, #400).

Masterdata (personen, gezinnen, adressen, contactgegevens, postcodes,
organisaties, codes) wordt buiten dit component uitsluitend via deze module
aangesproken. Soft-ref-patroon (§6): consumenten bewaren waarde-id's
(bv. ``person_id`` als integer, zonder FK) en lezen via ``resolve()``.
"""
from app.domains.mdm.models import (  # noqa: F401
    Address,
    AddressHistory,
    BankAccount,
    ContactDetail,
    ContactDetailHistory,
    ContactTypeCode,
    ExternalNumber,
    GenderCode,
    IdentificationScheme,
    IdentificationSchemeLabel,
    Member,
    MemberHistory,
    MemberPerson,
    MemberPersonHistory,
    Organization,
    OrganizationIdentification,
    OrganizationPerson,
    OrganizationRelationType,
    OrganizationRelationTypeLabel,
    Person,
    PersonHistory,
    PostalCode,
    RelationTypeCode,
)
# ── Doorgangen naar de ledenimport ───────────────────────────────────────────
# De implementatie blijft in `import_router.py` (het is één domeinbewerking die
# het scherm alleen aanroept); de weg ernaartoe loopt via de facade (#635 I).

async def import_preview(db, file, admin=None):
    from app.domains.mdm.import_router import preview as _impl

    return await _impl(file=file, db=db, admin=admin)


def import_commit(db, token: str, admin=None):
    from app.domains.mdm.import_router import CommitRequest, commit as _impl

    return _impl(CommitRequest(token=token), db=db, admin=admin)


from app.domains.mdm.service import (  # noqa: F401
    family_registrations, gezin_tabs, person_name_parts,
)
from app.domains.mdm.service import (  # noqa: F401
    BOARD_MEETING,
    CirclePerson,
    add_to_circle,
    create_person_for_circle,
    end_circle_relation,
    new_members_between,
    organization_circle,
)
from app.domains.mdm.service import (  # noqa: E402,F401
    MergeError,
    merge_persons,
    resolve,
    unmerge_person,
)
from app.domains.mdm.tenant_lookup import (  # noqa: F401
    invalidate_tenant_codes,
    platform_tenant_id,
    tenant_codes,
)

from app.domains.mdm.service import (  # noqa: F401
    admin_code_lists,
    form_code_lists,
    list_persons,
    list_postal_codes,
)
# De organisatie als rechtspersoon staat sinds #971 apart van de tenant als site.
# Zie de moduledocstring daar: de ACCOUNT-organisatie is geen tenant, en zolang deze
# functies onder "tenant" hingen, las de code alsof zo'n organisatie niet bestond.
from app.domains.mdm.organization_service import (  # noqa: F401
    ALLE_ORGANISATIEVELDEN,
    legal_form_options,
    organization_address,
    organization_details,
    organization_options,
    update_organization_address,
    update_organization_details,
)
from app.domains.mdm.tenant_service import (  # noqa: F401
    OngeldigeInstelling,
    TenantFout,
    create_tenant,
    list_accounts,
    list_manageable_tenants,
    list_units,
    platform_org,
    secrets_gezet,
    update_tenant_settings,
)

__all__ = [
    "family_registrations", "gezin_tabs", "person_name_parts",
    "OngeldigeInstelling", "TenantFout", "admin_code_lists", "import_commit", "import_preview", "create_tenant", "form_code_lists",
    "list_persons", "list_postal_codes", "list_accounts", "list_units",
    "secrets_gezet", "update_tenant_settings", "platform_tenant_id",
    "organization_details", "update_organization_details",
    "organization_address", "update_organization_address",
    "organization_options", "legal_form_options",
    "ALLE_ORGANISATIEVELDEN",
    "list_manageable_tenants", "platform_org",
    "Address", "AddressHistory", "ContactDetail", "ContactDetailHistory",
    "ContactTypeCode", "ExternalNumber", "GenderCode", "Member",
    "BankAccount", "OrganizationIdentification", "IdentificationScheme",
    "IdentificationSchemeLabel",
    "MemberHistory", "MemberPerson", "MemberPersonHistory", "Organization",
    "Person", "PersonHistory", "PostalCode", "RelationTypeCode",
    "MergeError", "merge_persons", "resolve", "unmerge_person",
    "tenant_codes", "invalidate_tenant_codes",
    "BOARD_MEETING", "CirclePerson", "OrganizationPerson",
    "OrganizationRelationType", "OrganizationRelationTypeLabel", "add_to_circle", "create_person_for_circle", "end_circle_relation",
    "new_members_between", "organization_circle",
]

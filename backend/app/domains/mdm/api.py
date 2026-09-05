"""Publieke facade van het MDM-component (fase 2, #400).

Masterdata (personen, gezinnen, adressen, contactgegevens, postcodes,
organisaties, codes) wordt buiten dit component uitsluitend via deze module
aangesproken. Soft-ref-patroon (§6): consumenten bewaren waarde-id's
(bv. ``person_id`` als integer, zonder FK) en lezen via ``resolve()``.
"""
from app.domains.mdm.models import (  # noqa: F401
    Address,
    AddressHistory,
    ContactDetail,
    ContactDetailHistory,
    ContactTypeCode,
    ExternalNumber,
    GenderCode,
    Member,
    MemberHistory,
    MemberPerson,
    MemberPersonHistory,
    Organization,
    Person,
    PersonHistory,
    PostalCode,
    RelationTypeCode,
)
from app.domains.mdm.service import (  # noqa: F401
    MergeError,
    merge_persons,
    resolve,
    unmerge_person,
)
from app.domains.mdm.tenant_lookup import (  # noqa: F401
    invalidate_tenant_codes,
    tenant_codes,
)

from app.domains.mdm.service import form_code_lists  # noqa: F401
from app.domains.mdm.tenant_service import (  # noqa: F401
    TenantFout,
    create_tenant,
    list_accounts,
    list_units,
    secrets_gezet,
    update_tenant_settings,
)

__all__ = [
    "TenantFout", "create_tenant", "form_code_lists", "list_accounts", "list_units",
    "secrets_gezet", "update_tenant_settings",
    "Address", "AddressHistory", "ContactDetail", "ContactDetailHistory",
    "ContactTypeCode", "ExternalNumber", "GenderCode", "Member",
    "MemberHistory", "MemberPerson", "MemberPersonHistory", "Organization",
    "Person", "PersonHistory", "PostalCode", "RelationTypeCode",
    "MergeError", "merge_persons", "resolve", "unmerge_person",
    "tenant_codes", "invalidate_tenant_codes",
]

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
# ── Doorgangen naar de ledenimport ───────────────────────────────────────────
# De implementatie blijft in `import_router.py` (het is één domeinbewerking die
# het scherm alleen aanroept); de weg ernaartoe loopt via de facade (#635 I).

async def import_preview(db, file, admin=None):
    from app.domains.mdm.import_router import preview as _impl

    return await _impl(file=file, db=db, admin=admin)


def import_commit(db, token: str, admin=None):
    from app.domains.mdm.import_router import CommitRequest, commit as _impl

    return _impl(CommitRequest(token=token), db=db, admin=admin)


from app.domains.mdm.service import (  # noqa: E402,F401
    MergeError,
    merge_persons,
    resolve,
    unmerge_person,
)
from app.domains.mdm.tenant_lookup import (  # noqa: F401
    invalidate_tenant_codes,
    tenant_codes,
)

from app.domains.mdm.service import (  # noqa: F401
    admin_code_lists,
    form_code_lists,
    list_persons,
    list_postal_codes,
)
from app.domains.mdm.tenant_service import (  # noqa: F401
    TenantFout,
    create_tenant,
    list_accounts,
    list_units,
    secrets_gezet,
    update_tenant_settings,
)

__all__ = [
    "TenantFout", "admin_code_lists", "import_commit", "import_preview", "create_tenant", "form_code_lists",
    "list_persons", "list_postal_codes", "list_accounts", "list_units",
    "secrets_gezet", "update_tenant_settings",
    "Address", "AddressHistory", "ContactDetail", "ContactDetailHistory",
    "ContactTypeCode", "ExternalNumber", "GenderCode", "Member",
    "MemberHistory", "MemberPerson", "MemberPersonHistory", "Organization",
    "Person", "PersonHistory", "PostalCode", "RelationTypeCode",
    "MergeError", "merge_persons", "resolve", "unmerge_person",
    "tenant_codes", "invalidate_tenant_codes",
]

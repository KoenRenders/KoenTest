"""The code list the auth domain owns (CR-12 phase 2).

One list: the roles. It lives here and not in `mdm` because **master data
describes the world and security vocabulary does not** (§B4.1, Koen's
refinement of 25 September 2026). Roles, and later permissions, identity
providers and the mapping of an external group onto an internal role, belong
to the domain that Keycloak or a SAML directory attaches to.

That makes `auth` the second foundation domain: it depends on `mdm` only, so a
foreign key from any schema towards `auth.role_codes` cannot create a cycle —
which is what `workflow.workflow_tasks.required_role` needs.
"""
from app.domains.auth.models import Role, RoleCode, RoleLabel
from app.kernel.codes import CodeList, CodeSeed

ROLE_CODES = (
    CodeSeed(code="ADMIN", nl="Beheerder", en="Administrator", sort_order=10),
    CodeSeed(code="FINANCE", nl="Penningmeester", en="Treasurer", sort_order=20),
    CodeSeed(code="OPERATOR", nl="Platformbeheerder", en="Platform operator",
             sort_order=30),
    CodeSeed(code="ACCOUNT_ADMIN", nl="Accountbeheerder",
             en="Account administrator", sort_order=40),
    # Retired: they have existed since migration 001, are filtered out on
    # every screen, and nobody holds them. Not deleted — an existing row would
    # then get an invalid reference, and the member stays in any case
    # (§B4.3).
    CodeSeed(code="MEMBER", nl="Lid", en="Member", sort_order=90,
             is_active=False),
    CodeSeed(code="USER", nl="Gebruiker", en="User", sort_order=91,
             is_active=False),
)

ROLE = CodeList(
    name="role",
    schema="auth",
    codes=RoleCode,
    labels=RoleLabel,
    enum=Role,
    # The second column is cross-schema, towards a code table of a
    # foundation domain — the exception of §B2.4, and the reason roles belong
    # in `auth` and not in whichever domain happens to use them.
    fk_from=("auth.user_roles.role_code",
             "workflow.workflow_tasks.required_role"),
)

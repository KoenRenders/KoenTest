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

from app.domains.auth.models import (
    LoginPurpose,
    LoginPurposeCode,
    LoginPurposeLabel,
    Right,
    RightCode,
    RightLabel,
    Role,
    RoleCode,
    RoleLabel,
)
from app.kernel.codes import CodeList, CodeSeed

ROLE_CODES = (
    CodeSeed(code="ADMIN", nl="Beheerder", en="Administrator", sort_order=10),
    # CR-24 (Q8): Penningmeester became Boekhouding on screen; the code stays.
    CodeSeed(code="FINANCE", nl="Boekhouding", en="Accounting", sort_order=20),
    CodeSeed(code="OPERATOR", nl="Platformbeheerder", en="Platform operator", sort_order=30),
    CodeSeed(
        code="ACCOUNT_ADMIN", nl="Accountbeheerder", en="Account administrator", sort_order=40
    ),
    # CR-24 (#1722): master data, and the three roles of the webshop (CR-21).
    CodeSeed(code="MASTERDATA", nl="Masterdata", en="Master data", sort_order=50),
    CodeSeed(code="PRICING", nl="Prijsbeheer", en="Pricing", sort_order=60),
    CodeSeed(code="SALES", nl="Verkoop", en="Sales", sort_order=70),
    CodeSeed(code="STOCK", nl="Voorraadbeheer", en="Stock management", sort_order=80),
    # Retired: they have existed since migration 001, are filtered out on
    # every screen, and nobody holds them. Not deleted — an existing row would
    # then get an invalid reference, and the member stays in any case
    # (§B4.3).
    CodeSeed(code="MEMBER", nl="Lid", en="Member", sort_order=90, is_active=False),
    CodeSeed(code="USER", nl="Gebruiker", en="User", sort_order=91, is_active=False),
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
    fk_from=(
        "auth.user_roles.role_code",
        "workflow.workflow_tasks.required_role",
        "auth.role_rights.role_code",
    ),
)


def _rights(start: int, obj: str, nl: str, en: str, change: str = "manage") -> tuple:
    """The two rights of one kind of object (CR-24 §B1 D1): viewing, changing."""
    return (
        CodeSeed(code=f"{obj}.view", nl=f"{nl} bekijken", en=f"View {en}", sort_order=start),
        CodeSeed(
            code=f"{obj}.{change}", nl=f"{nl} beheren", en=f"Manage {en}", sort_order=start + 5
        ),
    )


# CR-24 (#1722): the rights a gate asks for, in the order of §B1's table.
# Which role holds which is not here: the bundles are rows in
# `auth.role_rights`, written by a migration (D2).
RIGHT_CODES = (
    *_rights(10, "activity", "Activiteiten", "activities"),
    *_rights(20, "form", "Formulieren", "forms"),
    *_rights(30, "page", "Pagina's", "pages"),
    *_rights(40, "media", "Media", "media"),
    *_rights(50, "design", "Ontwerpen", "designs"),
    *_rights(60, "newsletter", "Nieuwsbrieven", "newsletters"),
    *_rights(70, "meeting", "Vergaderingen", "meetings"),
    *_rights(80, "report", "Rapporten", "reports"),
    CodeSeed(code="assistant.use", nl="Raakje gebruiken", en="Use the assistant", sort_order=90),
    *_rights(100, "party", "Personen en organisaties", "persons and organisations", "masterdata"),
    *_rights(110, "product", "Producten", "products", "masterdata"),
    *_rights(120, "price", "Prijzen", "prices"),
    *_rights(130, "sales", "Bestellingen", "orders"),
    *_rights(140, "stock", "Voorraad", "stock"),
    *_rights(150, "payment", "Betalingen", "payments"),
    CodeSeed(code="workbench.use", nl="Werkbank gebruiken", en="Use the workbench", sort_order=160),
    *_rights(170, "user", "Gebruikers", "users"),
    *_rights(180, "settings", "Instellingen", "settings"),
    *_rights(190, "platform", "Platform", "the platform"),
)

RIGHT = CodeList(
    name="right",
    schema="auth",
    codes=RightCode,
    labels=RightLabel,
    enum=Right,
    fk_from=("auth.role_rights.right_code",),
)

# CR-22 (#1704): what a code sent by mail is for. In `auth` for the reason the
# roles are: it is vocabulary of signing in, not a description of the world.
LOGIN_PURPOSE_CODES = (
    CodeSeed(code="SIGN_IN", nl="Inloggen", en="Sign in", sort_order=10),
    CodeSeed(code="CREATE_ACCOUNT", nl="Account aanmaken", en="Create account", sort_order=20),
    CodeSeed(
        code="CONFIRM_ADDRESS", nl="E-mailadres bevestigen", en="Confirm address", sort_order=30
    ),
)

LOGIN_PURPOSE = CodeList(
    name="login_purpose",
    schema="auth",
    codes=LoginPurposeCode,
    labels=LoginPurposeLabel,
    enum=LoginPurpose,
    fk_from=("auth.login_tokens.purpose",),
)

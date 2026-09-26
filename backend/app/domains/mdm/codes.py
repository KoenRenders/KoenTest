"""The code lists master data owns (CR-12).

A list lands here when it is used by more than one domain, which is what
master data means (§B4.1). Doubt therefore resolves towards `mdm`: moving a
list later copies rows and re-points a foreign key, and the stored values do
not change, so a wrong guess is cheap.

Phase 0 declared the language list; phase 1 adds the payment method. The four
single-language code tables already here (`gender`, `contact_type`,
`relation_type`, `legal_form`) are split into the codes/labels shape in phase 2.
"""
from app.domains.mdm.models import (
    ContactTypeCode,
    ContactTypeLabel,
    GenderCode,
    GenderLabel,
    IdentificationScheme,
    IdentificationSchemeLabel,
    LanguageCode,
    LanguageLabel,
    LegalForm,
    LegalFormCode,
    LegalFormLabel,
    OrganizationRelationType,
    OrganizationRelationTypeLabel,
    OrganizationType,
    OrganizationTypeCode,
    OrganizationTypeLabel,
    PaymentMethod,
    PaymentMethodCode,
    PaymentMethodLabel,
    RelationType,
    RelationTypeCode,
    RelationTypeLabel,
)
from app.kernel.codes import Code, CodeList, CodeSeed

#: The two languages every label table is keyed against.
LANGUAGE_CODES = (
    CodeSeed(code="nl", nl="Nederlands", en="Dutch", sort_order=10),
    CodeSeed(code="en", nl="Engels", en="English", sort_order=20),
)

LANGUAGE = CodeList(
    name="language",
    schema="mdm",
    codes=LanguageCode,
    labels=LanguageLabel,
    # No enum: nothing in Python branches on a language code. The active
    # language comes from the tenant setting and is used as a lookup key, never
    # compared to a member (§B4.3).
    enum=None,
    # Deliberately empty, and this is the one list where that needs saying.
    # Every `_labels` table in every schema stores a language code, so a
    # hand-written list here would need a line per phase and would be wrong
    # the first time somebody forgot. The shape gate checks it instead: it
    # walks every registered list and holds that its labels table carries the
    # foreign key to `mdm.language_codes`.
    fk_from=(),
)


PAYMENT_METHOD_CODES = (
    CodeSeed(code="online", nl="Online", en="Online", sort_order=10),
    CodeSeed(code="transfer", nl="Overschrijving", en="Bank transfer",
             sort_order=20),
    CodeSeed(code="cash", nl="Cash", en="Cash", sort_order=30),
)

PAYMENT_METHOD = CodeList(
    name="payment_method",
    schema="mdm",
    codes=PaymentMethodCode,
    labels=PaymentMethodLabel,
    enum=PaymentMethod,
    # The two columns that store a payment method, in two different schemas.
    # This is the cross-schema foreign key §B2.4 allows, and the reason the
    # list sits in `mdm` rather than in `payment`.
    fk_from=("payment.payment_records.method",
             "activities.registrations.payment_method"),
)


# ── Phase 2: the master data itself ─────────────────────────────────────────
#
# Five lists that already existed but in the old shape — one row per (code,
# language), with uniqueness on the code alone. That shape allows exactly one
# language (#929) and is the reason migration 017 wiped out every English
# label. Two lists already had the split shape (#924) and are only registered
# here.

GENDER_CODES = (
    CodeSeed(code="M", nl="Man", en="Male", sort_order=10),
    CodeSeed(code="F", nl="Vrouw", en="Female", sort_order=20),
    CodeSeed(code="X", nl="X", en="X", sort_order=30),
    # Retired (Koen, 26 September 2026): the list is M, F, X and nothing more.
    # The label stays, so an existing person with this code still renders.
    CodeSeed(code="U", nl="Onbekend", en="Unknown", sort_order=90,
             is_active=False),
)

GENDER = CodeList(
    name="gender",
    schema="mdm",
    codes=GenderCode,
    labels=GenderLabel,
    # No enum: nothing in Python branches on a gender code. It is an attribute
    # that is stored and shown, not a value a rule depends on (§B4.3).
    enum=None,
    fk_from=("mdm.persons.gender_code",),
)

CONTACT_TYPE_CODES = (
    CodeSeed(code="EMAIL", nl="E-mail", en="E-mail", sort_order=10),
    CodeSeed(code="MOBILE", nl="Mobiel", en="Mobile", sort_order=20),
    CodeSeed(code="PHONE", nl="Telefoon", en="Phone", sort_order=30),
    CodeSeed(code="WEBSITE", nl="Website", en="Website", sort_order=40),
    CodeSeed(code="FACEBOOK", nl="Facebook", en="Facebook", sort_order=50),
    CodeSeed(code="INSTAGRAM", nl="Instagram", en="Instagram", sort_order=60),
    CodeSeed(code="TIKTOK", nl="TikTok", en="TikTok", sort_order=70),
)

#: Which contact types are social networks (#1160). A property of the code,
#: so on the code table — not in a list in the footer. This set is only the
#: seed for that column; the footer reads the column.
SOCIAL_NETWORKS = {"FACEBOOK", "INSTAGRAM", "TIKTOK"}


class CONTACT:
    """The contact types the code names — codes, not an enum.

    **Why there is no enum here** (Koen, 26 September 2026). §B4.3 asks for an
    enum as soon as Python branches on a value, and it does here: an e-mail
    address and a mobile number are treated differently from the rest. But
    #1160 made the public footer data-driven — a fifth social network is one
    row in `mdm.contact_type_codes` with `is_social_network = true`, and not a
    code change. An enum column would reject that row on the **write side**,
    and the code list would thereby lose exactly what #1160 opened it up for.
    The read side does not need the enum: the footer asks the source *which*
    codes are social networks.

    What remains is that the code never uses a bare string literal. These
    constants are that safety net: one place where the spelling lives, and a
    typo is an `AttributeError` at import instead of a comparison that is
    silently never true. The foreign key guards the rest.
    """

    EMAIL = Code("EMAIL")
    MOBILE = Code("MOBILE")
    PHONE = Code("PHONE")
    WEBSITE = Code("WEBSITE")
    FACEBOOK = Code("FACEBOOK")
    INSTAGRAM = Code("INSTAGRAM")
    TIKTOK = Code("TIKTOK")


CONTACT_TYPE = CodeList(
    name="contact_type",
    schema="mdm",
    codes=ContactTypeCode,
    labels=ContactTypeLabel,
    # No enum — see `CONTACT` above for the reason and for what takes its
    # place.
    enum=None,
    fk_from=("mdm.contact_details.contact_type_code",),
    extra_code_columns=("is_social_network",),
)

RELATION_TYPE_CODES = (
    CodeSeed(code="HOOFDLID", nl="Hoofdlid", en="Primary member", sort_order=10),
    CodeSeed(code="PARTNER", nl="Partner", en="Partner", sort_order=20),
    CodeSeed(code="KIND", nl="(meerderjarig) kind", en="Adult child",
             sort_order=30),
)

RELATION_TYPE = CodeList(
    name="relation_type",
    schema="mdm",
    codes=RelationTypeCode,
    labels=RelationTypeLabel,
    enum=RelationType,
    fk_from=("mdm.member_persons.relation_type",),
)

LEGAL_FORM_CODES = (
    CodeSeed(code="VZW", nl="vzw", en="Non-profit association", sort_order=10),
    CodeSeed(code="FEITELIJKE_VERENIGING", nl="Feitelijke vereniging",
             en="Unincorporated association", sort_order=20),
    CodeSeed(code="BEDRIJF", nl="Bedrijf", en="Company", sort_order=30),
)

LEGAL_FORM = CodeList(
    name="legal_form",
    schema="mdm",
    codes=LegalFormCode,
    labels=LegalFormLabel,
    enum=LegalForm,
    fk_from=("mdm.organizations.legal_form",),
)

ORGANIZATION_TYPE_CODES = (
    CodeSeed(code="ACCOUNT", nl="Rechtspersoon", en="Legal entity", sort_order=10),
    CodeSeed(code="UNIT", nl="Afdeling", en="Unit", sort_order=20),
    CodeSeed(code="PLATFORM", nl="Platform", en="Platform", sort_order=30),
)

ORGANIZATION_TYPE = CodeList(
    name="organization_type",
    schema="mdm",
    codes=OrganizationTypeCode,
    labels=OrganizationTypeLabel,
    enum=OrganizationType,
    fk_from=("mdm.organizations.org_type",),
)

#: These two already had the shape (#924); they are only registered here, so
#: the gates include them. The `en` rows of the identification schemes were
#: missing and are added in the same migration.
ORGANIZATION_RELATION_TYPE_CODES = (
    CodeSeed(code="BOARD_MEETING", nl="Bestuursvergadering", en="Board meeting",
             sort_order=10),
)

ORGANIZATION_RELATION_TYPE = CodeList(
    name="organization_relation_type",
    schema="mdm",
    codes=OrganizationRelationType,
    labels=OrganizationRelationTypeLabel,
    enum=None,
    fk_from=("mdm.organization_persons.relation_type",),
)

IDENTIFICATION_SCHEME_CODES = (
    CodeSeed(code="KBO", nl="Ondernemingsnummer", en="Enterprise number",
             sort_order=10,
             description_nl="Belgisch ondernemingsnummer (KBO)",
             description_en="Belgian enterprise number (KBO)"),
    CodeSeed(code="VAT", nl="Btw-nummer", en="VAT number", sort_order=20,
             description_nl="Btw-identificatienummer",
             description_en="VAT identification number"),
)

IDENTIFICATION_SCHEME = CodeList(
    name="identification_scheme",
    schema="mdm",
    codes=IdentificationScheme,
    labels=IdentificationSchemeLabel,
    enum=None,
    fk_from=("mdm.organization_identifications.scheme",),
)

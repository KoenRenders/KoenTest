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


# ── Fase 2: de masterdata zelf ───────────────────────────────────────────────
#
# Vijf lijsten die al bestonden maar in de oude vorm — één rij per (code, taal),
# met een uniciteit op de code alleen. Die vorm laat precies één taal toe (#929)
# en is de reden dat migratie 017 elk Engels label wegvaagde. Twee lijsten
# hadden de gesplitste vorm al (#924) en worden hier alleen aangemeld.

GENDER_CODES = (
    CodeSeed(code="M", nl="Man", en="Male", sort_order=10),
    CodeSeed(code="F", nl="Vrouw", en="Female", sort_order=20),
    CodeSeed(code="X", nl="X", en="X", sort_order=30),
    # Ingetrokken (Koen, 26 september 2026): de lijst is M, F, X en niets meer.
    # Het label blijft, zodat een bestaande persoon met deze code nog rendert.
    CodeSeed(code="U", nl="Onbekend", en="Unknown", sort_order=90,
             is_active=False),
)

GENDER = CodeList(
    name="gender",
    schema="mdm",
    codes=GenderCode,
    labels=GenderLabel,
    # Geen enum: niets in Python vertakt op een geslachtscode. Het is een
    # kenmerk dat opgeslagen en getoond wordt, niet een waarde waar een regel
    # aan hangt (§B4.3).
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

#: Welke contactsoorten sociale netwerken zijn (#1160). Een eigenschap ván de
#: code, dus op de codetabel — niet in een lijstje in de voetnoot. Dit tupel is
#: alleen het zaadje voor die kolom; de voetnoot leest de kolom.
SOCIAL_NETWORKS = {"FACEBOOK", "INSTAGRAM", "TIKTOK"}


class CONTACT:
    """De contactsoorten die de code bij naam noemt — codes, geen enum.

    **Waarom hier geen enum staat** (Koen, 26 september 2026). §B4.3 vraagt een
    enum zodra Python op een waarde vertakt, en dat doet ze hier: een e-mailadres
    en een mobiel nummer worden anders behandeld dan de rest. Maar #1160 maakte
    de publieke voetnoot data-gedreven — een vijfde sociaal netwerk is één rij
    in `mdm.contact_type_codes` met `is_social_network = true`, en geen
    codewijziging. Een enum-kolom zou die rij aan de **schrijfkant** weigeren,
    en daarmee zou de codelijst precies datgene verliezen waarvoor #1160 hem
    open zette. De leeskant heeft de enum niet nodig: de voetnoot vraagt de
    bron wélke codes sociale netwerken zijn.

    Wat blijft, is dat de code nergens een los stringliteraal gebruikt. Deze
    constanten zijn dat vangnet: één plek waar de spelling staat, en een typfout
    is een `AttributeError` bij import in plaats van een vergelijking die stil
    nooit waar wordt. De foreign key bewaakt de rest.
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
    # Geen enum — zie `CONTACT` hierboven voor de reden en voor wat er in de
    # plaats komt.
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

#: Deze twee hadden de vorm al (#924); ze worden hier alleen aangemeld, zodat
#: de poorten ze meenemen. De `en`-rijen van de identificatieschema's ontbraken
#: en komen er in dezelfde migratie bij.
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

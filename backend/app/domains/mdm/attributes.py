"""The attributes of the `mdm` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="mdm.address.street",
        columns=("mdm.addresses.street",),
        label="Straat",
        name_en="Street",
        help="De straatnaam van dit adres, zonder huisnummer.",
        ai_exposure=AiExposure.INTERNAL,  # the street is intern: Raakje groups by street (Koen, 15 October 2026: "intern")
    ),
    Attribute(
        key="mdm.address.house_number",
        columns=("mdm.addresses.house_number",),
        label="Huisnummer",
        name_en="House number",
        help="Het huisnummer.",
        ai_exposure=AiExposure.TOKENISED,  # a token (Koen, 15 October 2026, read by the master CLI)
    ),
    Attribute(
        key="mdm.address.bus_number",
        columns=("mdm.addresses.bus_number",),
        label="Bus",
        name_en="Bus number",
        help="Het busnummer, leeg als er geen is.",
        ai_exposure=AiExposure.TOKENISED,  # a token (Koen, 15 October 2026, read by the master CLI)
    ),
    Attribute(
        key="mdm.address.postal_code_id",
        columns=("mdm.addresses.postal_code_id",),
        label="Postcode",
        name_en="Postal code id",
        help="De postcode van een adres, uit de postcodetabel.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.bank_account.iban",
        columns=("mdm.bank_accounts.iban",),
        label=None,
        name_en="Iban",
        help="The iban of the bank account.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.bank_account.bic",
        columns=("mdm.bank_accounts.bic",),
        label=None,
        name_en="Bic",
        help="The bic of the bank account.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.bank_account.beneficiary",
        columns=("mdm.bank_accounts.beneficiary",),
        label=None,
        name_en="Beneficiary",
        help="The beneficiary of the bank account.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.bank_account.sort_order",
        columns=("mdm.bank_accounts.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the bank account.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.contact_detail.contact_type_code",
        columns=("mdm.contact_details.contact_type_code",),
        label=None,
        name_en="Contact type code",
        help="The contact type code of the contact detail, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.contact_detail.is_primary",
        columns=("mdm.contact_details.is_primary",),
        label=None,
        name_en="Is primary",
        help="The is primary of the contact detail.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.contact_detail.confirmed_at",
        columns=("mdm.contact_details.confirmed_at",),
        label=None,
        name_en="Confirmed at",
        help="The confirmed at of the contact detail.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.external_number.source",
        columns=("mdm.external_numbers.source",),
        label=None,
        name_en="Source",
        help="The source of the external number, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.external_number.external_id",
        columns=("mdm.external_numbers.external_id",),
        label=None,
        name_en="External id",
        help="The external id of the external number.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.member_person.relation_type",
        columns=("mdm.member_persons.relation_type",),
        label="Relatie",
        name_en="Relation type",
        help="Hoofdlid, partner of (meerderjarig) kind binnen het gezin.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.tenant.code",
        columns=("mdm.tenants.code",),
        label="Code",
        name_en="Code",
        help="The code of the tenant: its path prefix and the key a host maps to.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.tenant.kind",
        columns=("mdm.tenants.kind",),
        label="Type",
        name_en="Kind",
        help="The kind of the tenant, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.tenant.site_name",
        columns=("mdm.tenants.site_name",),
        label="Naam van de site",
        name_en="Site name",
        help="The name the tenant's site shows, when it differs from its organisation's.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.tenant.time_zone",
        columns=("mdm.tenants.time_zone",),
        label="Tijdzone",
        name_en="Time zone",
        help="The IANA time zone the tenant's days are counted in; Europe/Brussels by default.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.tenant.is_active",
        columns=("mdm.tenants.is_active",),
        label=None,
        name_en="Is active",
        help="Whether the tenant's site is active.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.organization.name",
        columns=("mdm.organizations.name",),
        label="Naam",
        name_en="Name",
        help="The name of the organization.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.organization.is_active",
        columns=("mdm.organizations.is_active",),
        label=None,
        name_en="Is active",
        help="The is active of the organization.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.party.kind",
        columns=("mdm.parties.kind",),
        label=None,
        name_en="Party kind",
        help="Whether the party is a person or an organisation, a code of its code list "
        "(CR-26). No screen shows it.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization.legal_form",
        columns=("mdm.organizations.legal_form",),
        label=None,
        name_en="Legal form",
        help="The legal form of the organization, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.party_identification.scheme",
        columns=("mdm.party_identifications.scheme",),
        label=None,
        name_en="Scheme",
        help="The scheme of the party identification, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.party_identification.value",
        columns=("mdm.party_identifications.value",),
        label=None,
        name_en="Value",
        help="The value of the party identification.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.party_identification.country",
        columns=("mdm.party_identifications.country",),
        label=None,
        name_en="Country",
        help="The country of the party identification.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.party_identification.sort_order",
        columns=("mdm.party_identifications.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the party identification.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.party_relationship.from_party_id",
        columns=("mdm.party_relationships.from_party_id",),
        label=None,
        name_en="From party",
        help="The party that stands in the relation: the person of a circle, the person who acts for an organisation.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.party_relationship.to_party_id",
        columns=("mdm.party_relationships.to_party_id",),
        label=None,
        name_en="To party",
        help="The party the relation is to: the organisation of a circle, the organisation acted for.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.party_relationship.kind",
        columns=("mdm.party_relationships.kind",),
        label=None,
        name_en="Kind",
        help="The kind of the party relationship, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.party_relationship.start_date",
        columns=("mdm.party_relationships.start_date",),
        label=None,
        name_en="Start date",
        help="The start date of the party relationship.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.party_relationship.end_date",
        columns=("mdm.party_relationships.end_date",),
        label=None,
        name_en="End date",
        help="The end date of the party relationship; it ends, nothing is deleted.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.person.last_name",
        columns=("mdm.persons.last_name",),
        label="Achternaam",
        name_en="Last name",
        help="The last name of the person.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.person.first_name",
        columns=("mdm.persons.first_name",),
        label="Voornaam",
        name_en="First name",
        help="The first name of the person.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.person.date_of_birth",
        columns=("mdm.persons.date_of_birth",),
        label="Geboortedatum",
        name_en="Date of birth",
        help="The date of birth of the person.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.person.gender_code",
        columns=("mdm.persons.gender_code",),
        label="Geslacht",
        name_en="Gender code",
        help="Het geslacht van een persoon.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
)

# One column that holds several data: the contact's value reads by its contact type
# (`mdm.contact_details.contact_type_code`), so each kind is an entry of its own and the
# label comes from the type (Mobiel, E-mail, Telefoon). A person's number or address
# identifies them: never to a model (K1).
CONTACT_VALUES: tuple[Attribute, ...] = (
    Attribute(
        key="mdm.contact_detail.mobile",
        columns=("mdm.contact_details.value",),
        label="Mobiel",
        name_en="Mobile",
        help="The mobile number of a contact, when its contact type is MOBILE.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.contact_detail.email",
        columns=("mdm.contact_details.value",),
        label="E-mail",
        name_en="E-mail",
        help="The e-mail address of a contact, when its contact type is EMAIL.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.contact_detail.phone",
        columns=("mdm.contact_details.value",),
        label="Telefoon",
        name_en="Phone",
        help="The telephone number of a contact, when its contact type is PHONE.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.contact_detail.link",
        columns=("mdm.contact_details.value",),
        label=None,
        name_en="Link",
        help="The web address or social-network address of a contact (WEBSITE, FACEBOOK, INSTAGRAM, TIKTOK).",
        ai_exposure=AiExposure.NONE,  # K1: a person's page identifies them
    ),
)

# Several columns, one datum: the address as it reads on one line (street, number, box,
# postal code). Its label is the word of the changes list and of the import's check.
ADDRESS_LINE = Attribute(
    key="mdm.address.line",
    columns=(
        "mdm.addresses.street",
        "mdm.addresses.house_number",
        "mdm.addresses.bus_number",
        "mdm.addresses.postal_code_id",
    ),
    label="Adres",
    name_en="Address",
    help="Straat, huisnummer en bus op één lijn.",
    ai_exposure=AiExposure.TOKENISED,  # a token (Koen, 15 October 2026, read by the master CLI)
)


# The data the reporting universe stands on that no single stored column is (CR-33 phase 1).
UNIVERSE_ENTRIES: tuple[Attribute, ...] = (
    Attribute(
        key="mdm.member.created_at",
        columns=("mdm.members.created_at",),
        label="Aanmaakdatum gezin",
        name_en="Created at",
        help="Wanneer het gezin in de administratie kwam.",
        ai_exposure=AiExposure.INTERNAL,
    ),
    Attribute(
        key="mdm.address.municipality",
        columns=("mdm.addresses.postal_code_id",),
        label="Gemeente",
        name_en="Municipality",
        help="De gemeente van een adres, uit de postcodetabel.",
        ai_exposure=AiExposure.INTERNAL,
    ),
    Attribute(
        key="mdm.member.id",
        columns=("mdm.members.id",),
        label="Gezin",
        name_en="Id",
        help="Het gezin zelf.",
        ai_exposure=AiExposure.TOKENISED,  # the source of the token gezin-23
    ),
)

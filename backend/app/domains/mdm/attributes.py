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
        help="The street of the address.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.address.house_number",
        columns=("mdm.addresses.house_number",),
        label="Huisnummer",
        name_en="House number",
        help="The house number of the address.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.address.bus_number",
        columns=("mdm.addresses.bus_number",),
        label="Bus",
        name_en="Bus number",
        help="The bus number of the address.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mdm.address.postal_code_id",
        columns=("mdm.addresses.postal_code_id",),
        label="Postcode",
        name_en="Postal code id",
        help="The postal code id of the address, a code of its code list.",
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
        help="The relation type of the member person, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization.org_type",
        columns=("mdm.organizations.org_type",),
        label=None,
        name_en="Org type",
        help="The org type of the organization, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization.code",
        columns=("mdm.organizations.code",),
        label=None,
        name_en="Code",
        help="The code of the organization.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.organization.name",
        columns=("mdm.organizations.name",),
        label=None,
        name_en="Name",
        help="The name of the organization.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.organization.site_name",
        columns=("mdm.organizations.site_name",),
        label=None,
        name_en="Site name",
        help="The site name of the organization.",
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
        key="mdm.organization.legal_form",
        columns=("mdm.organizations.legal_form",),
        label=None,
        name_en="Legal form",
        help="The legal form of the organization, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization.kind",
        columns=("mdm.organizations.kind",),
        label=None,
        name_en="Kind",
        help="The kind of the organization, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization_identification.scheme",
        columns=("mdm.organization_identifications.scheme",),
        label=None,
        name_en="Scheme",
        help="The scheme of the organization identification, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization_identification.value",
        columns=("mdm.organization_identifications.value",),
        label=None,
        name_en="Value",
        help="The value of the organization identification.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.organization_identification.country",
        columns=("mdm.organization_identifications.country",),
        label=None,
        name_en="Country",
        help="The country of the organization identification.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="mdm.organization_identification.sort_order",
        columns=("mdm.organization_identifications.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the organization identification.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.organization_person.relation_type",
        columns=("mdm.organization_persons.relation_type",),
        label=None,
        name_en="Relation type",
        help="The relation type of the organization person, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="mdm.organization_person.start_date",
        columns=("mdm.organization_persons.start_date",),
        label=None,
        name_en="Start date",
        help="The start date of the organization person.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="mdm.organization_person.end_date",
        columns=("mdm.organization_persons.end_date",),
        label=None,
        name_en="End date",
        help="The end date of the organization person.",
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
        help="The gender code of the person, a code of its code list.",
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
    help="The address on one line: street, house number, box and postal code.",
    ai_exposure=AiExposure.NONE,  # K1
)

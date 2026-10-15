"""The attributes of the `activities` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="activities.activity.name",
        columns=("activities.activities.name",),
        label="Activiteit",
        name_en="Name",
        help="Naam van de activiteit.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity.slug",
        columns=("activities.activities.slug",),
        label=None,
        name_en="Slug",
        help="The slug of the activity.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity.location",
        columns=("activities.activities.location",),
        label="Locatie",
        name_en="Location",
        help="Waar de activiteit doorgaat, zoals ingevuld bij de activiteit — vrije tekst, dus geen adres en niet genormaliseerd.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity.description",
        columns=("activities.activities.description",),
        label="Omschrijving",
        name_en="Description",
        help="De omschrijving die het bestuur bij de activiteit schreef — dezelfde zinnen die op de website en in de nieuwsbrief staan.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity.poster_url",
        columns=("activities.activities.poster_url",),
        label=None,
        name_en="Poster url",
        help="The poster url of the activity.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="activities.activity.is_cancelled",
        columns=("activities.activities.is_cancelled",),
        label="Geannuleerd",
        name_en="Is cancelled",
        help="Of de activiteit geannuleerd werd.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity.members_only",
        columns=("activities.activities.members_only",),
        label="Enkel voor leden",
        name_en="Members only",
        help="Of enkel leden zich mochten inschrijven op deze activiteit.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity.board_notes",
        columns=("activities.activities.board_notes",),
        label="Notities bestuur",
        name_en="Board notes",
        help="De interne nota bij de activiteit: afspraken, contacten, wat iemand zichzelf wilde herinneren.",
        ai_exposure=AiExposure.NONE,  # the board's own notes: never to a model (Koen, 15 October 2026: "akkoord")
    ),
    Attribute(
        key="activities.activity.status",
        columns=("activities.activities.status",),
        label="Publicatiestatus",
        name_en="Status",
        help="Concept of Gepubliceerd.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="activities.activity.target_audience",
        columns=("activities.activities.target_audience",),
        label="Doelpubliek",
        name_en="Target audience",
        help="Voor wie de activiteit bedoeld is — Gezinnen, Volwassenen, Mannen, Vrouwen, Tieners of Kinderen.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="activities.activity.copied_from_id",
        columns=("activities.activities.copied_from_id",),
        label=None,
        name_en="Copied from id",
        help="The copied from id of the activity.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_date.start_date",
        columns=("activities.activity_dates.start_date",),
        label="Startdatum",
        name_en="Start date",
        help="De eerste dag van de activiteit.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_date.end_date",
        columns=("activities.activity_dates.end_date",),
        label="Einddatum",
        name_en="End date",
        help="De laatste dag van de activiteit, of de startdag als er maar één is.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_date.start_time",
        columns=("activities.activity_dates.start_time",),
        label="Aanvangsuur",
        name_en="Start time",
        help="Het uur waarop de activiteit die dag begint, als 19:30. Leeg als er geen uur is ingevuld.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_date.end_time",
        columns=("activities.activity_dates.end_time",),
        label=None,
        name_en="End time",
        help="The end time of the activity date.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_organiser.person_id",
        columns=("activities.activity_organisers.person_id",),
        label=None,
        name_en="Person id",
        help="The person id of the activity organiser.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_organiser.sort_order",
        columns=("activities.activity_organisers.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the activity organiser.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_organiser.is_contact",
        columns=("activities.activity_organisers.is_contact",),
        label=None,
        name_en="Is contact",
        help="The is contact of the activity organiser.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_organiser.email_override",
        columns=("activities.activity_organisers.email_override",),
        label=None,
        name_en="Email override",
        help="The email override of the activity organiser.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="activities.activity_organiser.mobile_override",
        columns=("activities.activity_organisers.mobile_override",),
        label=None,
        name_en="Mobile override",
        help="The mobile override of the activity organiser.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="activities.activity_organiser.show_email",
        columns=("activities.activity_organisers.show_email",),
        label=None,
        name_en="Show email",
        help="The show email of the activity organiser.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_organiser.show_mobile",
        columns=("activities.activity_organisers.show_mobile",),
        label=None,
        name_en="Show mobile",
        help="The show mobile of the activity organiser.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_product.name",
        columns=("activities.activity_products.name",),
        label="Product",
        name_en="Name",
        help="Het gekozen product.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_product.price",
        columns=("activities.activity_products.price",),
        label="Prijs",
        name_en="Price",
        help="The price of the activity product.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_product.member_price",
        columns=("activities.activity_products.member_price",),
        label=None,
        name_en="Member price",
        help="The member price of the activity product.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_product.is_free",
        columns=("activities.activity_products.is_free",),
        label=None,
        name_en="Is free",
        help="The is free of the activity product.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_product.pay_on_site",
        columns=("activities.activity_products.pay_on_site",),
        label=None,
        name_en="Pay on site",
        help="The pay on site of the activity product.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_product.is_active",
        columns=("activities.activity_products.is_active",),
        label=None,
        name_en="Is active",
        help="The is active of the activity product.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_product.max_participants",
        columns=("activities.activity_products.max_participants",),
        label=None,
        name_en="Max participants",
        help="The max participants of the activity product.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_product.sort_order",
        columns=("activities.activity_products.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the activity product.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_sub_registration.name",
        columns=("activities.activity_sub_registrations.name",),
        label="Onderdeel",
        name_en="Name",
        help="Het onderdeel van de activiteit waarop ingeschreven werd — een activiteit kan er meerdere hebben, elk met een eigen prijs en capaciteit.",
        ai_exposure=AiExposure.PUBLIC,  # K5 (CR-33 phase 2: the inventory's name rule read a registration table as a person)
    ),
    Attribute(
        key="activities.activity_sub_registration.description",
        columns=("activities.activity_sub_registrations.description",),
        label="Omschrijving",
        name_en="Description",
        help="The description of the activity sub registration.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_sub_registration.external_register_url",
        columns=("activities.activity_sub_registrations.external_register_url",),
        label=None,
        name_en="External register url",
        help="The external register url of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="activities.activity_sub_registration.external_registrations_url",
        columns=("activities.activity_sub_registrations.external_registrations_url",),
        label=None,
        name_en="External registrations url",
        help="The external registrations url of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="activities.activity_sub_registration.info_url",
        columns=("activities.activity_sub_registrations.info_url",),
        label=None,
        name_en="Info url",
        help="The info url of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="activities.activity_sub_registration.registration_type_code",
        columns=("activities.activity_sub_registrations.registration_type_code",),
        label=None,
        name_en="Registration type code",
        help="The registration type code of the activity sub registration, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="activities.activity_sub_registration.max_participants",
        columns=("activities.activity_sub_registrations.max_participants",),
        label=None,
        name_en="Max participants",
        help="The max participants of the activity sub registration.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_sub_registration.registration_closes_on",
        columns=("activities.activity_sub_registrations.registration_closes_on",),
        label=None,
        name_en="Registration closes on",
        help="The registration closes on of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_sub_registration.price",
        columns=("activities.activity_sub_registrations.price",),
        label="Prijs",
        name_en="Price",
        help="The price of the activity sub registration.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_sub_registration.member_price",
        columns=("activities.activity_sub_registrations.member_price",),
        label=None,
        name_en="Member price",
        help="The member price of the activity sub registration.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_sub_registration.is_free",
        columns=("activities.activity_sub_registrations.is_free",),
        label=None,
        name_en="Is free",
        help="The is free of the activity sub registration.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="activities.activity_sub_registration.team_name_required",
        columns=("activities.activity_sub_registrations.team_name_required",),
        label=None,
        name_en="Team name required",
        help="The team name required of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_sub_registration.form_id",
        columns=("activities.activity_sub_registrations.form_id",),
        label=None,
        name_en="Form id",
        help="The form id of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.activity_sub_registration.sort_order",
        columns=("activities.activity_sub_registrations.sort_order",),
        label=None,
        name_en="Sort order",
        help="The sort order of the activity sub registration.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.registration.registered_at",
        columns=("activities.registrations.registered_at",),
        label="Inschrijfdatum",
        name_en="Registered at",
        help="Wanneer er ingeschreven is.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.registration.registration_type",
        columns=("activities.registrations.registration_type",),
        label="Inschrijfvorm",
        name_en="Registration type",
        help="Of er individueel of als gezin ingeschreven werd.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="activities.registration.contact_name",
        columns=("activities.registrations.contact_name",),
        label="Naam",
        name_en="Contact name",
        help="The contact name of the registration.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="activities.registration.contact_email",
        columns=("activities.registrations.contact_email",),
        label="E-mail",
        name_en="Contact email",
        help="The contact email of the registration.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="activities.registration.phone",
        columns=("activities.registrations.phone",),
        label="Mobiel",
        name_en="Phone",
        help="The phone of the registration.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="activities.registration.team_name",
        columns=("activities.registrations.team_name",),
        label=None,
        name_en="Team name",
        help="The team name of the registration.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="activities.registration.payment_method",
        columns=("activities.registrations.payment_method",),
        label="Betaalmethode",
        name_en="Payment method",
        help="The payment method of the registration.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="activities.registration.remarks",
        columns=("activities.registrations.remarks",),
        label=None,
        name_en="Remarks",
        help="The remarks of the registration.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="activities.registration.form_submission_id",
        columns=("activities.registrations.form_submission_id",),
        label=None,
        name_en="Form submission id",
        help="The form submission id of the registration.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="activities.registration.answer_token",
        columns=("activities.registrations.answer_token",),
        label=None,
        name_en="Answer token",
        help="The answer token of the registration.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="activities.registration_item.quantity",
        columns=("activities.registration_items.quantity",),
        label=None,
        name_en="Quantity",
        help="The quantity of the registration item.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)


# The data the reporting universe stands on that no single stored column is (CR-33 phase 1).
UNIVERSE_ENTRIES: tuple[Attribute, ...] = (
    Attribute(
        key="activities.activity.id",
        columns=("activities.activities.id",),
        label="Activiteitnummer",
        name_en="Id",
        help="Het technische nummer van de activiteit.",
        ai_exposure=AiExposure.INTERNAL,
    ),
)


# Several columns, one datum: the dates of an activity as the fiche reads them, one line.
ACTIVITY_DATES = Attribute(
    key="activities.activity.dates",
    columns=(
        "activities.activity_dates.start_date",
        "activities.activity_dates.end_date",
        "activities.activity_dates.start_time",
        "activities.activity_dates.end_time",
    ),
    label="Datums",
    name_en="Dates",
    help="De dagen en uren van de activiteit, op één regel.",
    ai_exposure=AiExposure.PUBLIC,  # K5
)

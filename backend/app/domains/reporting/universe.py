"""The universe: the semantic layer over the ``reporting`` star (CR-06 §4.2).

A BusinessObjects universe is metadata, not a query: a list of **objects** — the
things a board member picks — each carrying a Dutch name, a type, the SQL it
resolves to, its format, the role that may see it, and one sentence of
explanation. Plus the **join graph**: which dimension attaches to which fact on
which key. Facts never join facts (CR-06 §2.6).

Everything a report can ever ask is declared here. The engine builds SQL from this
declaration and from nothing else, which is what makes "no free SQL, ever" (CR-06
§7.5) a property of the design rather than a promise.

**Names are Dutch, keys are English.** The name is what a board member reads in
the objects pane, so it follows the UI language. The key is an identifier — it
travels in saved selections, in URLs and in tests — so it follows the code
language, and it never changes once shipped: a renamed key silently breaks every
saved report that referenced it.

**The SQL is a template over one view alias.** ``{view}`` is filled in by the
engine with the alias it gave that view. Writing the alias explicitly, instead of
letting a bare column name find its own table, means the gate can extract exactly
which columns an object depends on (``{view}.<column>``) and resolve each against
``information_schema`` — so a view column that disappears turns CI red with the
object's name, instead of turning a report into a 500 in front of a user.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ObjectKind(str, Enum):
    """What a user may do with an object.

    A **dimension** groups and filters. A **measure** aggregates — it always
    carries an aggregate function, and the engine groups by everything else. A
    **detail** is an attribute of a dimension you may show but not group by: it
    would split the grain without adding a question.
    """

    DIMENSION = "dimension"
    MEASURE = "measure"
    DETAIL = "detail"


class Format(str, Enum):
    """How a value is rendered — by the panel, the export and later the chart.

    Kept separate from the SQL type on purpose: ``COUNT`` and ``DAYS`` are both
    integers but do not read the same, and ``MONEY`` is the one thing that must
    never be formatted twice in two places (there is one money formatter).
    """

    COUNT = "count"
    MONEY = "money"
    PERCENTAGE = "percentage"
    DAYS = "days"
    LABEL = "label"
    YEAR = "year"
    DATE = "date"


class Role(str, Enum):
    """Who may put this object in a report.

    Mirrors the screens (CR-06 §2.5), with money as its own fence: what you cannot
    see on a screen you cannot put in a report. ``MEMBER_DETAILS`` exists for the
    person-level details that CR-06 §7.3 keeps out of the universe for now — no
    object carries it yet, and the fence is declared before the first object needs
    it rather than after.

    **Declared, not enforced — in this release (#832, decision of 10 September
    2026).** v2.3.0 adds no new security surface: reporting sits behind
    `require_admin_ui`, the same door as every other admin screen, and the engine
    applies no per-object fence. The role on an object records what must hold once
    that switch is built, as its own change with its own test.

    Half a fence is worse than none: it suggests a protection that is not there,
    and it invites the next reader to trust it. So the declaration is complete and
    the enforcement is absent, rather than both being partial.
    """

    ADMIN = "admin"
    FINANCE = "finance"
    MEMBER_DETAILS = "member_details"


# The classes, in the order the objects pane shows them. A class is how a user
# thinks about the data, not how it is stored.
CLASSES: tuple[str, ...] = ("Leden", "Activiteiten", "Betalingen",
                            "Betaaldetail", "Formulieren", "Operaties", "Tijd")


@dataclass(frozen=True)
class Fact:
    """A fact table: the grain of a report and the only thing measures come from."""

    key: str
    name: str
    # Declared, not enforced (see `Role`): the strictest role any column of this
    # fact will need once the fence is built. A flat dump carries every column,
    # money included, so all three facts read `finance`.
    role: Role
    grain: str
    description: str
    # The columns that identify one row of the fact. The flat dataset export sorts
    # on them so two exports of unchanged data are byte-for-byte the same file —
    # without a unique tail Postgres hands back whatever order the heap has (#761).
    dataset_key: tuple[str, ...] = ()
    # The natural reading order of the fact's rows, for a detail listing. Ends in
    # the unique key (#761): without it, paging a listing shows the same row twice
    # and never another.
    detail_order: tuple[str, ...] = ()
    # How many distinct people a group of this fact covers, as SQL over its view.
    # The small-cell threshold (#841) needs to know the size of a cell before it
    # can protect it; a fact that cannot say leaves the threshold inapplicable and
    # therefore refuses a sensitive grouping outright.
    people_sql: str = ""


@dataclass(frozen=True)
class Dimension:
    """A dimension view and the column that identifies one of its rows.

    ``key_column`` is what makes a default sort end in a unique key (#761): the
    engine appends the grouping expressions, and a dimension that cannot identify
    its own rows would leave the order to the heap.
    """

    key: str
    name: str
    key_column: str


@dataclass(frozen=True)
class Join:
    """How a dimension attaches to a fact.

    ``pairs`` are ``(fact_column, dimension_column)``; ``tenant_id`` is added by
    the engine on every join, unconditionally, so a dimension row can never be
    borrowed from another tenant.
    """

    fact: str
    dimension: str
    pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class UniverseObject:
    """One thing a board member can put in a report."""

    key: str
    name: str
    klass: str
    kind: ObjectKind
    view: str
    sql: str
    format: Format
    role: Role
    description: str
    # Measures name the fact they aggregate. A measure is the only object that
    # decides the grain, which is why the fan-trap check reads exactly this field.
    fact: str | None = None
    # A dimension that points at a record: the panel turns its cell into a link
    # (CR-06 §5, drill-down). The value comes from `drill_sql`, not from the label.
    drill: str | None = None
    drill_sql: str | None = None
    # A dimension that cuts people into groups small enough to recognise somebody
    # by. Grouping on one of these turns on the small-cell threshold (#841).
    sensitive: bool = False
    # A measure that may be added across merged rows. True for a SUM or a plain
    # COUNT; false for an average or a distinct count, where the sum of the parts
    # is not the whole — the merged row then shows nothing rather than a number
    # that looks right.
    additive: bool = True

    @property
    def is_measure(self) -> bool:
        return self.kind is ObjectKind.MEASURE

    @property
    def is_groupable(self) -> bool:
        return self.kind is ObjectKind.DIMENSION


FACTS: tuple[Fact, ...] = (
    Fact(
        key="f_memberships",
        name="Lidmaatschappen",
        role=Role.FINANCE,
        grain="één rij per gezin per lidmaatschapsjaar",
        description=(
            "Lidmaatschappen per gezin per jaar, inclusief de gezinnen die dat jaar "
            "níét vernieuwden — anders is 'hoeveel vervallen er?' niet te tellen."
        ),
        dataset_key=("household_id", "year"),
        people_sql="SUM({view}.person_count)",
    ),
    Fact(
        key="f_registrations",
        name="Inschrijvingen",
        role=Role.FINANCE,
        grain="één rij per inschrijfregel",
        description=(
            "Inschrijvingen op activiteiten, één rij per gekozen product. Een "
            "inschrijving zonder producten telt mee met aantal 0."
        ),
        dataset_key=("registration_id", "registration_line_id"),
        people_sql="COUNT(DISTINCT {view}.person_id)",
    ),
    Fact(
        key="f_payments",
        name="Betalingen",
        role=Role.FINANCE,
        grain="één rij per betaalrecord",
        description=(
            "Vorderingen en terugbetalingen. Een terugbetaling draagt een negatief "
            "bedrag, dus elke som is meteen een nettobedrag."
        ),
        dataset_key=("payment_id",),
        # A payment belongs to a household, not to a person; counting households
        # is the closest honest measure of how few people a cell covers.
        people_sql="COUNT(DISTINCT {view}.household_id)",
        # Newest first, like the payments screen and its export.
        detail_order=("{view}.created_at DESC", "{view}.payment_id"),
    ),
    Fact(
        key="f_membership_persons",
        name="Leden (personen)",
        role=Role.ADMIN,
        grain="één rij per persoon per lidmaatschapsjaar",
        description=(
            "Wie er lid is, op persoonsniveau — de korrel die vraag 8 nodig heeft. "
            "Een persoon in twee gezinnen telt één keer."
        ),
        dataset_key=("year", "person_id"),
        people_sql="COUNT({view}.person_id)",
    ),
    Fact(
        key="f_form_submissions",
        name="Formulierinzendingen",
        role=Role.ADMIN,
        grain="één rij per inzending",
        description=(
            "Inzendingen op formulieren. Zonder naam of e-mailadres: een rapport "
            "telt inzendingen, het formulierscherm toont wat iemand schreef."
        ),
        dataset_key=("submission_id",),
    ),
    Fact(
        key="f_operations",
        name="Operaties",
        role=Role.ADMIN,
        grain="één rij per open werkbanktaak",
        description=(
            "De werkvoorraad: wat er open staat in de werkbank. Een definitief "
            "mislukte e-mail en een te bevestigen terugbetaling zitten er als "
            "taaksoort in — niet als aparte rij ernaast. Antwoordt morgen anders, "
            "en dat is wat een werkvoorraad hoort te doen."
        ),
        dataset_key=("kind", "item_id"),
    ),
)

DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(key="d_date", name="Datum", key_column="date_key"),
    Dimension(key="d_activity", name="Activiteit", key_column="activity_id"),
    Dimension(key="d_household", name="Gezin", key_column="household_id"),
    Dimension(key="d_person", name="Persoon", key_column="person_id"),
    Dimension(key="d_payment_method", name="Betaalwijze", key_column="code"),
    Dimension(key="d_payment_status", name="Betaalstatus", key_column="code"),
    Dimension(key="d_membership_status", name="Lidmaatschapsstatus", key_column="code"),
    Dimension(key="d_form", name="Formulier", key_column="form_id"),
)

JOINS: tuple[Join, ...] = (
    Join("f_payments", "d_date", (("date_key", "date_key"),)),
    Join("f_payments", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_payments", "d_household", (("household_id", "household_id"),)),
    Join("f_payments", "d_payment_method", (("method_code", "code"),)),
    Join("f_payments", "d_payment_status", (("status_code", "code"),)),
    Join("f_registrations", "d_date", (("date_key", "date_key"),)),
    Join("f_registrations", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_registrations", "d_person", (("person_id", "person_id"),)),
    Join("f_registrations", "d_payment_method", (("method_code", "code"),)),
    Join("f_memberships", "d_household", (("household_id", "household_id"),)),
    Join("f_memberships", "d_membership_status", (("status_code", "code"),)),
    Join("f_membership_persons", "d_person", (("person_id", "person_id"),)),
    Join("f_membership_persons", "d_household", (("household_id", "household_id"),)),
    Join("f_form_submissions", "d_form", (("form_id", "form_id"),)),
    Join("f_form_submissions", "d_date", (("date_key", "date_key"),)),
    Join("f_operations", "d_date", (("date_key", "date_key"),)),
)


def _boolean_label(column: str) -> str:
    """A boolean reads as Ja/Nee in a report, never as ``true``."""
    return f"CASE WHEN {{view}}.{column} THEN 'Ja' ELSE 'Nee' END"


OBJECTS: tuple[UniverseObject, ...] = (
    # ── Tijd ────────────────────────────────────────────────────────────────
    UniverseObject(
        key="date_year", name="Jaar", klass="Tijd", kind=ObjectKind.DIMENSION,
        view="d_date", sql="{view}.year", format=Format.YEAR, role=Role.ADMIN,
        description="Kalenderjaar van de gebeurtenis (inschrijfdatum of aanmaakdatum van de betaling).",
    ),
    UniverseObject(
        key="date_quarter", name="Kwartaal", klass="Tijd", kind=ObjectKind.DIMENSION,
        view="d_date", sql="{view}.quarter", format=Format.COUNT, role=Role.ADMIN,
        description="Kwartaal 1 tot 4 binnen het jaar.",
    ),
    UniverseObject(
        key="date_month", name="Maand", klass="Tijd", kind=ObjectKind.DIMENSION,
        view="d_date", sql="{view}.year_month", format=Format.LABEL, role=Role.ADMIN,
        description="Jaar en maand als 2026-03, zodat maanden vanzelf chronologisch staan.",
    ),
    UniverseObject(
        key="date_month_label", name="Maand voluit", klass="Tijd", kind=ObjectKind.DETAIL,
        view="d_date", sql="{view}.month_year_label", format=Format.LABEL, role=Role.ADMIN,
        description="Dezelfde maand als 'maart 2026'. Een detail: sorteren doe je op Maand.",
    ),
    UniverseObject(
        key="date_day", name="Datum", klass="Tijd", kind=ObjectKind.DIMENSION,
        view="d_date", sql="{view}.date_key", format=Format.DATE, role=Role.ADMIN,
        description="De dag zelf.",
    ),
    UniverseObject(
        key="membership_year", name="Lidmaatschapsjaar", klass="Tijd",
        kind=ObjectKind.DIMENSION, view="f_memberships", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN, fact="f_memberships",
        description=(
            "Het jaar waarvoor het lidgeld geldt. Staat los van Jaar: een lidmaatschap "
            "heeft een lidmaatschapsjaar, geen datum."
        ),
    ),

    # ── Leden ───────────────────────────────────────────────────────────────
    UniverseObject(
        key="membership_households", name="Aantal gezinnen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.is_member)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_memberships",
        description="Gezinnen met een lidmaatschap in dat jaar.",
    ),
    UniverseObject(
        key="membership_persons", name="Aantal personen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.person_count)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_memberships",
        description="Personen in de gezinnen met een lidmaatschap in dat jaar.",
    ),
    UniverseObject(
        key="membership_new", name="Nieuw", klass="Leden", kind=ObjectKind.MEASURE,
        view="f_memberships", sql="SUM({view}.is_new)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_memberships",
        description="Gezinnen die dat jaar lid werden en het jaar ervoor niet waren.",
    ),
    UniverseObject(
        key="membership_renewed", name="Vernieuwd", klass="Leden", kind=ObjectKind.MEASURE,
        view="f_memberships", sql="SUM({view}.is_renewed)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_memberships",
        description="Gezinnen die dat jaar én het jaar ervoor lid waren.",
    ),
    UniverseObject(
        key="membership_lapsed", name="Vervallen", klass="Leden", kind=ObjectKind.MEASURE,
        view="f_memberships", sql="SUM({view}.is_lapsed)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_memberships",
        description="Gezinnen die het jaar ervoor lid waren en dat jaar niet vernieuwden.",
    ),
    UniverseObject(
        key="membership_amount_charged", name="Lidgeld gefactureerd", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.amount_charged)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description="Som van de vorderingen op het lidgeld, terugbetalingen afgetrokken.",
    ),
    UniverseObject(
        key="membership_amount_paid", name="Lidgeld ontvangen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.amount_paid)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description="Wat er effectief op het lidgeld ontvangen is.",
    ),
    UniverseObject(
        key="membership_open_amount", name="Lidgeld openstaand", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.open_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description="Gefactureerd min ontvangen.",
    ),
    UniverseObject(
        key="membership_status", name="Lidmaatschapsstatus", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_membership_status", sql="{view}.label",
        format=Format.LABEL, role=Role.ADMIN,
        description="Nieuw, vernieuwd of vervallen.",
    ),
    UniverseObject(
        key="household_municipality", name="Gemeente", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_household", sql="{view}.municipality",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Gemeente van het gezin, uit de postcodetabel.",
    ),
    UniverseObject(
        key="household_postal_code", name="Postcode", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_household", sql="{view}.postal_code",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Postcode van het gezin.",
    ),
    UniverseObject(
        key="household_size_group", name="Gezinsgrootte", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_household", sql="{view}.household_size_group",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Aantal personen in het gezin, in klassen.",
    ),
    UniverseObject(
        key="household_member_since", name="Lid sinds", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_household", sql="{view}.member_since_year",
        format=Format.YEAR, role=Role.ADMIN, sensitive=True,
        description="Het eerste jaar waarvoor dit gezin een lidmaatschap heeft.",
    ),
    UniverseObject(
        key="household", name="Gezin", klass="Leden", kind=ObjectKind.DIMENSION,
        view="d_household", sql="{view}.household_id", format=Format.COUNT,
        role=Role.ADMIN, sensitive=True, drill="household", drill_sql="{view}.household_id",
        description="Het gezin zelf. Klik door naar het gezinsdossier.",
    ),
    UniverseObject(
        key="person_age_group", name="Leeftijdsgroep", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_person", sql="{view}.age_group",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Leeftijdsklasse van de inschrijver, berekend op vandaag.",
    ),
    UniverseObject(
        key="person_gender", name="Geslacht", klass="Leden", kind=ObjectKind.DIMENSION,
        view="d_person", sql="{view}.gender_label", format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Geslacht van de inschrijver.",
    ),
    UniverseObject(
        key="person_relation_type", name="Relatietype", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_person", sql="{view}.relation_type_label",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Hoofdlid, partner of (meerderjarig) kind binnen het gezin.",
    ),

    # ── Activiteiten ────────────────────────────────────────────────────────
    UniverseObject(
        key="registration_count", name="Aantal inschrijvingen", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations",
        sql="COUNT(DISTINCT {view}.registration_id)", format=Format.COUNT,
        role=Role.ADMIN, additive=False, fact="f_registrations",
        description="Aantal inschrijvingen, ongeacht hoeveel producten erop staan.",
    ),
    UniverseObject(
        key="registration_quantity", name="Aantal stuks", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations", sql="SUM({view}.quantity)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_registrations",
        description="Som van de aantallen op de inschrijfregels — de bezetting.",
    ),
    UniverseObject(
        key="registration_amount", name="Inschrijfbedrag", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations", sql="SUM({view}.line_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_registrations",
        description=(
            "Waarde van de inschrijfregels aan de prijs van dat moment. Gratis "
            "producten en 'ter plaatse te betalen' tellen niet mee."
        ),
    ),
    UniverseObject(
        key="activity", name="Activiteit", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="d_activity", sql="{view}.activity_name", format=Format.LABEL,
        role=Role.ADMIN, drill="activity", drill_sql="{view}.activity_id",
        description="Naam van de activiteit. Klik door naar het activiteitdossier.",
    ),
    UniverseObject(
        key="activity_year", name="Jaar van de activiteit", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity", sql="{view}.activity_year",
        format=Format.YEAR, role=Role.ADMIN,
        description=(
            "Het jaar van de eerste datum van de activiteit. Het model kent geen "
            "seizoen (CR-06 §12)."
        ),
    ),
    UniverseObject(
        key="activity_location", name="Locatie", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity", sql="{view}.location",
        format=Format.LABEL, role=Role.ADMIN,
        description="Waar de activiteit doorgaat.",
    ),
    UniverseObject(
        key="activity_cancelled", name="Geannuleerd", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity",
        sql=_boolean_label("is_cancelled"), format=Format.LABEL, role=Role.ADMIN,
        description="Of de activiteit geannuleerd werd.",
    ),
    UniverseObject(
        key="activity_members_only", name="Enkel voor leden", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity",
        sql=_boolean_label("members_only"), format=Format.LABEL, role=Role.ADMIN,
        description="Of enkel leden zich mochten inschrijven.",
    ),
    UniverseObject(
        key="component", name="Onderdeel", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="f_registrations", sql="{view}.component_name", format=Format.LABEL,
        role=Role.ADMIN, fact="f_registrations",
        description="Het onderdeel van de activiteit waarop ingeschreven werd.",
    ),
    UniverseObject(
        key="product", name="Product", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="f_registrations", sql="{view}.product_name", format=Format.LABEL,
        role=Role.ADMIN, fact="f_registrations",
        description="Het gekozen product. 'Geen product' bij een inschrijving zonder regels.",
    ),
    UniverseObject(
        key="registration_type", name="Inschrijfvorm", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="f_registrations", sql="{view}.registration_type",
        format=Format.LABEL, role=Role.ADMIN, fact="f_registrations",
        description="Individueel of gezin.",
    ),
    UniverseObject(
        key="registration_has_team", name="Ploegnaam ingevuld", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="f_registrations", sql=_boolean_label("has_team"),
        format=Format.LABEL, role=Role.ADMIN, fact="f_registrations",
        description="Of er een ploegnaam ingevuld werd.",
    ),

    # ── Betalingen ──────────────────────────────────────────────────────────
    # Elk object in deze klasse draagt de rol `finance`: CR-06 §5.1 zegt dat een
    # FINANCE-only gebruiker precies deze klasse ziet, en dat klopt alleen als de
    # klasse en de rol samenvallen.
    UniverseObject(
        key="payment_amount", name="Te betalen", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Som van de bedragen; terugbetalingen tellen negatief mee.",
    ),
    UniverseObject(
        key="payment_amount_paid", name="Ontvangen", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.amount_paid)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Wat er effectief ontvangen is.",
    ),
    UniverseObject(
        key="payment_open_amount", name="Openstaand", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.open_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Te betalen min ontvangen.",
    ),
    UniverseObject(
        key="payment_refunded", name="Terugbetaald", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments",
        sql="SUM(CASE WHEN {view}.record_type = 'refund' THEN -{view}.amount ELSE 0 END)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Terugbetaalde bedragen als positief getal.",
    ),
    UniverseObject(
        key="payment_count", name="Aantal betalingen", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments",
        sql="COUNT(DISTINCT {view}.payment_id)", format=Format.COUNT,
        role=Role.FINANCE, additive=False, fact="f_payments",
        description="Aantal betaalrecords, vorderingen en terugbetalingen samen.",
    ),
    UniverseObject(
        key="payment_days_to_paid", name="Gemiddelde betaaltermijn", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="AVG({view}.days_to_paid)",
        format=Format.DAYS, role=Role.FINANCE, additive=False, fact="f_payments",
        description="Gemiddeld aantal dagen tussen aanmaak en betaling, over de betaalde records.",
    ),
    UniverseObject(
        key="payment_method", name="Betaalwijze", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_method", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description="Online, overschrijving of cash.",
    ),
    UniverseObject(
        key="payment_status", name="Betaalstatus", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_status", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description="In afwachting, betaald, mislukt of geannuleerd.",
    ),
    UniverseObject(
        key="payment_type", name="Soort", klass="Betalingen", kind=ObjectKind.DIMENSION,
        view="f_payments", sql="{view}.record_type_label", format=Format.LABEL,
        role=Role.FINANCE, fact="f_payments",
        description="Vordering of terugbetaling.",
    ),
    UniverseObject(
        key="payment_payable_type", name="Waarvoor", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.payable_type_label",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Lidgeld of activiteit.",
    ),
    UniverseObject(
        key="payment_age_bucket", name="Ouderdom", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.age_bucket",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Hoe lang een vordering al openstaat, in klassen. Betaalde records staan op 'Betaald'.",
    ),
    UniverseObject(
        key="payment_record", name="Betaling", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.payment_id",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        drill="payment", drill_sql="{view}.payment_id",
        description="Het betaalrecord zelf. Klik door naar de betalingenpagina.",
    ),

    UniverseObject(
        key="membership_person_count", name="Aantal leden (personen)", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_membership_persons",
        sql="COUNT({view}.person_id)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_membership_persons",
        description=(
            "Personen met een lidmaatschap in dat jaar. Eén rij per persoon per "
            "jaar, dus tellen is optellen."
        ),
    ),
    UniverseObject(
        key="membership_person_year", name="Jaar van het lidmaatschap", klass="Tijd",
        kind=ObjectKind.DIMENSION, view="f_membership_persons", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN, fact="f_membership_persons",
        description="Het jaar waarvoor deze persoon lid was.",
    ),

    # ── Betaaldetail ────────────────────────────────────────────────────────
    # The row-level fields of a payment, for a listing rather than a summary.
    # A class of their own and not beside the measures, for two reasons: their
    # names would otherwise collide ("Te betalen" is both a total and a row
    # value), and a user choosing between "the sum of the amounts" and "the
    # amount on this row" deserves to see that they are different kinds of thing.
    #
    # `payment_payable_label` carries a person's name. That is allowed since
    # CR-06 §7.3 (10 September 2026) and bounded by the role that reaches the
    # screen; it declares `member_details` so the later per-object switch has
    # something to turn on.
    UniverseObject(
        key="payment_payable_label", name="Waarvoor", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.payable_label",
        format=Format.LABEL, role=Role.MEMBER_DETAILS, fact="f_payments",
        description="Voor wie en waarvoor deze betaling is — de inschrijver en de activiteit, of het hoofdlid en het lidmaatschapsjaar.",
    ),
    UniverseObject(
        key="payment_kind_label", name="Soort", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.payable_type_label",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Lidgeld of activiteit.",
    ),
    UniverseObject(
        key="payment_type_label", name="Type", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.record_type_label",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Vordering of terugbetaling.",
    ),
    UniverseObject(
        key="payment_method_label", name="Betaalwijze", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="d_payment_method", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description="Online, overschrijving of cash.",
    ),
    UniverseObject(
        key="payment_status_label", name="Status", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="d_payment_status", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description="In afwachting, betaald, mislukt of geannuleerd.",
    ),
    UniverseObject(
        key="payment_ogm", name="Mededeling (OGM)", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments",
        sql="{view}.structured_communication", format=Format.LABEL,
        role=Role.FINANCE, fact="f_payments",
        description="De gestructureerde mededeling op een overschrijving.",
    ),
    UniverseObject(
        key="payment_due", name="Te betalen", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.amount",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Het bedrag van deze ene regel. Een terugbetaling is negatief.",
    ),
    UniverseObject(
        key="payment_received", name="Betaald", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.amount_paid",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Wat er op deze regel ontvangen is.",
    ),
    UniverseObject(
        key="payment_balance", name="Saldo", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.open_amount",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Te betalen min betaald, op deze regel.",
    ),
    UniverseObject(
        key="payment_paid_on", name="Betaald op", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.paid_date",
        format=Format.DATE, role=Role.FINANCE, fact="f_payments",
        description="Wanneer de betaling binnenkwam.",
    ),
    UniverseObject(
        key="payment_note", name="Notitie", klass="Betaaldetail",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.note",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Wat de penningmeester erbij schreef.",
    ),

    # ── Formulieren ─────────────────────────────────────────────────────────
    UniverseObject(
        key="submission_count", name="Aantal inzendingen", klass="Formulieren",
        kind=ObjectKind.MEASURE, view="f_form_submissions",
        sql="COUNT(DISTINCT {view}.submission_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_form_submissions", additive=False,
        description="Aantal inzendingen op een formulier.",
    ),
    UniverseObject(
        key="submission_answers", name="Aantal antwoorden", klass="Formulieren",
        kind=ObjectKind.MEASURE, view="f_form_submissions",
        sql="SUM({view}.answer_count)", format=Format.COUNT, role=Role.ADMIN,
        fact="f_form_submissions",
        description="Som van de ingevulde antwoorden — hoeveel er werkelijk ingevuld is.",
    ),
    UniverseObject(
        key="form", name="Formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.form_name",
        format=Format.LABEL, role=Role.ADMIN, drill="form",
        drill_sql="{view}.form_id",
        description="Naam van het formulier. Klik door naar de formulierbouwer.",
    ),
    UniverseObject(
        key="form_status", name="Status van het formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.form_status_label",
        format=Format.LABEL, role=Role.ADMIN,
        description="Concept, gepubliceerd of gesloten.",
    ),
    UniverseObject(
        key="form_anonymous", name="Anoniem formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.is_anonymous_label",
        format=Format.LABEL, role=Role.ADMIN,
        description="Of het formulier anoniem ingevuld wordt.",
    ),
    UniverseObject(
        key="submission_edited", name="Achteraf gewijzigd", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="f_form_submissions",
        sql=_boolean_label("was_edited"), format=Format.LABEL, role=Role.ADMIN,
        fact="f_form_submissions",
        description="Of de inzender zijn antwoord nadien nog aangepast heeft.",
    ),

    # ── Operaties ───────────────────────────────────────────────────────────
    UniverseObject(
        key="operation_count", name="Aantal open items", klass="Operaties",
        kind=ObjectKind.MEASURE, view="f_operations",
        sql="COUNT(DISTINCT {view}.item_id)", format=Format.COUNT, role=Role.ADMIN,
        fact="f_operations", additive=False,
        description="Hoeveel er nog ligt te wachten.",
    ),
    UniverseObject(
        key="operation_age_days", name="Gemiddelde ouderdom", klass="Operaties",
        kind=ObjectKind.MEASURE, view="f_operations", sql="AVG({view}.age_days)",
        format=Format.DAYS, role=Role.ADMIN, fact="f_operations", additive=False,
        description="Gemiddeld aantal dagen dat een open item al wacht.",
    ),
    UniverseObject(
        key="operation_kind", name="Soort", klass="Operaties",
        kind=ObjectKind.DIMENSION, view="f_operations", sql="{view}.kind_label",
        format=Format.LABEL, role=Role.ADMIN, fact="f_operations",
        description="Wat voor taak het is: een terugbetaling bevestigen, een mislukte e-mail, een webhook die afwijkt, een mislukte achtergrondtaak.",
    ),
    UniverseObject(
        key="operation_detail", name="Onderwerp", klass="Operaties",
        kind=ObjectKind.DIMENSION, view="f_operations", sql="{view}.detail",
        format=Format.LABEL, role=Role.ADMIN, fact="f_operations",
        description="Waar de taak over gaat: een betaalrecord, een e-mail, een achtergrondtaak.",
    ),
    UniverseObject(
        key="operation_role", name="Voor welke rol", klass="Operaties",
        kind=ObjectKind.DIMENSION, view="f_operations", sql="{view}.required_role",
        format=Format.LABEL, role=Role.ADMIN, fact="f_operations",
        description="Wie de taak hoort op te pakken.",
    ),
    UniverseObject(
        key="operation_age_bucket", name="Ouderdom", klass="Operaties",
        kind=ObjectKind.DIMENSION, view="f_operations", sql="{view}.age_bucket",
        format=Format.LABEL, role=Role.ADMIN, fact="f_operations",
        description="Hoe lang een item al open staat, in klassen.",
    ),
)


# ── Lookups ──────────────────────────────────────────────────────────────────

BY_KEY: dict[str, UniverseObject] = {o.key: o for o in OBJECTS}
FACT_BY_KEY: dict[str, Fact] = {f.key: f for f in FACTS}
DIMENSION_BY_KEY: dict[str, Dimension] = {d.key: d for d in DIMENSIONS}


def joins_for(fact: str) -> dict[str, Join]:
    """The dimensions reachable from ``fact``, keyed by dimension view."""
    return {j.dimension: j for j in JOINS if j.fact == fact}


def objects_in_pane_order() -> list[UniverseObject]:
    """Every object, in class order and then declaration order.

    Declaration order, not alphabetical: the order in this file is the order a
    board member reads them in, and it is chosen (measures before the dimensions
    that qualify them).
    """
    order = {name: i for i, name in enumerate(CLASSES)}
    return sorted(OBJECTS, key=lambda o: (order.get(o.klass, len(order)),
                                          OBJECTS.index(o)))


def classes_with_objects() -> list[tuple[str, list[UniverseObject]]]:
    """The objects pane: classes with their objects, empty classes dropped."""
    per_class: dict[str, list[UniverseObject]] = {}
    for obj in objects_in_pane_order():
        per_class.setdefault(obj.klass, []).append(obj)
    return [(name, per_class[name]) for name in CLASSES if name in per_class]

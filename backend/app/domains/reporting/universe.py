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

from app.kernel.attributes import AiExposure, attribute
from app.kernel.codes import TechnicalEnum


class ObjectKind(str, TechnicalEnum):
    """What a user may do with an object.

    `TechnicalEnum` (CR-12 §B4.9): how the engine may use an object — a rule
    of the engine, never stored in a column and never shown to a reader.

    A **dimension** groups and filters. A **measure** aggregates — it always
    carries an aggregate function, and the engine groups by everything else. A
    **detail** is an attribute of a dimension you may show but not group by: it
    would split the grain without adding a question.
    """

    DIMENSION = "dimension"
    MEASURE = "measure"
    DETAIL = "detail"


class Format(str, TechnicalEnum):
    """How a value is rendered — by the panel, the export and later the chart.

    `TechnicalEnum` (CR-12 §B4.9): the renderer branches on it; nobody reads
    it, and it is never stored.

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


class Grain(str, TechnicalEnum):
    """The time grain of a date object (CR-33 F4): the date's own attribute names the
    datum, the grain says how far it is rolled up. The universe composes the name
    (`Inschrijfdatum › Jaar`) and the description from the date's entry and the grain,
    so a date is written once and four objects read it."""

    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    DAY = "day"

    @property
    def word(self) -> str:
        """The word in the object's name."""
        return {"year": "Jaar", "quarter": "Kwartaal", "month": "Maand", "day": "Datum"}[self.value]

    @property
    def phrase(self) -> str:
        """The words of the description's last sentence: *Opgerold tot jaar.*"""
        return {"year": "jaar", "quarter": "kwartaal", "month": "maand", "day": "datum"}[self.value]


class Role(str, TechnicalEnum):
    """Who may put this object in a report.

    **`TechnicalEnum` (CR-12 §B4.9), and not the role list** (CR-12 phase 4
    residue, 27 September 2026). This docstring used to promise that the enum
    would point at `auth`'s role list once that list moved there. It moved, and
    the promise does not hold: this is an access fence *per report object*,
    never stored and never shown, and ``MEMBER_DETAILS`` is a fence that no
    role in `auth` is called. Replacing it with `auth.models.Role` would drop
    that fence from every object that declares it.

    Mirrors the screens (CR-06 §2.5), with money as its own fence: what you cannot
    see on a screen you cannot put in a report. ``MEMBER_DETAILS`` exists for the
    person-level details that CR-06 §7.3 keeps out of the universe for now — no
    object carries it yet, and the fence is declared before the first object needs
    it rather than after.

    **Declared, not enforced — in this release (#832, decision of 10 September
    2026).** v2.3.0 adds no new security surface: reporting sits behind
    its own rights (`report.view`, `report.manage`), and the engine
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
# "Betaaldetail" is gone since #871. It was the only class named after a SHAPE
# instead of a subject, and that split is what hid the collisions: two objects
# called "Soort" and two called "Te betalen", each pair meaning something
# different, invisible as long as they sat in separate classes. Inside one class
# they had to be resolved. Four of those "details" turned out to be the same
# expression as an existing dimension and simply went.
CLASSES: tuple[str, ...] = ("Leden", "Activiteiten", "Betalingen", "Formulieren", "Taken")


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
    #: Hoe fijn de datum van dit feit gelezen mag worden. "day" voor een echte
    #: datum; "year" voor de twee lidmaatschapsfeiten, waar de dag 1 januari is en
    #: dus verzonnen (#894).
    date_grain: str = "day"
    # The natural reading order of the fact's rows, for a detail listing. Ends in
    # the unique key (#761): without it, paging a listing shows the same row twice
    # and never another.
    detail_order: tuple[str, ...] = ()
    # How many distinct people a group of this fact covers, as SQL over its view.
    # Declared and not enforced since 14 September 2026: the small-cell threshold
    # that needed this count was removed, so no query asks for it any more. It
    # records which facts *could* answer "how many people are behind this group",
    # and that stays true whether or not a rule leans on it.
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
    #: De weergave waaruit deze dimensie leest, als die anders heet dan de sleutel.
    #: Zo kan één weergave twee keer in een rapport staan onder een eigen alias:
    #: `d_paid_date` en `d_date` lezen allebei uit `reporting.d_date`, maar hangen
    #: aan een andere kolom van het feit (#895). Leeg = de sleutel zelf.
    source_view: str = ""
    #: Kan deze dimensie MEER DAN ÉÉN rij per koppelsleutel hebben? (#1114)
    #:
    #: Zo ja, dan vermenigvuldigt een join de rijen van het feit eronder, en telt
    #: elke maat die niet op `DISTINCT` steunt dubbel. `d_activity_organiser` is
    #: vandaag de enige: een activiteit heeft er tot drie.
    #:
    #: De meeste dimensies staan hier op False omdat een unieke sleutel dat
    #: afdwingt — `d_address` heeft er een op `person_id`, `d_board_member` één per
    #: gezin. Zet dit dus niet op gevoel: kijk de constraint na. Stond het op False
    #: terwijl de databank het niet afdwingt, dan bewaakt de poort iets wat niet
    #: waar is.
    #:
    #: `test_reporting_fanout_gate.py` dwingt af wat dit veld belooft.
    multi_row: bool = False

    @property
    def source(self) -> str:
        return self.source_view or self.key


@dataclass(frozen=True)
class Join:
    """How a dimension attaches — to a fact, or to another dimension.

    ``pairs`` are ``(left_column, right_column)``; ``tenant_id`` is added by the
    engine on every join, unconditionally, so a dimension row can never be
    borrowed from another tenant.

    ``left`` is usually a fact, and then this is the plain star. It may also be
    another **dimension**, which makes a snowflake: the board member hangs off the
    household, the address off the person. The engine follows the chain and joins
    in dependency order.

    The direction is not free. A chained dimension must sit at the same grain as
    the one it hangs off, or the join multiplies the fact underneath it — the
    address hangs off `d_person` and not off `d_member` for exactly that reason: a
    household with three addressed people would count three times.
    """

    left: str
    dimension: str
    pairs: tuple[tuple[str, str], ...]

    @property
    def fact(self) -> str:
        """The old name of ``left``, kept for readability at the call sites."""
        return self.left


@dataclass(frozen=True)
class UniverseObject:
    """One thing a board member can put in a report."""

    key: str
    #: The attribute (CR-33) this object stands on: its label is the object's name, its
    #: help the start of the description. A key of `kernel/attributes.py`.
    attribute: str
    klass: str
    kind: ObjectKind
    view: str
    sql: str
    format: Format
    role: Role
    # CR-07 §5.1: hoe ver dit object naar een taalmodel mag reizen. GEEN default —
    # zie AiExposure. Staat hier tussen de verplichte velden zodat een nieuw object
    # zonder classificatie niet eens importeert.
    ai_exposure: AiExposure
    # Measures name the fact they aggregate. A measure is the only object that
    # decides the grain, which is why the fan-trap check reads exactly this field.
    fact: str | None = None
    #: A date object rolled up to a grain: the name and the description compose it.
    grain: Grain | None = None
    #: A role word composed into the name, `Gemeente (adres)`, for an object that
    #: stands on the same attribute as another in its class.
    qualifier: str = ""
    #: What the REPORT does with the datum and the attribute's help does not say:
    #: "each household counts once on this grain", "a click leads to the dossier".
    #: What the datum IS stands once, in the register (CR-33 F4, C4.5).
    note: str = ""
    # A dimension that points at a record: the panel turns its cell into a link
    # (CR-06 §5, drill-down). The value comes from `drill_sql`, not from the label.
    drill: str | None = None
    drill_sql: str | None = None
    # An expression to ORDER BY instead of the object's own value. For a label
    # that is not sortable as text: `house_number` is a String(10), so "10" sorts
    # before "9". Empty means "sort on the value itself", which is the normal case.
    sort_sql: str = ""
    # CR-07 §5.2: waar het entiteit-id van de rij vandaan komt, voor de tokenisatie.
    # Meestal is dat `drill_sql` — een object dat naar een record wijst, draagt dat id
    # al. Dit veld bestaat voor de objecten die wél een persoon aanwijzen maar géén
    # drill-link horen te krijgen: `member_head_name` mag niet stilzwijgend een
    # klikbare cel in het paneel worden omdat de assistent een id nodig heeft. Leeg =
    # gebruik `drill_sql`.
    entity_sql: str = ""
    # CR-07 §5.2: het woord vóór het id in de token — `gezin-23`, `persoon-90`. Het
    # hoort bij de ENTITEIT waar het id naar wijst en niet bij het object, want
    # 'Hoofdlid' en 'Adres' wijzen allebei een gezin aan: dezelfde rij levert dan
    # twee keer `gezin-23`, en dat is juist wat het model moet zien. Verplicht zodra
    # `ai_exposure` op tokenised staat — anders valt er niets te tokeniseren.
    token_prefix: str = ""
    # A dimension that cuts people into groups small enough to recognise somebody
    # by: municipality, age group, household size. **Declared and not enforced**
    # since 14 September 2026, when the small-cell threshold that read this flag was
    # removed — inside the back office a report shows what it counted. What may not
    # travel to a language model is a different question and is answered by
    # `ai_exposure`, because a count is not personal data.
    #
    # It stays because it describes the DATA and that description is still true; the
    # generated documentation says in as many words that nothing acts on it, so
    # nobody reads it as a protection that is not there.
    sensitive: bool = False
    # Whether a measure may be added across groups that were rolled together. True
    # for a SUM or a plain COUNT; false for an average or a distinct count, where
    # the sum of the parts is not the whole.
    #
    # Declared and not enforced, for the same reason and since the same date: the
    # merged row it protected no longer exists. It is not wired to anything — the
    # result column stopped carrying it, because a field travelling to no reader is
    # the kind of thing that looks like a working mechanism.
    additive: bool = True
    # #975: whether the object is offered to a PERSON — in the objects pane and in
    # the assistant's catalogue. False for an object that exists only for the
    # server to filter on. It stays a full universe object otherwise: validated,
    # documented, resolvable, and refused by the same rules as every other one.
    in_pane: bool = True

    @property
    def name(self) -> str:
        """What the object is called: the attribute's label, with the grain word and the
        qualifier composed in (`Inschrijfdatum › Jaar`, `Gemeente (adres)`). CR-33 F4."""
        text = attribute(self.attribute).text
        if self.grain is not None:
            text = f"{text} › {self.grain.word}"
        if self.qualifier:
            text = f"{text} ({self.qualifier})"
        return text

    @property
    def description(self) -> str:
        """What the object means: the attribute's help, then the grain's sentence for a
        date, then the note on what the report does with it."""
        parts = [attribute(self.attribute).help]
        if self.grain is not None:
            parts.append(f"Opgerold tot {self.grain.phrase}.")
        if self.note:
            parts.append(self.note)
        return " ".join(parts)

    @property
    def entity_source(self) -> str:
        """De uitdrukking die het entiteit-id levert, of leeg als het object er geen heeft."""
        return self.entity_sql or self.drill_sql or ""

    @property
    def is_measure(self) -> bool:
        return self.kind is ObjectKind.MEASURE

    @property
    def is_groupable(self) -> bool:
        return self.kind is ObjectKind.DIMENSION


# Van grof naar fijn. Een feit dat zijn datum op `year` zet, laat zich niet op de
# soorten daarachter groeperen (#894). The order of `Grain`.
DATE_GRAINS: tuple[str, ...] = tuple(grain.value for grain in Grain)


FACTS: tuple[Fact, ...] = (
    Fact(
        key="f_memberships",
        date_grain="year",
        name="Lidmaatschappen",
        role=Role.FINANCE,
        grain="één rij per gezin per lidmaatschapsjaar",
        description=(
            "Lidmaatschappen per gezin per jaar, inclusief de gezinnen die dat jaar "
            "níét vernieuwden — anders is 'hoeveel vervallen er?' niet te tellen."
        ),
        dataset_key=("member_id", "year"),
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
        people_sql="COUNT(DISTINCT {view}.member_id)",
        # Newest first, like the payments screen and its export.
        detail_order=("{view}.created_at DESC", "{view}.payment_id"),
    ),
    Fact(
        key="f_membership_persons",
        date_grain="year",
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
        key="f_members",
        name="Gezinnen",
        role=Role.ADMIN,
        grain="één rij per gezin",
        description=(
            "Elk gezin, ook een dat nooit lid was. Dat is het verschil met "
            "Lidmaatschappen, dat alleen gezinnen kent die ooit aansloten."
        ),
        dataset_key=("member_id",),
        people_sql="COUNT(DISTINCT {view}.member_id)",
    ),
    Fact(
        key="f_forms",
        name="Formulieren",
        role=Role.ADMIN,
        grain="één rij per formulier",
        description=(
            "Elk formulier, ook een zonder inzendingen. Dat is het verschil met "
            "Inzendingen, dat alleen formulieren kent waarop iemand antwoordde."
        ),
        dataset_key=("form_id",),
    ),
    Fact(
        key="f_activities",
        name="Activiteiten",
        role=Role.ADMIN,
        grain="één rij per activiteit",
        description=(
            "Elke activiteit, ook een zonder inschrijvingen. Dat is het verschil "
            "met Inschrijvingen, dat alleen activiteiten kent waarop iemand "
            "inschreef."
        ),
        dataset_key=("activity_id",),
    ),
    # #1428: the annual programme lists every DATE, and `f_activities` folds the
    # dates of an activity into a first and a last day.
    Fact(
        key="f_activity_dates",
        name="Activiteitsdatums",
        role=Role.ADMIN,
        grain="één rij per datum van een activiteit",
        description=(
            "Elke datum van elke activiteit, ook van een concept of een "
            "geannuleerde. Een reeks van zes avonden is zes rijen — dat is het "
            "verschil met Activiteiten, dat één rij per activiteit telt."
        ),
        dataset_key=("activity_date_id",),
        # In the order of the year, like the programme on paper.
        detail_order=("{view}.date_key", "{view}.start_time", "{view}.activity_date_id"),
    ),
    # #1439: Koen wants every activity ONCE in the programme. "The first date in
    # the year" depends on the year, so the grain is activity × year: a series
    # from November to February is a row in each year, with that year's dates.
    Fact(
        key="f_activity_years",
        name="Activiteiten per jaar",
        role=Role.ADMIN,
        grain="één rij per activiteit per jaar waarin ze een datum heeft",
        description=(
            "Elke activiteit één keer per jaar, met haar eerste datum in dat jaar "
            "en al haar datums van dat jaar in één cel. Een datum telt in het jaar "
            "van haar startdag. Ook concepten en geannuleerde activiteiten."
        ),
        dataset_key=("activity_id", "year"),
        # By the first date, like the programme on paper.
        detail_order=("{view}.first_date", "{view}.first_time", "{view}.activity_id"),
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
        key="f_tasks",
        name="Taken",
        role=Role.ADMIN,
        grain="één rij per werkbanktaak, open én afgehandeld",
        description=(
            "De werkbank: elke taak, met haar status als dimensie. Een definitief "
            "mislukte e-mail en een te bevestigen terugbetaling zitten erin als "
            "taaksoort — niet als aparte rij ernaast. Filter op Open voor de "
            "werkvoorraad; laat het filter weg en je ziet of ze groeit of krimpt."
        ),
        dataset_key=("kind", "item_id"),
        detail_order=("{view}.created_at DESC", "{view}.item_id"),
    ),
)

DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(key="d_date", name="Datum", key_column="date_key"),
    Dimension(key="d_activity", name="Activiteit", key_column="activity_id"),
    # #1077: één rij per organisator, naast de samengevoegde kolom op d_activity.
    # De sleutel is de rij zelf en niet de persoon: dezelfde persoon trekt
    # meerdere activiteiten.
    Dimension(
        key="d_activity_organiser", name="Organisator", key_column="organiser_id", multi_row=True
    ),
    Dimension(key="d_member", name="Gezin", key_column="member_id"),
    Dimension(key="d_person", name="Persoon", key_column="person_id"),
    Dimension(key="d_payment_method", name="Betaalwijze", key_column="code"),
    Dimension(key="d_payment_status", name="Betaalstatus", key_column="code"),
    Dimension(key="d_membership_status", name="Lidmaatschapsstatus", key_column="code"),
    Dimension(key="d_form", name="Formulier", key_column="form_id"),
    Dimension(
        key="d_board_member", name="Verantwoordelijk bestuurslid", key_column="board_member_id"
    ),
    Dimension(key="d_address", name="Adres", key_column="address_id"),
    # #895: een feit heeft vaak méér dan één datum, en tot nu was er maar één
    # oprolbaar. "Betalingen per betaalmaand" was dus niet te vragen, terwijl de
    # kolom er al lag. Een rol is dezelfde datumdimensie onder een eigen alias,
    # aangehaakt op een andere kolom — geen tweede weergave, geen tweede kopie van
    # de kalenderlogica.
    # #901: de gedeelde datum betekende per feit iets ANDERS — bij inschrijvingen
    # de inschrijfdatum, bij betalingen de aanmaakdatum. Eén object met twee
    # betekenissen is erger dan #894, want daar stond de fout zichtbaar in de
    # lijst; hier klopt het rapport en weet alleen wie het feit eronder kent wat
    # er geteld is. Elke sleuteldatum krijgt dus de naam van haar onderwerp, via
    # dezelfde alias-machinerie als de rollen van #895.
    Dimension(
        key="d_registration_date",
        name="Inschrijfdatum",
        key_column="date_key",
        source_view="d_date",
    ),
    Dimension(
        key="d_payment_created", name="Aanmaakdatum", key_column="date_key", source_view="d_date"
    ),
    Dimension(
        key="d_membership_year",
        name="Lidmaatschapsjaar",
        key_column="date_key",
        source_view="d_date",
    ),
    Dimension(
        key="d_member_created",
        name="Aanmaakdatum gezin",
        key_column="date_key",
        source_view="d_date",
    ),
    Dimension(
        key="d_form_created",
        name="Aanmaakdatum formulier",
        key_column="date_key",
        source_view="d_date",
    ),
    Dimension(
        key="d_submission_date", name="Inzenddatum", key_column="date_key", source_view="d_date"
    ),
    Dimension(
        key="d_task_created", name="Aanmaakdatum taak", key_column="date_key", source_view="d_date"
    ),
    Dimension(key="d_paid_date", name="Betaaldatum", key_column="date_key", source_view="d_date"),
    Dimension(key="d_done_date", name="Afhandeldatum", key_column="date_key", source_view="d_date"),
    Dimension(
        key="d_activity_start", name="Startdatum", key_column="date_key", source_view="d_date"
    ),
    Dimension(key="d_activity_end", name="Einddatum", key_column="date_key", source_view="d_date"),
    Dimension(
        key="d_activity_date",
        name="Activiteitsdatum",
        key_column="date_key",
        source_view="d_date",
    ),
    Dimension(
        key="d_year_first_date",
        name="Eerste datum in het jaar",
        key_column="date_key",
        source_view="d_date",
    ),
)

JOINS: tuple[Join, ...] = (
    Join("f_payments", "d_payment_created", (("date_key", "date_key"),)),
    Join("f_payments", "d_paid_date", (("paid_date", "date_key"),)),
    Join("f_payments", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_payments", "d_member", (("member_id", "member_id"),)),
    Join("f_payments", "d_payment_method", (("method_code", "code"),)),
    Join("f_payments", "d_payment_status", (("status_code", "code"),)),
    Join("f_registrations", "d_registration_date", (("date_key", "date_key"),)),
    Join("f_registrations", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_registrations", "d_person", (("person_id", "person_id"),)),
    Join("f_registrations", "d_payment_method", (("method_code", "code"),)),
    # #894: de twee lidmaatschapsfeiten waren de enige die NIET aan `d_date`
    # hingen, en droegen daarom hun eigen jaarkolom — twee feiten, twee objecten,
    # dezelfde woorden in een andere volgorde. De dag is 1 januari en dus
    # verzonnen; `Fact.date_grain` weigert hem fijner te lezen dan een jaar.
    Join("f_memberships", "d_membership_year", (("date_key", "date_key"),)),
    Join("f_memberships", "d_member", (("member_id", "member_id"),)),
    Join("f_memberships", "d_membership_status", (("status_code", "code"),)),
    Join("f_membership_persons", "d_membership_year", (("date_key", "date_key"),)),
    Join("f_membership_persons", "d_person", (("person_id", "person_id"),)),
    Join("f_membership_persons", "d_member", (("member_id", "member_id"),)),
    Join("f_form_submissions", "d_form", (("form_id", "form_id"),)),
    Join("f_forms", "d_form_created", (("date_key", "date_key"),)),
    Join("f_forms", "d_form", (("form_id", "form_id"),)),
    Join("f_form_submissions", "d_submission_date", (("date_key", "date_key"),)),
    Join("f_tasks", "d_task_created", (("date_key", "date_key"),)),
    Join("f_tasks", "d_done_date", (("done_date", "date_key"),)),
    Join("f_members", "d_member_created", (("date_key", "date_key"),)),
    Join("f_members", "d_member", (("member_id", "member_id"),)),
    Join("f_activities", "d_activity", (("activity_id", "activity_id"),)),
    # #1077: ALLEEN aan dit feit, en dat is gemeten. Een activiteit met twee
    # organisatoren levert twee rijen; `f_activities` draagt precies één maat en
    # die is `COUNT(DISTINCT activity_id)`, dus die vermenigvuldiging kan hem niet
    # opblazen. Dezelfde join op `f_payments` zou een `SUM(amount)` verdubbelen —
    # stil, en in geld.
    Join("f_activities", "d_activity_organiser", (("activity_id", "activity_id"),)),
    Join("f_activities", "d_activity_start", (("first_date", "date_key"),)),
    Join("f_activities", "d_activity_end", (("last_date", "date_key"),)),
    # #1428: the activity's own fields reach every one of its dates. Not
    # `d_activity_organiser`: it would split a programme line per organiser; the
    # programme takes the joined column instead.
    Join("f_activity_dates", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_activity_dates", "d_activity_date", (("date_key", "date_key"),)),
    # #1439: one row per activity and year, so `d_activity` cannot multiply it.
    Join("f_activity_years", "d_activity", (("activity_id", "activity_id"),)),
    Join("f_activity_years", "d_year_first_date", (("first_date", "date_key"),)),
    # A snowflake: the board member hangs off the household, not off a fact. Same
    # grain as the household it hangs off, so nothing multiplies (#849).
    Join("d_member", "d_board_member", (("board_member_id", "board_member_id"),)),
    # The address hangs off the PERSON and not off the household: it lives at
    # person grain, and chaining it to the household would count a household once
    # per resident with an address (#850).
    Join("d_person", "d_address", (("person_id", "person_id"),)),
    # The Gezinnen fact reaches the person dimension through the HEAD of the
    # household, which is how a household-grain report gets at the address without
    # the address changing grain. Deliberately on the fact and not on `d_member`:
    # on the dimension it would make the person reachable from memberships and
    # payments too, where it is refused today. Here the person objects describe
    # the hoofdlid, and their descriptions say so.
    Join("f_members", "d_person", (("head_person_id", "person_id"),)),
)


def _boolean_label(column: str) -> str:
    """A boolean reads as Ja/Nee in a report, never as ``true``."""
    return f"CASE WHEN {{view}}.{column} THEN 'Ja' ELSE 'Nee' END"


OBJECTS: tuple[UniverseObject, ...] = (
    # ── Tijd ────────────────────────────────────────────────────────────────
    # #901: elke sleuteldatum draagt de naam van haar onderwerp. Zolang ze allemaal
    # "Datum" heetten, betekende hetzelfde object per feit iets anders — en dat
    # stond nergens op het scherm.
    UniverseObject(
        key="registration_date_year",
        attribute="activities.registration.registered_at",
        grain=Grain.YEAR,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_registration_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_date_quarter",
        attribute="activities.registration.registered_at",
        grain=Grain.QUARTER,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_registration_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_date_month",
        attribute="activities.registration.registered_at",
        grain=Grain.MONTH,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_registration_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_date_day",
        attribute="activities.registration.registered_at",
        grain=Grain.DAY,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_registration_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_created_year",
        attribute="payment.payment_record.created_at",
        grain=Grain.YEAR,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_created",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_created_quarter",
        attribute="payment.payment_record.created_at",
        grain=Grain.QUARTER,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_created",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_created_month",
        attribute="payment.payment_record.created_at",
        grain=Grain.MONTH,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_created",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_created_day",
        attribute="payment.payment_record.created_at",
        grain=Grain.DAY,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_created",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_created_year",
        attribute="mdm.member.created_at",
        grain=Grain.YEAR,
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member_created",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_created_quarter",
        attribute="mdm.member.created_at",
        grain=Grain.QUARTER,
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member_created",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_created_month",
        attribute="mdm.member.created_at",
        grain=Grain.MONTH,
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member_created",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_created_day",
        attribute="mdm.member.created_at",
        grain=Grain.DAY,
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member_created",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_created_year",
        attribute="forms.form.created_at",
        grain=Grain.YEAR,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form_created",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_created_quarter",
        attribute="forms.form.created_at",
        grain=Grain.QUARTER,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form_created",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_created_month",
        attribute="forms.form.created_at",
        grain=Grain.MONTH,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form_created",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_created_day",
        attribute="forms.form.created_at",
        grain=Grain.DAY,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form_created",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_date_year",
        attribute="forms.form_submission.submitted_at",
        grain=Grain.YEAR,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_submission_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_date_quarter",
        attribute="forms.form_submission.submitted_at",
        grain=Grain.QUARTER,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_submission_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_date_month",
        attribute="forms.form_submission.submitted_at",
        grain=Grain.MONTH,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_submission_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_date_day",
        attribute="forms.form_submission.submitted_at",
        grain=Grain.DAY,
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_submission_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_created_year",
        attribute="workflow.workflow_task.created_at",
        grain=Grain.YEAR,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_task_created",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_created_quarter",
        attribute="workflow.workflow_task.created_at",
        grain=Grain.QUARTER,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_task_created",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_created_month",
        attribute="workflow.workflow_task.created_at",
        grain=Grain.MONTH,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_task_created",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_created_day",
        attribute="workflow.workflow_task.created_at",
        grain=Grain.DAY,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_task_created",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_year",
        attribute="membership.membership.year",
        note="Eén object voor beide lidmaatschapsfeiten (#894) — en géén hiërarchie, want de dag eronder is 1 januari en dus verzonnen. Niet te verwarren met 'Lid sinds' (het eerste jaar) of met de aanmaakdatum van het gezin.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_membership_year",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # #895: dezelfde oprolling op een TWEEDE datum van hetzelfde feit. De rol staat
    # in de naam — "Betaaldatum › Maand" en niet een tweede kaal "Maand" — want
    # zodra hetzelfde begrip twee keer voorkomt, hoort het onderscheid op het
    # scherm en niet in een naam die je uit je hoofd moet kennen (#894, #871).
    UniverseObject(
        key="paid_date_year",
        attribute="payment.payment_record.paid_at",
        grain=Grain.YEAR,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_paid_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="paid_date_quarter",
        attribute="payment.payment_record.paid_at",
        grain=Grain.QUARTER,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_paid_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="paid_date_month",
        attribute="payment.payment_record.paid_at",
        grain=Grain.MONTH,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_paid_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="paid_date_day",
        attribute="payment.payment_record.paid_at",
        grain=Grain.DAY,
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_paid_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="done_date_year",
        attribute="workflow.workflow_task.done_at",
        grain=Grain.YEAR,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_done_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="done_date_quarter",
        attribute="workflow.workflow_task.done_at",
        grain=Grain.QUARTER,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_done_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="done_date_month",
        attribute="workflow.workflow_task.done_at",
        grain=Grain.MONTH,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_done_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="done_date_day",
        attribute="workflow.workflow_task.done_at",
        grain=Grain.DAY,
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="d_done_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="start_date_year",
        attribute="activities.activity_date.start_date",
        grain=Grain.YEAR,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_start",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="start_date_quarter",
        attribute="activities.activity_date.start_date",
        grain=Grain.QUARTER,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_start",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="start_date_month",
        attribute="activities.activity_date.start_date",
        grain=Grain.MONTH,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_start",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="start_date_day",
        attribute="activities.activity_date.start_date",
        grain=Grain.DAY,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_start",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="end_date_year",
        attribute="activities.activity_date.end_date",
        grain=Grain.YEAR,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_end",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="end_date_quarter",
        attribute="activities.activity_date.end_date",
        grain=Grain.QUARTER,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_end",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="end_date_month",
        attribute="activities.activity_date.end_date",
        grain=Grain.MONTH,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_end",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="end_date_day",
        attribute="activities.activity_date.end_date",
        grain=Grain.DAY,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_end",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # #1428: every date of an activity, not only its first and last.
    UniverseObject(
        key="activity_date_year",
        attribute="reporting.activities.activity_date",
        grain=Grain.YEAR,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_date_quarter",
        attribute="reporting.activities.activity_date",
        grain=Grain.QUARTER,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        # With the year in it, for the reason of #912 at `start_date_quarter`.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_date_month",
        attribute="reporting.activities.activity_date",
        grain=Grain.MONTH,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_date_day",
        attribute="reporting.activities.activity_date",
        grain=Grain.DAY,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_date_time",
        attribute="activities.activity_date.start_time",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="f_activity_dates",
        sql="{view}.start_time_label",
        sort_sql="{view}.start_time",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_activity_dates",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_date_count",
        attribute="reporting.activities.activity_date_count",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_activity_dates",
        sql="COUNT({view}.activity_date_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_activity_dates",
        ai_exposure=AiExposure.INTERNAL,
    ),
    # #1439: the annual programme, one row per activity per year.
    UniverseObject(
        key="year_first_date_year",
        attribute="reporting.activities.year_first_date",
        grain=Grain.YEAR,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_year_first_date",
        sql="{view}.year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_first_date_quarter",
        attribute="reporting.activities.year_first_date",
        grain=Grain.QUARTER,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_year_first_date",
        sql="({view}.year::text || '-K' || {view}.quarter::text)",
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_first_date_month",
        attribute="reporting.activities.year_first_date",
        grain=Grain.MONTH,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_year_first_date",
        sql="{view}.year_month",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_first_date_day",
        attribute="reporting.activities.year_first_date",
        grain=Grain.DAY,
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_year_first_date",
        sql="{view}.date_key",
        format=Format.DATE,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_first_time",
        attribute="reporting.activities.year_first_time",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="f_activity_years",
        sql="{view}.first_time_label",
        sort_sql="{view}.first_time",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_activity_years",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_dates",
        attribute="reporting.activities.year_dates",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="f_activity_years",
        sql="{view}.dates_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_activity_years",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="year_activity_count",
        attribute="reporting.activities.year_activity_count",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_activity_years",
        sql="COUNT(DISTINCT {view}.activity_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_activity_years",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # ── Leden ───────────────────────────────────────────────────────────────
    UniverseObject(
        key="membership_count",
        attribute="reporting.members.membership_count",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="COUNT(DISTINCT {view}.member_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_memberships",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_households",
        attribute="reporting.members.membership_households",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.is_member)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_persons",
        attribute="reporting.members.membership_persons",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.person_count)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_amount_charged",
        attribute="reporting.members.membership_amount_charged",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.amount_charged)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_amount_paid",
        attribute="reporting.members.membership_amount_paid",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.amount_paid)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_open_amount",
        attribute="reporting.members.membership_open_amount",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.open_amount)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_is_active",
        attribute="reporting.members.membership_is_active",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="f_memberships",
        sql="CASE WHEN {view}.active_membership_count > 0 THEN 'Ja' ELSE 'Nee' END",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_status",
        attribute="reporting.members.membership_status",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_membership_status",
        sql="{view}.label",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_municipality",
        attribute="mdm.address.municipality",
        note="Van het gezin, op gezinskorrel: elk gezin telt één keer, ook al wonen er vier mensen. Voor de telling per bewoner is er 'Gemeente (adres)'.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.municipality",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_postal_code",
        attribute="mdm.address.postal_code_id",
        note="Van het gezin, op gezinskorrel: elk gezin telt één keer. Voor de postcode per bewoner is er 'Postcode (adres)'.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.postal_code",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_size_group",
        attribute="reporting.members.member_size_group",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.household_size_group",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_since",
        attribute="reporting.members.member_since",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.member_since_year",
        format=Format.YEAR,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member",
        attribute="mdm.member.id",
        note="Klik door naar het gezinsdossier.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.member_id",
        format=Format.COUNT,
        role=Role.ADMIN,
        sensitive=True,
        drill="member",
        drill_sql="{view}.member_id",
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
    ),
    UniverseObject(
        key="address_line",
        attribute="mdm.address.line",
        note="'Geen adres' als er geen is. Afgeleid in de weergave, niet bewaard — een samenvoeging die in de databank staat, drijft weg van de velden waaruit ze komt. Sorteert op straat, huisnummer numeriek en bus, dus niet op zichzelf. Voor 'hoeveel gezinnen per gemeente' neem je Gemeente, die al op gezinskorrel staat.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="COALESCE({view}.address_line, 'Geen adres')",
        # Sorted on the SPLIT fields, never on the composed text — composing is
        # exactly what made a street come back as 10, 12A, 2, 9 (#850, #851).
        sort_sql=(
            "{view}.street, {view}.house_number_num, {view}.house_number_rest, {view}.bus_number"
        ),
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="address_municipality",
        attribute="mdm.address.municipality",
        qualifier="adres",
        note="Van dit adres, op persoonskorrel. Verschilt van 'Gemeente', die het gezin volgt: daar telt een gezin één keer, hier elke bewoner met een adres. Wie geen adres heeft, valt onder 'Geen adres' en verdwijnt dus niet uit het rapport.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="COALESCE({view}.municipality, 'Geen adres')",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="address_postal_code",
        attribute="mdm.address.postal_code_id",
        qualifier="adres",
        note="Van dit adres, op persoonskorrel; 'Geen adres' voor wie er geen heeft.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="COALESCE({view}.postal_code, 'Geen adres')",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="address_street",
        attribute="mdm.address.street",
        note="Op persoonskorrel, dus elke bewoner telt mee.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="COALESCE({view}.street, 'Geen adres')",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="address_house_number",
        attribute="mdm.address.house_number",
        note="Wordt natuurlijk gesorteerd — het is tekst, dus alfabetisch zou 10 vóór 9 komen en staat een straat door elkaar.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="COALESCE({view}.house_number, '')",
        sort_sql="{view}.house_number_num, {view}.house_number_rest",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="address_bus",
        attribute="mdm.address.bus_number",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_address",
        sql="{view}.bus_number",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_head_name",
        attribute="reporting.members.member_head_name",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.head_name",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_partner_name",
        attribute="reporting.members.member_partner_name",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_member",
        sql="{view}.partner_name",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_valid_today",
        attribute="reporting.members.member_valid_today",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="f_members",
        sql=_boolean_label("is_valid_today"),
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_members",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="person_age_group",
        attribute="reporting.members.person_age_group",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_person",
        sql="{view}.age_group",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="person_gender",
        attribute="mdm.person.gender_code",
        note="De persoon in het feit: de inschrijver bij inschrijvingen, het hoofdlid bij een gezinsrapport. Niet ingevuld blijft een eigen waarde en verdwijnt niet uit het rapport.",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_person",
        sql="{view}.gender_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="person_relation_type",
        attribute="mdm.member_person.relation_type",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_person",
        sql="{view}.relation_type_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        sensitive=True,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # ── Activiteiten ────────────────────────────────────────────────────────
    UniverseObject(
        key="registration_count",
        attribute="reporting.activities.registration_count",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_registrations",
        sql="COUNT(DISTINCT {view}.registration_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        additive=False,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_quantity",
        attribute="reporting.activities.registration_quantity",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_registrations",
        sql="SUM({view}.quantity)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_amount",
        attribute="reporting.activities.registration_amount",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_registrations",
        sql="SUM({view}.line_amount)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity",
        attribute="activities.activity.name",
        note="Klik door naar het activiteitdossier.",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.activity_name",
        format=Format.LABEL,
        role=Role.ADMIN,
        drill="activity",
        drill_sql="{view}.activity_id",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_description",
        attribute="activities.activity.description",
        note="Publieke tekst, dus geen reden om ze voor een rapport achter te houden.",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="d_activity",
        sql="{view}.activity_description",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_board_notes",
        attribute="activities.activity.board_notes",
        note="Zichtbaar in een rapport dat een bestuurder zelf opvraagt, en NOOIT in een vraag aan Raakje — het is vrije interne tekst en wat erin staat is niet te voorspellen. Het scherm belooft precies dat bij het veld.",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="d_activity",
        sql="{view}.activity_board_notes",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="activity_organisers",
        attribute="reporting.activities.activity_organisers",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL,
        view="d_activity",
        sql="{view}.activity_organisers",
        format=Format.LABEL,
        role=Role.ADMIN,
        # NIET tokenised, en dat is een meting en geen slordigheid (#1077):
        # tokenisatie vervangt een waarde door `persoon-23` met een id dat de engine
        # per RIJ meelevert. Deze kolom voegt meerdere personen samen, dus er is
        # geen id om te vervangen — en een naam zonder id laat de naadwachter de
        # hele toolaanroep blokkeren, niet enkel deze kolom. NONE weigert hem netjes
        # bij naam, vóór de query, terwijl het rapportenpaneel de namen gewoon toont.
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="activity_organiser",
        attribute="reporting.activities.activity_organiser",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity_organiser",
        sql="{view}.organiser_name",
        format=Format.LABEL,
        role=Role.ADMIN,
        # Een organisator is een persoon, dus het model krijgt `persoon-23` en niet
        # de naam. Dat kan hier wél en bij de samengevoegde kolom niet: deze rij
        # wijst één persoon aan, dus er is een id om het token op te bouwen.
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="persoon",
        entity_sql="{view}.person_id",
    ),
    UniverseObject(
        key="activity_id",
        attribute="activities.activity.id",
        note="Niet in het objectenpaneel: het bestaat om op één activiteit te kunnen filteren, want de naam is daar niet eenduidig genoeg voor — een activiteit die elk jaar terugkomt, heet elk jaar hetzelfde (#975).",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.activity_id",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
        # #975: the activity mode of the assistant filters on this, server-side.
        # Hidden from the pane and from the catalogue; see `in_pane`.
        in_pane=False,
    ),
    UniverseObject(
        key="activity_year",
        attribute="reporting.activities.activity_year",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.activity_year",
        format=Format.YEAR,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_location",
        attribute="activities.activity.location",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.location",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # #1428: the two fields of part A, as their Dutch label.
    UniverseObject(
        key="activity_status",
        attribute="activities.activity.status",
        note="Een concept staat nergens op de publieke site; het rapport toont het wel, zodat je ziet wat nog gepubliceerd moet worden. Geannuleerd is een aparte eigenschap.",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.status_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_target_audience",
        attribute="activities.activity.target_audience",
        note="Leeg als het bestuur het niet invulde.",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql="{view}.target_audience_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_cancelled",
        attribute="activities.activity.is_cancelled",
        note="Geannuleerde activiteiten blijven in de cijfers staan, dus filter hierop als je ze niet wil meetellen.",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql=_boolean_label("is_cancelled"),
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_members_only",
        attribute="activities.activity.members_only",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="d_activity",
        sql=_boolean_label("members_only"),
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_count",
        attribute="reporting.activities.activity_count",
        klass="Activiteiten",
        kind=ObjectKind.MEASURE,
        view="f_activities",
        sql="COUNT(DISTINCT {view}.activity_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_activities",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="activity_last_date",
        attribute="reporting.activities.activity_last_date",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_activities",
        sql="{view}.last_date",
        format=Format.DATE,
        role=Role.ADMIN,
        fact="f_activities",
        ai_exposure=AiExposure.INTERNAL,
    ),
    # #1135: de vraag "wie is ingeschreven?" kon het universum niet beantwoorden —
    # `f_registrations` draagt `person_id`, maar niets ontsloot de ingeschrevene.
    # Het model bleef daarom gereedschap proberen: acht aanroepen, geen antwoord.
    UniverseObject(
        key="registrant",
        attribute="reporting.activities.registrant",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql="COALESCE(NULLIF({view}.registrant_name, ''), 'Onbekend')",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        fact="f_registrations",
        # Getokeniseerd op de INSCHRIJVING en niet op de persoon (Koen, 21
        # september 2026). Een contactnaam is vrije tekst en heeft geen
        # persoons-id, dus tokeniseren op de persoon zou 98% van de rijen hun
        # naam ongewijzigd laten meegeven. De inschrijving heeft altijd een id,
        # dus werkt één tokensoort voor allebei de bronnen.
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="inschrijving",
        entity_sql="{view}.registration_id",
    ),
    UniverseObject(
        key="registrant_source",
        attribute="reporting.activities.registrant_source",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql="{view}.registrant_source",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_registrations",
        # Geen naam, wel een van drie vaste woorden: mag ongewijzigd mee.
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="component",
        attribute="activities.activity_sub_registration.name",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql="{view}.component_name",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="product",
        attribute="activities.activity_product.name",
        note="'Geen product' bij een inschrijving zonder regels.",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql="{view}.product_name",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_type",
        attribute="activities.registration.registration_type",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql="{view}.registration_type",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="registration_has_team",
        attribute="reporting.activities.registration_has_team",
        klass="Activiteiten",
        kind=ObjectKind.DIMENSION,
        view="f_registrations",
        sql=_boolean_label("has_team"),
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_registrations",
        ai_exposure=AiExposure.INTERNAL,
    ),
    # ── Betalingen ──────────────────────────────────────────────────────────
    # Elk object in deze klasse draagt de rol `finance`: CR-06 §5.1 zegt dat een
    # FINANCE-only gebruiker precies deze klasse ziet, en dat klopt alleen als de
    # klasse en de rol samenvallen.
    UniverseObject(
        key="payment_amount",
        attribute="reporting.payments.payment_amount",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="SUM({view}.amount)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_amount_paid",
        attribute="reporting.payments.payment_amount_paid",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="SUM({view}.amount_paid)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_open_amount",
        attribute="reporting.payments.payment_open_amount",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="SUM({view}.open_amount)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_refunded",
        attribute="reporting.payments.payment_refunded",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="SUM(CASE WHEN {view}.record_type = 'refund' THEN -{view}.amount ELSE 0 END)",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_count",
        attribute="reporting.payments.payment_count",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="COUNT(DISTINCT {view}.payment_id)",
        format=Format.COUNT,
        role=Role.FINANCE,
        additive=False,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_days_to_paid",
        attribute="reporting.payments.payment_days_to_paid",
        klass="Betalingen",
        kind=ObjectKind.MEASURE,
        view="f_payments",
        sql="AVG({view}.days_to_paid)",
        format=Format.DAYS,
        role=Role.FINANCE,
        additive=False,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_method",
        attribute="payment.payment_record.method",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_method",
        sql="{view}.label",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_status",
        attribute="payment.payment_record.status",
        note="Een deels betaalde vordering staat nog in afwachting.",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="d_payment_status",
        sql="{view}.label",
        format=Format.LABEL,
        role=Role.FINANCE,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_open",
        attribute="reporting.payments.payment_open",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="f_payments",
        sql="CASE WHEN ABS({view}.open_amount) > 0 THEN 'Ja' ELSE 'Nee' END",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_type",
        attribute="payment.payment_record.type",
        note="Terugbetalingen tellen negatief mee in 'Te betalen'.",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="f_payments",
        sql="{view}.record_type_label",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_payable_type",
        attribute="payment.payment_record.payable_type",
        note="Hiermee splits je de geldvragen in hun twee stromen.",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="f_payments",
        sql="{view}.payable_type_label",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_age_bucket",
        attribute="reporting.payments.payment_age_bucket",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="f_payments",
        sql="{view}.age_bucket",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_record",
        attribute="payment.payment_record.id",
        note="Klik door naar de betalingenpagina.",
        klass="Betalingen",
        kind=ObjectKind.DIMENSION,
        view="f_payments",
        sql="{view}.payment_id",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        drill="payment",
        drill_sql="{view}.payment_id",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_person_count",
        attribute="reporting.members.membership_person_count",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_membership_persons",
        sql="COUNT({view}.person_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_membership_persons",
        ai_exposure=AiExposure.INTERNAL,
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
        key="payment_payable_label",
        attribute="reporting.payments.payment_payable_label",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.payable_label",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        fact="f_payments",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="payment_ogm",
        attribute="payment.payment_record.structured_communication",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.structured_communication",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="payment_due",
        attribute="payment.payment_record.amount",
        qualifier="regel",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.amount",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_received",
        attribute="payment.payment_record.amount_paid",
        qualifier="regel",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.amount_paid",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_balance",
        attribute="reporting.payments.payment_balance",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.open_amount",
        format=Format.MONEY,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_paid_on",
        attribute="payment.payment_record.paid_at",
        note="De dag waarop deze ene betaling binnenkwam. Leeg zolang er niets ontvangen is.",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.paid_date",
        format=Format.DATE,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="payment_note",
        attribute="payment.payment_record.note",
        klass="Betalingen",
        kind=ObjectKind.DETAIL,
        view="f_payments",
        sql="{view}.note",
        format=Format.LABEL,
        role=Role.FINANCE,
        fact="f_payments",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="board_member",
        attribute="reporting.members.board_member",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="d_board_member",
        sql="COALESCE({view}.board_member_name, 'Niet toegewezen')",
        # NOT `sensitive`: that flag describes a dimension that cuts MEMBERS into
        # small groups, and a board member is the axis here, not the population
        # (#849). Unchanged by the removal of the threshold on 14 September 2026 —
        # the flag is a description of the data, and this description was never
        # about the rule that used to read it.
        #
        # What protects this column is `ai_exposure`: a board member is a person,
        # so it travels as `persoon-90` and the admin reads the name back on screen.
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        ai_exposure=AiExposure.TOKENISED,
        token_prefix="persoon",
        entity_sql="{view}.board_member_id",
    ),
    UniverseObject(
        key="member_total_count",
        attribute="reporting.members.member_total_count",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_members",
        sql="COUNT(DISTINCT {view}.member_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_members",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="member_ever_member",
        attribute="reporting.members.member_ever_member",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="f_members",
        sql=_boolean_label("was_ever_member"),
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_members",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_active_count",
        attribute="reporting.members.membership_active_count",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_memberships",
        sql="SUM({view}.active_membership_count)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_memberships",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_person_valid_today",
        attribute="reporting.members.membership_person_valid_today",
        klass="Leden",
        kind=ObjectKind.DIMENSION,
        view="f_membership_persons",
        sql=_boolean_label("is_valid_today"),
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_membership_persons",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="membership_person_unique",
        attribute="reporting.members.membership_person_unique",
        klass="Leden",
        kind=ObjectKind.MEASURE,
        view="f_membership_persons",
        sql="COUNT(DISTINCT {view}.person_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_membership_persons",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    # ── Formulieren ─────────────────────────────────────────────────────────
    UniverseObject(
        key="form_count",
        attribute="reporting.forms.form_count",
        klass="Formulieren",
        kind=ObjectKind.MEASURE,
        view="f_forms",
        sql="COUNT(DISTINCT {view}.form_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_forms",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_count",
        attribute="reporting.forms.submission_count",
        klass="Formulieren",
        kind=ObjectKind.MEASURE,
        view="f_form_submissions",
        sql="COUNT(DISTINCT {view}.submission_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_form_submissions",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_answers",
        attribute="reporting.forms.submission_answers",
        klass="Formulieren",
        kind=ObjectKind.MEASURE,
        view="f_form_submissions",
        sql="SUM({view}.answer_count)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_form_submissions",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form",
        attribute="forms.form.title",
        note="Klik door naar de formulierbouwer.",
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form",
        sql="{view}.form_name",
        format=Format.LABEL,
        role=Role.ADMIN,
        drill="form",
        drill_sql="{view}.form_id",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_status",
        attribute="forms.form.status",
        note="Enkel een gepubliceerd formulier kan inzendingen krijgen.",
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form",
        sql="{view}.form_status_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="form_anonymous",
        attribute="forms.form.is_anonymous",
        note="Bij een anoniem formulier is er geen inzender bekend, dus koppelen aan een gezin kan daar niet.",
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="d_form",
        sql="{view}.is_anonymous_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="submission_edited",
        attribute="reporting.forms.submission_edited",
        klass="Formulieren",
        kind=ObjectKind.DIMENSION,
        view="f_form_submissions",
        sql=_boolean_label("was_edited"),
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_form_submissions",
        ai_exposure=AiExposure.INTERNAL,
    ),
    # ── Taken ───────────────────────────────────────────────────────────────
    UniverseObject(
        key="task_count",
        attribute="reporting.tasks.task_count",
        klass="Taken",
        kind=ObjectKind.MEASURE,
        view="f_tasks",
        sql="COUNT(DISTINCT {view}.item_id)",
        format=Format.COUNT,
        role=Role.ADMIN,
        fact="f_tasks",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_age_days",
        attribute="reporting.tasks.task_age_days",
        klass="Taken",
        kind=ObjectKind.MEASURE,
        view="f_tasks",
        sql="AVG({view}.age_days)",
        format=Format.DAYS,
        role=Role.ADMIN,
        fact="f_tasks",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_days_to_done",
        attribute="reporting.tasks.task_days_to_done",
        klass="Taken",
        kind=ObjectKind.MEASURE,
        view="f_tasks",
        sql="AVG({view}.days_to_done)",
        format=Format.DAYS,
        role=Role.ADMIN,
        fact="f_tasks",
        additive=False,
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_kind",
        attribute="workflow.workflow_task.kind",
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.kind_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_tasks",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_status",
        attribute="workflow.workflow_task.status",
        note="Filter hierop in plaats van te vertrouwen op wat het feit toevallig bevat.",
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.status_label",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_tasks",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_detail",
        attribute="reporting.tasks.task_detail",
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.detail",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_tasks",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="task_role",
        attribute="workflow.workflow_task.required_role",
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.required_role",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_tasks",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_age_bucket",
        attribute="reporting.tasks.task_age_bucket",
        klass="Taken",
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.age_bucket",
        format=Format.LABEL,
        role=Role.ADMIN,
        fact="f_tasks",
        ai_exposure=AiExposure.INTERNAL,
    ),
    UniverseObject(
        key="task_done_by",
        attribute="workflow.workflow_task.done_by",
        klass="Taken",
        # A dimension and not a detail, corrected when the gate of #852 refused
        # the personal work list of #847. An e-mail address is a key, unlike a
        # free-text note, and "how many did each of us close" is a question — it
        # is the very question `@ik` was built for. The declaration was wrong,
        # not the report.
        kind=ObjectKind.DIMENSION,
        view="f_tasks",
        sql="{view}.done_by",
        format=Format.LABEL,
        role=Role.MEMBER_DETAILS,
        fact="f_tasks",
        ai_exposure=AiExposure.NONE,
    ),
)


# ── Lookups ──────────────────────────────────────────────────────────────────

BY_KEY: dict[str, UniverseObject] = {o.key: o for o in OBJECTS}

# Welke korrel elk object van de datumdimensie leest: what the object itself says
# (`grain`), plus `membership_year`, a year that is no roll-up of a date. A new date object
# without a grain slips through no lock: `test_reporting_year_object.py` keeps this complete.
DATE_OBJECT_GRAIN: dict[str, str] = {
    **{o.key: o.grain.value for o in OBJECTS if o.grain is not None},
    "membership_year": "year",
}
FACT_BY_KEY: dict[str, Fact] = {f.key: f for f in FACTS}
DIMENSION_BY_KEY: dict[str, Dimension] = {d.key: d for d in DIMENSIONS}


def joins_for(fact: str) -> dict[str, Join]:
    """Every dimension reachable from ``fact``, keyed by dimension view.

    Follows chains: a dimension that hangs off another dimension is reachable as
    soon as that one is. The value is the join that attaches it, so the caller can
    put them in dependency order.
    """
    bereikbaar: dict[str, Join] = {}
    grens = {fact}
    while grens:
        volgende: set[str] = set()
        for join in JOINS:
            if join.left in grens and join.dimension not in bereikbaar:
                bereikbaar[join.dimension] = join
                volgende.add(join.dimension)
        grens = volgende
    return bereikbaar


def join_order(needed: list[str], reachable: dict[str, Join]) -> list[str]:
    """The needed views plus whatever they hang off, parents first.

    A snowflake join cannot be emitted before the dimension it references exists
    in the FROM clause, and a dimension pulled in only as a stepping stone still
    has to be there.
    """
    volgorde: list[str] = []

    def _zet(view: str) -> None:
        if view in volgorde or view not in reachable:
            return
        ouder = reachable[view].left
        if ouder in reachable:
            _zet(ouder)
        volgorde.append(view)

    for view in needed:
        _zet(view)
    return volgorde


# ── Hiërarchieën (#899) ──────────────────────────────────────────────────────
#
# Na #895 telde de klasse Tijd eenentwintig regels: vijf basisobjecten plus vier
# datumrollen × vier niveaus. Zestien van die eenentwintig zijn dezelfde vier
# niveaus, vier keer herhaald — en dat leest niemand als vier keer hetzelfde, dat
# leest als zestien keuzes.
#
# Een hiërarchie is puur een **presentatiebegrip**: de niveaus blijven gewone
# objecten met hun eigen sleutel, want daar hangen de bewaarde rapporten aan en
# daar kijken alle poorten naar. Wat verandert is dat het paneel ze als één regel
# toont in plaats van als vier.
#
# Een niveau blijft dus **rechtstreeks** te kiezen: Maand op de kolomas zetten mag
# geen omweg via Jaar worden. Een hiërarchie die alleen van bovenaf benaderbaar is,
# neemt iets weg dat vandaag werkt.


@dataclass(frozen=True)
class Hierarchy:
    """Eén regel in het paneel, met haar niveaus als knoppen ernaast."""

    key: str
    name: str
    klass: str
    #: De objectsleutels, van grof naar fijn. Elk is een gewoon object in `BY_KEY`.
    level_keys: tuple[str, ...]

    @property
    def levels(self) -> list["UniverseObject"]:
        return [BY_KEY[k] for k in self.level_keys]

    @property
    def description(self) -> str:
        return BY_KEY[self.level_keys[0]].description

    def step(self, key: str, richting: int) -> str:
        """The next level down (+1) or up (-1), or "" at the end of the road.

        Detail levels are skipped: "Maand voluit" sits between month and day in
        the shared date, and drilling into something you cannot group by would be
        a dead end (#852).
        """
        bruikbaar = [k for k in self.level_keys if BY_KEY[k].kind is ObjectKind.DIMENSION]
        if key not in bruikbaar:
            return ""
        index = bruikbaar.index(key) + richting
        return bruikbaar[index] if 0 <= index < len(bruikbaar) else ""


def _date_levels(prefix: str) -> tuple[str, ...]:
    return tuple(f"{prefix}{korrel}" for korrel in ("year", "quarter", "month", "day"))


HIERARCHIES: tuple[Hierarchy, ...] = (
    # Elke datum staat bij haar onderwerp (#901). De klasse "Tijd" bestond niet
    # meer zodra dat doorgetrokken werd: ze was ingedeeld naar SOORT ding en niet
    # naar onderwerp, net als "Betaaldetail" voor #871.
    Hierarchy(
        key="registration_date",
        name="Inschrijfdatum",
        klass="Activiteiten",
        level_keys=_date_levels("registration_date_"),
    ),
    Hierarchy(
        key="start_date",
        name="Startdatum",
        klass="Activiteiten",
        level_keys=_date_levels("start_date_"),
    ),
    Hierarchy(
        key="end_date", name="Einddatum", klass="Activiteiten", level_keys=_date_levels("end_date_")
    ),
    Hierarchy(
        key="activity_date",
        name="Activiteitsdatum",
        klass="Activiteiten",
        level_keys=_date_levels("activity_date_"),
    ),
    Hierarchy(
        key="year_first_date",
        name="Eerste datum in het jaar",
        klass="Activiteiten",
        level_keys=_date_levels("year_first_date_"),
    ),
    Hierarchy(
        key="payment_created",
        name="Aanmaakdatum",
        klass="Betalingen",
        level_keys=_date_levels("payment_created_"),
    ),
    Hierarchy(
        key="paid_date",
        name="Betaaldatum",
        klass="Betalingen",
        level_keys=_date_levels("paid_date_"),
    ),
    Hierarchy(
        key="member_created",
        name="Aanmaakdatum gezin",
        klass="Leden",
        level_keys=_date_levels("member_created_"),
    ),
    Hierarchy(
        key="form_created",
        name="Aanmaakdatum formulier",
        klass="Formulieren",
        level_keys=_date_levels("form_created_"),
    ),
    Hierarchy(
        key="submission_date",
        name="Inzenddatum",
        klass="Formulieren",
        level_keys=_date_levels("submission_date_"),
    ),
    Hierarchy(
        key="task_created",
        name="Aanmaakdatum taak",
        klass="Taken",
        level_keys=_date_levels("task_created_"),
    ),
    Hierarchy(
        key="done_date", name="Afhandeldatum", klass="Taken", level_keys=_date_levels("done_date_")
    ),
)

HIERARCHY_OF: dict[str, Hierarchy] = {key: hier for hier in HIERARCHIES for key in hier.level_keys}


def physical_view(view: str) -> str:
    """The view name in the database for an object's view.

    Usually the same string — but a date role (#895) is an **alias**: `d_paid_date`
    reads from `reporting.d_date` under its own name, so that the same calendar can
    sit in one report twice. Anything that puts a view into SQL has to translate
    first, or Postgres is asked for a relation that does not exist.

    Here, and called from both places that build a FROM. Two implementations of
    this one line is how drilling on a payment date reached a board member as
    *"Er ging iets mis"*: the main query translated, the value list did not.
    """
    dimensie = DIMENSION_BY_KEY.get(view)
    return dimensie.source if dimensie else view


def objects_in_pane_order() -> list[UniverseObject]:
    """Every object, in class order and then declaration order.

    Declaration order, not alphabetical: the order in this file is the order a
    board member reads them in, and it is chosen (measures before the dimensions
    that qualify them).
    """
    order = {name: i for i, name in enumerate(CLASSES)}
    # #975: an object that exists only for the server to filter on is not offered.
    return sorted(
        (o for o in OBJECTS if o.in_pane),
        key=lambda o: (order.get(o.klass, len(order)), OBJECTS.index(o)),
    )


def classes_with_objects() -> list[tuple[str, list]]:
    """The objects pane: classes with their entries, empty classes dropped.

    An entry is either a `UniverseObject` or a `Hierarchy` (#899). The levels of a
    hierarchy are ordinary objects and stay selectable one by one; they simply
    share one line here instead of taking four.
    """
    per_class: dict[str, list] = {}
    gezien: set[str] = set()
    for obj in objects_in_pane_order():
        hier = HIERARCHY_OF.get(obj.key)
        if hier is None:
            per_class.setdefault(obj.klass, []).append(obj)
            continue
        if hier.key in gezien:
            continue
        gezien.add(hier.key)
        per_class.setdefault(hier.klass, []).append(hier)
    return [(name, per_class[name]) for name in CLASSES if name in per_class]

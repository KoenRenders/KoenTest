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


class AiExposure(str, Enum):
    """Hoe ver een object naar een taalmodel mag reizen (CR-07 §5.1).

    **Zonder default, met opzet.** Een vlag die iemand kan vergeten is de verkeerde
    default op een uitgaand AI-kanaal: dan bepaalt een vergetelheid wat er naar Mistral
    gaat. Een object toevoegen zonder classificatie is hier een importfout — CI staat
    rood vóór er één test gedraaid heeft.

    Bewust afwezig: een waarde "publiek". De publieke Raakje raakt de universe
    structureel niet aan, en deze declaratie mag niet suggereren dat dat wél zou kunnen.
    """

    #: Aggregaten en niet-identificerende dimensies: straat, gemeente, leeftijdsgroep,
    #: gezinsgrootte. Mag ongewijzigd naar de assistent.
    PLAIN = "admin_plain"
    #: Wijst een persoon aan. Bereikt de assistent enkel als token (`gezin-23`), en
    #: vereist dus een entiteit-id in de rij — zie `entity_sql`.
    TOKENISED = "admin_tokenised"
    #: Bereikt geen enkel taalmodel, ook de beheerder-assistent niet.
    NONE = "none"


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
# "Betaaldetail" is gone since #871. It was the only class named after a SHAPE
# instead of a subject, and that split is what hid the collisions: two objects
# called "Soort" and two called "Te betalen", each pair meaning something
# different, invisible as long as they sat in separate classes. Inside one class
# they had to be resolved. Four of those "details" turned out to be the same
# expression as an existing dimension and simply went.
CLASSES: tuple[str, ...] = ("Leden", "Activiteiten", "Betalingen",
                            "Formulieren", "Taken")


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
    name: str
    klass: str
    kind: ObjectKind
    view: str
    sql: str
    format: Format
    role: Role
    description: str
    # CR-07 §5.1: hoe ver dit object naar een taalmodel mag reizen. GEEN default —
    # zie AiExposure. Staat hier tussen de verplichte velden zodat een nieuw object
    # zonder classificatie niet eens importeert.
    ai_exposure: AiExposure
    # Measures name the fact they aggregate. A measure is the only object that
    # decides the grain, which is why the fan-trap check reads exactly this field.
    fact: str | None = None
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
# soorten daarachter groeperen (#894).
DATE_GRAINS: tuple[str, ...] = ("year", "quarter", "month", "day")

# Welke korrel elk object van de datumdimensie leest. Een nieuw datumobject dat
# hier niet in staat, laat de poort in `test_reporting_year_object.py` falen — dan
# zou het stilzwijgend door elke grendel heen glippen.
DATE_OBJECT_GRAIN: dict[str, str] = {
    # Elke datum in de universe, per korrel. Een datumobject dat hier niet in staat
    # glipt door elke grendel heen, dus de poort in `test_reporting_year_object.py`
    # houdt deze afbeelding volledig.
    "membership_year": "year",
    **{f"{rol}_{korrel}": korrel
       for rol in ("registration_date", "payment_created", "member_created",
                   "form_created", "submission_date", "task_created",
                   "paid_date", "done_date", "start_date", "end_date")
       for korrel in ("year", "quarter", "month", "day")},
}


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
    Dimension(key="d_activity_organiser", name="Organisator",
              key_column="organiser_id"),
    Dimension(key="d_member", name="Gezin", key_column="member_id"),
    Dimension(key="d_person", name="Persoon", key_column="person_id"),
    Dimension(key="d_payment_method", name="Betaalwijze", key_column="code"),
    Dimension(key="d_payment_status", name="Betaalstatus", key_column="code"),
    Dimension(key="d_membership_status", name="Lidmaatschapsstatus", key_column="code"),
    Dimension(key="d_form", name="Formulier", key_column="form_id"),
    Dimension(key="d_board_member", name="Verantwoordelijk bestuurslid",
              key_column="board_member_id"),
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
    Dimension(key="d_registration_date", name="Inschrijfdatum",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_payment_created", name="Aanmaakdatum",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_membership_year", name="Lidmaatschapsjaar",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_member_created", name="Aanmaakdatum gezin",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_form_created", name="Aanmaakdatum formulier",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_submission_date", name="Inzenddatum",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_task_created", name="Aanmaakdatum taak",
              key_column="date_key", source_view="d_date"),
    Dimension(key="d_paid_date", name="Betaaldatum", key_column="date_key",
              source_view="d_date"),
    Dimension(key="d_done_date", name="Afhandeldatum", key_column="date_key",
              source_view="d_date"),
    Dimension(key="d_activity_start", name="Startdatum", key_column="date_key",
              source_view="d_date"),
    Dimension(key="d_activity_end", name="Einddatum", key_column="date_key",
              source_view="d_date"),
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
    Join("f_activities", "d_activity_organiser",
         (("activity_id", "activity_id"),)),
    Join("f_activities", "d_activity_start", (("first_date", "date_key"),)),
    Join("f_activities", "d_activity_end", (("last_date", "date_key"),)),
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
        key="registration_date_year", name="Inschrijfdatum › Jaar", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_registration_date", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer er ingeschreven is. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_date_quarter", name="Inschrijfdatum › Kwartaal", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_registration_date",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer er ingeschreven is. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_date_month", name="Inschrijfdatum › Maand", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_registration_date", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer er ingeschreven is. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_date_day", name="Inschrijfdatum › Datum", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_registration_date", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer er ingeschreven is. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_created_year", name="Aanmaakdatum › Jaar", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_created", sql="{view}.year",
        format=Format.YEAR, role=Role.FINANCE,
        description="Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_created_quarter", name="Aanmaakdatum › Kwartaal", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_created",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.FINANCE,
        description="Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_created_month", name="Aanmaakdatum › Maand", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_created", sql="{view}.year_month",
        format=Format.LABEL, role=Role.FINANCE,
        description="Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_created_day", name="Aanmaakdatum › Datum", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_created", sql="{view}.date_key",
        format=Format.DATE, role=Role.FINANCE,
        description="Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_created_year", name="Aanmaakdatum gezin › Jaar", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member_created", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer het gezin in de administratie kwam. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_created_quarter", name="Aanmaakdatum gezin › Kwartaal", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member_created",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het gezin in de administratie kwam. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_created_month", name="Aanmaakdatum gezin › Maand", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member_created", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het gezin in de administratie kwam. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_created_day", name="Aanmaakdatum gezin › Datum", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member_created", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer het gezin in de administratie kwam. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_created_year", name="Aanmaakdatum formulier › Jaar", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form_created", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer het formulier aangemaakt is. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_created_quarter", name="Aanmaakdatum formulier › Kwartaal", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form_created",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het formulier aangemaakt is. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_created_month", name="Aanmaakdatum formulier › Maand", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form_created", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het formulier aangemaakt is. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_created_day", name="Aanmaakdatum formulier › Datum", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form_created", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer het formulier aangemaakt is. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_date_year", name="Inzenddatum › Jaar", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_submission_date", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer het formulier ingevuld is. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_date_quarter", name="Inzenddatum › Kwartaal", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_submission_date",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het formulier ingevuld is. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_date_month", name="Inzenddatum › Maand", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_submission_date", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer het formulier ingevuld is. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_date_day", name="Inzenddatum › Datum", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_submission_date", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer het formulier ingevuld is. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_created_year", name="Aanmaakdatum taak › Jaar", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_task_created", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer de taak ontstond. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_created_quarter", name="Aanmaakdatum taak › Kwartaal", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_task_created",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer de taak ontstond. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_created_month", name="Aanmaakdatum taak › Maand", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_task_created", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer de taak ontstond. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_created_day", name="Aanmaakdatum taak › Datum", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_task_created", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer de taak ontstond. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_year", name="Lidmaatschapsjaar", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_membership_year", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description=(
            "Het jaar waarover een lidmaatschap gaat. Eén object voor beide "
            "lidmaatschapsfeiten (#894) — en géén hiërarchie, want de dag eronder is 1 "
            "januari en dus verzonnen. Niet te verwarren met 'Lid sinds' (het eerste "
            "jaar) of met de aanmaakdatum van het gezin."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    # #895: dezelfde oprolling op een TWEEDE datum van hetzelfde feit. De rol staat
    # in de naam — "Betaaldatum › Maand" en niet een tweede kaal "Maand" — want
    # zodra hetzelfde begrip twee keer voorkomt, hoort het onderscheid op het
    # scherm en niet in een naam die je uit je hoofd moet kennen (#894, #871).
    UniverseObject(
        key="paid_date_year", name="Betaaldatum › Jaar", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_paid_date", sql="{view}.year",
        format=Format.YEAR, role=Role.FINANCE,
        description=(
            "Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. "
            "Opgerold tot jaar."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="paid_date_quarter", name="Betaaldatum › Kwartaal", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_paid_date",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.FINANCE,
        description="Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="paid_date_month", name="Betaaldatum › Maand", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_paid_date", sql="{view}.year_month",
        format=Format.LABEL, role=Role.FINANCE,
        description="Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="paid_date_day", name="Betaaldatum › Datum", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_paid_date", sql="{view}.date_key",
        format=Format.DATE, role=Role.FINANCE,
        description="Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="done_date_year", name="Afhandeldatum › Jaar", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_done_date", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="done_date_quarter", name="Afhandeldatum › Kwartaal", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_done_date",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="done_date_month", name="Afhandeldatum › Maand", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_done_date", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="done_date_day", name="Afhandeldatum › Datum", klass="Taken",
        kind=ObjectKind.DIMENSION, view="d_done_date", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="Wanneer de taak afgesloten is. Leeg zolang ze open staat. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="start_date_year", name="Startdatum › Jaar", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_start", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="De eerste dag van de activiteit. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="start_date_quarter", name="Startdatum › Kwartaal", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_start",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="De eerste dag van de activiteit. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="start_date_month", name="Startdatum › Maand", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_start", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="De eerste dag van de activiteit. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="start_date_day", name="Startdatum › Datum", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_start", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="De eerste dag van de activiteit. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="end_date_year", name="Einddatum › Jaar", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_end", sql="{view}.year",
        format=Format.YEAR, role=Role.ADMIN,
        description="De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="end_date_quarter", name="Einddatum › Kwartaal", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_end",
        sql="({view}.year::text || \'-K\' || {view}.quarter::text)",
        # #912: MET het jaartal erin. Kaal telde een kwartaal de tweede
        # kwartalen van 2025, 2026 en 2027 in één rij op — een getal dat
        # netjes optelt en een andere vraag beantwoordt. Precies de val van
        # #894, en ze viel pas op toen drillen jaar en kwartaal naast elkaar
        # zette: daar leest "2026 · 2" nog, op zichzelf niet.
        sort_sql="{view}.year, {view}.quarter",
        format=Format.LABEL, role=Role.ADMIN,
        description="De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot kwartaal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="end_date_month", name="Einddatum › Maand", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_end", sql="{view}.year_month",
        format=Format.LABEL, role=Role.ADMIN,
        description="De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot maand.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="end_date_day", name="Einddatum › Datum", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_end", sql="{view}.date_key",
        format=Format.DATE, role=Role.ADMIN,
        description="De laatste dag van de activiteit, of de startdag als er maar één is. Opgerold tot datum.",
        ai_exposure=AiExposure.PLAIN,
    ),

    # ── Leden ───────────────────────────────────────────────────────────────
    UniverseObject(
        key="membership_count", name="Aantal gezinnen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships",
        sql="COUNT(DISTINCT {view}.member_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_memberships", additive=False,
        description=(
            "Gezinnen in de telling, ongeacht of ze dat jaar lid waren. Dit is de "
            "maat waarmee je op Lidmaatschapsstatus groepeert: een vervallen gezin "
            "heeft dat jaar per definitie géén lidmaatschap, dus 'Aantal leden "
            "(hoofdlid)' staat daar terecht op nul en telt het niet (#871)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_households", name="Aantal leden (hoofdlid)", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.is_member)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_memberships",
        description=(
            "Gezinnen met een lidmaatschap in dat jaar — één per gezin, wat Koen "
            "'leden (hoofdlid)' noemt. Wil je weten hoeveel daarvan nieuw, "
            "vernieuwd of vervallen zijn, groepeer dan op Lidmaatschapsstatus; "
            "dat is een dimensie en geen aparte maat (#871)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_persons", name="Aantal leden (personen)", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.person_count)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_memberships",
        description="Personen in de gezinnen met een lidmaatschap in dat jaar.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_amount_charged", name="Lidgeld gefactureerd", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.amount_charged)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description=(
            "Som van de vorderingen op het lidgeld, terugbetalingen afgetrokken. De "
            "standaardbetekenis van 'lidgeldomzet': gefactureerd, niet ontvangen."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_amount_paid", name="Lidgeld ontvangen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.amount_paid)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description=(
            "Wat er effectief op het lidgeld ontvangen is. Lager dan 'Lidgeld "
            "gefactureerd' zolang er nog iets openstaat."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_open_amount", name="Lidgeld openstaand", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_memberships", sql="SUM({view}.open_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_memberships",
        description="Gefactureerd min ontvangen: het lidgeld dat nog binnen moet komen.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_is_active", name="Actief", klass="Leden",
        kind=ObjectKind.DIMENSION, view="f_memberships",
        sql="CASE WHEN {view}.active_membership_count > 0 THEN 'Ja' ELSE 'Nee' END",
        format=Format.LABEL, role=Role.ADMIN, fact="f_memberships",
        description=(
            "Of dit gezin dat jaar een actief lidmaatschap had. Een dimensie en "
            "geen maat: 'hoeveel actieve leden' is een telling mét een filter, en "
            "dan staat op het scherm welk filter (#871)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_status", name="Lidmaatschapsstatus", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_membership_status", sql="{view}.label",
        format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Of dit lidmaatschap nieuw, vernieuwd of vervallen is ten opzichte van het "
            "jaar ervoor. Dit is de dimensie die 'hoeveel nieuwe leden' beantwoordt."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_municipality", name="Gemeente", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.municipality",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "De gemeente van het gezin, uit de postcodetabel. Op gezinskorrel: elk gezin "
            "telt één keer, ook al wonen er vier mensen. Voor de telling per bewoner is er "
            "'Gemeente (adres)'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_postal_code", name="Postcode", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.postal_code",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "De postcode van het gezin, uit de postcodetabel. Op gezinskorrel: elk gezin "
            "telt één keer. Voor de postcode per bewoner is er 'Postcode (adres)'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_size_group", name="Gezinsgrootte", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.household_size_group",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "Het aantal personen in het gezin, samengenomen in klassen. Vraag de waarden "
            "op als je erop wil filteren — de klassegrenzen staan in de data, niet hier."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_since", name="Lid sinds", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.member_since_year",
        format=Format.YEAR, role=Role.ADMIN, sensitive=True,
        description=(
            "Het eerste jaar waarvoor dit gezin een lidmaatschap heeft — sinds wanneer het "
            "lid is. Iets anders dan de aanmaakdatum van het gezin (wanneer het in de "
            "administratie kwam) en dan Lidmaatschapsjaar (het jaar waarover een "
            "lidmaatschap gaat)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member", name="Gezin", klass="Leden", kind=ObjectKind.DIMENSION,
        view="d_member", sql="{view}.member_id", format=Format.COUNT,
        role=Role.ADMIN, sensitive=True, drill="member", drill_sql="{view}.member_id",
        description="Het gezin zelf. Klik door naar het gezinsdossier.",
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
    ),
    UniverseObject(
        key="address_line", name="Adres", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address",
        sql="COALESCE({view}.address_line, 'Geen adres')",
        # Sorted on the SPLIT fields, never on the composed text — composing is
        # exactly what made a street come back as 10, 12A, 2, 9 (#850, #851).
        sort_sql=("{view}.street, {view}.house_number_num, "
                  "{view}.house_number_rest, {view}.bus_number"),
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "Straat, huisnummer en bus op één lijn; 'Geen adres' als er geen is. "
            "Afgeleid in de weergave, niet bewaard — een samenvoeging die in de "
            "databank staat, drijft weg van de velden waaruit ze komt. Sorteert op "
            "straat, huisnummer numeriek en bus, dus niet op zichzelf. Voor "
            "'hoeveel gezinnen per gemeente' neem je Gemeente, die al op "
            "gezinskorrel staat."
        ),
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="address_municipality", name="Gemeente (adres)", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address",
        sql="COALESCE({view}.municipality, 'Geen adres')",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "De gemeente van dit adres, op persoonskorrel. Verschilt van "
            "'Gemeente', die het gezin volgt: daar telt een gezin één keer, hier "
            "elke bewoner met een adres. Wie geen adres heeft, valt onder 'Geen "
            "adres' en verdwijnt dus niet uit het rapport."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="address_postal_code", name="Postcode (adres)", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address",
        sql="COALESCE({view}.postal_code, 'Geen adres')",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "De postcode van dit adres, op persoonskorrel; 'Geen adres' voor wie "
            "er geen heeft."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="address_street", name="Straat", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address",
        sql="COALESCE({view}.street, 'Geen adres')",
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "De straatnaam van dit adres, zonder huisnummer. Op persoonskorrel, dus elke "
            "bewoner telt mee."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="address_house_number", name="Huisnummer", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address",
        sql="COALESCE({view}.house_number, '')",
        sort_sql="{view}.house_number_num, {view}.house_number_rest",
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "Het huisnummer. Wordt natuurlijk gesorteerd — het is tekst, dus "
            "alfabetisch zou 10 vóór 9 komen en staat een straat door elkaar."
        ),
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="address_bus", name="Bus", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_address", sql="{view}.bus_number",
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description="Het busnummer, leeg als er geen is.",
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_head_name", name="Hoofdlid", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.head_name",
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "De naam van het hoofdlid van dit gezin. Op gezinskorrel, dus één per "
            "rij."
        ),
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_partner_name", name="Partner", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_member", sql="{view}.partner_name",
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "De naam van de partner, leeg als er geen is. Staan er twee partners "
            "in één gezin, dan toont dit er één — de korrel blijft één rij per "
            "gezin."
        ),
        ai_exposure=AiExposure.TOKENISED, token_prefix="gezin",
        entity_sql="{view}.member_id",
    ),
    UniverseObject(
        key="member_valid_today", name="Vandaag geldig lid", klass="Leden",
        kind=ObjectKind.DIMENSION, view="f_members",
        sql=_boolean_label("is_valid_today"), format=Format.LABEL,
        role=Role.ADMIN, fact="f_members",
        description=(
            "Of dit gezin vandaag een geldig lidmaatschap heeft. Iets anders dan "
            "'lid voor dit jaar': wie in oktober voor volgend jaar aansluit, is "
            "vandaag geldig en hoort bij volgend jaar."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="person_age_group", name="Leeftijdsgroep", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_person", sql="{view}.age_group",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "Leeftijdsklasse, berekend op vandaag. Van de persoon in het feit: de "
            "inschrijver bij inschrijvingen, het hoofdlid bij een gezinsrapport."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="person_gender", name="Geslacht", klass="Leden", kind=ObjectKind.DIMENSION,
        view="d_person", sql="{view}.gender_label", format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description=(
            "Het geslacht van de persoon in het feit: de inschrijver bij inschrijvingen, "
            "het hoofdlid bij een gezinsrapport. Niet ingevuld blijft een eigen waarde en "
            "verdwijnt niet uit het rapport."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="person_relation_type", name="Relatietype", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_person", sql="{view}.relation_type_label",
        format=Format.LABEL, role=Role.ADMIN, sensitive=True,
        description="Hoofdlid, partner of (meerderjarig) kind binnen het gezin.",
        ai_exposure=AiExposure.PLAIN,
    ),

    # ── Activiteiten ────────────────────────────────────────────────────────
    UniverseObject(
        key="registration_count", name="Aantal inschrijvingen", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations",
        sql="COUNT(DISTINCT {view}.registration_id)", format=Format.COUNT,
        role=Role.ADMIN, additive=False, fact="f_registrations",
        description=(
            "Aantal inschrijvingen, ongeacht hoeveel producten erop staan. Voor 'hoeveel "
            "mensen of plaatsen' neem je 'Aantal stuks': één inschrijving kan vier kaarten "
            "bevatten."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_quantity", name="Aantal stuks", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations", sql="SUM({view}.quantity)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_registrations",
        description=(
            "Som van de aantallen op de inschrijfregels — de bezetting, dus wat je neemt "
            "voor 'hoeveel deelnemers'. Een inschrijving met vier kaarten telt hier vier "
            "en bij 'Aantal inschrijvingen' één."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_amount", name="Inschrijfbedrag", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_registrations", sql="SUM({view}.line_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_registrations",
        description=(
            "Waarde van de inschrijfregels aan de prijs van dat moment — de omzet uit "
            "inschrijvingen, gefactureerd en niet ontvangen. Gratis producten en 'ter "
            "plaatse te betalen' tellen niet mee. Wat er werkelijk betaald is, staat bij "
            "Betalingen."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity", name="Activiteit", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="d_activity", sql="{view}.activity_name", format=Format.LABEL,
        role=Role.ADMIN, drill="activity", drill_sql="{view}.activity_id",
        description="Naam van de activiteit. Klik door naar het activiteitdossier.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_description", name="Omschrijving", klass="Activiteiten",
        kind=ObjectKind.DETAIL, view="d_activity",
        sql="{view}.activity_description", format=Format.LABEL, role=Role.ADMIN,
        description=(
            "De omschrijving die het bestuur bij de activiteit schreef — dezelfde "
            "zinnen die op de website en in de nieuwsbrief staan. Publieke tekst, "
            "dus geen reden om ze voor een rapport achter te houden."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_board_notes", name="Notities bestuur", klass="Activiteiten",
        kind=ObjectKind.DETAIL, view="d_activity",
        sql="{view}.activity_board_notes", format=Format.LABEL, role=Role.ADMIN,
        description=(
            "De interne nota bij de activiteit: afspraken, contacten, wat iemand "
            "zichzelf wilde herinneren. Zichtbaar in een rapport dat een bestuurder "
            "zelf opvraagt, en NOOIT in een vraag aan Raakje — het is vrije interne "
            "tekst en wat erin staat is niet te voorspellen. Het scherm belooft "
            "precies dat bij het veld."
        ),
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="activity_organisers", name="Organisatoren (samengevoegd)",
        klass="Activiteiten",
        kind=ObjectKind.DETAIL, view="d_activity",
        sql="{view}.activity_organisers", format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Wie deze activiteit trekt, als één regel: de aangevinkte "
            "contactpersonen met een · ertussen, in dezelfde volgorde als op de "
            "affiche. Eén kolom en geen eigen korrel — daardoor blijft een rapport "
            "over activiteiten één rij per activiteit, en kan je er niet op "
            "groeperen. Wil je dat laatste — of wil je Raakje erover kunnen vragen "
            "— neem dan 'Organisator'; die heeft een eigen korrel."
        ),
        # NIET tokenised, en dat is een meting en geen slordigheid (#1077):
        # tokenisatie vervangt een waarde door `persoon-23` met een id dat de engine
        # per RIJ meelevert. Deze kolom voegt meerdere personen samen, dus er is
        # geen id om te vervangen — en een naam zonder id laat de naadwachter de
        # hele toolaanroep blokkeren, niet enkel deze kolom. NONE weigert hem netjes
        # bij naam, vóór de query, terwijl het rapportenpaneel de namen gewoon toont.
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="activity_organiser", name="Organisator", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity_organiser",
        sql="{view}.organiser_name", format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Wie een activiteit trekt, met één rij PER ORGANISATOR. Daarmee kan je "
            "groeperen op 'activiteiten per organisator', en kan Raakje vertellen "
            "wie wat organiseert. LET OP: een activiteit met twee organisatoren "
            "levert twee rijen, dus zet dit object alleen in een rapport waar je "
            "die opsplitsing wil. Wil je één regel per activiteit, neem dan "
            "'Organisatoren (samengevoegd)'."
        ),
        # Een organisator is een persoon, dus het model krijgt `persoon-23` en niet
        # de naam. Dat kan hier wél en bij de samengevoegde kolom niet: deze rij
        # wijst één persoon aan, dus er is een id om het token op te bouwen.
        ai_exposure=AiExposure.TOKENISED, token_prefix="persoon",
        entity_sql="{view}.person_id",
    ),
    UniverseObject(
        key="activity_id", name="Activiteitnummer", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity", sql="{view}.activity_id",
        format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Het technische nummer van de activiteit. Niet in het objectenpaneel: "
            "het bestaat om op één activiteit te kunnen filteren, want de naam is "
            "daar niet eenduidig genoeg voor — een activiteit die elk jaar "
            "terugkomt, heet elk jaar hetzelfde (#975)."
        ),
        ai_exposure=AiExposure.PLAIN,
        # #975: the activity mode of the assistant filters on this, server-side.
        # Hidden from the pane and from the catalogue; see `in_pane`.
        in_pane=False,
    ),
    UniverseObject(
        key="activity_year", name="Jaar van de activiteit", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity", sql="{view}.activity_year",
        format=Format.YEAR, role=Role.ADMIN,
        description=(
            "Het jaar van de eerste datum van de activiteit, als eigenschap van de "
            "activiteit zelf. Neem dit voor 'welke activiteiten in 2026'; wil je per "
            "maand of kwartaal groeperen, gebruik dan Startdatum. Het model kent geen "
            "seizoen (CR-06 §12)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_location", name="Locatie", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity", sql="{view}.location",
        format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Waar de activiteit doorgaat, zoals ingevuld bij de activiteit — vrije tekst, "
            "dus geen adres en niet genormaliseerd."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_cancelled", name="Geannuleerd", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity",
        sql=_boolean_label("is_cancelled"), format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Of de activiteit geannuleerd werd. Geannuleerde activiteiten blijven in de "
            "cijfers staan, dus filter hierop als je ze niet wil meetellen."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_members_only", name="Enkel voor leden", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="d_activity",
        sql=_boolean_label("members_only"), format=Format.LABEL, role=Role.ADMIN,
        description="Of enkel leden zich mochten inschrijven op deze activiteit.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_count", name="Aantal activiteiten", klass="Activiteiten",
        kind=ObjectKind.MEASURE, view="f_activities",
        sql="COUNT(DISTINCT {view}.activity_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_activities", additive=False,
        description=(
            "Elke activiteit, ook zonder inschrijvingen. Verschilt van 'Aantal "
            "inschrijvingen', dat de inschrijvingen telt."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="activity_last_date", name="Laatste datum", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="f_activities", sql="{view}.last_date",
        format=Format.DATE, role=Role.ADMIN, fact="f_activities",
        description=(
            "De laatste dag van de activiteit (einddatum, anders begindatum). "
            "Filter hierop vanaf vandaag voor de komende activiteiten."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="component", name="Onderdeel", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="f_registrations", sql="{view}.component_name", format=Format.LABEL,
        role=Role.ADMIN, fact="f_registrations",
        description=(
            "Het onderdeel van de activiteit waarop ingeschreven werd — een activiteit kan "
            "er meerdere hebben, elk met een eigen prijs en capaciteit."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="product", name="Product", klass="Activiteiten", kind=ObjectKind.DIMENSION,
        view="f_registrations", sql="{view}.product_name", format=Format.LABEL,
        role=Role.ADMIN, fact="f_registrations",
        description="Het gekozen product. 'Geen product' bij een inschrijving zonder regels.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_type", name="Inschrijfvorm", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="f_registrations", sql="{view}.registration_type",
        format=Format.LABEL, role=Role.ADMIN, fact="f_registrations",
        description="Of er individueel of als gezin ingeschreven werd.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="registration_has_team", name="Ploegnaam ingevuld", klass="Activiteiten",
        kind=ObjectKind.DIMENSION, view="f_registrations", sql=_boolean_label("has_team"),
        format=Format.LABEL, role=Role.ADMIN, fact="f_registrations",
        description="Of er een ploegnaam ingevuld werd.",
        ai_exposure=AiExposure.PLAIN,
    ),

    # ── Betalingen ──────────────────────────────────────────────────────────
    # Elk object in deze klasse draagt de rol `finance`: CR-06 §5.1 zegt dat een
    # FINANCE-only gebruiker precies deze klasse ziet, en dat klopt alleen als de
    # klasse en de rol samenvallen.
    UniverseObject(
        key="payment_amount", name="Te betalen", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description=(
            "Som van de bedragen; terugbetalingen tellen negatief mee. Dit is wat 'omzet', "
            "'opbrengst' of 'inkomsten' betekent zolang de vraag het niet preciseert: wat "
            "gefactureerd is, niet wat binnenkwam. Voor dat laatste neem je 'Betaald'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_amount_paid", name="Betaald", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.amount_paid)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description=(
            "Wat er effectief ontvangen is. Niet hetzelfde als 'Te betalen': het verschil "
            "tussen die twee is wat openstaat. Vraagt iemand naar omzet zonder meer, dan "
            "bedoelt hij 'Te betalen'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_open_amount", name="Openstaand", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="SUM({view}.open_amount)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description=(
            "Te betalen min betaald — het derde getal van de rij Te betalen · "
            "Betaald · Openstaand, en zichtbaar het verschil van de eerste twee. "
            "De enige openstaand-maat sinds #871: "
            "'Openstaand volgens status' stond ernaast met een statusvoorwaarde "
            "in zijn naam, en die twee liepen uiteen zodra een betaling deels "
            "betaald was. Wil je dat tweede antwoord, neem dan 'Te betalen' met "
            "een filter op Betaalstatus — dan staat de voorwaarde op het scherm."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_refunded", name="Terugbetaald", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments",
        sql="SUM(CASE WHEN {view}.record_type = 'refund' THEN -{view}.amount ELSE 0 END)",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Terugbetaalde bedragen als positief getal.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_count", name="Aantal betalingen", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments",
        sql="COUNT(DISTINCT {view}.payment_id)", format=Format.COUNT,
        role=Role.FINANCE, additive=False, fact="f_payments",
        description=(
            "Aantal betaalrecords, vorderingen en terugbetalingen samen. Telt regels en "
            "geen gezinnen: één gezin kan er meerdere hebben."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_days_to_paid", name="Gemiddelde betaaltermijn", klass="Betalingen",
        kind=ObjectKind.MEASURE, view="f_payments", sql="AVG({view}.days_to_paid)",
        format=Format.DAYS, role=Role.FINANCE, additive=False, fact="f_payments",
        description="Gemiddeld aantal dagen tussen aanmaak en betaling, over de betaalde records.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_method", name="Betaalwijze", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_method", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description="Hoe er betaald werd of moet worden: online, overschrijving of cash.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_status", name="Status", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="d_payment_status", sql="{view}.label",
        format=Format.LABEL, role=Role.FINANCE,
        description=(
            "Waar deze betaling staat: in afwachting, betaald, mislukt of geannuleerd. Een "
            "deels betaalde vordering staat nog in afwachting."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_open", name="Openstaand (ja/nee)", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments",
        sql="CASE WHEN ABS({view}.open_amount) > 0 THEN 'Ja' ELSE 'Nee' END",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description=(
            "Of er op deze betaling nog geld openstaat — het verschil tussen te betalen "
            "en ontvangen. Kijkt naar het SALDO en niet naar de status: een deels "
            "betaalde vordering staat nog op 'In afwachting' maar kan al grotendeels "
            "voldaan zijn, en een vordering die op 'Betaald' staat kan nog een rest "
            "openhebben. Dit is dezelfde doorsnede als het tab 'Openstaand' op het "
            "betalingenscherm, en net als daar op de ABSOLUTE waarde: een "
            "terugbetaling draagt een negatief bedrag en een te veel betaalde "
            "vordering levert eveneens een negatief saldo — met een "
            "eenrichtingsvergelijking vielen die uit het filter (#668). De "
            "verduidelijking tussen haakjes staat er omdat "
            "'Openstaand' in deze klasse al het BEDRAG is dat openstaat; zo staan de "
            "twee in de kiezer naast elkaar en blijft zichtbaar dat ze over hetzelfde "
            "begrip gaan. Dezelfde vorm als 'Gemeente (adres)' en 'Aantal leden "
            "(personen)'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_type", name="Type", klass="Betalingen", kind=ObjectKind.DIMENSION,
        view="f_payments", sql="{view}.record_type_label", format=Format.LABEL,
        role=Role.FINANCE, fact="f_payments",
        description=(
            "Of deze regel een vordering is of een terugbetaling. Terugbetalingen tellen "
            "negatief mee in 'Te betalen'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_payable_type", name="Soort", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.payable_type_label",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description=(
            "Waarvoor betaald wordt: lidgeld of een activiteit. Hiermee splits je de "
            "geldvragen in hun twee stromen."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_age_bucket", name="Ouderdom", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.age_bucket",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Hoe lang een vordering al openstaat, in klassen. Betaalde records staan op 'Betaald'.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_record", name="Betaling", klass="Betalingen",
        kind=ObjectKind.DIMENSION, view="f_payments", sql="{view}.payment_id",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        drill="payment", drill_sql="{view}.payment_id",
        description="Het betaalrecord zelf. Klik door naar de betalingenpagina.",
        ai_exposure=AiExposure.PLAIN,
    ),

    UniverseObject(
        key="membership_person_count", name="Aantal lidmaatschappen (personen)", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_membership_persons",
        sql="COUNT({view}.person_id)",
        format=Format.COUNT, role=Role.ADMIN, fact="f_membership_persons",
        description=(
            "Personen met een lidmaatschap in dat jaar. Eén rij per persoon per "
            "jaar, dus tellen is optellen."
        ),
        ai_exposure=AiExposure.PLAIN,
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
        key="payment_payable_label", name="Waarvoor", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.payable_label",
        format=Format.LABEL, role=Role.MEMBER_DETAILS, fact="f_payments",
        description="Voor wie en waarvoor deze betaling is — de inschrijver en de activiteit, of het hoofdlid en het lidmaatschapsjaar.",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="payment_ogm", name="Mededeling (OGM)", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments",
        sql="{view}.structured_communication", format=Format.LABEL,
        role=Role.FINANCE, fact="f_payments",
        description="De gestructureerde mededeling op een overschrijving.",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="payment_due", name="Bedrag", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.amount",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Het bedrag van deze ene regel. Een terugbetaling is negatief.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_received", name="Betaald bedrag", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.amount_paid",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Wat er op deze regel ontvangen is.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_balance", name="Saldo", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.open_amount",
        format=Format.MONEY, role=Role.FINANCE, fact="f_payments",
        description="Te betalen min betaald, op deze regel.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_paid_on", name="Betaald op", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.paid_date",
        format=Format.DATE, role=Role.FINANCE, fact="f_payments",
        description=(
            "De dag waarop deze ene betaling binnenkwam. Leeg zolang er niets ontvangen "
            "is."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="payment_note", name="Notitie", klass="Betalingen",
        kind=ObjectKind.DETAIL, view="f_payments", sql="{view}.note",
        format=Format.LABEL, role=Role.FINANCE, fact="f_payments",
        description="Wat de penningmeester erbij schreef.",
        ai_exposure=AiExposure.NONE,
    ),

    UniverseObject(
        key="board_member", name="Verantwoordelijk bestuurslid", klass="Leden",
        kind=ObjectKind.DIMENSION, view="d_board_member",
        sql="COALESCE({view}.board_member_name, 'Niet toegewezen')",
        # NOT `sensitive`: that flag describes a dimension that cuts MEMBERS into
        # small groups, and a board member is the axis here, not the population
        # (#849). Unchanged by the removal of the threshold on 14 September 2026 —
        # the flag is a description of the data, and this description was never
        # about the rule that used to read it.
        #
        # What protects this column is `ai_exposure`: a board member is a person,
        # so it travels as `persoon-90` and the admin reads the name back on screen.
        format=Format.LABEL, role=Role.MEMBER_DETAILS,
        description=(
            "Het bestuurslid dat dit gezin tot zijn verantwoordelijkheid neemt. "
            "Gezinnen zonder toewijzing staan onder 'Niet toegewezen' — dat is "
            "een van de nuttigste uitkomsten van dit rapport, geen gat. Draagt de "
            "huidige toewijzing, geen historie."
        ),
        ai_exposure=AiExposure.TOKENISED, token_prefix="persoon",
        entity_sql="{view}.board_member_id",
    ),
    UniverseObject(
        key="member_total_count", name="Aantal gezinnen in de administratie", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_members",
        sql="COUNT(DISTINCT {view}.member_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_members", additive=False,
        description=(
            "Elk gezin in de administratie, of het ooit lid was of niet. Dat is de "
            "populatie van het feit Gezinnen; 'Aantal leden (hoofdlid)' telt op het "
            "feit Lidmaatschappen en kent alleen gezinnen die ooit aansloten. Het "
            "paneel toont bij elk rapport welke populatie je telt."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="member_ever_member", name="Ooit lid geweest", klass="Leden",
        kind=ObjectKind.DIMENSION, view="f_members",
        sql=_boolean_label("was_ever_member"), format=Format.LABEL,
        role=Role.ADMIN, fact="f_members",
        description="Of dit gezin ooit een lidmaatschap had.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_active_count", name="Aantal actieve lidmaatschappen",
        klass="Leden", kind=ObjectKind.MEASURE, view="f_memberships",
        sql="SUM({view}.active_membership_count)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_memberships",
        description=(
            "Lidmaatschappen die op actief staan. Telt lidmaatschappen en geen "
            "gezinnen — dat is wat de dashboardtegel telt."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_person_valid_today", name="Vandaag geldig", klass="Leden",
        kind=ObjectKind.DIMENSION, view="f_membership_persons",
        sql=_boolean_label("is_valid_today"), format=Format.LABEL,
        role=Role.ADMIN, fact="f_membership_persons",
        description=(
            "Of het lidmaatschap van deze persoon vandaag geldig is. Iets anders "
            "dan 'lid voor dit jaar': wie in oktober voor volgend jaar aansluit, "
            "is vandaag geldig en hoort bij volgend jaar."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="membership_person_unique", name="Aantal unieke personen", klass="Leden",
        kind=ObjectKind.MEASURE, view="f_membership_persons",
        sql="COUNT(DISTINCT {view}.person_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_membership_persons", additive=False,
        description=(
            "Personen, elk één keer geteld over alle jaren heen. Gebruik dit als "
            "je niet op jaar groepeert; anders telt 'Aantal leden (personen)'."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),

    # ── Formulieren ─────────────────────────────────────────────────────────
    UniverseObject(
        key="form_count", name="Aantal formulieren", klass="Formulieren",
        kind=ObjectKind.MEASURE, view="f_forms",
        sql="COUNT(DISTINCT {view}.form_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_forms", additive=False,
        description=(
            "Formulieren, ook die zonder één inzending. Dat is de reden dat deze "
            "telling van het formulierfeit komt en niet van de inzendingen: op "
            "het inzendingenfeit verdwijnt een leeg formulier stilzwijgend, en "
            "'welk formulier staat open en krijgt niets binnen' is juist een "
            "vraag die een bestuurder stelt (#871, dezelfde val als #848)."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_count", name="Aantal inzendingen", klass="Formulieren",
        kind=ObjectKind.MEASURE, view="f_form_submissions",
        sql="COUNT(DISTINCT {view}.submission_id)", format=Format.COUNT,
        role=Role.ADMIN, fact="f_form_submissions", additive=False,
        description=(
            "Aantal inzendingen op een formulier. Telt de inzendingen, niet de personen — "
            "wie twee keer invult, telt twee keer."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_answers", name="Ingevulde velden", klass="Formulieren",
        kind=ObjectKind.MEASURE, view="f_form_submissions",
        sql="SUM({view}.answer_count)", format=Format.COUNT, role=Role.ADMIN,
        fact="f_form_submissions",
        description="Som van de ingevulde antwoorden — hoeveel er werkelijk ingevuld is.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form", name="Formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.form_name",
        format=Format.LABEL, role=Role.ADMIN, drill="form",
        drill_sql="{view}.form_id",
        description="Naam van het formulier. Klik door naar de formulierbouwer.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_status", name="Status van het formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.form_status_label",
        format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Waar het formulier staat: concept, gepubliceerd of gesloten. Enkel een "
            "gepubliceerd formulier kan inzendingen krijgen."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="form_anonymous", name="Anoniem formulier", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="d_form", sql="{view}.is_anonymous_label",
        format=Format.LABEL, role=Role.ADMIN,
        description=(
            "Of het formulier anoniem ingevuld wordt. Bij een anoniem formulier is er geen "
            "inzender bekend, dus koppelen aan een gezin kan daar niet."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="submission_edited", name="Achteraf gewijzigd", klass="Formulieren",
        kind=ObjectKind.DIMENSION, view="f_form_submissions",
        sql=_boolean_label("was_edited"), format=Format.LABEL, role=Role.ADMIN,
        fact="f_form_submissions",
        description="Of de inzender zijn antwoord nadien nog aangepast heeft.",
        ai_exposure=AiExposure.PLAIN,
    ),

    # ── Taken ───────────────────────────────────────────────────────────────
    UniverseObject(
        key="task_count", name="Aantal taken", klass="Taken",
        kind=ObjectKind.MEASURE, view="f_tasks",
        sql="COUNT(DISTINCT {view}.item_id)", format=Format.COUNT, role=Role.ADMIN,
        fact="f_tasks", additive=False,
        description="Hoeveel taken er zijn. Filter op status Open voor de werkvoorraad.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_age_days", name="Gemiddelde ouderdom", klass="Taken",
        kind=ObjectKind.MEASURE, view="f_tasks", sql="AVG({view}.age_days)",
        format=Format.DAYS, role=Role.ADMIN, fact="f_tasks", additive=False,
        description="Gemiddeld aantal dagen dat een openstaande taak al wacht. Afgehandelde taken tellen niet mee — die wachten niet meer.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_days_to_done", name="Gemiddelde doorlooptijd", klass="Taken",
        kind=ObjectKind.MEASURE, view="f_tasks", sql="AVG({view}.days_to_done)",
        format=Format.DAYS, role=Role.ADMIN, fact="f_tasks", additive=False,
        description="Gemiddeld aantal dagen tussen aanmaken en afhandelen, over de afgehandelde taken.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_kind", name="Soort", klass="Taken",
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.kind_label",
        format=Format.LABEL, role=Role.ADMIN, fact="f_tasks",
        description=(
            "Wat voor taak het is: een terugbetaling bevestigen, een mislukte e-mail, een "
            "webhook die afwijkt, een mislukte achtergrondtaak."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_status", name="Status", klass="Taken",
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.status_label",
        format=Format.LABEL, role=Role.ADMIN, fact="f_tasks",
        description=(
            "Of de taak open staat of afgehandeld is. Filter hierop in plaats van te "
            "vertrouwen op wat het feit toevallig bevat."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_detail", name="Onderwerp", klass="Taken",
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.detail",
        format=Format.LABEL, role=Role.ADMIN, fact="f_tasks",
        description="Waar de taak over gaat: een betaalrecord, een e-mail, een achtergrondtaak.",
        ai_exposure=AiExposure.NONE,
    ),
    UniverseObject(
        key="task_role", name="Voor welke rol", klass="Taken",
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.required_role",
        format=Format.LABEL, role=Role.ADMIN, fact="f_tasks",
        description=(
            "De rol die deze taak hoort op te pakken — wie ze toegewezen krijgt, niet wie "
            "ze afhandelde."
        ),
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_age_bucket", name="Ouderdom", klass="Taken",
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.age_bucket",
        format=Format.LABEL, role=Role.ADMIN, fact="f_tasks",
        description="Hoe lang een taak al open staat, in klassen. Afgehandelde taken staan op 'Afgehandeld'.",
        ai_exposure=AiExposure.PLAIN,
    ),
    UniverseObject(
        key="task_done_by", name="Afgehandeld door", klass="Taken",
        # A dimension and not a detail, corrected when the gate of #852 refused
        # the personal work list of #847. An e-mail address is a key, unlike a
        # free-text note, and "how many did each of us close" is a question — it
        # is the very question `@ik` was built for. The declaration was wrong,
        # not the report.
        kind=ObjectKind.DIMENSION, view="f_tasks", sql="{view}.done_by",
        format=Format.LABEL, role=Role.MEMBER_DETAILS, fact="f_tasks",
        description=(
            "Het e-mailadres van wie de taak afsloot. Groepeerbaar: dat is de "
            "vraag 'hoeveel heeft ieder van ons afgewerkt'."
        ),
        ai_exposure=AiExposure.NONE,
    ),
)


# ── Lookups ──────────────────────────────────────────────────────────────────

BY_KEY: dict[str, UniverseObject] = {o.key: o for o in OBJECTS}
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
        bruikbaar = [k for k in self.level_keys
                     if BY_KEY[k].kind is ObjectKind.DIMENSION]
        if key not in bruikbaar:
            return ""
        index = bruikbaar.index(key) + richting
        return bruikbaar[index] if 0 <= index < len(bruikbaar) else ""


def _date_levels(prefix: str) -> tuple[str, ...]:
    return tuple(f"{prefix}{korrel}"
                 for korrel in ("year", "quarter", "month", "day"))


HIERARCHIES: tuple[Hierarchy, ...] = (
    # Elke datum staat bij haar onderwerp (#901). De klasse "Tijd" bestond niet
    # meer zodra dat doorgetrokken werd: ze was ingedeeld naar SOORT ding en niet
    # naar onderwerp, net als "Betaaldetail" voor #871.
    Hierarchy(key="registration_date", name="Inschrijfdatum", klass="Activiteiten",
              level_keys=_date_levels("registration_date_")),
    Hierarchy(key="start_date", name="Startdatum", klass="Activiteiten",
              level_keys=_date_levels("start_date_")),
    Hierarchy(key="end_date", name="Einddatum", klass="Activiteiten",
              level_keys=_date_levels("end_date_")),
    Hierarchy(key="payment_created", name="Aanmaakdatum", klass="Betalingen",
              level_keys=_date_levels("payment_created_")),
    Hierarchy(key="paid_date", name="Betaaldatum", klass="Betalingen",
              level_keys=_date_levels("paid_date_")),
    Hierarchy(key="member_created", name="Aanmaakdatum gezin", klass="Leden",
              level_keys=_date_levels("member_created_")),
    Hierarchy(key="form_created", name="Aanmaakdatum formulier",
              klass="Formulieren", level_keys=_date_levels("form_created_")),
    Hierarchy(key="submission_date", name="Inzenddatum", klass="Formulieren",
              level_keys=_date_levels("submission_date_")),
    Hierarchy(key="task_created", name="Aanmaakdatum taak", klass="Taken",
              level_keys=_date_levels("task_created_")),
    Hierarchy(key="done_date", name="Afhandeldatum", klass="Taken",
              level_keys=_date_levels("done_date_")),
)

HIERARCHY_OF: dict[str, Hierarchy] = {
    key: hier for hier in HIERARCHIES for key in hier.level_keys}


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
    return sorted((o for o in OBJECTS if o.in_pane),
                  key=lambda o: (order.get(o.klass, len(order)), OBJECTS.index(o)))


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

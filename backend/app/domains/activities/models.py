from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.domains.mdm.api import PaymentMethod
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.rules import aggregate
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin

if TYPE_CHECKING:
    from app.domains.media.api import MediaAsset
    from app.kernel.money import Money


def _media_of(owner_id: Any, fk_attr: str, kind: str) -> Any:
    """The join of a media asset of one kind to its owner — `media`'s table read
    through its facade. MediaAsset is not soft-deletable, so the global filter
    does not touch it."""
    from sqlalchemy import and_
    from sqlalchemy.orm import foreign

    from app.domains.media.api import MediaAsset, MediaKind

    return and_(
        foreign(getattr(MediaAsset, fk_attr)) == owner_id,
        MediaAsset.kind == getattr(MediaKind, kind),
    )


def _media_newest_first() -> Any:
    from app.domains.media.api import MediaAsset

    return MediaAsset.id.desc()


class ActivityStatus(CodeEnum):
    """Whether an activity is on the public site (#1428, Koen 1 October 2026).

    An Enum because the code branches on it: a draft is left out of every
    public place. In Koen's programme spreadsheet a draft was "TBD" and a
    published activity "OK". Cancelled stays a state of its own
    (`is_cancelled`): a published activity can be cancelled.
    """

    DRAFT = "draft"
    PUBLISHED = "published"


class RegistrationState(CodeEnum):
    """Whether an activity accepts a NEW registration, and if not, why (#974).

    The reason matters as much as the answer: the refusal message and the badge on
    the card say different things for "this has passed" and "registrations closed
    on 1 October", and a caller that only gets a boolean will guess.
    """

    OPEN = "open"
    #: No date of the activity lies today or later.
    PAST = "past"
    #: The registration deadline has passed.
    CLOSED = "closed"
    #: The activity is cancelled. Until #974 only the public card knew this: it
    #: hid the button, while the server accepted a form that was posted anyway.
    #: Koen decided on 16 September 2026 that the server refuses too.
    CANCELLED = "cancelled"


class ActivityError(ValueError):
    """A domain rule of this component was violated (#679, batch 3).

    Not an HTTPException: that belongs to the entrance, not to the rule. The router
    turns it into a 422; a script may do something else with it.

    English since CR-13 phase 0a (§B4.4): one exception class per domain, English,
    and the Dutch name it had before stays as an alias — one class, two names, no
    rename of the callers. New rules raise `ActivityError`. It lives here rather
    than in `service.py` since #792, because a rule that lives on an object itself
    needs it and a model may not import from the service.
    """


#: The Dutch name this class had before CR-13 (§B4.4). The same class, not a
#: second one: `except ActiviteitFout` keeps catching `ActivityError`. Removed
#: only when the last Dutch reference is gone.
ActiviteitFout = ActivityError


class RegistrationRefused(ActivityError):
    """A registration refused for its circumstances, not its fields: closed, full,
    a product that is not the component's, a quantity out of bounds (CR-13 phase 1).

    A kind of `ActivityError`, so every `except ActivityError` still catches it; the
    entrance tells it apart only to keep the answer it gave before the rules moved
    into the service (400, where a missing field is a 422).
    """


class RegistrationLimitReached(RegistrationRefused):
    """The tenant's limit of registrations per e-mail address for a component is
    reached — the one refusal the entrance answers with a 409 (a conflict with what
    is there), as it did before (#1284)."""


class ActivityOrganiser(TenantMixin, Base):
    """One "trekker" of an activity (#1004, CR-10 §3.9).

    Up to three, kept in `sort_order` 0..2 — a CHECK in the database says so and
    the service refuses the fourth with a readable message. The screen hiding the
    button is a courtesy, not the limit.

    `person_id` is a soft reference to `mdm.persons` (§8: no foreign key across
    schemas). No soft delete: removing an organiser removes the fact that they
    carried this activity; there is nothing to keep a tombstone for.

    `is_contact` is what a poster reads: ticked means name and details are
    published. The overrides are per activity — someone can be reachable on
    another address for this one without touching their member record.
    """

    __tablename__ = "activity_organisers"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_contact = Column(Boolean, nullable=False, default=False)
    email_override = Column(String(255), nullable=True)
    mobile_override = Column(String(50), nullable=True)
    # #1032: mag dit gegeven op de affiche? Standaard ja, zodat er niets verandert
    # aan wat er vandaag gedrukt wordt. Een LEGE override betekent "neem de
    # ledenwaarde" — niet "toon niets"; daarvoor zijn deze twee.
    show_email = Column(Boolean, nullable=False, default=True)
    show_mobile = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    activity = relationship("Activity", back_populates="organisers")


class ActivityDate(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "activity_dates"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(
        Integer, ForeignKey("activities.activities.id", ondelete="CASCADE"), nullable=False
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    activity = relationship("Activity", back_populates="dates")

    def validate_coherence(self) -> None:
        """A date row may not end before it starts (#792).

        **On the object and not in the screen**, per the placement rule of CR-04: this
        rule looks at several fields of the same object, so it belongs on the object. A
        check in the create form would let the editor keep the hole — and then there
        are two truths about the same row. Until now the editor happily saved a row
        running from 20 September to 18 September.

        The time only counts within a single day. A row starting at 20:00 and ending at
        02:00 the next morning is not wrong; it simply lasts a night.

        Equal times on the same day ARE wrong: a row from 14:00 to 14:00 lasts nothing,
        and that is almost always a half-finished entry.
        """
        from app.i18n import _ as translate

        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ActiviteitFout(translate("De einddatum ligt vóór de begindatum."))
        one_day = self.end_date is None or self.end_date == self.start_date
        if one_day and self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ActiviteitFout(translate("Het einduur ligt niet na het beginuur."))


# The rule applies at EVERY entrance, not only at the two screens that exist today
# (#792). A service that forgets to validate, a script, or a future import route all
# pass through here: this fires on the write itself.
@event.listens_for(ActivityDate, "before_insert")
@event.listens_for(ActivityDate, "before_update")
def _enforce_date_coherence(mapper: Any, connection: Any, target: ActivityDate) -> None:  # noqa: ARG001
    target.validate_coherence()


class Activity(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "activities"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    # Optionele vriendelijke URL (#884), uniek per tenant — zelfde patroon als
    # `CmsPage.slug`. VOLGT DE NAAM NIET: bij het aanmaken wordt er één voorgesteld,
    # daarna blijft hij staan, ook als de activiteit hernoemd wordt. Anders breken
    # gedeelde links zonder dat iemand het merkt — wie op zo'n link klikt is geen
    # bestuurder en meldt het dus nooit.
    slug = Column(String(255), nullable=True, index=True)
    location = Column(String(255), nullable=True)
    # #1016: two or three sentences the visitor reads — on the activity page and
    # in the newsletter block (#984). Since #1028 Raakje reads it too — the
    # question "what is this about?" used to be answered from the poster text.
    description = Column(Text, nullable=True)
    poster_url = Column(Text, nullable=True)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    members_only = Column(Boolean, default=False, nullable=False)
    # #1028: de interne nota van het bestuur — alleen op het beheerscherm. Hier
    # stond `notes`, met de opmerking dat die kolom nergens getoond werd; dat
    # klopte niet (de publieke bot zette hem in `get_activity_detail`), dus ze is
    # weg en deze begint leeg, onder een naam die niet met de oude te verwarren
    # is. Wat de bezoeker mag lezen is `description` hierboven.
    board_notes = Column(Text, nullable=True)
    # #1428: draft or published. Every activity that existed before is published
    # (migration 179); a new one by hand is too, as before; a copy starts as a
    # draft unless the copy step says otherwise.
    status: Mapped[ActivityStatus] = mapped_column(
        EnumColumn(ActivityStatus, length=20),
        ForeignKey("activities.activity_status_codes.code"),
        nullable=False,
        default=ActivityStatus.PUBLISHED,
    )
    # #1428: who the activity is for — ONE value, on purpose (Koen: "vandaag is
    # het altijd één"). If one activity ever needs more, that is a link table,
    # not a second column. A plain code with a foreign key and no Enum: nothing in
    # Python branches on it yet (docs/code-style.md). Empty until the board picks.
    target_audience = Column(
        String(20), ForeignKey("activities.target_audience_codes.code"), nullable=True
    )
    # #1397: the activity this one was copied from, if any. No foreign key:
    # activities are soft-deleted, and a link to a deleted predecessor is history.
    # The Design Studio reads the chain to offer last year's photos.
    copied_from_id = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    organisers = relationship(
        "ActivityOrganiser",
        back_populates="activity",
        cascade="all, delete-orphan",
        # GEEN id-tiebreak nodig, en dat is gemeten (#1068): migratie 133 legt een
        # unieke sleutel op (activity_id, sort_order) plus een CHECK op 0/1/2, dus
        # twee organisatoren kunnen geen gelijke `sort_order` hebben. Zonder
        # gelijkstand is er niets om willekeurig te ordenen. Zie
        # `test_sorteervolgorde_gelijkstand.py`, dat die sleutel vastlegt — valt
        # hij weg, dan geldt deze redenering niet meer.
        order_by="ActivityOrganiser.sort_order",
    )
    dates = relationship("ActivityDate", back_populates="activity", cascade="all, delete-orphan")
    # #1340: oldest first, and the id breaks a tie. Without an order the list —
    # "Wie doet er mee?" reads it — followed the order in which PostgreSQL returned
    # the rows, which is not the order of registering: a registration the board
    # types in afterwards for an earlier moment, or a row rewritten by an update,
    # landed anywhere.
    registrations = relationship(
        "Registration",
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="Registration.registered_at, Registration.id",
    )
    # De id is de tiebreak, en dat is geen franje: `sort_order` staat standaard op 0,
    # dus twee onderdelen die je achter elkaar toevoegt zijn gelijk gerangschikt en
    # Postgres mag ze dan in om het even welke volgorde teruggeven. Dat gebeurde ook:
    # CI-run 35499069480 zette op de Inschrijvingen-tab het tweede onderdeel boven het
    # eerste, terwijl dezelfde code lokaal de invoegvolgorde gaf. Met de id erbij is
    # de volgorde overal dezelfde — en sinds #1053 draagt elk onderdeel zijn eigen
    # uiterste datum, dus een wisselende volgorde is ook op de publieke kaart zichtbaar.
    sub_registrations = relationship(
        "ActivitySubRegistration",
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="ActivitySubRegistration.sort_order, ActivitySubRegistration.id",
    )

    # The uploaded poster, newest first (#223). A read-only relationship and not a
    # query from the entity (CR-13 phase 4, §B4.1: an entity never opens a session);
    # it loads the way every relationship does, once, when first read.
    poster_assets = relationship(
        "MediaAsset",
        primaryjoin=lambda: _media_of(Activity.id, "activity_id", "ACTIVITY_POSTER"),
        viewonly=True,
        order_by=lambda: _media_newest_first(),
    )

    @property
    def _poster_asset(self) -> Optional[MediaAsset]:
        return self.poster_assets[0] if self.poster_assets else None

    @property
    def poster_asset_url(self) -> Optional[str]:
        """Een geüploade poster primeert op ``poster_url`` (#223)."""
        from app.domains.media.api import media_url

        a = self._poster_asset
        return media_url(a.id) if a else None

    @property
    def poster_asset_title(self) -> Optional[str]:
        """De titel van de opgeladen affiche (feedbackronde golf 8): de leeslink
        toont wat er hangt, niet een generieke tekst."""
        a = self._poster_asset
        return a.title if a else None

    @property
    def poster_asset_is_pdf(self) -> bool:
        a = self._poster_asset
        return bool(a and a.content_type == "application/pdf")


def _blank(value: object) -> bool:
    """Empty or only whitespace counts as not filled in (#733)."""
    return not (str(value) if value is not None else "").strip()


@aggregate
class Registration(TenantMixin, SoftDeleteMixin, Base):
    """One registration for an activity: the aggregate of CR-13 phase 1 (#757).

    Its rules live at the four addresses of §B4.2, each for what it can judge:

    - **one field** — `@validates` refuses a blank name, and a blank or malformed
      e-mail address, on every assignment, on every path: the public form, the JSON API, the board's form
      and the screen that corrects a registration afterwards (#733). It does not
      fire on a field that is never assigned; `NOT NULL` at rest catches that;
    - **several fields, already loaded** — `check()`: a component that asks for a
      team name gets one. It runs on every flush through the kernel's listener
      (`kernel/rules.py`), so nobody has to call it. The team name follows the
      component's CURRENT setting, not the row's history (Koen, 8 September 2026);
      it cannot be a constraint, because it needs the component;
    - **the mobile number** is required at the entrances, not on the row: no
      database constraint on the registration phone (Koen, 29 September 2026); the
      entrances still require it — `service.require_phone`, on every way in. A
      validator without its constraint is what the gate refuses, so it is not one;
    - **other rows** — full, already registered, open — stay service functions;
    - **at rest** — the constraints of the phase-1 migration.

    Until phase 1 these checks were one function (`controleer_inschrijfvelden`)
    every writer had to remember to call; that function is gone, not copied.
    """

    __tablename__ = "registrations"
    # CR-13 phase 1 (§B5.2): what `@validates` says about one field, at rest too —
    # the same rules as migration 168, which is where the environments get them.
    __table_args__ = (
        CheckConstraint(
            "btrim(contact_name) <> ''", name="ck_registrations_contact_name_not_blank"
        ),
        CheckConstraint(
            "btrim(contact_email) <> ''", name="ck_registrations_contact_email_not_blank"
        ),
        # CR-14 phase 2 (§B2.3): answered and still waiting for answers cannot both
        # be true — the answer link is cleared when the answers come in.
        CheckConstraint(
            "form_submission_id IS NULL OR answer_token IS NULL",
            name="ck_registrations_answered_or_open",
        ),
        Index(
            "uq_registrations_form_submission_id_living",
            "form_submission_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND form_submission_id IS NOT NULL"),
        ),
        Index("uq_registrations_answer_token", "answer_token", unique=True),
        {"schema": "activities"},
    )

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.activities.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    registered_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # CR-12 phase 4: the list moved into this schema, so the key is allowed now.
    registration_type = Column(
        String(10), ForeignKey("activities.registration_type_codes.code"), nullable=False
    )

    contact_name = Column(String(200), nullable=False)
    contact_email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    team_name = Column(String(200), nullable=True)
    # CR-12 phase 1: the same list as `payment.payment_records.method`,
    # so the same shape — `mdm.payment_method_codes` with an FK. Nullable:
    # a free registration has no payment method.
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(
        EnumColumn(PaymentMethod, length=20), nullable=True
    )
    component_id = Column(
        Integer,
        ForeignKey("activities.activity_sub_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    remarks = Column(Text, nullable=True)
    # CR-14 phase 2 (§B4.2, §B4.8): the answers to the component's questions, or —
    # while they are still to come — the secret of the link that asks for them. A
    # soft reference across the schema line (#396): no key in the database and no
    # ORM relationship — whoever needs the submission reads it through `forms.api`.
    # The form builder refuses to delete a submission it marked `attached`.
    form_submission_id = Column(Integer, nullable=True)
    answer_token = Column(String(64), nullable=True)

    activity = relationship("Activity", back_populates="registrations")
    person = relationship("Person", backref="registrations")
    # #1352: in the order they were added. Without an order a registration's lines
    # came back as PostgreSQL returned them — a characterisation snapshot saw
    # "on site, paid, free" once in a large run where it had recorded "paid, free,
    # on site". The registration detail pairs the lines with the amounts of
    # `compute_registration_total` by position; both read this one collection, so
    # both follow this one order.
    items = relationship(
        "RegistrationItem",
        back_populates="registration",
        cascade="all, delete-orphan",
        order_by="RegistrationItem.id",
    )
    # Read-only: `component_id` stays the one column that is written. `check()` reads
    # the component through this. A service that has the component sets it, and then
    # nothing is queried (§B4.1); `load_on_pending` is the net under every other way
    # in: SQLAlchemy does not load a relationship of an object that is not saved
    # yet, so without it a new registration with only `component_id` would pass
    # `check()` without its component — the team-name rule silently skipped. With
    # it, the flush reads the component once. A read, never a skipped rule.
    component = relationship("ActivitySubRegistration", viewonly=True, load_on_pending=True)

    @validates("contact_name")
    def _name_not_blank(self, key: str, value: Optional[str]) -> Optional[str]:
        """A name is never blank (#733). The value is kept as given — stripping
        would change what is stored today (R13)."""
        if _blank(value):
            from app.i18n import _

            raise ActivityError(_("Vul een naam in."))
        return value

    @validates("contact_email")
    def _well_formed_email(self, key: str, value: Optional[str]) -> Optional[str]:
        """An e-mail address is never blank and always well-formed — on every path,
        the screen that corrects a registration included (Koen, 29 September 2026:
        the board can change an address, not clear it). The same check `EmailStr`
        runs on the forms, without looking up the domain; the value is kept as given."""
        from email_validator import EmailNotValidError, validate_email

        from app.i18n import _

        if _blank(value):
            raise ActivityError(_("Vul een geldig e-mailadres in."))
        try:
            validate_email(str(value), check_deliverability=False)
        except EmailNotValidError:
            raise ActivityError(_("Vul een geldig e-mailadres in.")) from None
        return value

    def total(self) -> Money:
        """What this registration costs, as `Money` (CR-13 phase 1, §B4.3).

        Delegates to `activities.totals.compute_registration_total`, the one owner of
        the computation, and stays that way (master CLI, 29 September 2026): the
        price rule of a line — the member price on the registration date, free and
        pay-on-site lines not counted — also prices the public form's quote before
        any registration exists and the back office's live recomputation. Moving it
        onto this model would split one rule over two places or make those quotes
        need a registration they do not have. A parity test binds the method, both
        quotes and the report's view to each other.

        Reads the items with their products and the person with the memberships;
        loaded by whoever asks, never queried here (§B4.1).
        """
        from app.domains.activities.totals import compute_registration_total
        from app.kernel.money import Money

        return Money(compute_registration_total(self)[0])

    def check(self) -> None:
        """The rule over several fields: a component that asks for a team name gets one.

        Not here: "the answers belong to the component's own questions" (CR-14). The
        submission lives across the schema line, and a rule on a flush reads only
        what is loaded; it holds by construction at its one writer
        (`service.take_answers`, which creates the submission for the component's
        own form)."""
        component = self.component if self.component_id is not None else None
        if component is not None and component.team_name_required and _blank(self.team_name):
            from app.i18n import _

            raise ActivityError(_("Dit onderdeel vraagt een ploegnaam."))


class RegistrationItem(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "registration_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_registration_items_quantity_positive"),
        {"schema": "activities"},
    )

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("activities.registrations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("activities.activity_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    registration = relationship("Registration", back_populates="items")
    product = relationship("ActivityProduct")


class ActivitySubRegistration(TenantMixin, SoftDeleteMixin, Base):
    """A component (onderdeel) of an activity. Each component can have products."""

    __tablename__ = "activity_sub_registrations"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_activity_sub_registrations_price_non_negative"),
        CheckConstraint(
            "member_price >= 0 OR member_price IS NULL",
            name="ck_activity_sub_registrations_member_price_non_negative",
        ),
        CheckConstraint(
            "max_participants IS NULL OR max_participants > 0",
            name="ck_activity_sub_registrations_max_participants_positive",
        ),
        {"schema": "activities"},
    )

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.activities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    external_register_url = Column(String(500), nullable=True)
    external_registrations_url = Column(String(500), nullable=True)
    info_url = Column(String(500), nullable=True)
    # CR-12 phase 4: the list moved into this schema, so the key is allowed now.
    registration_type_code = Column(
        String(10),
        ForeignKey("activities.registration_type_codes.code"),
        nullable=False,
        default="INDIVIDUAL",
    )
    max_participants = Column(Integer, nullable=True)
    # #1053: the last day on which a NEW registration for THIS component is
    # accepted, inclusive, in Belgian time. A date and not a timestamp: what the
    # board types is a day. It sat on the activity until #1053 — and then the
    # barbecue's deadline also closed cornhole, which is the case Koen ran into.
    # Who decides whether registration is open is `service.registration_state`;
    # this column is only one of its inputs.
    registration_closes_on = Column(Date, nullable=True)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    member_price = Column(Numeric(10, 2), nullable=True)
    is_free = Column(Boolean, default=True, nullable=False)
    team_name_required = Column(Boolean, default=False, nullable=False)
    # CR-14 phase 2 (§B4.5): the questions this component asks, a form of the form
    # builder. A soft reference (#396): no key, no ORM relationship — read through
    # `service.question_form`. A form deleted in the builder leaves the id behind,
    # and the component then asks nothing.
    form_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    activity = relationship("Activity", back_populates="sub_registrations")
    products = relationship(
        "ActivityProduct",
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="ActivityProduct.sort_order, ActivityProduct.id",
    )  # id als tiebreak, #1068

    # The uploaded info/rules file, newest first (#223) — a read-only relationship,
    # like the activity's poster (CR-13 phase 4).
    info_assets = relationship(
        "MediaAsset",
        primaryjoin=lambda: _media_of(ActivitySubRegistration.id, "component_id", "COMPONENT_INFO"),
        viewonly=True,
        order_by=lambda: _media_newest_first(),
    )

    def _info_asset(self) -> Optional[MediaAsset]:
        return self.info_assets[0] if self.info_assets else None

    @property
    def info_asset_url(self) -> Optional[str]:
        """Een geüpload info/reglement-bestand primeert op ``info_url`` (#223)."""
        from app.domains.media.api import media_url

        a = self._info_asset()
        return media_url(a.id) if a else None

    @property
    def info_asset_is_pdf(self) -> bool:
        a = self._info_asset()
        return bool(a and a.content_type == "application/pdf")


class ActivityProduct(TenantMixin, SoftDeleteMixin, Base):
    """A product (inschrijvingsoptie) within an activity component."""

    __tablename__ = "activity_products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_activity_products_price_non_negative"),
        CheckConstraint(
            "member_price >= 0 OR member_price IS NULL",
            name="ck_activity_products_member_price_non_negative",
        ),
        CheckConstraint(
            "max_participants IS NULL OR max_participants > 0",
            name="ck_activity_products_max_participants_positive",
        ),
        {"schema": "activities"},
    )

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(
        Integer, ForeignKey("activities.activity_sub_registrations.id"), nullable=False
    )
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    member_price = Column(Numeric(10, 2), nullable=True)
    is_free = Column(Boolean, default=True, nullable=False)
    # Ter plaatse / op eigen budget te betalen (#373): inschrijven verplicht, maar
    # NIET via het portaal afrekenen. Telt — net als is_free — niet mee in het
    # Mollie-totaal. Sluit is_free uit (een product is betalend, gratis óf ter plaatse).
    pay_on_site = Column(Boolean, default=False, nullable=False, server_default="false")
    # #1191: off means "gone from the public registration form", NOT "closed".
    # The board can still book an inactive product from the back office — that is
    # the whole reason the flag exists (Koen, 26 September 2026): a guest list is
    # entered on a product no visitor may pick. Deleting the product instead would
    # keep the line but drop its name from the screen and its column from the
    # door list, because both read the LIVING products.
    #
    # This is the master switch, the role `is_active` already plays on MediaAsset:
    # off means nowhere on the public side, whatever is_free or pay_on_site say.
    # Comes last in that order on purpose — a price only matters once the product
    # can be picked at all.
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    max_participants = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    component = relationship("ActivitySubRegistration", back_populates="products")


class HistoryMixin:
    """Gedeelde audit-metadata voor de history-tabellen van dit component."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)
    action = Column(String(40), nullable=False)
    source = Column(String(30), nullable=False)
    actor = Column(String(255), nullable=True)
    recorded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class RegistrationItemHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van bestelregels (#84): elke insert/update/delete van een
    RegistrationItem, zodat wijzigingen aan een bestelling ná betaling traceerbaar
    zijn (bv. product wisselen naar een helper-variant, of een regel verwijderen)."""

    __tablename__ = "registration_item_history"
    __table_args__ = {"schema": "activities"}

    registration_item_id = Column(Integer, nullable=False, index=True)
    registration_id = Column(Integer, nullable=True, index=True)
    product_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)


class RegistrationHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van de CONTACTGEGEVENS van een inschrijving (#624).

    Een beheerder mag een tikfout in naam, e-mail of gsm rechtzetten; zonder spoor
    is zo'n stille correctie op iemands contactgegevens niet te verklaren. De
    bestelregels hebben hun eigen historie (RegistrationItemHistory) — deze tabel
    gaat enkel over wie de inschrijver is en wat hij meegaf.
    """

    __tablename__ = "registration_history"
    __table_args__ = {"schema": "activities"}

    registration_id = Column(Integer, nullable=False, index=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    remarks = Column(Text, nullable=True)
    # CR-14 phase 3 (§B4.7): the answers to the component's questions, as
    # "label: value" lines, on the rows of an action that concerns them — the
    # previous such row is the old answers, this the new.
    answers = Column(Text, nullable=True)


class ActivityHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van activiteiten (#189), incl. soft-delete."""

    __tablename__ = "activity_history"
    __table_args__ = {"schema": "activities"}

    activity_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=True)


class ActivityDateHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van activiteitdatums (#189)."""

    __tablename__ = "activity_date_history"
    __table_args__ = {"schema": "activities"}

    activity_date_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)


class ComponentHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van onderdelen (activity_sub_registration) (#189)."""

    __tablename__ = "component_history"
    __table_args__ = {"schema": "activities"}

    component_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)


class ProductHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van producten (activity_product) (#189)."""

    __tablename__ = "product_history"
    __table_args__ = {"schema": "activities"}

    product_id = Column(Integer, nullable=False, index=True)
    component_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)


class RegistrationTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4).

    Moved out of `public` in CR-12 phase 4. Until then the two columns that
    store it carried no foreign key, because §8 forbids one across schemas;
    in its own schema the key is allowed and both columns get it.
    """

    __tablename__ = "registration_type_codes"
    __table_args__ = {"schema": "activities"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class RegistrationTypeLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "registration_type_labels"
    __table_args__ = {"schema": "activities"}

    code = Column(
        String(10), ForeignKey("activities.registration_type_codes.code"), primary_key=True
    )
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RegistrationStateCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4).

    A DERIVED list (§B5.3 note 5): the state is computed by
    `service.registration_state` and stored nowhere, so no column points here.
    The table exists so that its words come from `code_label()` like every
    other code's.
    """

    __tablename__ = "registration_state_codes"
    __table_args__ = {"schema": "activities"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class RegistrationStateLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "registration_state_labels"
    __table_args__ = {"schema": "activities"}

    code = Column(
        String(10), ForeignKey("activities.registration_state_codes.code"), primary_key=True
    )
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ActivityStatusCode(Base):
    """Which activity statuses exist — the target of the foreign key (#1428)."""

    __tablename__ = "activity_status_codes"
    __table_args__ = {"schema": "activities"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ActivityStatusLabel(Base):
    """The word a screen shows for an activity status, per language (#1428)."""

    __tablename__ = "activity_status_labels"
    __table_args__ = {"schema": "activities"}

    code = Column(String(20), ForeignKey("activities.activity_status_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TargetAudienceCode(Base):
    """Which target audiences exist — the target of the foreign key (#1428)."""

    __tablename__ = "target_audience_codes"
    __table_args__ = {"schema": "activities"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class TargetAudienceLabel(Base):
    """The word a screen shows for a target audience, per language (#1428)."""

    __tablename__ = "target_audience_labels"
    __table_args__ = {"schema": "activities"}

    code = Column(String(20), ForeignKey("activities.target_audience_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

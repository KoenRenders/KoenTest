"""Masterdata (MDM-component, fase 2 #400 — §5.3/§6): personen, gezinnen,
adressen, contactgegevens, postcodes, externe nummers, organisaties en de
bijbehorende codetabellen + history. Alles in Postgres-schema ``mdm``.

Survivorship (§6): een Person wordt nooit hard verwijderd bij een merge —
``superseded_by_id`` wijst naar de overlever; ``service.resolve()`` slaat de
keten plat (O(1) doordat merges platgeslagen worden bijgehouden).
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.rules import aggregate, exemption
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MasterDataError(ValueError):
    """A rule of master data was violated (CR-13 phase 3, §B4.4).

    Not an HTTPException: that belongs to the entrance, not to the rule. English,
    one class for the domain; the older `MergeError` and `TenantFout` predate it.
    It lives here rather than in a service because a rule on an object raises it,
    and a model may not import from a service.
    """


class EmailAddressInUse(MasterDataError):
    """An e-mail address that another person outside the household already
    uses (CR-22 R4, R7; #1704). Inside one household persons may share an
    address — the household acts as one; outside it, an address says who
    signs in."""


class PersonDetailsMissing(MasterDataError):
    """A member of a household without a birth date or a gender (#681)."""


class MainMemberMobileMissing(MasterDataError):
    """The main member of a household without a mobile number (#1590)."""


#: The rule of #681, by name — what `kernel.rules.exempt` names when a path may
#: stand it aside.
HOUSEHOLD_MEMBER_DETAILS = "household member details"

#: The one path that may: the member report import (Koen, 29 September 2026, #1250).
#: It reads a household member without a birth date or a gender in, and says so in
#: its report (`import_service._meld_onvolledig`, #681/#685) — because the report of
#: Raak Nationaal is the source of truth, and a member missing from the
#: administration is worse than an incomplete card. Every other path refuses.
MEMBER_REPORT_IMPORT = "the member report import reads what Raak Nationaal holds, incomplete or not"


def _blank(value: object) -> bool:
    """Empty or only whitespace counts as not filled in."""
    return not (str(value) if value is not None else "").strip()


def _changed(obj: object, *fields: str) -> bool:
    """Whether any of these columns changes in the coming flush — the object's own
    bookkeeping, no query."""
    state = sa_inspect(obj)
    return any(state.attrs[field].history.has_changes() for field in fields)


# ── The vocabularies of this domain (CR-12 phase 2) ─────────────────────────
#
# Up front, because the columns below use them in their declaration:
# `Mapped[LegalForm] = mapped_column(EnumColumn(LegalForm))` is executed at
# class-definition time, not evaluated lazily.


class TenantKind(CodeEnum):
    """What a tenant's site is for (CR-19 §C4.1, §C4.6; #1478).

    The operator chooses it once, in words a person uses; it gives a new tenant
    its module set (`app/kernel/modules.py`, `DEFAULTS`). Next to `legal_form`
    and not instead of it: the legal form is about law — a company can run a
    club — the kind about what the site is for. On UNIT rows, the tenants, and
    since #1523 on the PLATFORM row (its own kind, PLATFORM); NULL on ACCOUNT. No
    standard has a home for "kind of site" (UBL's `PartyLegalEntity` holds the
    legal form), so this one is ours.
    """

    ASSOCIATION = "VERENIGING"
    COMPANY = "BEDRIJF"
    #: The platform's own kind (#1523): there is one platform, so a new tenant
    #: never takes it (`tenant_service.CREATABLE_TENANT_KINDS`).
    PLATFORM = "PLATFORM"


class LegalForm(CodeEnum):
    """The legal forms the code list knows (#924, pattern of #779).

    The code lives in the database, the label per language in
    `mdm.legal_form_labels`, and this Enum is where the code comes from in the
    application. Extensible: a new form is a row plus a member.

    CR-12 phase 2: from `str, Enum` to a plain enum (now `CodeEnum`, #1280). With the `str` mixin,
    `organisatie.legal_form == "VZW"` remained a valid comparison that happened
    to be true; with a plain one it is silently false, and therefore findable.
    """

    #: Member names English, values unchanged (§B4.3, which gives
    #: `LegalForm.COMPANY = "BEDRIJF"` literally as its example). The value is
    #: stored data and stays; the name is an identifier and falls under the
    #: English rule.
    NON_PROFIT = "VZW"
    UNINCORPORATED = "FEITELIJKE_VERENIGING"
    COMPANY = "BEDRIJF"


class OrganizationType(CodeEnum):
    """What kind of organization this is (CR-12 phase 2).

    `ACCOUNT` is the legal entity that holds the account, `UNIT` a unit,
    `PLATFORM` the one organization that represents the platform itself (#406).
    The column had a CHECK constraint with these three values; it goes away with
    the foreign key, because otherwise a fourth kind costs a row and a migration.
    """

    ACCOUNT = "ACCOUNT"
    UNIT = "UNIT"
    PLATFORM = "PLATFORM"


class RelationType(CodeEnum):
    """How a person belongs to a household (CR-12 phase 2).

    Member names are English, values remain the stored Dutch codes (§B4.3):
    the value is data and does not change, the name is an identifier and falls
    under the English rule.
    """

    PRIMARY_MEMBER = "HOOFDLID"
    PARTNER = "PARTNER"
    ADULT_CHILD = "KIND"


#: The order of a household (Koen, 29 September 2026): the main member, the partner,
#: then the children. One source: the family portal sorts on it
#: (`MemberPerson.household_position`) and the member report import derives its
#: `RELATIE_ORDER` from it.
HOUSEHOLD_ORDER = (RelationType.PRIMARY_MEMBER, RelationType.PARTNER, RelationType.ADULT_CHILD)


class Member(TenantMixin, SoftDeleteMixin, Base):
    """Household grouping — dynamic, can change over time."""

    __tablename__ = "members"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    board_member_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    member_persons = relationship(
        "MemberPerson", back_populates="member", cascade="all, delete-orphan"
    )
    # Bewust GEEN memberships-relatie hier: lidmaatschap is een ander domein
    # (fase 4a). Membership definieert de koppeling via een backref, zodat de
    # masterdata standalone geladen kan worden (§6, soft-ref-richting).
    board_member = relationship("Person", foreign_keys=[board_member_id])


@aggregate
class Person(TenantMixin, SoftDeleteMixin, Base):
    """Stable, permanent individual entity (CR-13 phase 3, #1250).

    Its rules, each at its address (§B4.2):

    - **one field** — `@validates`: a person always has a first and a last name
      (Koen, 29 September 2026), on every assignment, on every path;
    - **several fields and the household link, already loaded** — `check()`: a
      member of a household has a birth date and a gender (#681) — the same rule
      `MemberPerson.check()` holds for a new link, here for a change to a person who
      is in a household. Only when the person's own details change, so a merge or
      a soft delete of an old incomplete row stays possible;
    - **at rest** — the not-blank CHECKs of migration 172. No constraint on the
      birth date or the gender: a person outside a household (the meeting circle,
      #939) may lack both.
    """

    __tablename__ = "persons"
    # CR-13 phase 3 (§B5.2): what `@validates` says, at rest too — the same rules as
    # migration 172, which is where the environments get them.
    __table_args__ = (
        CheckConstraint("btrim(first_name) <> ''", name="ck_persons_first_name_not_blank"),
        CheckConstraint("btrim(last_name) <> ''", name="ck_persons_last_name_not_blank"),
        {"schema": "mdm"},
    )

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), ForeignKey("mdm.gender_codes.code"), nullable=True)
    # Survivorship (§6): gezet door service.merge_persons(); wijst ALTIJD direct
    # naar de eind-overlever (platgeslagen keten → resolve() is O(1)).
    superseded_by_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    member_persons = relationship("MemberPerson", back_populates="person")
    address = relationship("Address", back_populates="person", uselist=False)
    contact_details = relationship(
        "ContactDetail", back_populates="person", cascade="all, delete-orphan"
    )
    external_numbers = relationship(
        "ExternalNumber", back_populates="person", cascade="all, delete-orphan"
    )
    # Bewust GEEN registrations-relatie: activiteiten zijn een ander domein;
    # Registration definieert de koppeling via een backref (zelfde regel).

    @validates("first_name", "last_name")
    def _name_not_blank(self, key: str, value: Optional[str]) -> Optional[str]:
        """A person always has a first and a last name. The value is kept as given —
        stripping would change what is stored today (R13)."""
        if _blank(value):
            from app.i18n import _

            raise MasterDataError(_("Voornaam en achternaam zijn verplicht."))
        return value

    def check(self) -> None:
        """A member of a household keeps a birth date and a gender (#681), whatever
        path changes their details. Judged on the outcome, not on what was sent."""
        if not _changed(self, "first_name", "last_name", "date_of_birth", "gender_code"):
            return
        if not any(link.deleted_at is None for link in self.member_persons or []):
            return
        if exemption(self, HOUSEHOLD_MEMBER_DETAILS):
            return
        MemberPerson.require_details(self.date_of_birth, self.gender_code)

    def primary_contact(self, contact_type: str) -> Optional["ContactDetail"]:
        """This person's main contact of one kind — `CONTACT.EMAIL`, `CONTACT.MOBILE`, …
        (CR-13 phase 3, #1250).

        The primary row, else the first row of that kind that has a value. The
        fallback is deliberate (#1174): the database allows *at most* one primary
        per kind (`uq_contact_details_one_primary_per_type`), not *at least* one,
        and a person whose main address was removed still has something to show.
        This is for showing one contact; sending has its own answer per kind of mail.

        Reads the loaded relationship only; it never opens a session (§B4.1).
        """
        of_kind = [
            c for c in self.contact_details or [] if c.contact_type_code == contact_type and c.value
        ]
        return next((c for c in of_kind if c.is_primary), of_kind[0] if of_kind else None)


@aggregate
class MemberPerson(TenantMixin, SoftDeleteMixin, Base):
    """A person's place in a household — the link, and the rule that comes with it
    (CR-13 phase 3, #1250).

    **A member of a household has a birth date and a gender (#681).** That is a rule
    about a person *in a household*, not about a person: the meeting circle (#939)
    holds persons without either, on purpose. So it lives here, on the link, and
    `check()` holds it for every new link, every link moved to another person or
    household, and every link that comes back from a soft delete — on every path,
    fired by the flush listener. Until this phase it was a function every writer had
    to remember (`controleer_geboortedatum_en_geslacht`); that function is gone, not
    copied. A door that wants to refuse before it changes anything asks
    `require_details` — the same rule, asked early.

    The one exception is written down by name: `MEMBER_REPORT_IMPORT`.
    """

    __tablename__ = "member_persons"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("mdm.members.id"), nullable=False)
    # ondelete RESTRICT: een persoon kan niet hard verdwijnen zolang er
    # gezinskoppelingen aan hangen (DB als laatste vangnet, #97 / migr. 058).
    person_id = Column(Integer, ForeignKey("mdm.persons.id", ondelete="RESTRICT"), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(
        EnumColumn(RelationType, length=10),
        ForeignKey("mdm.relation_type_codes.code"),
        nullable=False,
        default=RelationType.PRIMARY_MEMBER,
    )
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    member = relationship("Member", back_populates="member_persons")
    # `load_on_pending`: a new link often carries only `person_id`; without it,
    # `check()` would see no person and the rule would be skipped silently. With
    # it, the flush reads the person once. A read, never a skipped rule.
    person = relationship("Person", back_populates="member_persons", load_on_pending=True)

    def household_position(self) -> tuple:
        """Where this person stands in the household (Koen, 29 September 2026): by
        relation (`HOUSEHOLD_ORDER`), then oldest first, without a birth date last,
        then in the order they joined. Reads what is loaded; no query."""
        relation = RelationType(self.relation_type)
        born = self.person.date_of_birth if self.person is not None else None
        return (
            HOUSEHOLD_ORDER.index(relation)
            if relation in HOUSEHOLD_ORDER
            else len(HOUSEHOLD_ORDER),
            born is None,
            born or date.max,
            self.id or 0,
        )

    @staticmethod
    def require_details(date_of_birth: object, gender_code: object) -> None:
        """Birth date and gender, both — or `PersonDetailsMissing` (#681)."""
        if not date_of_birth or _blank(gender_code):
            from app.i18n import _

            raise PersonDetailsMissing(
                _("Geboortedatum en geslacht zijn verplicht voor elk gezinslid.")
            )

    @staticmethod
    def require_main_member_mobile(mobile: object) -> None:
        """The main member can be called — or `MainMemberMobileMissing`.

        One rule for the two doors a member uses (#1590): Word lid, which asked it
        in its schema, and the one save of "Mijn gezin", where until then only the
        browser's `required` held it — a rule that left with the browser's own
        validation. The board's household screen and the JSON API do not ask it,
        today as before (master CLI, 5 October 2026): it is called at those two
        doors and is no rule of the object.
        """
        if _blank(mobile):
            from app.i18n import _

            raise MainMemberMobileMissing(_("Mobiel nummer is verplicht voor het hoofdgezinslid."))

    def check(self) -> None:
        """A new, moved or revived link needs a person with a birth date and a gender."""
        if not (sa_inspect(self).pending or _changed(self, "person_id", "member_id", "deleted_at")):
            return
        if exemption(self, HOUSEHOLD_MEMBER_DETAILS):
            return
        person = self.person
        if person is None:
            return  # nothing to judge yet; the foreign key refuses a missing person
        self.require_details(person.date_of_birth, person.gender_code)


@aggregate
class OrganizationPerson(TenantMixin, SoftDeleteMixin, Base):
    """Junction table linking persons to an organisation in a named role (#258).

    The board-meeting circle is the first consumer (CR-09 §3.11): the people who
    receive the agenda and the report are not derivable from membership — the
    circle holds fixed participants who are not board members, and the branch
    supporter of the national organisation, who is not a member at all. Modelling
    them as a *relation to the organisation* keeps the fact in master data, where
    persons and their contact details already live, instead of in a second address
    list owned by the meetings module.

    Deliberately generic, following :class:`MemberPerson`: a code table decides
    which relations exist, so a second kind (committee, working group) is a row and
    not a table. ``end_date`` ends a relation instead of deleting it — the
    attendance of an old report must keep resolving to the person who was there.
    """

    __tablename__ = "organization_persons"
    # #1346: what `check()` says, at rest too; migration 174 puts it on the
    # environments. `<=` and not `<`, deliberately: someone added to the circle
    # and taken out again on the same day has start = end today, and that must
    # stay possible. `end_date` is the day someone leaves, so such a relation
    # never counts for any meeting, which is exactly what happened.
    __table_args__ = (
        CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR start_date <= end_date",
            name="ck_organization_persons_period",
        ),
        {"schema": "mdm"},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("mdm.organizations.id"), nullable=False, index=True
    )
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False, index=True)
    relation_type = Column(
        String(30),
        ForeignKey("mdm.organization_relation_type_codes.code"),
        nullable=False,
        default="BOARD_MEETING",
    )
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    organization = relationship("Organization")
    person = relationship("Person")

    def check(self) -> None:
        """A relation cannot start after it ends (#1346). Reads only its own fields.

        The circle screen lets the secretary choose the start date since #1346, so
        a start after the end became possible on a normal path.
        """
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                from app.i18n import _, short_date

                raise MasterDataError(
                    _("De startdatum kan niet na de einddatum liggen (%(end)s).")
                    % {"end": short_date(self.end_date)}
                )


class OrganizationRelationType(Base):
    """Which relations a person can have to an organisation (#258) — the identity.

    Split from its labels deliberately. The older code tables key on
    (code, language), so the code alone is not unique and no foreign key can
    point at it; adding a unique key on the code alone is precisely what dropped
    every English label in migration 017. Here the code is the row, and
    :class:`OrganizationRelationTypeLabel` carries the texts — a third language
    is a row, and the foreign key keeps working.
    """

    # CR-12 phase 2: renamed to the shape of §B4.2 (`<list>_codes`). The
    # label table was already called `..._labels`; the code table was the only
    # one outside the pattern, and then every gate has to make an exception
    # for it.
    __tablename__ = "organization_relation_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), primary_key=True)
    # CR-12 phase 2, same addition as for `identification_schemes`: the shape
    # of #924 was almost that of §B4.2, but without ordering and without
    # retirability. Now this list fits the pattern.
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OrganizationRelationTypeLabel(Base):
    """The readable name of a relation type, per language."""

    __tablename__ = "organization_relation_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(
        String(30), ForeignKey("mdm.organization_relation_type_codes.code"), primary_key=True
    )
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class Address(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    # Uniciteit op person_id is partieel (WHERE deleted_at IS NULL) — zie migratie 050.
    #
    # #924: een adres hangt aan een persoon OF aan een organisatie, nooit aan
    # allebei en nooit aan geen van beide. De databank bewaakt dat met een
    # XOR-CHECK; `person_id` gaf daarvoor zijn NOT NULL af. Bestaande query's
    # zoeken op `person_id = X` en zien de organisatierijen niet — dat is wat deze
    # uitbreiding contained maakt.
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=True)
    street = Column(String(255), nullable=False)
    house_number = Column(String(10), nullable=False)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, ForeignKey("mdm.postal_codes.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    person = relationship("Person", back_populates="address")
    postal_code = relationship("PostalCode")


class ContactDetail(TenantMixin, SoftDeleteMixin, Base):
    """Een contactgegeven van een persoon OF van een organisatie (#945).

    UBL ``cac:Contact`` (``cbc:ElectronicMail``, ``cbc:Telephone``) en
    ``cbc:WebsiteURI``. Waar UBL die enkelvoudig houdt, draagt deze tabel ze als
    rijen met een type uit ``contact_type_codes`` — dat is de vorm die de
    codebase al voor personen gebruikt, en ze laat een vijfde sociaal netwerk een
    rij zijn in plaats van een kolom.

    **De tenant-naad, expliciet (#945).** Deze tabel draagt ``TenantMixin`` omdat
    ze gedeeld wordt met persoonsrijen, die de scope echt nodig hebben.
    ``organizations`` draagt zelf géén ``tenant_id``.

    Voor een organisatierij is ``tenant_id`` daarom **niet de scope**. De scope is
    ``organization_id``. De kolom staat er alleen omdat ze ``NOT NULL`` is en de
    tabel gedeeld wordt; ze krijgt de waarde van ``organization_id`` omdat er geen
    betere bestaat, niet omdat ze iets betekent. Organisatierijen lees je dus met
    ``include_all_tenants=True``, zoals de footer dat al voor het adres doet, en
    ``test_organisatie_contactgegevens`` legt vast dat ze **zonder** die optie
    niet gevonden worden.

    **Waarschuwing voor wie ooit RLS aanzet.** De mixin bestaat opdat "RLS
    aanzetten later een migratieregel wordt, geen verbouwing". Een policy op
    ``tenant_id`` zou deze rijen **stil mis-scopen**: de rijen van de
    ACCOUNT-organisatie krijgen ``tenant_id = 1``, en tenant 1 is geen tenant. Wie
    die policy schrijft, moet organisatierijen apart behandelen — op
    ``organization_id``, of door ze uit te sluiten met ``person_id IS NOT NULL``.

    Bij ``addresses`` (#924) bleef deze naad impliciet; hier staat ze opgeschreven.

    Dezelfde XOR-regel als ``Address``: precies één van ``person_id`` en
    ``organization_id`` is gevuld, bewaakt door een CHECK. Bestaande query's
    zoeken op ``person_id`` en zien de organisatierijen niet — dat is wat deze
    uitbreiding contained maakt.
    """

    __tablename__ = "contact_details"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=True)
    # No enum, unlike the other lists of this change request (Koen,
    # 26 September 2026). #1160 made the public footer data-driven: a fifth
    # social network is one row and not a code change. An enum column would
    # reject such a row on the WRITE side, and that is exactly what #1160
    # removed. The code names the kinds it distinguishes with named constants
    # (`CONTACT.EMAIL`, `CONTACT.MOBILE` in `codes.py`); the foreign key
    # guards that the value is in the list.
    contact_type_code = Column(
        String(10), ForeignKey("mdm.contact_type_codes.code"), nullable=False
    )
    value = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
    # CR-22 (§B1 D3, #1704): since when this detail counts. An e-mail address
    # is the key someone signs in with, so it counts only once its owner has
    # proven he reads it; until then the row exists — it must be visible where
    # it was typed — and this is NULL. OpenID Connect's `email_verified`, as a
    # timestamp because WHEN matters for an audit; `confirmed_at IS NOT NULL`
    # is the boolean. Rows from before the column were backfilled as confirmed
    # at their creation, and every writer goes through
    # `mdm.service.new_contact_detail`, which decides it.
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    person = relationship("Person", back_populates="contact_details")


class PostalCode(Base):
    __tablename__ = "postal_codes"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    postal_code = Column(String(4), nullable=False, index=True)
    municipality = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class ExternalNumber(TenantMixin, SoftDeleteMixin, Base):
    """External identifier for a person from another system.

    Bijvoorbeeld het oude lidnummer uit de vorige ledenadministratie.
    Genormaliseerd zodat één persoon meerdere externe nummers (uit
    verschillende bronsystemen) kan hebben.
    """

    __tablename__ = "external_numbers"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False, index=True)
    # CR-12 phase 5 (#1182): a code of `external_source`, with a foreign key of
    # its own. It leaves the partial unique index on (source, external_id) of
    # migration 053 as it is. The default is the code as a literal because
    # `mdm.codes` imports this module; `EXTERNAL.MEMBER_ADMINISTRATION`
    # is the same value, and the code list's seed is where it is defined.
    source = Column(
        String(50),
        ForeignKey("mdm.external_source_codes.code"),
        nullable=False,
        default="ledenadministratie",
    )
    external_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    # Uniciteit op (source, external_id) is partieel (WHERE deleted_at IS NULL) — zie migratie 050.

    person = relationship("Person", back_populates="external_numbers")


class Organization(SoftDeleteMixin, Base):
    """Organisatie (§6). Zelf-refererend; de tenancy-fase (#406) hangt de
    tenant-kolommen aan dit begrip.

    Drie soorten, en de vorige versie van deze docstring had er twee door elkaar:

    - ``ACCOUNT`` — de klant, de rij waar de facturatie aan hangt (bv. Raak vzw).
    - ``UNIT`` — de afdeling met haar eigen site en merk (bv. Raak Millegem). Dít is
      wat elders "tenant" heet en wat een pad-prefix krijgt.
    - ``PLATFORM`` — het platform zelf (#854): één rij zonder ouder, met een naam, een
      afzender en sleutels, maar zonder leden, gezinnen of activiteiten. Geen
      pad-prefix; ``tenant_lookup`` filtert bewust op ``UNIT``.

    Tot 10 september 2026 stond hier "ACCOUNT = afdeling/klant (bv. Raak Millegem)".
    Dat klopte niet met de data — Millegem is een UNIT — en het is precies de regel die
    je leest als je hieraan werkt.
    """

    __tablename__ = "organizations"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=True)
    # #1550: on a tenant, the organisation whose data its site shows (footer,
    # "Onze organisatie", mails) when that is not its own row: the account, or
    # another organisation of that account. NULL = its own row. Read only
    # through `kernel.tenant_config.site_organization_id`.
    site_organization_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=True)
    # ACCOUNT | UNIT | PLATFORM — CHECK in migratie 078, uitgebreid in 097.
    # Dit is de ROL die de organisatie speelt in het platform; de kolommen
    # hieronder zeggen wat ze IS in de wereld (#924). Twee assen, één ding.
    org_type: Mapped[OrganizationType] = mapped_column(
        EnumColumn(OrganizationType, length=10),
        ForeignKey("mdm.organization_type_codes.code"),
        nullable=False,
        default=OrganizationType.ACCOUNT,
    )
    # Stabiele technische naam (bv. "raakmillegem") — uniek.
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    # #1546: on a tenant, the name its site shows (wordmark, tab, footer, mails,
    # the list of sites), when it differs from the organisation's. NULL = the name
    # of the organisation behind the site (#1550). Read only through
    # `kernel.tenant_config.tenant_display_name`.
    site_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    # ── Wat de organisatie is in de wereld (#924) ────────────────────────────
    # Rechtsvorm uit `mdm.legal_form_codes` (#779-patroon). Leeg voor PLATFORM:
    # het platform is geen vereniging, en een verzonnen rechtsvorm is erger dan
    # een lege kolom.
    # Geen FK: een verwijzing naar `code` alleen vereist een uniciteit daarop, en
    # die laat maar één taal per code toe — zie de migratie. De geldige waarden
    # staan in `LegalForm` hieronder.
    legal_form: Mapped[Optional[LegalForm]] = mapped_column(
        EnumColumn(LegalForm, length=30), ForeignKey("mdm.legal_form_codes.code"), nullable=True
    )
    # CR-19 (#1478): what the site is for — `mdm.tenant_kind_codes`. A UNIT
    # carries one; ACCOUNT and PLATFORM do not.
    kind: Mapped[Optional[TenantKind]] = mapped_column(
        EnumColumn(TenantKind, length=20), ForeignKey("mdm.tenant_kind_codes.code"), nullable=True
    )

    # #1550: two keys to this table now — the parent is `parent_id`.
    parent = relationship("Organization", remote_side=[id], foreign_keys=[parent_id])

    # Elf kolommen stonden hier tot #945: `enterprise_number`, `vat_number`,
    # `email`, `phone`, `website`, `payment_iban`, `payment_beneficiary`,
    # `payment_bic` en de drie `*_url`. Ze zijn geen kolom meer maar een rij —
    # identificaties in `OrganizationIdentification`, rekeningen in `BankAccount`,
    # contact en links in `ContactDetail`. Reden: elk van de drie is van nature
    # een lijst (een tweede btw-nummer in een ander land, een tweede rekening,
    # een vijfde netwerk) en één kolom per soort laat het tweede geval niet toe.
    # `legal_form` blijft wél staan: UBL houdt `cac:PartyLegalEntity/
    # cbc:CompanyLegalForm` per definitie enkelvoudig.


class TenantModule(Base):
    """One module switched on for one tenant (CR-19 §C4.2, #1475).

    The set is data, the modules themselves are code (`app/kernel/modules.py`):
    a module code exists only there, and the column's CHECK holds the stored
    values to it. No soft delete: switching a module off removes its row, and
    the module's own data stays where it is (§C4.3).
    """

    __tablename__ = "tenant_modules"
    __table_args__ = {"schema": "mdm"}

    tenant_id = Column(
        Integer, ForeignKey("mdm.organizations.id", ondelete="CASCADE"), primary_key=True
    )
    module_code = Column(String(20), primary_key=True)


class BankAccount(SoftDeleteMixin, Base):
    """Een rekening van een organisatie (#945) — UBL ``cac:PayeeFinancialAccount``.

    Tot #945 stonden IBAN, BIC en begunstigde als drie kolommen op de
    organisatie. Een vzw met een aparte rekening per werking is niets
    bijzonders, en UBL modelleert de rekening dan ook als een eigen,
    herhaalbare structuur. Vandaag vullen we er één.

    **Afwijking van de naamgeving, bewust.** UBL noemt de IBAN ``cbc:ID`` en de
    BIC ``cac:FinancialInstitutionBranch/cbc:ID``; ISO 20022 noemt die laatste
    ``BICFI``. Hier heten ze ``iban`` en ``bic``. Een kolom ``id`` die een
    rekeningnummer draagt naast een technische sleutel die óók ``id`` heet is
    onleesbaar, en ``bicfi`` zegt een penningmeester niets. De mapping naar UBL
    is een hernoeming van twee velden en geen vertaalslag — dat is de afweging
    die `CLAUDE.md` vraagt op te schrijven.

    **Geen ``TenantMixin``**, en dat is geen vergetelheid. De rijen zijn eigendom
    van de organisatie en raken niets dat tenant-scoped is; ``organization_id``
    ís de scope, precies zoals ``organizations`` zelf geen ``tenant_id`` draagt.
    ``organization_persons`` heeft er wél een omdat die naar personen wijst, en
    die zijn het wel.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("mdm.organizations.id"), nullable=False, index=True
    )
    iban = Column(String(40), nullable=False)
    bic = Column(String(20), nullable=True)
    # UBL `cac:PayeeFinancialAccount/cbc:Name`: op wiens naam de rekening staat.
    beneficiary = Column(String(255), nullable=True)
    # Welke rekening de eerste is waar er één getoond wordt (footer, overschrijving).
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    organization = relationship("Organization")


class OrganizationIdentification(SoftDeleteMixin, Base):
    """Een identificatienummer van een organisatie (#945).

    UBL ``cac:PartyIdentification`` en ``cac:PartyTaxScheme`` — allebei
    **herhaalbaar**, en die laatste draagt een eigen ``cac:RegistrationAddress``.
    Dát is Koens geval: een btw-nummer hoort bij een **land**, niet bij de partij
    als geheel, dus een tweede btw-nummer in een tweede land is hier een rij en
    geen migratie. Het ondernemingsnummer (KBO) en het btw-nummer zijn vandaag
    de twee rijen die we vullen.

    ``scheme`` komt uit :class:`IdentificationScheme`; ISO 6523/ICD levert de
    vocabulaire en wij vullen alleen wat we gebruiken. ``country`` is
    ISO 3166-1 alpha-2, zoals ``cbc:IdentificationCode``.

    Geen ``TenantMixin``, om dezelfde reden als :class:`BankAccount`.
    """

    __tablename__ = "organization_identifications"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("mdm.organizations.id"), nullable=False, index=True
    )
    scheme = Column(String(20), ForeignKey("mdm.identification_scheme_codes.code"), nullable=False)
    value = Column(String(50), nullable=False)
    country = Column(String(2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    organization = relationship("Organization")


# ── Codetabellen van de masterdata ──────────────────────────────────────────────


class PaymentMethod(CodeEnum):
    """How money moves: online, by bank transfer, or in cash (CR-12 phase 1).

    In `mdm` and not in `payment`, because two domains store it — a payment
    record and an activity registration — and a list used by more than one
    domain is master data by definition (§B4.1). That makes the foreign key
    from `payment` and from `activities` the allowed cross-schema one.

    A `CodeEnum`, no `str` mixin. Member names are English and so are the values here; the
    Dutch `OVERSCHRIJVING` the public form used to post is mapped to `transfer`
    once, by the migration of this phase (§B4.6).
    """

    ONLINE = "online"
    TRANSFER = "transfer"
    CASH = "cash"


class PaymentMethodCode(Base):
    """Which payment methods exist — the target of the foreign keys."""

    __tablename__ = "payment_method_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PaymentMethodLabel(Base):
    """The word a screen or an export shows for a payment method, per language."""

    __tablename__ = "payment_method_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.payment_method_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class LanguageCode(Base):
    """Which languages a label may be written in (CR-12 phase 0).

    The smallest list in the codebase and the one every other list depends on:
    the ``language`` column of every ``_labels`` table points here, so a typo
    like ``nl_BE`` or ``NL`` in a label row is refused by the database instead
    of quietly producing a label nobody ever reads.

    It lives in ``mdm`` because it is used by every domain, which is the
    definition of master data (§B4.1). That makes it the one named exception to
    "no cross-schema foreign keys": a label table in any schema points at this
    one. ``mdm`` depends on no business domain, so no cycle can arise.

    Language **codes**, not locales: ``nl``, not ``nl_BE``. The tenant setting
    stays a locale (``nl_BE`` decides how a date reads); the label lookup takes
    the language part of it (§F8).
    """

    __tablename__ = "language_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(5), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class LanguageLabel(Base):
    """The name of a language, in each language (CR-12 phase 0)."""

    __tablename__ = "language_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class IdentificationScheme(Base):
    """Welke identificatieschema's bestaan (#945) — de identiteit.

    Gesplitst van zijn labels, zoals :class:`OrganizationRelationType` en om
    dezelfde reden: de oudere codetabellen sleutelen op (code, taal), waardoor de
    code alleen niet uniek is en er geen foreign key naar kan wijzen. Een
    uniciteit op de code alleen toevoegen is precies wat in migratie 017 elk
    Engels label wegvaagde. Hier is de code de rij en draagt
    :class:`IdentificationSchemeLabel` de teksten — een derde taal is een rij en
    de foreign key blijft werken.

    Bewust **niet** het patroon van ``contact_type_codes`` nagevolgd: die vorm is
    stuk (#929) en op een tabel die vandaag nog niet bestaat hoef je die fout
    niet opnieuw te maken.
    """

    # CR-12 phase 2: renamed to `<list>_codes`, see OrganizationRelationType.
    __tablename__ = "identification_scheme_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    # CR-12 phase 2: these two were missing. The table already had the split
    # shape of #924, but not the ordering and retirability that §B4.2 asks for
    # — and without those two a list cannot fit the pattern and a code cannot
    # be retired without deleting it.
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class IdentificationSchemeLabel(Base):
    """De leesbare naam van een identificatieschema, per taal (#945)."""

    __tablename__ = "identification_scheme_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.identification_scheme_codes.code"), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class LegalFormCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 2)."""

    __tablename__ = "legal_form_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class LegalFormLabel(Base):
    """The word a screen shows, per language (CR-12 phase 2)."""

    __tablename__ = "legal_form_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), ForeignKey("mdm.legal_form_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class TenantKindCode(Base):
    """Which tenant kinds exist — the target of the foreign key (#1478)."""

    __tablename__ = "tenant_kind_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class TenantKindLabel(Base):
    """The word a screen shows for a tenant kind, per language (#1478)."""

    __tablename__ = "tenant_kind_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.tenant_kind_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class OrganizationTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 2)."""

    __tablename__ = "organization_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OrganizationTypeLabel(Base):
    """The word a screen shows, per language (CR-12 phase 2)."""

    __tablename__ = "organization_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.organization_type_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class GenderCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 2)."""

    __tablename__ = "gender_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ExternalSourceCode(Base):
    """Which source systems an external number can come from (CR-12 phase 5)."""

    __tablename__ = "external_source_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(50), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ExternalSourceLabel(Base):
    """The word a screen shows, per language (CR-12 phase 5)."""

    __tablename__ = "external_source_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(50), ForeignKey("mdm.external_source_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class GenderLabel(Base):
    """The word a screen shows, per language (CR-12 phase 2)."""

    __tablename__ = "gender_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.gender_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class ContactTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 2).

    Carries one property more than the standard shape, see `is_social_network`.
    """

    __tablename__ = "contact_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    # #1160: the source says which codes are social networks. The public
    # footer asks this column instead of keeping a list of its own — that list
    # was a code short and put the mobile number between the icons. NULL means
    # "not classified yet" and renders as "not a network"; the suite fails on
    # it. A property of the code, not a label, so here and not in the label
    # table; declared as `extra_code_columns` on the CodeList.
    is_social_network = Column(Boolean, nullable=True)


class ContactTypeLabel(Base):
    """The word a screen shows, per language (CR-12 phase 2)."""

    __tablename__ = "contact_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.contact_type_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class RelationTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 2)."""

    __tablename__ = "relation_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class RelationTypeLabel(Base):
    """The word a screen shows, per language (CR-12 phase 2)."""

    __tablename__ = "relation_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.relation_type_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


# ── History (append-only; geen FK's — overleeft het verdwijnen van de bron) ────


class HistoryMixin:
    """Gedeelde audit-metadata voor alle history-tabellen."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)  # insert / update / delete
    action = Column(String(40), nullable=False)  # semantische business-actie
    source = Column(String(30), nullable=False)  # system / registration / mollie / ...
    actor = Column(String(255), nullable=True)  # admin-e-mail of None
    recorded_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False, index=True)


class PersonHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "person_history"
    __table_args__ = {"schema": "mdm"}

    person_id = Column(Integer, nullable=False, index=True)
    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), nullable=True)


class MemberHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "member_history"
    __table_args__ = {"schema": "mdm"}

    member_id = Column(Integer, nullable=False, index=True)
    board_member_id = Column(Integer, nullable=True)


class MemberPersonHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "member_person_history"
    __table_args__ = {"schema": "mdm"}

    member_person_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    relation_type = Column(String(10), nullable=True)


class AddressHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "address_history"
    __table_args__ = {"schema": "mdm"}

    address_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    street = Column(String(255), nullable=True)
    house_number = Column(String(20), nullable=True)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, nullable=True)


class ContactDetailHistory(TenantMixin, HistoryMixin, Base):
    __tablename__ = "contact_detail_history"
    __table_args__ = {"schema": "mdm"}

    contact_detail_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    contact_type_code = Column(String(10), nullable=True)
    value = Column(String(255), nullable=True)
    is_primary = Column(Boolean, nullable=True)

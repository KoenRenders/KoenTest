"""Masterdata (MDM-component, fase 2 #400 — §5.3/§6): personen, gezinnen,
adressen, contactgegevens, postcodes, externe nummers, organisaties en de
bijbehorende codetabellen + history. Alles in Postgres-schema ``mdm``.

Survivorship (§6): een Person wordt nooit hard verwijderd bij een merge —
``superseded_by_id`` wijst naar de overlever; ``service.resolve()`` slaat de
keten plat (O(1) doordat merges platgeslagen worden bijgehouden).
"""
from datetime import datetime, timezone
from typing import Optional

from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── De vocabularia van dit domein (CR-12 fase 2) ────────────────────────────
#
# Vooraan, omdat de kolommen eronder ze in hun declaratie gebruiken:
# `Mapped[LegalForm] = mapped_column(EnumColumn(LegalForm))` wordt op
# klasse-definitietijd uitgevoerd, niet luie evaluatie.


class LegalForm(Enum):
    """De rechtsvormen die de codelijst kent (#924, patroon van #779).

    De code staat in de databank, het label per taal in
    `mdm.legal_form_labels`, en deze Enum is waar de code in de applicatie
    vandaan komt. Uitbreidbaar: een nieuwe vorm is een rij plus een lid.

    CR-12 fase 2: van `str, Enum` naar een gewone `Enum`. Met de `str`-mengvorm
    bleef `organisatie.legal_form == "VZW"` een geldige vergelijking die
    toevallig waar was; gewoon is ze stil onwaar, en dus vindbaar.
    """

    #: Ledennamen Engels, waarden onveranderd (§B4.3, dat `LegalForm.COMPANY =
    #: "BEDRIJF"` letterlijk als voorbeeld geeft). De waarde is opgeslagen data
    #: en blijft; de naam is een identifier en valt onder de Engelse regel.
    NON_PROFIT = "VZW"
    UNINCORPORATED = "FEITELIJKE_VERENIGING"
    COMPANY = "BEDRIJF"


class OrganizationType(Enum):
    """Wat voor soort organisatie dit is (CR-12 fase 2).

    `ACCOUNT` is de rechtspersoon die de rekening draagt, `UNIT` een afdeling,
    `PLATFORM` de ene organisatie die het platform zelf voorstelt (#406). De
    kolom had een CHECK-constraint met deze drie waarden; die verdwijnt met de
    foreign key, want anders kost een vierde soort een rij én een migratie.
    """

    ACCOUNT = "ACCOUNT"
    UNIT = "UNIT"
    PLATFORM = "PLATFORM"


class RelationType(Enum):
    """Hoe een persoon bij een gezin hoort (CR-12 fase 2).

    Ledennamen zijn Engels, waarden blijven de opgeslagen Nederlandse codes
    (§B4.3): de waarde is data en verandert niet, de naam is een identifier en
    valt onder de Engelse regel.
    """

    PRIMARY_MEMBER = "HOOFDLID"
    PARTNER = "PARTNER"
    ADULT_CHILD = "KIND"


class Member(TenantMixin, SoftDeleteMixin, Base):
    """Household grouping — dynamic, can change over time."""
    __tablename__ = "members"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    board_member_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="member", cascade="all, delete-orphan")
    # Bewust GEEN memberships-relatie hier: lidmaatschap is een ander domein
    # (fase 4a). Membership definieert de koppeling via een backref, zodat de
    # masterdata standalone geladen kan worden (§6, soft-ref-richting).
    board_member = relationship("Person", foreign_keys=[board_member_id])


class Person(TenantMixin, SoftDeleteMixin, Base):
    """Stable, permanent individual entity."""
    __tablename__ = "persons"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), ForeignKey("mdm.gender_codes.code"), nullable=True)
    # Survivorship (§6): gezet door service.merge_persons(); wijst ALTIJD direct
    # naar de eind-overlever (platgeslagen keten → resolve() is O(1)).
    superseded_by_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="person")
    address = relationship("Address", back_populates="person", uselist=False)
    contact_details = relationship("ContactDetail", back_populates="person", cascade="all, delete-orphan")
    external_numbers = relationship("ExternalNumber", back_populates="person", cascade="all, delete-orphan")
    # Bewust GEEN registrations-relatie: activiteiten zijn een ander domein;
    # Registration definieert de koppeling via een backref (zelfde regel).


class MemberPerson(TenantMixin, SoftDeleteMixin, Base):
    """Junction table linking persons to member households."""
    __tablename__ = "member_persons"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("mdm.members.id"), nullable=False)
    # ondelete RESTRICT: een persoon kan niet hard verdwijnen zolang er
    # gezinskoppelingen aan hangen (DB als laatste vangnet, #97 / migr. 058).
    person_id = Column(Integer, ForeignKey("mdm.persons.id", ondelete="RESTRICT"), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(
        EnumColumn(RelationType, length=10),
        ForeignKey("mdm.relation_type_codes.code"), nullable=False,
        default=RelationType.PRIMARY_MEMBER)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member = relationship("Member", back_populates="member_persons")
    person = relationship("Person", back_populates="member_persons")


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
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False, index=True)
    relation_type = Column(String(30), ForeignKey("mdm.organization_relation_type_codes.code"),
                           nullable=False, default="BOARD_MEETING")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    organization = relationship("Organization")
    person = relationship("Person")


class OrganizationRelationType(Base):
    """Which relations a person can have to an organisation (#258) — the identity.

    Split from its labels deliberately. The older code tables key on
    (code, language), so the code alone is not unique and no foreign key can
    point at it; adding a unique key on the code alone is precisely what dropped
    every English label in migration 017. Here the code is the row, and
    :class:`OrganizationRelationTypeLabel` carries the texts — a third language
    is a row, and the foreign key keeps working.
    """

    # CR-12 fase 2: hernoemd naar de vorm van §B4.2 (`<lijst>_codes`). De
    # labeltabel heette al `..._labels`; de codetabel viel als enige buiten
    # het patroon, en dan moet elke poort er een uitzondering voor maken.
    __tablename__ = "organization_relation_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), primary_key=True)
    # CR-12 fase 2, zelfde aanvulling als bij `identification_schemes`: de vorm
    # van #924 was bijna die van §B4.2, maar zonder volgorde en zonder
    # intrekbaarheid. Nu kan deze lijst in het patroon.
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OrganizationRelationTypeLabel(Base):
    """The readable name of a relation type, per language."""

    __tablename__ = "organization_relation_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), ForeignKey("mdm.organization_relation_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


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
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"),
                             nullable=True)
    street = Column(String(255), nullable=False)
    house_number = Column(String(10), nullable=False)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, ForeignKey("mdm.postal_codes.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

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
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"),
                             nullable=True)
    # Geen enum, anders dan bij de andere lijsten van deze change request
    # (Koen, 26 september 2026). #1160 maakte de publieke voetnoot
    # data-gedreven: een vijfde sociaal netwerk is één rij en geen
    # codewijziging. Een enum-kolom zou zo'n rij aan de SCHRIJFKANT weigeren,
    # en dat is precies wat #1160 wegnam. De code noemt de soorten die ze
    # onderscheidt met genoemde constanten (`CONTACT.EMAIL`, `CONTACT.MOBILE`
    # in `codes.py`); de foreign key bewaakt dat de waarde in de lijst staat.
    contact_type_code = Column(String(10),
                               ForeignKey("mdm.contact_type_codes.code"),
                               nullable=False)
    value = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    person = relationship("Person", back_populates="contact_details")


class PostalCode(Base):
    __tablename__ = "postal_codes"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    postal_code = Column(String(4), nullable=False, index=True)
    municipality = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


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
    source = Column(String(50), nullable=False, default="ledenadministratie")
    external_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

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
    # ACCOUNT | UNIT | PLATFORM — CHECK in migratie 078, uitgebreid in 097.
    # Dit is de ROL die de organisatie speelt in het platform; de kolommen
    # hieronder zeggen wat ze IS in de wereld (#924). Twee assen, één ding.
    org_type: Mapped[OrganizationType] = mapped_column(
        EnumColumn(OrganizationType, length=10),
        ForeignKey("mdm.organization_type_codes.code"), nullable=False,
        default=OrganizationType.ACCOUNT)
    # Stabiele technische naam (bv. "raakmillegem") — uniek.
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    # ── Wat de organisatie is in de wereld (#924) ────────────────────────────
    # Rechtsvorm uit `mdm.legal_form_codes` (#779-patroon). Leeg voor PLATFORM:
    # het platform is geen vereniging, en een verzonnen rechtsvorm is erger dan
    # een lege kolom.
    # Geen FK: een verwijzing naar `code` alleen vereist een uniciteit daarop, en
    # die laat maar één taal per code toe — zie de migratie. De geldige waarden
    # staan in `LegalForm` hieronder.
    legal_form: Mapped[Optional[LegalForm]] = mapped_column(
        EnumColumn(LegalForm, length=30),
        ForeignKey("mdm.legal_form_codes.code"), nullable=True)

    parent = relationship("Organization", remote_side=[id])

    # Elf kolommen stonden hier tot #945: `enterprise_number`, `vat_number`,
    # `email`, `phone`, `website`, `payment_iban`, `payment_beneficiary`,
    # `payment_bic` en de drie `*_url`. Ze zijn geen kolom meer maar een rij —
    # identificaties in `OrganizationIdentification`, rekeningen in `BankAccount`,
    # contact en links in `ContactDetail`. Reden: elk van de drie is van nature
    # een lijst (een tweede btw-nummer in een ander land, een tweede rekening,
    # een vijfde netwerk) en één kolom per soort laat het tweede geval niet toe.
    # `legal_form` blijft wél staan: UBL houdt `cac:PartyLegalEntity/
    # cbc:CompanyLegalForm` per definitie enkelvoudig.


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
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"),
                             nullable=False, index=True)
    iban = Column(String(40), nullable=False)
    bic = Column(String(20), nullable=True)
    # UBL `cac:PayeeFinancialAccount/cbc:Name`: op wiens naam de rekening staat.
    beneficiary = Column(String(255), nullable=True)
    # Welke rekening de eerste is waar er één getoond wordt (footer, overschrijving).
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

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
    organization_id = Column(Integer, ForeignKey("mdm.organizations.id"),
                             nullable=False, index=True)
    scheme = Column(String(20), ForeignKey("mdm.identification_scheme_codes.code"),
                    nullable=False)
    value = Column(String(50), nullable=False)
    country = Column(String(2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    organization = relationship("Organization")


# ── Codetabellen van de masterdata ──────────────────────────────────────────────


class PaymentMethod(Enum):
    """How money moves: online, by bank transfer, or in cash (CR-12 phase 1).

    In `mdm` and not in `payment`, because two domains store it — a payment
    record and an activity registration — and a list used by more than one
    domain is master data by definition (§B4.1). That makes the foreign key
    from `payment` and from `activities` the allowed cross-schema one.

    Plain `Enum`. Member names are English and so are the values here; the
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

    code = Column(String(20), ForeignKey("mdm.payment_method_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


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
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


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

    # CR-12 fase 2: hernoemd naar `<lijst>_codes`, zie OrganizationRelationType.
    __tablename__ = "identification_scheme_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    # CR-12 fase 2: deze twee ontbraken. De tabel had de gesplitste vorm van
    # #924 al, maar niet de volgorde en de intrekbaarheid die §B4.2 vraagt — en
    # zonder die twee kan een lijst niet in het patroon en kan een code niet
    # ingetrokken worden zonder haar te verwijderen.
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class IdentificationSchemeLabel(Base):
    """De leesbare naam van een identificatieschema, per taal (#945)."""

    __tablename__ = "identification_scheme_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.identification_scheme_codes.code"),
                  primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

class LegalFormCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 2)."""

    __tablename__ = "legal_form_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class LegalFormLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 2)."""

    __tablename__ = "legal_form_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), ForeignKey("mdm.legal_form_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class OrganizationTypeCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 2)."""

    __tablename__ = "organization_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OrganizationTypeLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 2)."""

    __tablename__ = "organization_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.organization_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class GenderCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 2)."""

    __tablename__ = "gender_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class GenderLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 2)."""

    __tablename__ = "gender_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.gender_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class ContactTypeCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 2).

    Draagt één eigenschap meer dan de standaardvorm, zie `is_social_network`.
    """

    __tablename__ = "contact_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    # #1160: de bron zegt welke codes sociale netwerken zijn. De publieke
    # voetnoot vraagt deze kolom in plaats van een eigen lijstje bij te houden —
    # dat lijstje was een code te kort en zette het mobiele nummer tussen de
    # iconen. Een eigenschap ván de code, geen label, dus hier en niet in de
    # labeltabel; aangemeld als `extra_code_columns` op de CodeList.
    is_social_network = Column(Boolean, nullable=True)


class ContactTypeLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 2)."""

    __tablename__ = "contact_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.contact_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class RelationTypeCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 2)."""

    __tablename__ = "relation_type_codes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class RelationTypeLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 2)."""

    __tablename__ = "relation_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(10), ForeignKey("mdm.relation_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


# ── History (append-only; geen FK's — overleeft het verdwijnen van de bron) ────

class HistoryMixin:
    """Gedeelde audit-metadata voor alle history-tabellen."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)   # insert / update / delete
    action = Column(String(40), nullable=False)       # semantische business-actie
    source = Column(String(30), nullable=False)       # system / registration / mollie / ...
    actor = Column(String(255), nullable=True)        # admin-e-mail of None
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

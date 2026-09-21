"""Masterdata (MDM-component, fase 2 #400 — §5.3/§6): personen, gezinnen,
adressen, contactgegevens, postcodes, externe nummers, organisaties en de
bijbehorende codetabellen + history. Alles in Postgres-schema ``mdm``.

Survivorship (§6): een Person wordt nooit hard verwijderd bij een merge —
``superseded_by_id`` wijst naar de overlever; ``service.resolve()`` slaat de
keten plat (O(1) doordat merges platgeslagen worden bijgehouden).
"""
from datetime import datetime, timezone

from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    relation_type = Column(String(10), ForeignKey("mdm.relation_type_codes.code"), nullable=False, default="HOOFDLID")
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
    relation_type = Column(String(30), ForeignKey("mdm.organization_relation_types.code"),
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

    __tablename__ = "organization_relation_types"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class OrganizationRelationTypeLabel(Base):
    """The readable name of a relation type, per language."""

    __tablename__ = "organization_relation_type_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(30), ForeignKey("mdm.organization_relation_types.code"),
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
    contact_type_code = Column(String(10), ForeignKey("mdm.contact_type_codes.code"), nullable=False)
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
    org_type = Column(String(10), nullable=False, default="ACCOUNT")
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
    legal_form = Column(String(30), nullable=True)

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
    scheme = Column(String(20), ForeignKey("mdm.identification_schemes.code"),
                    nullable=False)
    value = Column(String(50), nullable=False)
    country = Column(String(2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    organization = relationship("Organization")


# ── Codetabellen van de masterdata ──────────────────────────────────────────────


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

    __tablename__ = "identification_schemes"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class IdentificationSchemeLabel(Base):
    """De leesbare naam van een identificatieschema, per taal (#945)."""

    __tablename__ = "identification_scheme_labels"
    __table_args__ = {"schema": "mdm"}

    code = Column(String(20), ForeignKey("mdm.identification_schemes.code"),
                  primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

class LegalForm(str, Enum):
    """De rechtsvormen die de codelijst kent (#924, patroon van #779).

    De code staat in de databank, het label per taal in `mdm.legal_form_codes`, en
    deze Enum is waar de code in de applicatie vandaan komt. Uitbreidbaar: een
    nieuwe vorm is een rij in de codelijst plus een lid hier.
    """

    VZW = "VZW"
    FEITELIJKE_VERENIGING = "FEITELIJKE_VERENIGING"
    BEDRIJF = "BEDRIJF"


class LegalFormCode(Base):
    """Rechtsvorm van een organisatie (#924), patroon van #779.

    vzw, feitelijke vereniging, bedrijf — uitbreidbaar. Let op het verschil dat
    ertoe doet: een **feitelijke vereniging heeft geen rechtspersoonlijkheid**, en
    dat is precies wat Raak Millegem is. Daarom heet dit veld de rechtsVORM en niet
    de rechtsPERSOON.
    """

    __tablename__ = "legal_form_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(30), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)


class GenderCode(Base):
    __tablename__ = "gender_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


class ContactTypeCode(Base):
    __tablename__ = "contact_type_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    # #1160: the source says which codes are social networks. The public footer
    # asks this column instead of keeping a list of its own — that list was a
    # code short and put the mobile number between the icons. NULL means "not
    # classified yet" and renders as "not a network"; the suite fails on it.
    is_social_network = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


class RelationTypeCode(Base):
    __tablename__ = "relation_type_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


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

"""Upsert-service voor het opladen van het Raak-Nationaal-ledenrapport (#74).

Bij het opladen is het **Raak-Nationaal-ledenrapport de bron van waarheid**:
bestaande gezinnen worden bijgewerkt in plaats van te aborteren. De match gebeurt
op het **lidnummer** (``ExternalNumber(source="ledenadministratie")``):

  - Een gezin wordt herkend aan het lidnummer van zijn **hoofdlid**.
  - Een rij met een bekend lidnummer is een *update*; een onbekend lidnummer is
    een *nieuwe* persoon/gezin — tenzij het op identiteit (naam+geboortedatum)
    een bestaand, lidnummer-loos lid matcht: dan wordt het lidnummer aan dat
    bestaande lid gehecht in plaats van een duplicaat te maken (#192).
  - Personen die wél in ons gezin zitten maar **niet** in de adresgroep van het
    rapport staan, worden uit het gezin verwijderd (verhuisd of weggevallen). Wie
    verhuist, staat in het rapport onder zijn nieuwe adres en wordt daar
    toegevoegd.

Elke insert/update/delete wordt geauditeerd via de history-infrastructuur met
``source="ledenadministratie"`` (snapshot vóór een delete, zodat #82 / de
wijzigingslijst de verwijderde persoon nog ziet). De aanroeper kan een ``actor``
meegeven (de ingelogde admin-email bij de upload, een sentinel bij het CLI) die
in elke history-rij belandt (#214).

De service muteert de sessie maar **commit niet**: de aanroeper (CLI of test)
beslist over commit/rollback. Met ``apply=False`` worden geen DB-wijzigingen
gedaan — enkel het rapport van wat *zou* veranderen wordt opgebouwd (dry-run).
(verhuisd uit app/services/member_import.py, #444)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.domains.auth.api import has_login
from app.domains.mdm.api import (
    Address,
    ExternalNumber,
    Member,
    MemberPerson,
    Person,
    PostalCode,
)
from app.domains.mdm.change_lines import (
    ADDRESS_LABEL,
    RELATION_LABEL,
    FieldChange,
    address_line,
    contact_change,
    lines_text,
    person_change,
    relation_value,
)
from app.domains.mdm.codes import CONTACT, EXTERNAL
from app.domains.mdm.history import (
    snapshot_address,
    snapshot_member,
    snapshot_member_person,
    snapshot_person,
)
from app.domains.mdm.service import email_refusal
from app.domains.membership.api import has_membership_for_year
from app.kernel.codes import code_of
from app.kernel.contracts.mdm import BoardMemberReported, MembershipReported
from app.kernel.events import KernelEvent, has_subscribers, publish

# Bronsysteem-label voor de lidnummers en de audit-source.
LEGACY_SOURCE = EXTERNAL.MEMBER_ADMINISTRATION

# Jaar waarvoor het lidmaatschap wordt aangemaakt.
IMPORT_YEAR = 2026

# Rapportkolom → contacttype.
_CONTACT_FIELDS = ((CONTACT.EMAIL, "email"), (CONTACT.PHONE, "telefoon"), (CONTACT.MOBILE, "gsm"))


@dataclass
class _Household:
    """One household's block in the report (#1314): its header and its change lines.

    The lines are its changes, so an existing household with none is unchanged and
    gets no header. A block, and not a slice of one flat list, because the board
    members are linked after every household is done and their line belongs under
    the household it changes.
    """

    header: str
    is_new: bool
    #: The household's `Member`, until `finish()` lets go of it.
    member: Any
    lines: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    """Wat de load (zou) doen — voor het dry-run-rapport én de samenvatting.

    #1314, Koen: *"voor de import moet alles getoond worden wat geüpdate of
    geïnsert gaat worden."* Every write the import makes has a line, in the preview
    and in the run alike, and every line names the writes it stands for in
    `writes` (per table: `person`, `member_person`, `address`, …). That tally is
    what `tests/integration/test_import_reports_every_write.py` holds against the
    history rows and tables the run really adds: a write without a line fails it.
    """

    new_families: int = 0
    #: Households that change (#1308) — not every existing household in the report.
    updated_families: int = 0
    #: Existing households in the report that nothing changes; counted, not listed.
    unchanged_families: int = 0
    persons_added: int = 0
    persons_updated: int = 0
    persons_removed: int = 0
    persons_revived: int = 0
    memberships_created: int = 0
    admins_created: int = 0
    #: Board members who already have their admin account (#1308); counted, not listed.
    admins_existing: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    #: Filled by `finish()`: every household that changes, header and lines, then
    #: the lines that belong to no household (the admin accounts).
    lines: list[str] = field(default_factory=list)
    #: The writes the lines stand for, per table (#1314).
    writes: Counter = field(default_factory=Counter)
    #: Persons revived before the upsert (#227), by id → (member number, whether
    #: their household link and their household came back too). `_sync_family`
    #: writes the line under the household it belongs to (#1308).
    revived: dict[int, tuple[str, bool, bool]] = field(default_factory=dict)
    households: list[_Household] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)
    current: _Household | None = None

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def line(self, msg: str, *writes: str) -> None:
        """A change line, and the writes it stands for (#1314)."""
        (self.current.lines if self.current is not None else self.tail).append(msg)
        self.writes.update(writes)

    def begin_household(self, header: str, *, is_new: bool, member: object) -> _Household:
        self.current = _Household(header=header, is_new=is_new, member=member)
        self.households.append(self.current)
        return self.current

    def end_household(self) -> None:
        self.current = None

    def finish(self) -> ImportReport:
        """Lay out the lines and count the households, once every step has run.

        And let go of the ORM objects: a report outlives the import, and a household
        it kept alive would keep its collections from the session's identity map —
        measured: a second import then read last run's `memberships` and created
        the year's membership twice (`uq_memberships_member_year`)."""
        for h in self.households:
            h.member = None
        self.current = None
        self.lines = []
        self.updated_families = self.unchanged_families = 0
        for h in self.households:
            if not h.is_new:
                if not h.lines:
                    self.unchanged_families += 1
                    continue
                self.updated_families += 1
            self.lines.append(h.header)
            self.lines.extend(h.lines)
        self.lines.extend(self.tail)
        return self

    def to_dict(self) -> dict:
        """JSON-vriendelijke vorm voor het upload-endpoint."""
        return {
            "new_families": self.new_families,
            "updated_families": self.updated_families,
            "unchanged_families": self.unchanged_families,
            "persons_added": self.persons_added,
            "persons_updated": self.persons_updated,
            "persons_removed": self.persons_removed,
            "persons_revived": self.persons_revived,
            "memberships_created": self.memberships_created,
            "admins_created": self.admins_created,
            "admins_existing": self.admins_existing,
            "skipped": self.skipped,
            "warnings": list(self.warnings),
            "lines": list(self.lines),
        }


def _sort_lidnr(lidnr: str) -> int:
    """Numerieke sortering van lidnummers (lager = ouder lid)."""
    try:
        return int(lidnr)
    except (TypeError, ValueError):
        return 999999999


def _person_lidnr(person: Person, source: str) -> str | None:
    """Het lidnummer van een persoon voor deze bron, of None."""
    for en in person.external_numbers:
        if en.source == source:
            return en.external_id
    return None


def _delete_link(db: Session, link: MemberPerson) -> None:
    """Delete a household link, and forget the two collections that held it.

    `db.delete` removes the row, not the object from `person.member_persons` and
    `member.member_persons`: both keep listing a link that is gone for as long as
    their owner stays in the session. Every decision below reads those collections
    — which household is this person in, is he linked to this one already — so a
    later one in the same session decided on a link that no longer existed (#1756:
    a person who left a household and came back as the head of a new one was sent
    to the old household, found "already linked" there, and ended with no link at
    all). Expired, the collections are read from the database when next asked.
    """
    person, member = link.person, link.member
    db.delete(link)
    db.flush()
    db.expire(person, ["member_persons"])
    db.expire(member, ["member_persons"])


def _current_member(person: Person) -> Member | None:
    mp = next((m for m in person.member_persons), None)
    return mp.member if mp else None


# ── Identiteitsmatch (lidnummer-loze bestaande leden) ─────────────────────────


def _ident_norm(s) -> str:
    return _norm(str(s or "")).lower()


def _identity_key(first, last, dob):
    """Sleutel voor de identiteitsindex: genormaliseerde naam + geboortedatum."""
    return (_ident_norm(first), _ident_norm(last), dob)


def _identity_lookup(identity_map: dict, row: dict):
    """Zoek een bestaand lidnummer-loos lid op identiteit.

    Geeft ``(person, ambiguous)``. ``person`` is None bij 0 of >1 matches. Een
    geboortedatum is vereist — naam alleen is te zwak om automatisch te koppelen.
    """
    dob = row["geboortedatum"]
    if not dob:
        return None, False
    cands = identity_map.get(_identity_key(row["voornaam"], row["naam"], dob), [])
    if len(cands) == 1:
        return cands[0], False
    if len(cands) > 1:
        return None, True
    return None, False


def _identity_remove(identity_map: dict, person: Person) -> None:
    """Haal een persoon uit de identiteitsindex (nadat hij een lidnummer kreeg)."""
    key = _identity_key(person.first_name, person.last_name, person.date_of_birth)
    lst = identity_map.get(key)
    if lst and person in lst:
        lst.remove(person)


# Kolom in het rapport → attribuut op Person, in de volgorde waarin het rapport
# ze noemt (het wijzigingsverslag leest zo als de rij).
_PERSOONSVELDEN = {
    "naam": "last_name",
    "voornaam": "first_name",
    "geboortedatum": "date_of_birth",
    "geslacht": "gender_code",
}


def _leeg(waarde) -> bool:
    """Een lege cel: niets, of enkel witruimte."""
    return waarde is None or (isinstance(waarde, str) and not waarde.strip())


def _person_field_values(person: Person, row: dict) -> dict:
    """De waarden die deze rij op een BESTAANDE persoon zet (#685).

    **Een lege cel laat staan wat er is.** Een import vult aan en corrigeert; hij
    wist niet. Het ledenrapport komt uit een ander systeem en een leeg vakje daar
    betekent "hier weet ik niets van", niet "verwijder dit". Voorheen overschreef
    de import blind, dus één herimport kon een geboortedatum stilzwijgend op NULL
    zetten — en juist die twee velden zijn sinds #681 overal elders verplicht.

    Deze functie is de énige plek waar die regel staat. Zowel het bepalen wat er
    verandert als het toepassen ervan gaat er doorheen: repareer je alleen het
    toepassen, dan meldt het rapport een wijziging die niet gebeurt, telt
    `persons_updated` te hoog en schrijft `snapshot_person` een lege auditregel.

    **Bewust anders dan `_upsert_contact`, die op leeg juist verwíjdert.** Dat is
    geen inconsistentie om weg te poetsen: een gsm-nummer kan ophouden te bestaan —
    iemand geeft zijn nummer op, of wil het niet meer delen — en dan is een lege
    cel een mededeling. Een geboortedatum houdt niet op te bestaan. Wie deze twee
    gelijk wil trekken uit netheid, trekt ze de verkeerde kant op.

    Geldt niet voor een nieuwe persoon: daar is niets om te behouden, en een
    onvolledige rij wordt gemeld via `_meld_onvolledig`.
    """
    return {
        attr: (getattr(person, attr) if _leeg(row[kolom]) else row[kolom])
        for kolom, attr in _PERSOONSVELDEN.items()
    }


def _person_field_changes(person: Person, row: dict) -> list[FieldChange]:
    """Welke persoonsvelden wijken af van de rapportrij — and, since #1687, from
    what to what: the decision and the line come from the same pair."""
    waarden = _person_field_values(person, row)
    return [
        person_change(kolom, attr, getattr(person, attr), waarden[attr])
        for kolom, attr in _PERSOONSVELDEN.items()
        if getattr(person, attr) != waarden[attr]
    ]


def _meld_onvolledig(row: dict, report: ImportReport, person: Person | None = None) -> None:
    """Meld een rij zonder geboortedatum of geslacht (#681).

    De import weigert de rij NIET. Élk formulier dwingt deze twee velden af, maar
    een ledenrapport is geen formulier: het komt uit een ander systeem, het gaat om
    honderden rijen tegelijk, en op productie missen er vandaag twee een
    geboortedatum. Een import die daarop afbreekt, kost meer dan hij oplevert.

    Wat wél moet: zichtbaar zijn. Zonder melding is de import de ene weg waarlangs
    onvolledige leden ongemerkt binnenkomen — precies het gat dat #681 dicht. De
    waarschuwing staat in het dry-run-rapport én in de samenvatting, met naam en
    reden, zodat je vóór het bevestigen ziet wie je moet aanvullen.

    Bij een BESTAANDE persoon telt wat er ná de import staat, niet wat er in de
    rij stond (#685). Een lege cel laat de bestaande waarde staan, dus die persoon
    mist niets en hoort niet in de lijst met aan te vullen namen. Zou de melding op
    de rij blijven kijken, dan noemde het rapport bij elke herimport dezelfde mensen
    zonder dat er iets aan te vullen valt — en een waarschuwing die je altijd ziet,
    lees je niet meer.
    """
    waarden = (
        _person_field_values(person, row)
        if person is not None
        else {"date_of_birth": row["geboortedatum"], "gender_code": row["geslacht"]}
    )
    ontbreekt = [
        kolom
        for kolom, attr in (("geboortedatum", "date_of_birth"), ("geslacht", "gender_code"))
        if _leeg(waarden[attr])
    ]
    if ontbreekt:
        report.warn(
            f"{row['voornaam']} {row['naam']}: {' en '.join(ontbreekt)} "
            f"ontbreekt — wel ingelezen, aanvullen in het ledenbeheer."
        )


def _report_incomplete_address(row: dict, change: FieldChange | None, report: ImportReport) -> None:
    """Say that the report gives this household an address without a street or a
    house number, and what the import does with it (#1832; Koen, 9 October 2026:
    "dat is in orde, wel in de detail van de dry run die getoond wordt tonen").

    The import does NOT refuse it — the report of the national programme is the
    source, as for a missing birth date (`_meld_onvolledig`) — but until #1832 it
    said nothing: a new household got an address with an empty street, and an
    address that was there lost its house number, without a line that said so.
    `change` is what the import writes for this address, None when it stays as
    it is. In the preview and in the run alike.
    """
    missing = [
        word
        for word, column in (("straat", "straat"), ("huisnummer", "huisnummer"))
        if not (row[column] or "").strip()
    ]
    if not missing:
        return
    what = " en ".join(missing)
    if change is None:
        does = "het adres blijft zoals het is, onvolledig"
    elif change.old is None:
        does = f"het adres wordt ingelezen zonder {what}"
    else:
        does = f"het adres wordt bijgewerkt en verliest zijn {what} (was: {change.old})"
    report.warn(
        f"{row['voornaam']} {row['naam']}: het adres in het rapport heeft geen {what} — "
        f"{does}. Vul het aan in het rapport, of daarna in het ledenbeheer."
    )


def _apply_person_fields(person: Person, row: dict) -> None:
    for attr, waarde in _person_field_values(person, row).items():
        setattr(person, attr, waarde)


# ── Contacten ───────────────────────────────────────────────────────────────


def _upsert_contact(
    db: Session,
    person: Person,
    type_code,
    value: str | None,
    is_primary: bool,
    *,
    apply: bool,
    actor: str | None = None,
) -> FieldChange | None:
    """De import-kant van `mdm.service.upsert_primary_contact` (#1174).

    Dunne schil: hij vult alleen de audit-herkomst in, zodat een rij uit het
    Raak-Nationaal-rapport in de geschiedenis te onderscheiden blijft van een rij
    die iemand op het beheerscherm typte. De regel zelf — het HOOFDcontact en
    nooit een extra rij — staat op één plek, want ze stond er twee.
    """
    from app.domains.mdm.service import upsert_primary_contact

    changed = upsert_primary_contact(
        db,
        person,
        type_code,
        value,
        action="contacts_imported",
        source=LEGACY_SOURCE,
        is_primary=is_primary,
        apply=apply,
        actor=actor,
        # #1676: a phone or mobile row the first import wrote as non-primary is
        # the import's own — measured, no screen writes one. An e-mail address
        # that is not primary is an address we collected (#1174): never adopted.
        adopt_non_primary=type_code in (CONTACT.PHONE, CONTACT.MOBILE),
    )
    if changed is None:
        return None
    # #1687: the line is built from the decision itself — the pair it returns.
    return contact_change(type_code, changed.old, changed.new, promoted=changed.promoted)


def _sync_contacts(
    db: Session,
    person: Person,
    row: dict,
    *,
    apply: bool,
    actor: str | None = None,
    report: ImportReport | None = None,
    household_id: int | None = None,
) -> list[FieldChange]:
    """The contacts of one person; returns the fields that change (#1308),
    each with the value that stood and the value the report brings (#1687).

    Each is the PRIMARY row of its own type (#1676; Koen, 6 October 2026). The
    first import (#74) wrote a mobile number next to a landline as non-primary:
    "primary" then meant one number across the types. Since #1174 it is per
    type and means "what Raak Nationaal holds" — and a non-primary row is one
    `upsert_primary_contact` never touches. So that mobile row was out of the
    import's reach: every import logged it as changed while nothing changed,
    another number was added beside it, an emptied cell removed nothing.
    """
    changed = []
    for column, type_code in (
        ("email", CONTACT.EMAIL),
        ("telefoon", CONTACT.PHONE),
        ("gsm", CONTACT.MOBILE),
    ):
        # CR-22 (#1704): an address another person outside the household
        # already uses is not taken over. Reported and skipped — the import does
        # not stop on one row (the reasoning of `_meld_onvolledig`) — and decided
        # HERE, before the write, so the preview and the run say the same.
        if (
            type_code == CONTACT.EMAIL
            and row[column]
            and email_refusal(db, person, row[column], household_id=household_id)
        ):
            if report is not None:
                report.warn(
                    f"#{row['lidnr']} {row['voornaam']} {row['naam']}: e-mailadres niet "
                    "overgenomen — al in gebruik door iemand anders."
                )
            continue
        change = _upsert_contact(db, person, type_code, row[column], True, apply=apply, actor=actor)
        if change is not None:
            changed.append(change)
    return changed


# ── Adres (enkel hoofdlid) ──────────────────────────────────────────────────


def _sync_address(
    db: Session, person: Person, row: dict, pc: PostalCode, *, apply: bool, actor: str | None = None
) -> FieldChange | None:
    """Adres hoort enkel bij het hoofdlid (#125). Maak/werk bij.

    Returns the address change (#1308) — from which line to which (#1687) — or
    None when it stays, in dry-run too."""
    bus = row["busnummer"] or None
    existing = person.address
    new_line = address_line(row["straat"], row["huisnummer"], bus, pc)
    if existing:
        if (
            existing.street == row["straat"]
            and existing.house_number == row["huisnummer"]
            and existing.bus_number == bus
            and existing.postal_code_id == pc.id
        ):
            return None
        changed = FieldChange(
            key="adres",
            label=ADDRESS_LABEL,
            old=address_line(
                existing.street, existing.house_number, existing.bus_number, existing.postal_code
            ),
            new=new_line,
        )
        if apply:
            existing.street = row["straat"]
            existing.house_number = row["huisnummer"]
            existing.bus_number = bus
            existing.postal_code_id = pc.id
            db.flush()
            snapshot_address(
                db,
                existing,
                operation="update",
                action="address_imported",
                source=LEGACY_SOURCE,
                actor=actor,
            )
        return changed
    else:
        if apply:
            addr = Address(
                person_id=person.id,
                street=row["straat"],
                house_number=row["huisnummer"],
                bus_number=bus,
                postal_code_id=pc.id,
            )
            db.add(addr)
            db.flush()
            snapshot_address(
                db,
                addr,
                operation="insert",
                action="address_imported",
                source=LEGACY_SOURCE,
                actor=actor,
            )
        # A first address: the new line alone.
        return FieldChange(key="adres", label=ADDRESS_LABEL, old=None, new=new_line)


# ── Persoon aanmaken ────────────────────────────────────────────────────────


def _create_person(
    db: Session,
    row: dict,
    member: Member,
    pc: PostalCode | None,
    *,
    apply: bool,
    report: ImportReport,
    actor: str | None = None,
) -> Person | None:
    """Maak een nieuwe persoon, koppel aan het gezin, met externe-nummer,
    adres (enkel hoofdlid), contacten — alles geauditeerd.

    #1314: the address and the contacts are decided by `_sync_address` and
    `_sync_contacts` in the preview too, on a person that is never added to the
    session, so the preview lists the same writes as the run."""
    report.persons_added += 1
    _meld_onvolledig(row, report)
    writes = ["person", "member_person"] + (["external_number"] if row["lidnr"] else [])
    report.line(f"  + nieuw  #{row['lidnr']}  {row['voornaam']} {row['naam']}", *writes)

    person = Person(
        last_name=row["naam"],
        first_name=row["voornaam"],
        date_of_birth=row["geboortedatum"],
        gender_code=row["geslacht"],
    )
    if not apply:
        _report_new_details(db, person, row, pc, report, household_id=getattr(member, "id", None))
        return None

    db.add(person)
    db.flush()
    snapshot_person(
        db, person, operation="insert", action="person_imported", source=LEGACY_SOURCE, actor=actor
    )
    row["_person_id"] = person.id

    if row["lidnr"]:
        db.add(ExternalNumber(person_id=person.id, source=LEGACY_SOURCE, external_id=row["lidnr"]))

    mp = MemberPerson(member_id=member.id, person_id=person.id, relation_type=row["_relatie"])
    db.add(mp)
    db.flush()
    snapshot_member_person(
        db, mp, operation="insert", action="person_imported", source=LEGACY_SOURCE, actor=actor
    )

    _report_new_details(
        db, person, row, pc, report, apply=True, actor=actor, household_id=member.id
    )
    return person


def _report_new_details(
    db: Session,
    person: Person,
    row: dict,
    pc: PostalCode | None,
    report: ImportReport,
    *,
    apply: bool = False,
    actor: str | None = None,
    household_id: int | None = None,
) -> None:
    """A new person's address (head of household only) and contacts: written with
    `apply`, and in either mode reported with the writes they stand for (#1314)."""
    if row["_relatie"] == "HOOFDLID" and pc is not None:
        address = _sync_address(db, person, row, pc, apply=apply, actor=actor)
        _report_incomplete_address(row, address, report)
        if address:
            report.line(
                f"  + adres #{row['lidnr']}  {row['voornaam']} {row['naam']}  {address.text()}",
                "address",
            )
    contacts = _sync_contacts(
        db, person, row, apply=apply, actor=actor, report=report, household_id=household_id
    )
    if contacts:
        # A new person: there is nothing these replace, so the new values alone.
        new_only = [FieldChange(c.key, c.label, None, c.new) for c in contacts]
        report.line(
            f"  + contact #{row['lidnr']}  {row['voornaam']} {row['naam']}  {lines_text(new_only)}",
            *(["contact_detail"] * len(contacts)),
        )


# ── Lidmaatschap ────────────────────────────────────────────────────────────


def _say(db: Session, event: KernelEvent) -> None:
    """Publish what the report says to the domain that owns the consequence. Not
    optional: an import into silence would count a membership or a login it never
    made, so it refuses when nothing subscribes."""
    if not has_subscribers(type(event)):
        raise RuntimeError(
            f"nothing subscribes to {type(event).__name__}; import the owner's handlers.py"
        )
    publish(event, db)


def _ensure_membership(
    db: Session,
    member: Member,
    import_year: int,
    *,
    apply: bool,
    report: ImportReport,
    actor: str | None = None,
) -> bool:
    """Eén lidmaatschap voor het importjaar — nooit dupliceren (#74).

    Returns whether it creates one (#1308)."""
    if has_membership_for_year(member, import_year):
        return False
    report.memberships_created += 1
    if not apply:
        return True
    # The membership is membership's to write: the import says what the report
    # says, and membership adds it in this transaction (CR-13 phase 4c, #1251).
    _say(
        db,
        MembershipReported(
            household_id=member.id, year=import_year, source=str(LEGACY_SOURCE), actor=actor
        ),
    )
    return True


# ── Gezin synchroniseren (nieuw én bestaand via één pad) ─────────────────────


def _sync_family(
    db: Session,
    member: Member,
    fam: list[dict],
    pc: PostalCode | None,
    ext_map: dict,
    identity_map: dict,
    *,
    is_new: bool,
    apply: bool,
    report: ImportReport,
    actor: str | None = None,
    report_lidnrs: frozenset[str] = frozenset(),
) -> _Household | None:
    """Synchroniseer één gezin met zijn adresgroep uit het rapport.

    ``member`` is een echt object (bestaand of net aangemaakt) in apply-modus, of
    een transient object in dry-run voor een nieuw gezin. Bestaande personen
    worden ALTIJD hergebruikt op lidnummer (nooit gedupliceerd — dat zou de
    unieke (source, external_id)-constraint schenden); een onbekend lidnummer dat
    op identiteit een bestaand lidnummer-loos lid matcht krijgt dat lidnummer
    gehecht (#192); overige onbekende lidnummers worden aangemaakt; personen die
    niet meer in de adresgroep staan, worden bij een bestaand gezin uit het gezin
    verwijderd."""
    # #1308: an existing household gets its "UPDATE gezin" line only when
    # something in it changes. Every change below writes its own line — so the
    # lines this household adds ARE its changes, and the header goes in front of
    # them afterwards. No second comparison: the decision is the one each step
    # already makes.
    if is_new:
        report.new_families += 1
        report.begin_household(f"NIEUW gezin: {_family_label(fam)}", is_new=True, member=member)
        report.writes.update(["member"])  # the header is the household's own insert
    else:
        report.begin_household(
            f"UPDATE gezin (#{member.id}): {_family_label(fam)}", is_new=False, member=member
        )

    desired_lidnrs = {r["lidnr"] for r in fam if r["lidnr"]}
    # Personen (op id) die dit rapport voor dit gezin aanlevert — bepaalt straks
    # wie er níét meer in staat en dus verwijderd wordt. Robuuster dan enkel op
    # lidnummer, want het dekt ook identiteitsmatches en dry-run.
    processed_person_ids: set[int] = set()

    for row in fam:
        existing = ext_map.get(row["lidnr"]) if row["lidnr"] else None

        if existing is None and row["lidnr"]:
            # (#192) Probeer een identiteitsmatch op een bestaand lidnummer-loos
            # lid vóór we een nieuwe persoon aanmaken — anders dupliceren we elk
            # net-geregistreerd lid bij de eerste her-import.
            match, ambiguous = _identity_lookup(identity_map, row)
            if ambiguous:
                report.warn(
                    f"{row['voornaam']} {row['naam']} (geb. {row['geboortedatum']}): "
                    f"meerdere bestaande leden zonder lidnummer matchen op identiteit — "
                    f"niet automatisch gekoppeld, als nieuw behandeld."
                )
            elif match is not None:
                existing = match
                report.line(
                    f"  ⇄ identiteit #{row['lidnr']}  {row['voornaam']} {row['naam']}"
                    f"  — lidnummer gehecht aan bestaand lid",
                    "external_number",
                    "person",
                )
                if apply:
                    en = ExternalNumber(source=LEGACY_SOURCE, external_id=row["lidnr"])
                    en.person = match  # zet person_id én vult match.external_numbers in-sessie
                    db.add(en)
                    db.flush()
                    snapshot_person(
                        db,
                        match,
                        operation="update",
                        action="lidnr_attached",
                        source=LEGACY_SOURCE,
                        actor=actor,
                    )
                ext_map[row["lidnr"]] = match
                _identity_remove(identity_map, match)

        if existing is None:
            # Onbekend lidnummer (en geen identiteitsmatch) → nieuwe persoon.
            person = _create_person(db, row, member, pc, apply=apply, report=report, actor=actor)
            if person is not None:
                processed_person_ids.add(person.id)
                if row["lidnr"]:
                    ext_map[row["lidnr"]] = person
            continue

        # Bestaande persoon (lidnummer- of identiteitsmatch; mogelijk in een
        # ander gezin of verweesd) → hergebruik.
        processed_person_ids.add(existing.id)
        row["_person_id"] = existing.id
        if existing.id in report.revived:
            revived_lidnr, link_back, household_back = report.revived[existing.id]
            report.line(
                f"  ↺ hersteld #{revived_lidnr}  {existing.first_name} {existing.last_name}"
                + ("  (gezin hersteld)" if household_back else ""),
                "person",
                "external_number",
                *(["member_person_revive"] if link_back else []),
                *(["member"] if household_back else []),
            )
        cur_member = _current_member(existing)
        # Bij een nieuw (transient) gezin heeft member.id geen betekenis.
        mp = (
            None
            if is_new
            else next((m for m in existing.member_persons if m.member_id == member.id), None)
        )

        if mp is None:
            # Persoon nog niet aan dit gezin gekoppeld: verhuizen of (her)koppelen.
            verb = "verhuisd" if cur_member is not None else "gekoppeld"
            old_mp = (
                next((m for m in existing.member_persons if m.member_id == cur_member.id), None)
                if cur_member is not None
                else None
            )
            report.line(
                f"  ~ {verb} #{row['lidnr']}  {row['voornaam']} {row['naam']}",
                *(["member_person"] * (2 if old_mp else 1)),
            )
            if apply:
                if cur_member is not None:
                    if old_mp:
                        snapshot_member_person(
                            db,
                            old_mp,
                            operation="delete",
                            action="person_moved",
                            source=LEGACY_SOURCE,
                            actor=actor,
                        )
                        _delete_link(db, old_mp)
                # Relatie-attributen zetten (niet enkel de FK's) zodat zowel
                # member.member_persons als existing.member_persons consistent
                # blijven binnen de sessie.
                mp = MemberPerson(relation_type=row["_relatie"])
                mp.member = member
                mp.person = existing
                db.add(mp)
                db.flush()
                snapshot_member_person(
                    db,
                    mp,
                    operation="insert",
                    action="person_moved" if cur_member is not None else "person_imported",
                    source=LEGACY_SOURCE,
                    actor=actor,
                )

        _meld_onvolledig(row, report, existing)
        changes = _person_field_changes(existing, row)
        # `code_of`: since CR-12 phase 2 the column carries an enum member and
        # the report row a code. Without this step every row is "changed" and
        # the import reports a change that does not happen.
        rel_changed = mp is not None and code_of(mp.relation_type) != row["_relatie"]
        if changes or rel_changed:
            report.persons_updated += 1
            shown = changes + (
                [
                    FieldChange(
                        key="relatie",
                        label=RELATION_LABEL,
                        old=relation_value(mp.relation_type),
                        new=relation_value(row["_relatie"]),
                    )
                ]
                if rel_changed and mp is not None
                else []
            )
            report.line(
                f"  ~ update #{row['lidnr']}  {row['voornaam']} {row['naam']}  {lines_text(shown)}",
                *(["person"] if changes else []),
                *(["member_person"] if rel_changed else []),
            )
        if apply:
            if changes:
                _apply_person_fields(existing, row)
                db.flush()
                snapshot_person(
                    db,
                    existing,
                    operation="update",
                    action="person_imported",
                    source=LEGACY_SOURCE,
                    actor=actor,
                )
            if rel_changed and mp is not None:
                mp.relation_type = row["_relatie"]
                db.flush()
                snapshot_member_person(
                    db,
                    mp,
                    operation="update",
                    action="person_imported",
                    source=LEGACY_SOURCE,
                    actor=actor,
                )
        # Address and contacts are compared in dry-run too (#1308): they write only
        # with `apply`, but whether they WOULD change is part of the report.
        if row["_relatie"] == "HOOFDLID" and pc is not None:
            address = _sync_address(db, existing, row, pc, apply=apply, actor=actor)
            _report_incomplete_address(row, address, report)
            if address:
                report.line(
                    f"  ~ adres #{row['lidnr']}  {row['voornaam']} {row['naam']}  {address.text()}",
                    "address",
                )
        contacts = _sync_contacts(
            db,
            existing,
            row,
            apply=apply,
            actor=actor,
            report=report,
            household_id=None if is_new else member.id,
        )
        if contacts:
            report.line(
                f"  ~ contact #{row['lidnr']}  {row['voornaam']} {row['naam']}  "
                f"{lines_text(contacts)}",
                *(["contact_detail"] * len(contacts)),
            )

    # Verwijder personen die niet (meer) in de adresgroep van het rapport staan
    # (enkel bij een bestaand gezin; een nieuw gezin heeft nog geen leden).
    if not is_new:
        for mp in list(member.member_persons):
            if mp.person_id in processed_person_ids:
                continue
            lidnr = _person_lidnr(mp.person, LEGACY_SOURCE)
            # #1314: someone the report lists under another household is moving,
            # not leaving — that household's "~ verhuisd" removes this link. Removed
            # here as well, the link was deleted twice: two history rows and
            # "expected to delete 1 row(s); 0 were matched".
            if lidnr in desired_lidnrs or lidnr in report_lidnrs:
                continue
            report.persons_removed += 1
            # #1687: the member number when the person has one, and no "#?" when not.
            number = f"#{lidnr}  " if lidnr else ""
            report.line(
                f"  - verwijderd  {number}{mp.person.first_name} {mp.person.last_name}",
                "member_person",
            )
            if apply:
                snapshot_member_person(
                    db,
                    mp,
                    operation="delete",
                    action="person_removed",
                    source=LEGACY_SOURCE,
                    actor=actor,
                )
                _delete_link(db, mp)

    if _ensure_membership(db, member, IMPORT_YEAR, apply=apply, report=report, actor=actor):
        report.line(f"  + lidmaatschap {IMPORT_YEAR}", "membership")

    household = report.current
    report.end_household()
    return household


def _family_label(fam: list[dict]) -> str:
    h = fam[0]
    adres = f"{h['straat']} {h['huisnummer']}"
    if h["busnummer"]:
        adres += f" bus {h['busnummer']}"
    return f"{adres}, {h['postcode']} {h['gemeente']}"


# ── Bestuursleden + admin-gebruikers ────────────────────────────────────────


def _link_board_members(
    db: Session,
    families: list[list[dict]],
    bl_index: dict,
    households: dict[int, _Household],
    *,
    apply: bool,
    report: ImportReport,
    actor: str | None = None,
) -> None:
    """Koppel het verantwoordelijke bestuurslid per gezin (herkoppelen mag —
    het rapport wint, alle velden worden overschreven).

    #1314: decided in the preview too, and a change writes its line under the
    household it changes — which may make an otherwise unchanged household a
    changed one. In the preview a board member who is new in this report has no
    id yet; the run will create them, so their household changes."""
    for index, fam in enumerate(families):
        bl_name = fam[0].get("bestuurslid")
        if not bl_name:
            continue
        candidates = bl_index.get(_norm(bl_name), [])
        if not candidates:
            report.warn(f"bestuurslid '{bl_name}' niet gevonden voor gezin {fam[0]['naam']}.")
            continue
        best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
        pid = best.get("_person_id")
        household = households.get(index)
        if household is None or (apply and not pid):
            continue  # a skipped household, or a board member the run did not create
        member = household.member
        if pid is not None and member.board_member_id == pid:
            continue
        old = member.board_member if member.board_member_id else None
        was = f"{old.first_name} {old.last_name}" if old is not None else "—"
        report.current = household
        report.line(f"  ~ bestuurslid: {was} → {best['voornaam']} {best['naam']}", "member")
        report.current = None
        if apply:
            member.board_member_id = pid
            db.flush()
            snapshot_member(
                db,
                member,
                operation="update",
                action="board_member_imported",
                source=LEGACY_SOURCE,
                actor=actor,
            )


def _create_admin_users(
    db: Session, all_bl_names: list[str], bl_index: dict, *, apply: bool, report: ImportReport
) -> None:
    """Maak admin-gebruikers voor bestuursleden — enkel nieuwe; bestaande
    logins worden nooit overschreven.

    #1308: the existing account is looked up in dry-run too — a read — so the
    preview lists only the accounts the import will create, as the run does. It
    listed every board member with an address before, and the two disagreed.
    Existing accounts are counted (`admins_existing`), not listed."""
    for name in all_bl_names:
        candidates = bl_index.get(name, [])
        if not candidates:
            continue
        best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
        if not best.get("email"):
            continue
        if has_login(db, best["email"]):
            report.admins_existing += 1
            continue
        pid = best.get("_person_id")
        if apply and not pid:
            continue
        report.admins_created += 1
        report.line(
            f"  admin: {best['voornaam']} {best['naam']} <{best['email']}>", "user", "user_role"
        )
        if apply:
            # The login is auth's to write: the import says who the report names,
            # and auth makes the login in this transaction (CR-13 phase 4c, #1251).
            _say(db, BoardMemberReported(email=best["email"]))


def _norm(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", str(s).strip()).strip()


def _revive(obj) -> None:
    """De-soft-delete één object (idempotent)."""
    if getattr(obj, "deleted_at", None) is not None:
        obj.deleted_at = None


def _revive_soft_deleted(
    db: Session,
    families: list[list[dict]],
    *,
    apply: bool,
    report: ImportReport,
    actor: str | None = None,
) -> None:
    """Herleef soft-deleted personen/gezinnen die met hetzelfde lidnummer terugkomen,
    vóór de upsert (#227). Zonder dit zou de import ze — onzichtbaar door de
    soft-delete-filter — als nieuw beschouwen en een duplicaat aanmaken. We herleven
    de persoon + het lidnummer + de meest recente gezinskoppeling + dat gezin, zodat
    de gewone upsert ze als bestaand bijwerkt. Mutaties gebeuren in-sessie; de caller
    commit (apply) of verwerpt ze (dry-run, niet gecommit)."""
    lidnrs = {r["lidnr"] for fam in families for r in fam if r["lidnr"]}
    if not lidnrs:
        return

    def inc(model):
        return db.query(model).execution_options(include_deleted=True)

    ens = (
        inc(ExternalNumber)
        .filter(ExternalNumber.source == LEGACY_SOURCE, ExternalNumber.external_id.in_(lidnrs))
        .all()
    )
    for en in ens:
        person = inc(Person).filter(Person.id == en.person_id).first()
        if person is None or person.deleted_at is None:
            continue  # persoon nog actief → niets te herstellen
        report.persons_revived += 1
        _revive(person)
        _revive(en)
        link_back = household_back = False
        # De meest recente gezinskoppeling + dat gezin herleven, zodat het gezin
        # terugkomt i.p.v. dat er een duplicaat-gezin wordt aangemaakt.
        latest_mp = (
            inc(MemberPerson)
            .filter(MemberPerson.person_id == person.id)
            .order_by(MemberPerson.id.desc())
            .first()
        )
        if latest_mp is not None:
            link_back = latest_mp.deleted_at is not None
            _revive(latest_mp)
            member = inc(Member).filter(Member.id == latest_mp.member_id).first()
            if member is not None and member.deleted_at is not None:
                household_back = True
                _revive(member)
                if apply:
                    snapshot_member(
                        db,
                        member,
                        operation="update",
                        action="member_revived",
                        source=LEGACY_SOURCE,
                        actor=actor,
                    )
        report.revived[person.id] = (en.external_id, link_back, household_back)
        db.flush()
        if apply:
            snapshot_person(
                db,
                person,
                operation="update",
                action="person_revived",
                source=LEGACY_SOURCE,
                actor=actor,
            )


def _claimed_households(families: list[list[dict]], ext_map: dict) -> frozenset[int]:
    """The households an address group of this report claims through its own main
    member — the first lookup of `_resolve_existing_member`, for every group.
    Read before anything is written."""
    claimed = set()
    for fam in families:
        main = ext_map.get(fam[0]["lidnr"]) if fam[0]["lidnr"] else None
        member = _current_member(main) if main else None
        if member is not None:
            claimed.add(member.id)
    return frozenset(claimed)


def _resolve_existing_member(
    fam: list[dict],
    ext_map: dict,
    identity_map: dict,
    report: ImportReport,
    claimed: frozenset[int],
) -> Member | None:
    """Bepaal het bestaande gezin voor een adresgroep uit het rapport via het
    lidnummer van het hoofdlid. Lukt dat niet (hoofdlid onbekend of verweesd),
    val terug op een bestaand gezin van een ander gematcht gezinslid, en als
    laatste op het bestaande gezin van een lidnummer-loos lid dat op identiteit
    matcht (#192). Geen match → None (nieuw).

    #1832: the two fallbacks pass over a household in `claimed` — one that another
    address group of this report has through its own main member. Without that,
    a member who moved in with a main member the report did not know yet led
    this group to the household he LEFT, and the import made one household of
    the two: two main members, two addresses. The group is a new household
    then, and the member moves into it ("~ verhuisd")."""
    hoofd = ext_map.get(fam[0]["lidnr"]) if fam[0]["lidnr"] else None
    member = _current_member(hoofd) if hoofd else None
    if member is not None:
        return member
    for row in fam[1:]:
        p = ext_map.get(row["lidnr"]) if row["lidnr"] else None
        m = _current_member(p) if p else None
        if m is not None and m.id not in claimed:
            report.warn(
                f"gezin {fam[0]['naam']}: hoofdlid-lidnummer "
                f"{fam[0]['lidnr']} onbekend of verweesd; gekoppeld via "
                f"bestaand gezinslid #{row['lidnr']}."
            )
            return m
    # (#192) identiteit-terugval: het bestaande gezin van een lidnummer-loos lid
    # dat op naam+geboortedatum matcht (typisch een zelf-geregistreerd lid).
    for row in fam:
        p, _ambiguous = _identity_lookup(identity_map, row)
        m = _current_member(p) if p else None
        if m is not None and m.id not in claimed:
            report.warn(
                f"gezin {fam[0]['naam']}: geen lidnummer-match; gekoppeld "
                f"aan bestaand gezin via identiteit "
                f"({row['voornaam']} {row['naam']})."
            )
            return m
    return None


# ── Publieke entrypoint ─────────────────────────────────────────────────────


def _refuse_without_one_main_member(families: list[list[dict]], report: ImportReport) -> set[int]:
    """The address groups that do not hold exactly one row "lid": none of their rows
    is loaded, and the report says so (#1832). Two decisions of Koen, both of
    9 October 2026:

    - more than one — "dat mag niet kunnen, ik stel voor ze beiden niet op te laden
      en dat in detail zo te zeggen, dan moet er aan de aangeleverde file iets
      aangepast worden";
    - none — "a", to the master CLI's question "Kies je a of b?", a being: not
      loaded and said in the detail, the same rule as for two main members.

    A household has one main member (`require_one_main_member`). The import groups
    rows by address — street, house number, bus and postal code, exactly as typed
    (`group_families`). Two rows "lid" on one address would become ONE household
    with two main members; which of the two the partners and children belong to
    cannot be told. A group without any became a household without a main member
    and without an address — the address hangs on the main member's row — and a
    household that was loaded before lost its main member to it. So the whole
    group waits: nothing of it is added, changed or removed. Returns the indexes
    of those groups in `families`.
    """
    one_address = "één adres is dezelfde straat, huisnummer, bus en postcode"
    refused: set[int] = set()
    for index, fam in enumerate(families):
        mains = [row for row in fam if row["_relatie"] == "HOOFDLID"]
        if len(mains) == 1:
            continue
        refused.add(index)
        report.skipped += 1
        named = mains or fam
        who = " en ".join(f"{row['voornaam']} {row['naam']} (#{row['lidnr']})" for row in named)
        if mains:
            report.warn(
                f"{who} staan allebei als lid op hetzelfde adres — niemand van dit adres is "
                f"ingelezen ({len(fam)} rijen). Een gezin heeft één hoofdlid, en {one_address}. "
                f"Pas het rapport aan: geef elk gezin zijn eigen adres (bijvoorbeeld een "
                f"busnummer), of zet één van beide als partner of kind."
            )
        else:
            stands = "staat" if len(fam) == 1 else "staan"
            report.warn(
                f"{who} {stands} op een adres zonder lid — niemand van dit adres is ingelezen "
                f"({len(fam)} {'rij' if len(fam) == 1 else 'rijen'}). Een gezin heeft één "
                f"hoofdlid, en {one_address}. Pas het rapport aan: zet op dit adres één "
                f"persoon als lid, of geef {'deze persoon' if len(fam) == 1 else 'deze personen'} "
                f"het adres van het lid bij wie {'hij of zij hoort' if len(fam) == 1 else 'ze horen'}."
            )
    return refused


def upsert_families(
    db: Session,
    families: list[list[dict]],
    bl_index: dict,
    all_bl_names: list[str],
    *,
    apply: bool = True,
    import_year: int = IMPORT_YEAR,
    actor: str | None = None,
) -> ImportReport:
    """Upsert alle gezinnen uit het ledenrapport. Commit NIET.

    ``apply=False`` (dry-run): bepaalt alle wijzigingen en bouwt het rapport op,
    zonder de DB te muteren. ``actor`` belandt in elke history-rij (#214).
    """
    report = ImportReport()

    # The one exception to #681, by name (Koen, 29 September 2026, #1250): a
    # household member without a birth date or a gender is read in and reported
    # (`_meld_onvolledig`), not refused — the report of Raak Nationaal is the source
    # of truth, and a missing member is worse than an incomplete card. It holds for
    # this transaction, up to the caller's commit, and not a statement further.
    from app.domains.mdm.models import HOUSEHOLD_MEMBER_DETAILS, MEMBER_REPORT_IMPORT
    from app.kernel.rules import exempt

    exempt(db, HOUSEHOLD_MEMBER_DETAILS, MEMBER_REPORT_IMPORT)

    # Eerst: soft-deleted personen/gezinnen die terugkeren herleven (#227), zodat de
    # maps hieronder (gewone, gefilterde queries) ze als actief zien en de upsert ze
    # bijwerkt i.p.v. dupliceert.
    # #1832: an address group without exactly one main member is not loaded — and
    # so not revived either. Its member numbers stay in `report_lidnrs` below: a
    # person the report still names is nobody the import removes.
    refused = _refuse_without_one_main_member(families, report)
    loaded = [fam for index, fam in enumerate(families) if index not in refused]
    _revive_soft_deleted(db, loaded, apply=apply, report=report, actor=actor)

    # Preload bestaande lidnummers → persoon (met gezinnen/contacten/adres).
    ext_rows = (
        db.query(ExternalNumber)
        .filter(ExternalNumber.source == LEGACY_SOURCE)
        .options(joinedload(ExternalNumber.person))
        .all()
    )
    ext_map: dict[str, Person] = {e.external_id: e.person for e in ext_rows}

    # Bestaande personen ZONDER ledenadministratie-lidnummer, geïndexeerd op
    # identiteit (naam+geboortedatum) — voor de identiteitsmatch (#192). Een
    # geboortedatum is vereist; naamgenoten zonder datum komen niet in de index.
    lidnr_person_ids = {e.person_id for e in ext_rows}
    identity_map: dict[tuple, list[Person]] = defaultdict(list)
    for p in db.query(Person).options(joinedload(Person.member_persons)).all():
        if p.id in lidnr_person_ids or p.date_of_birth is None:
            continue
        identity_map[_identity_key(p.first_name, p.last_name, p.date_of_birth)].append(p)

    pc_map = {pc.postal_code: pc for pc in db.query(PostalCode).all()}

    households: dict[int, _Household] = {}
    report_lidnrs = frozenset(r["lidnr"] for fam in families for r in fam if r["lidnr"])
    claimed = _claimed_households(loaded, ext_map)
    for index, fam in enumerate(families):
        if index in refused:
            continue
        pc = pc_map.get(fam[0]["postcode"])
        member = _resolve_existing_member(fam, ext_map, identity_map, report, claimed)
        is_new = member is None

        if is_new:
            # #1314: skipped in the preview too — it listed the household as new,
            # and the run then left it out.
            if pc is None:
                report.skipped += 1
                report.warn(
                    f"gezin {fam[0]['naam']}: onbekende postcode "
                    f"{fam[0]['postcode']} — overgeslagen."
                )
                continue
            if apply:
                member = Member()
                db.add(member)
                db.flush()
                snapshot_member(
                    db,
                    member,
                    operation="insert",
                    action="member_imported",
                    source=LEGACY_SOURCE,
                    actor=actor,
                )
            else:
                member = Member()  # transient: enkel voor het dry-run-rapport

        assert member is not None  # is_new=False → bestaand lid; is_new=True → hierboven gezet
        household = _sync_family(
            db,
            member,
            fam,
            pc,
            ext_map,
            identity_map,
            is_new=is_new,
            apply=apply,
            report=report,
            actor=actor,
            report_lidnrs=report_lidnrs,
        )

        if household is not None:
            households[index] = household

    # Fase 2 + 3: bestuursleden koppelen en admin-gebruikers aanmaken.
    _link_board_members(db, families, bl_index, households, apply=apply, report=report, actor=actor)
    _create_admin_users(db, all_bl_names, bl_index, apply=apply, report=report)

    return report.finish()

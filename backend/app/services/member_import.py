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
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models.member import Member, Person, MemberPerson, Membership
from app.models.address import Address
from app.models.contact import ContactDetail
from app.models.external_number import ExternalNumber
from app.models.postal_codes import PostalCode
from app.models.user import User, UserRole
from app.domains.audit.service import (
    snapshot_person,
    snapshot_member,
    snapshot_member_person,
    snapshot_membership,
    snapshot_address,
    snapshot_contact_detail,
)

# Bronsysteem-label voor de lidnummers en de audit-source.
LEGACY_SOURCE = "ledenadministratie"

# Jaar waarvoor het lidmaatschap wordt aangemaakt.
IMPORT_YEAR = 2026

# Rapportkolom → contacttype.
_CONTACT_FIELDS = (("EMAIL", "email"), ("PHONE", "telefoon"), ("MOBILE", "gsm"))


@dataclass
class ImportReport:
    """Wat de load (zou) doen — voor het dry-run-rapport én de samenvatting."""

    new_families: int = 0
    updated_families: int = 0
    persons_added: int = 0
    persons_updated: int = 0
    persons_removed: int = 0
    persons_revived: int = 0
    memberships_created: int = 0
    admins_created: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def line(self, msg: str) -> None:
        self.lines.append(msg)

    def to_dict(self) -> dict:
        """JSON-vriendelijke vorm voor het upload-endpoint."""
        return {
            "new_families": self.new_families,
            "updated_families": self.updated_families,
            "persons_added": self.persons_added,
            "persons_updated": self.persons_updated,
            "persons_removed": self.persons_removed,
            "persons_revived": self.persons_revived,
            "memberships_created": self.memberships_created,
            "admins_created": self.admins_created,
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


def _person_field_changes(person: Person, row: dict) -> list[str]:
    """Welke persoonsvelden wijken af van de rapportrij?"""
    changes = []
    if person.last_name != row["naam"]:
        changes.append("naam")
    if person.first_name != row["voornaam"]:
        changes.append("voornaam")
    if person.date_of_birth != row["geboortedatum"]:
        changes.append("geboortedatum")
    if person.gender_code != row["geslacht"]:
        changes.append("geslacht")
    return changes


def _apply_person_fields(person: Person, row: dict) -> None:
    person.last_name = row["naam"]
    person.first_name = row["voornaam"]
    person.date_of_birth = row["geboortedatum"]
    person.gender_code = row["geslacht"]


# ── Contacten ───────────────────────────────────────────────────────────────

def _upsert_contact(db: Session, person: Person, type_code: str, value: str | None,
                    is_primary: bool, *, apply: bool, actor: str | None = None) -> None:
    """Maak/werk bij/verwijder één contactgegeven; snapshot elke wijziging."""
    existing = next((c for c in person.contact_details
                     if c.contact_type_code == type_code), None)
    if value:
        if existing:
            if existing.value == value and existing.is_primary == is_primary:
                return
            if apply:
                existing.value = value
                existing.is_primary = is_primary
                db.flush()
                snapshot_contact_detail(db, existing, operation="update",
                                        action="contacts_imported", source=LEGACY_SOURCE,
                                        actor=actor)
        else:
            if apply:
                contact = ContactDetail(person_id=person.id, contact_type_code=type_code,
                                        value=value, is_primary=is_primary)
                db.add(contact)
                db.flush()
                snapshot_contact_detail(db, contact, operation="insert",
                                        action="contacts_imported", source=LEGACY_SOURCE,
                                        actor=actor)
    elif existing:
        if apply:
            snapshot_contact_detail(db, existing, operation="delete",
                                    action="contacts_imported", source=LEGACY_SOURCE,
                                    actor=actor)
            person.contact_details.remove(existing)
            db.flush()


def _sync_contacts(db: Session, person: Person, row: dict, *, apply: bool,
                   actor: str | None = None) -> None:
    has_phone = bool(row["telefoon"])
    _upsert_contact(db, person, "EMAIL", row["email"], True, apply=apply, actor=actor)
    _upsert_contact(db, person, "PHONE", row["telefoon"], True, apply=apply, actor=actor)
    _upsert_contact(db, person, "MOBILE", row["gsm"], not has_phone, apply=apply, actor=actor)


# ── Adres (enkel hoofdlid) ──────────────────────────────────────────────────

def _sync_address(db: Session, person: Person, row: dict, pc: PostalCode,
                  *, apply: bool, actor: str | None = None) -> None:
    """Adres hoort enkel bij het hoofdlid (#125). Maak/werk bij."""
    bus = row["busnummer"] or None
    existing = person.address
    if existing:
        if (existing.street == row["straat"] and existing.house_number == row["huisnummer"]
                and existing.bus_number == bus and existing.postal_code_id == pc.id):
            return
        if apply:
            existing.street = row["straat"]
            existing.house_number = row["huisnummer"]
            existing.bus_number = bus
            existing.postal_code_id = pc.id
            db.flush()
            snapshot_address(db, existing, operation="update",
                             action="address_imported", source=LEGACY_SOURCE, actor=actor)
    else:
        if apply:
            addr = Address(person_id=person.id, street=row["straat"],
                           house_number=row["huisnummer"], bus_number=bus,
                           postal_code_id=pc.id)
            db.add(addr)
            db.flush()
            snapshot_address(db, addr, operation="insert",
                             action="address_imported", source=LEGACY_SOURCE, actor=actor)


# ── Persoon aanmaken ────────────────────────────────────────────────────────

def _create_person(db: Session, row: dict, member: Member, pc: PostalCode | None,
                   *, apply: bool, report: ImportReport, actor: str | None = None) -> Person | None:
    """Maak een nieuwe persoon, koppel aan het gezin, met externe-nummer,
    adres (enkel hoofdlid), contacten — alles geauditeerd."""
    report.persons_added += 1
    if not apply:
        return None

    person = Person(last_name=row["naam"], first_name=row["voornaam"],
                    date_of_birth=row["geboortedatum"], gender_code=row["geslacht"])
    db.add(person)
    db.flush()
    snapshot_person(db, person, operation="insert", action="person_imported",
                    source=LEGACY_SOURCE, actor=actor)
    row["_person_id"] = person.id

    if row["lidnr"]:
        db.add(ExternalNumber(person_id=person.id, source=LEGACY_SOURCE,
                              external_id=row["lidnr"]))

    mp = MemberPerson(member_id=member.id, person_id=person.id,
                      relation_type=row["_relatie"])
    db.add(mp)
    db.flush()
    snapshot_member_person(db, mp, operation="insert", action="person_imported",
                           source=LEGACY_SOURCE, actor=actor)

    if row["_relatie"] == "HOOFDLID" and pc is not None:
        _sync_address(db, person, row, pc, apply=apply, actor=actor)
    _sync_contacts(db, person, row, apply=apply, actor=actor)
    return person


# ── Lidmaatschap ────────────────────────────────────────────────────────────

def _ensure_membership(db: Session, member: Member, import_year: int,
                       *, apply: bool, report: ImportReport, actor: str | None = None) -> None:
    """Eén lidmaatschap voor het importjaar — nooit dupliceren (#74)."""
    existing = next((m for m in member.memberships if m.year == import_year), None)
    if existing:
        return
    report.memberships_created += 1
    if not apply:
        return
    ms = Membership(member_id=member.id, year=import_year, is_active=True,
                    valid_from=date(import_year, 1, 1), valid_to=date(import_year, 12, 31))
    db.add(ms)
    db.flush()
    snapshot_membership(db, ms, operation="insert", action="membership_imported",
                        source=LEGACY_SOURCE, actor=actor)


# ── Gezin synchroniseren (nieuw én bestaand via één pad) ─────────────────────

def _sync_family(db: Session, member: Member, fam: list[dict], pc: PostalCode | None,
                 ext_map: dict, identity_map: dict, *, is_new: bool, apply: bool,
                 report: ImportReport, actor: str | None = None) -> None:
    """Synchroniseer één gezin met zijn adresgroep uit het rapport.

    ``member`` is een echt object (bestaand of net aangemaakt) in apply-modus, of
    een transient object in dry-run voor een nieuw gezin. Bestaande personen
    worden ALTIJD hergebruikt op lidnummer (nooit gedupliceerd — dat zou de
    unieke (source, external_id)-constraint schenden); een onbekend lidnummer dat
    op identiteit een bestaand lidnummer-loos lid matcht krijgt dat lidnummer
    gehecht (#192); overige onbekende lidnummers worden aangemaakt; personen die
    niet meer in de adresgroep staan, worden bij een bestaand gezin uit het gezin
    verwijderd."""
    if is_new:
        report.new_families += 1
        report.line(f"NIEUW gezin: {_family_label(fam)}")
    else:
        report.updated_families += 1
        report.line(f"UPDATE gezin (#{member.id}): {_family_label(fam)}")

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
                report.warn(f"{row['voornaam']} {row['naam']} (geb. {row['geboortedatum']}): "
                            f"meerdere bestaande leden zonder lidnummer matchen op identiteit — "
                            f"niet automatisch gekoppeld, als nieuw behandeld.")
            elif match is not None:
                existing = match
                report.line(f"  ⇄ identiteit #{row['lidnr']}  {row['voornaam']} {row['naam']}"
                            f"  — lidnummer gehecht aan bestaand lid")
                if apply:
                    en = ExternalNumber(source=LEGACY_SOURCE, external_id=row["lidnr"])
                    en.person = match   # zet person_id én vult match.external_numbers in-sessie
                    db.add(en)
                    db.flush()
                    snapshot_person(db, match, operation="update", action="lidnr_attached",
                                    source=LEGACY_SOURCE, actor=actor)
                ext_map[row["lidnr"]] = match
                _identity_remove(identity_map, match)

        if existing is None:
            # Onbekend lidnummer (en geen identiteitsmatch) → nieuwe persoon.
            report.line(f"  + nieuw  #{row['lidnr']}  {row['voornaam']} {row['naam']}")
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
        cur_member = _current_member(existing)
        # Bij een nieuw (transient) gezin heeft member.id geen betekenis.
        mp = (None if is_new
              else next((m for m in existing.member_persons if m.member_id == member.id), None))

        if mp is None:
            # Persoon nog niet aan dit gezin gekoppeld: verhuizen of (her)koppelen.
            verb = "verhuisd" if cur_member is not None else "gekoppeld"
            report.line(f"  ~ {verb} #{row['lidnr']}  {row['voornaam']} {row['naam']}")
            if apply:
                if cur_member is not None:
                    old_mp = next((m for m in existing.member_persons
                                   if m.member_id == cur_member.id), None)
                    if old_mp:
                        snapshot_member_person(db, old_mp, operation="delete",
                                               action="person_moved", source=LEGACY_SOURCE,
                                               actor=actor)
                        db.delete(old_mp)
                        db.flush()
                # Relatie-attributen zetten (niet enkel de FK's) zodat zowel
                # member.member_persons als existing.member_persons consistent
                # blijven binnen de sessie.
                mp = MemberPerson(relation_type=row["_relatie"])
                mp.member = member
                mp.person = existing
                db.add(mp)
                db.flush()
                snapshot_member_person(
                    db, mp, operation="insert",
                    action="person_moved" if cur_member is not None else "person_imported",
                    source=LEGACY_SOURCE, actor=actor)

        changes = _person_field_changes(existing, row)
        rel_changed = mp is not None and mp.relation_type != row["_relatie"]
        if changes or rel_changed:
            report.persons_updated += 1
            label = ", ".join(changes) if changes else "—"
            report.line(f"  ~ update #{row['lidnr']}  {row['voornaam']} {row['naam']}"
                        f"  velden: {label}")
        if apply:
            if changes:
                _apply_person_fields(existing, row)
                db.flush()
                snapshot_person(db, existing, operation="update",
                                action="person_imported", source=LEGACY_SOURCE, actor=actor)
            if rel_changed and mp is not None:
                mp.relation_type = row["_relatie"]
                db.flush()
                snapshot_member_person(db, mp, operation="update",
                                       action="person_imported", source=LEGACY_SOURCE,
                                       actor=actor)
            if row["_relatie"] == "HOOFDLID" and pc is not None:
                _sync_address(db, existing, row, pc, apply=apply, actor=actor)
            _sync_contacts(db, existing, row, apply=apply, actor=actor)

    # Verwijder personen die niet (meer) in de adresgroep van het rapport staan
    # (enkel bij een bestaand gezin; een nieuw gezin heeft nog geen leden).
    if not is_new:
        for mp in list(member.member_persons):
            if mp.person_id in processed_person_ids:
                continue
            lidnr = _person_lidnr(mp.person, LEGACY_SOURCE)
            if lidnr in desired_lidnrs:
                continue
            report.persons_removed += 1
            report.line(f"  - verwijderd  #{lidnr or '?'}  "
                        f"{mp.person.first_name} {mp.person.last_name}")
            if apply:
                snapshot_member_person(db, mp, operation="delete",
                                       action="person_removed", source=LEGACY_SOURCE,
                                       actor=actor)
                db.delete(mp)
                db.flush()

    _ensure_membership(db, member, IMPORT_YEAR, apply=apply, report=report, actor=actor)


def _family_label(fam: list[dict]) -> str:
    h = fam[0]
    adres = f"{h['straat']} {h['huisnummer']}"
    if h["busnummer"]:
        adres += f" bus {h['busnummer']}"
    return f"{adres}, {h['postcode']} {h['gemeente']}"


# ── Bestuursleden + admin-gebruikers ────────────────────────────────────────

def _link_board_members(db: Session, families: list[list[dict]], bl_index: dict,
                        *, apply: bool, report: ImportReport, actor: str | None = None) -> None:
    """Koppel het verantwoordelijke bestuurslid per gezin (herkoppelen mag —
    het rapport wint, alle velden worden overschreven)."""
    if not apply:
        return
    for fam in families:
        bl_name = fam[0].get("bestuurslid")
        if not bl_name:
            continue
        candidates = bl_index.get(_norm(bl_name), [])
        if not candidates:
            report.warn(f"bestuurslid '{bl_name}' niet gevonden voor gezin "
                        f"{fam[0]['naam']}.")
            continue
        best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
        pid = best.get("_person_id")
        if not pid:
            continue
        member = _member_for_row(db, fam[0])
        if member is not None and member.board_member_id != pid:
            member.board_member_id = pid
            db.flush()
            snapshot_member(db, member, operation="update", action="board_member_imported",
                            source=LEGACY_SOURCE, actor=actor)


def _create_admin_users(db: Session, all_bl_names: list[str], bl_index: dict,
                        *, apply: bool, report: ImportReport) -> None:
    """Maak admin-gebruikers voor bestuursleden — enkel nieuwe; bestaande
    logins worden nooit overschreven."""
    for name in all_bl_names:
        candidates = bl_index.get(name, [])
        if not candidates:
            continue
        best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
        if not best.get("email"):
            continue
        if apply and db.query(User).filter(User.email == best["email"]).first():
            continue
        pid = best.get("_person_id")
        if apply and not pid:
            continue
        report.admins_created += 1
        report.line(f"  admin: {best['voornaam']} {best['naam']} <{best['email']}>")
        if apply:
            # User↔Person koppelt enkel via e-mail (geen FK/person_id-kolom op users):
            # dat is de bewuste auth-scheiding. Hier dus géén person_id meegeven (#226).
            user = User(email=best["email"], is_active=True)
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_code="ADMIN"))
            db.flush()


def _member_for_row(db: Session, row: dict) -> Member | None:
    pid = row.get("_person_id")
    if not pid:
        return None
    mp = db.query(MemberPerson).filter(MemberPerson.person_id == pid).first()
    return mp.member if mp else None


def _norm(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", str(s).strip()).strip()


def _revive(obj) -> None:
    """De-soft-delete één object (idempotent)."""
    if getattr(obj, "deleted_at", None) is not None:
        obj.deleted_at = None


def _revive_soft_deleted(db: Session, families: list[list[dict]], *, apply: bool,
                         report: ImportReport, actor: str | None = None) -> None:
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

    ens = (inc(ExternalNumber)
           .filter(ExternalNumber.source == LEGACY_SOURCE,
                   ExternalNumber.external_id.in_(lidnrs))
           .all())
    for en in ens:
        person = inc(Person).filter(Person.id == en.person_id).first()
        if person is None or person.deleted_at is None:
            continue   # persoon nog actief → niets te herstellen
        report.persons_revived += 1
        report.line(f"  ↺ hersteld #{en.external_id}  {person.first_name} {person.last_name}")
        _revive(person)
        _revive(en)
        # De meest recente gezinskoppeling + dat gezin herleven, zodat het gezin
        # terugkomt i.p.v. dat er een duplicaat-gezin wordt aangemaakt.
        latest_mp = (inc(MemberPerson)
                     .filter(MemberPerson.person_id == person.id)
                     .order_by(MemberPerson.id.desc()).first())
        if latest_mp is not None:
            _revive(latest_mp)
            member = inc(Member).filter(Member.id == latest_mp.member_id).first()
            if member is not None:
                _revive(member)
        db.flush()
        if apply:
            snapshot_person(db, person, operation="update", action="person_revived",
                            source=LEGACY_SOURCE, actor=actor)


def _resolve_existing_member(fam: list[dict], ext_map: dict, identity_map: dict,
                             report: ImportReport) -> Member | None:
    """Bepaal het bestaande gezin voor een adresgroep uit het rapport via het
    lidnummer van het hoofdlid. Lukt dat niet (hoofdlid onbekend of verweesd),
    val terug op een bestaand gezin van een ander gematcht gezinslid, en als
    laatste op het bestaande gezin van een lidnummer-loos lid dat op identiteit
    matcht (#192). Geen match → None (nieuw)."""
    hoofd = ext_map.get(fam[0]["lidnr"]) if fam[0]["lidnr"] else None
    member = _current_member(hoofd) if hoofd else None
    if member is not None:
        return member
    for row in fam[1:]:
        p = ext_map.get(row["lidnr"]) if row["lidnr"] else None
        m = _current_member(p) if p else None
        if m is not None:
            report.warn(f"gezin {fam[0]['naam']}: hoofdlid-lidnummer "
                        f"{fam[0]['lidnr']} onbekend of verweesd; gekoppeld via "
                        f"bestaand gezinslid #{row['lidnr']}.")
            return m
    # (#192) identiteit-terugval: het bestaande gezin van een lidnummer-loos lid
    # dat op naam+geboortedatum matcht (typisch een zelf-geregistreerd lid).
    for row in fam:
        p, _ambiguous = _identity_lookup(identity_map, row)
        m = _current_member(p) if p else None
        if m is not None:
            report.warn(f"gezin {fam[0]['naam']}: geen lidnummer-match; gekoppeld "
                        f"aan bestaand gezin via identiteit "
                        f"({row['voornaam']} {row['naam']}).")
            return m
    return None


# ── Publieke entrypoint ─────────────────────────────────────────────────────

def upsert_families(db: Session, families: list[list[dict]], bl_index: dict,
                    all_bl_names: list[str], *, apply: bool = True,
                    import_year: int = IMPORT_YEAR, actor: str | None = None) -> ImportReport:
    """Upsert alle gezinnen uit het ledenrapport. Commit NIET.

    ``apply=False`` (dry-run): bepaalt alle wijzigingen en bouwt het rapport op,
    zonder de DB te muteren. ``actor`` belandt in elke history-rij (#214).
    """
    report = ImportReport()

    # Eerst: soft-deleted personen/gezinnen die terugkeren herleven (#227), zodat de
    # maps hieronder (gewone, gefilterde queries) ze als actief zien en de upsert ze
    # bijwerkt i.p.v. dupliceert.
    _revive_soft_deleted(db, families, apply=apply, report=report, actor=actor)

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

    for fam in families:
        pc = pc_map.get(fam[0]["postcode"])
        member = _resolve_existing_member(fam, ext_map, identity_map, report)
        is_new = member is None

        if is_new:
            if pc is None and apply:
                report.skipped += 1
                report.warn(f"gezin {fam[0]['naam']}: onbekende postcode "
                            f"{fam[0]['postcode']} — overgeslagen.")
                continue
            if apply:
                member = Member()
                db.add(member)
                db.flush()
                snapshot_member(db, member, operation="insert", action="member_imported",
                                source=LEGACY_SOURCE, actor=actor)
            else:
                member = Member()   # transient: enkel voor het dry-run-rapport

        _sync_family(db, member, fam, pc, ext_map, identity_map, is_new=is_new,
                     apply=apply, report=report, actor=actor)

    # Fase 2 + 3: bestuursleden koppelen en admin-gebruikers aanmaken.
    _link_board_members(db, families, bl_index, apply=apply, report=report, actor=actor)
    _create_admin_users(db, all_bl_names, bl_index, apply=apply, report=report)

    return report

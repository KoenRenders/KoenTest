"""Upsert-service voor het opladen van het Raak-Nationaal-ledenrapport (#74).

Bij het opladen is het **Raak-Nationaal-Excel de bron van waarheid**: bestaande
gezinnen worden bijgewerkt in plaats van te aborteren. De match gebeurt op het
**lidnummer** (``ExternalNumber(source="ledenadministratie")``):

  - Een gezin wordt herkend aan het lidnummer van zijn **hoofdlid**.
  - Een rij met een bekend lidnummer is een *update*; een onbekend lidnummer is
    een *nieuwe* persoon/gezin.
  - Personen die wél in ons gezin zitten maar **niet** in de Excel-adresgroep
    staan, worden uit het gezin verwijderd (verhuisd of weggevallen). Wie
    verhuist, staat in de Excel onder zijn nieuwe adres en wordt daar toegevoegd.

Elke insert/update/delete wordt geauditeerd via de history-infrastructuur met
``source="ledenadministratie"`` (snapshot vóór een delete, zodat #82 / de
wijzigingslijst de verwijderde persoon nog ziet).

De service muteert de sessie maar **commit niet**: de aanroeper (CLI of test)
beslist over commit/rollback. Met ``apply=False`` worden geen DB-wijzigingen
gedaan — enkel het rapport van wat *zou* veranderen wordt opgebouwd (dry-run).
"""
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

# Excel-kolom → contacttype.
_CONTACT_FIELDS = (("EMAIL", "email"), ("PHONE", "telefoon"), ("MOBILE", "gsm"))


@dataclass
class ImportReport:
    """Wat de load (zou) doen — voor het dry-run-rapport én de samenvatting."""

    new_families: int = 0
    updated_families: int = 0
    persons_added: int = 0
    persons_updated: int = 0
    persons_removed: int = 0
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


def _person_field_changes(person: Person, row: dict) -> list[str]:
    """Welke persoonsvelden wijken af van de Excel-rij?"""
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
                    is_primary: bool, *, apply: bool) -> None:
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
                                        action="contacts_imported", source=LEGACY_SOURCE)
        else:
            if apply:
                contact = ContactDetail(person_id=person.id, contact_type_code=type_code,
                                        value=value, is_primary=is_primary)
                db.add(contact)
                db.flush()
                snapshot_contact_detail(db, contact, operation="insert",
                                        action="contacts_imported", source=LEGACY_SOURCE)
    elif existing:
        if apply:
            snapshot_contact_detail(db, existing, operation="delete",
                                    action="contacts_imported", source=LEGACY_SOURCE)
            person.contact_details.remove(existing)
            db.flush()


def _sync_contacts(db: Session, person: Person, row: dict, *, apply: bool) -> None:
    has_phone = bool(row["telefoon"])
    _upsert_contact(db, person, "EMAIL", row["email"], True, apply=apply)
    _upsert_contact(db, person, "PHONE", row["telefoon"], True, apply=apply)
    _upsert_contact(db, person, "MOBILE", row["gsm"], not has_phone, apply=apply)


# ── Adres (enkel hoofdlid) ──────────────────────────────────────────────────

def _sync_address(db: Session, person: Person, row: dict, pc: PostalCode,
                  *, apply: bool) -> None:
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
                             action="address_imported", source=LEGACY_SOURCE)
    else:
        if apply:
            addr = Address(person_id=person.id, street=row["straat"],
                           house_number=row["huisnummer"], bus_number=bus,
                           postal_code_id=pc.id)
            db.add(addr)
            db.flush()
            snapshot_address(db, addr, operation="insert",
                             action="address_imported", source=LEGACY_SOURCE)


# ── Persoon aanmaken ────────────────────────────────────────────────────────

def _create_person(db: Session, row: dict, member: Member, pc: PostalCode | None,
                   *, apply: bool, report: ImportReport) -> Person | None:
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
                    source=LEGACY_SOURCE)
    row["_person_id"] = person.id

    if row["lidnr"]:
        db.add(ExternalNumber(person_id=person.id, source=LEGACY_SOURCE,
                              external_id=row["lidnr"]))

    mp = MemberPerson(member_id=member.id, person_id=person.id,
                      relation_type=row["_relatie"])
    db.add(mp)
    db.flush()
    snapshot_member_person(db, mp, operation="insert", action="person_imported",
                           source=LEGACY_SOURCE)

    if row["_relatie"] == "HOOFDLID" and pc is not None:
        _sync_address(db, person, row, pc, apply=apply)
    _sync_contacts(db, person, row, apply=apply)
    return person


# ── Lidmaatschap ────────────────────────────────────────────────────────────

def _ensure_membership(db: Session, member: Member, import_year: int,
                       *, apply: bool, report: ImportReport) -> None:
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
                        source=LEGACY_SOURCE)


# ── Gezin synchroniseren (nieuw én bestaand via één pad) ─────────────────────

def _sync_family(db: Session, member: Member, fam: list[dict], pc: PostalCode | None,
                 ext_map: dict, *, is_new: bool, apply: bool, report: ImportReport) -> None:
    """Synchroniseer één gezin met zijn Excel-adresgroep.

    ``member`` is een echt object (bestaand of net aangemaakt) in apply-modus, of
    een transient object in dry-run voor een nieuw gezin. Bestaande personen
    worden ALTIJD hergebruikt op lidnummer (nooit gedupliceerd — dat zou de
    unieke (source, external_id)-constraint schenden); onbekende lidnummers worden
    aangemaakt; personen die niet meer in de adresgroep staan, worden bij een
    bestaand gezin uit het gezin verwijderd."""
    if is_new:
        report.new_families += 1
        report.line(f"NIEUW gezin: {_family_label(fam)}")
    else:
        report.updated_families += 1
        report.line(f"UPDATE gezin (#{member.id}): {_family_label(fam)}")

    desired_lidnrs = {r["lidnr"] for r in fam if r["lidnr"]}

    for row in fam:
        existing = ext_map.get(row["lidnr"]) if row["lidnr"] else None
        if existing is None:
            # Onbekend lidnummer → nieuwe persoon.
            report.line(f"  + nieuw  #{row['lidnr']}  {row['voornaam']} {row['naam']}")
            person = _create_person(db, row, member, pc, apply=apply, report=report)
            if person is not None and row["lidnr"]:
                ext_map[row["lidnr"]] = person
            continue

        # Bestaande persoon (mogelijk in een ander gezin of verweesd) → hergebruik.
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
                                               action="person_moved", source=LEGACY_SOURCE)
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
                    source=LEGACY_SOURCE)

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
                                action="person_imported", source=LEGACY_SOURCE)
            if rel_changed and mp is not None:
                mp.relation_type = row["_relatie"]
                db.flush()
                snapshot_member_person(db, mp, operation="update",
                                       action="person_imported", source=LEGACY_SOURCE)
            if row["_relatie"] == "HOOFDLID" and pc is not None:
                _sync_address(db, existing, row, pc, apply=apply)
            _sync_contacts(db, existing, row, apply=apply)

    # Verwijder personen die niet (meer) in de Excel-adresgroep staan (enkel
    # bij een bestaand gezin; een nieuw gezin heeft nog geen leden).
    if not is_new:
        for mp in list(member.member_persons):
            lidnr = _person_lidnr(mp.person, LEGACY_SOURCE)
            if lidnr in desired_lidnrs:
                continue
            report.persons_removed += 1
            report.line(f"  - verwijderd  #{lidnr or '?'}  "
                        f"{mp.person.first_name} {mp.person.last_name}")
            if apply:
                snapshot_member_person(db, mp, operation="delete",
                                       action="person_removed", source=LEGACY_SOURCE)
                db.delete(mp)
                db.flush()

    _ensure_membership(db, member, IMPORT_YEAR, apply=apply, report=report)


def _family_label(fam: list[dict]) -> str:
    h = fam[0]
    adres = f"{h['straat']} {h['huisnummer']}"
    if h["busnummer"]:
        adres += f" bus {h['busnummer']}"
    return f"{adres}, {h['postcode']} {h['gemeente']}"


# ── Bestuursleden + admin-gebruikers ────────────────────────────────────────

def _link_board_members(db: Session, families: list[list[dict]], bl_index: dict,
                        *, apply: bool, report: ImportReport) -> None:
    """Koppel het verantwoordelijke bestuurslid per gezin (herkoppelen mag —
    de Excel wint, alle velden worden overschreven)."""
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
                            source=LEGACY_SOURCE)


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
            user = User(email=best["email"], person_id=pid, is_active=True)
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


def _resolve_existing_member(fam: list[dict], ext_map: dict,
                             report: ImportReport) -> Member | None:
    """Bepaal het bestaande gezin voor een Excel-adresgroep via het lidnummer van
    het hoofdlid. Lukt dat niet (hoofdlid onbekend of verweesd), val terug op een
    bestaand gezin van een ander gematcht gezinslid. Geen match → None (nieuw)."""
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
    return None


# ── Publieke entrypoint ─────────────────────────────────────────────────────

def upsert_families(db: Session, families: list[list[dict]], bl_index: dict,
                    all_bl_names: list[str], *, apply: bool = True,
                    import_year: int = IMPORT_YEAR) -> ImportReport:
    """Upsert alle gezinnen uit het ledenrapport. Commit NIET.

    ``apply=False`` (dry-run): bepaalt alle wijzigingen en bouwt het rapport op,
    zonder de DB te muteren.
    """
    report = ImportReport()

    # Preload bestaande lidnummers → persoon (met gezinnen/contacten/adres).
    ext_rows = (
        db.query(ExternalNumber)
        .filter(ExternalNumber.source == LEGACY_SOURCE)
        .options(joinedload(ExternalNumber.person))
        .all()
    )
    ext_map: dict[str, Person] = {e.external_id: e.person for e in ext_rows}

    pc_map = {pc.postal_code: pc for pc in db.query(PostalCode).all()}

    for fam in families:
        pc = pc_map.get(fam[0]["postcode"])
        member = _resolve_existing_member(fam, ext_map, report)
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
                                source=LEGACY_SOURCE)
            else:
                member = Member()   # transient: enkel voor het dry-run-rapport

        _sync_family(db, member, fam, pc, ext_map, is_new=is_new, apply=apply, report=report)

    # Fase 2 + 3: bestuursleden koppelen en admin-gebruikers aanmaken.
    _link_board_members(db, families, bl_index, apply=apply, report=report)
    _create_admin_users(db, all_bl_names, bl_index, apply=apply, report=report)

    return report

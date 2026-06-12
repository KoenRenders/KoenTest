"""Import leden uit het Excel-ledenrapport.

Gebruik:
    python3 import_leden.py <pad/naar/Ledenrapport.xls> [--dry-run] [--env prod]

Zonder --env prod worden enkel de testgezinnen geladen
(Kerkebossenstraat 21 en Milostraat 40).

Zonder --dry-run schrijft het script effectief naar de DB.
Met --dry-run wordt enkel een rapport geprint zonder DB-wijzigingen.

OPGELET: Het Excel-bestand bevat persoonsgegevens en mag NIET in git.
"""

import sys
import os
import re
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import xlrd

from app.database import SessionLocal
from app.models.member import Member, Person, MemberPerson, Membership
from app.models.address import Address
from app.models.contact import ContactDetail
from app.models.external_number import ExternalNumber
from app.models.postal_codes import PostalCode
from app.models.user import User, UserRole

# Bronsysteem-label voor de oude lidnummers
LEGACY_SOURCE = "ledenadministratie"

# Testadressen voor niet-PROD omgevingen (straat lowercase, huisnummer exact)
TEST_ADDRESSES = [
    ("kerkebossenstraat", "21"),
    ("milostraat", "40"),
]

# Jaar waarvoor het lidmaatschap wordt aangemaakt
IMPORT_YEAR = 2026

# Relatie-mapping Excel → DB-code
RELATIE_MAP = {
    "lid": "HOOFDLID",
    "partner": "PARTNER",
    "(meerderjarig) kind": "KIND",
}

# Sorteervolgorde voor relaties binnen een gezin
RELATIE_ORDER = {"HOOFDLID": 0, "PARTNER": 1, "KIND": 2}


def normalize(s: str) -> str:
    """Verwijder overbodige spaties en zet om naar lowercase."""
    return re.sub(r"\s+", " ", str(s).strip()).strip()


def parse_gender(v: str) -> str | None:
    """Zet 'V'→'F', 'M'→'M'. Onbekend → None."""
    v = v.strip().upper()
    if v == "V":
        return "F"
    if v == "M":
        return "M"
    return None


def parse_date(serial: float, datemode: int) -> date | None:
    """Converteer een Excel-datumserienummer naar een Python date."""
    if not serial:
        return None
    try:
        return xlrd.xldate.xldate_as_datetime(serial, datemode).date()
    except Exception:
        return None


def clean_phone(v: str) -> str | None:
    """Verwijder spaties/slashes; geef None terug als leeg."""
    v = re.sub(r"\s+", "", v.strip())
    return v if v else None


def read_excel(path: str):
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_name("Sheet1")
    rows = []
    for r in range(4, sh.nrows):
        v = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if not str(v[0]).strip():
            continue
        rows.append({
            "lidnr":       str(v[0]).strip(),
            "voornaam":    normalize(v[1]),
            "naam":        normalize(v[2]),
            "straat":      normalize(v[3]),
            "huisnummer":  normalize(v[4]),
            "busnummer":   normalize(v[5]),
            "postcode":    str(v[6]).strip(),
            "gemeente":    normalize(v[7]),
            "email":       normalize(v[8]).lower() or None,
            "telefoon":    clean_phone(str(v[9])),
            "gsm":         clean_phone(str(v[10])),
            "geboortedatum": parse_date(v[11], wb.datemode),
            "geslacht":    parse_gender(str(v[12])),
            "bestuurslid": normalize(v[13]) or None,   # "NAAM Voornaam"
            "soort":       normalize(v[15]).lower(),   # lid / partner / kind
        })
    return rows


def group_families(rows: list[dict]) -> list[list[dict]]:
    """Groepeer personen per adres. Sorteer per gezin: HOOFDLID eerst."""
    fams: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["straat"].lower(), r["huisnummer"].lower(),
               r["busnummer"].lower(), r["postcode"])
        r["_relatie"] = RELATIE_MAP.get(r["soort"], "KIND")
        fams[key].append(r)
    result = []
    for members in fams.values():
        members.sort(key=lambda m: RELATIE_ORDER.get(m["_relatie"], 2))
        result.append(members)
    return result


def filter_test(families: list[list[dict]]) -> list[list[dict]]:
    """Houd enkel testadressen over."""
    out = []
    for fam in families:
        straat = fam[0]["straat"].lower()
        huisnr = fam[0]["huisnummer"].lower()
        if any(straat == t[0] and huisnr == t[1] for t in TEST_ADDRESSES):
            out.append(fam)
    return out


def build_bestuurslid_index(rows: list[dict]) -> dict[str, list[dict]]:
    """Index van "NAAM Voornaam" (genormaliseerd) → lijst van rijen.

    Meerdere rijen per naam = dubbelganger → wordt gewaarschuwd.
    """
    idx: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = f"{r['naam']} {r['voornaam']}"
        idx[normalize(key)].append(r)
    return idx


def run(excel_path: str, dry_run: bool, is_prod: bool):
    print(f"\n{'=== DROOGLOOP ===' if dry_run else '=== IMPORT ==='}")
    print(f"Omgeving: {'PROD (alle leden)' if is_prod else 'DEV/UAT (enkel testadressen)'}")
    print(f"Excel: {excel_path}\n")

    rows = read_excel(excel_path)
    families = group_families(rows)

    if not is_prod:
        families = filter_test(families)
        print(f"Testfilter actief: {len(families)} gezin(nen) geselecteerd.\n")

    print(f"Te importeren: {len(families)} gezinnen, "
          f"{sum(len(f) for f in families)} personen.\n")

    bl_index = build_bestuurslid_index(rows)

    # Waarschuwingen over dubbelgangers onder bestuursleden
    all_bl_names = sorted(set(
        normalize(r["bestuurslid"]) for r in rows if r["bestuurslid"]
    ))
    for name in all_bl_names:
        if len(bl_index.get(name, [])) > 1:
            print(f"  WAARSCHUWING: '{name}' komt {len(bl_index[name])} keer voor "
                  f"als persoon. Laagste lidnummer wordt gebruikt als bestuurslid-persoon.")

    if dry_run:
        _dry_run_report(families, bl_index)
        return

    db = SessionLocal()
    try:
        if db.query(Member).count() > 0:
            print("ABORT: er zijn al leden in de database. Droogloop eerst om dubbele import te voorkomen.")
            print("Gebruik --dry-run voor een overzicht.")
            return

        # Laad postcodes eenmalig in geheugen
        pc_map = {pc.postal_code: pc for pc in db.query(PostalCode).all()}

        # Fase 1: importeer alle gezinnen + personen
        imported_families: list[tuple[Member, list[dict]]] = []
        now = datetime.now(timezone.utc)

        for fam in families:
            eerste = fam[0]
            postcode = eerste["postcode"]
            pc = pc_map.get(postcode)
            if not pc:
                print(f"  SKIP gezin {eerste['naam']}: onbekende postcode {postcode}")
                continue

            member = Member()
            db.add(member)
            db.flush()

            for p in fam:
                person = Person(
                    last_name=p["naam"],
                    first_name=p["voornaam"],
                    date_of_birth=p["geboortedatum"],
                    gender_code=p["geslacht"],
                )
                db.add(person)
                db.flush()
                p["_person_id"] = person.id

                if p["lidnr"]:
                    db.add(ExternalNumber(
                        person_id=person.id,
                        source=LEGACY_SOURCE,
                        external_id=p["lidnr"],
                    ))

                db.add(MemberPerson(
                    member_id=member.id,
                    person_id=person.id,
                    relation_type=p["_relatie"],
                ))
                db.add(Address(
                    person_id=person.id,
                    street=p["straat"],
                    house_number=p["huisnummer"],
                    bus_number=p["busnummer"] or None,
                    postal_code_id=pc.id,
                ))
                if p["telefoon"]:
                    db.add(ContactDetail(
                        person_id=person.id,
                        contact_type_code="PHONE",
                        value=p["telefoon"],
                        is_primary=True,
                    ))
                if p["gsm"]:
                    db.add(ContactDetail(
                        person_id=person.id,
                        contact_type_code="MOBILE",
                        value=p["gsm"],
                        is_primary=not p["telefoon"],
                    ))
                if p["email"]:
                    db.add(ContactDetail(
                        person_id=person.id,
                        contact_type_code="EMAIL",
                        value=p["email"],
                        is_primary=True,
                    ))

            # Lidmaatschap 2026: reeds betaald
            db.add(Membership(
                member_id=member.id,
                year=IMPORT_YEAR,
                is_active=True,
                valid_from=date(IMPORT_YEAR, 1, 1),
                valid_to=date(IMPORT_YEAR, 12, 31),
            ))

            imported_families.append((member, fam))

        db.flush()

        # Fase 2: koppel verantwoordelijk bestuurslid per gezin
        for member, fam in imported_families:
            bl_name = fam[0].get("bestuurslid")
            if not bl_name:
                continue
            candidates = bl_index.get(normalize(bl_name), [])
            if not candidates:
                print(f"  WAARSCHUWING: bestuurslid '{bl_name}' niet gevonden voor gezin {fam[0]['naam']}.")
                continue
            # Bij dubbelganger: laagste lidnummer
            best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
            pid = best.get("_person_id")
            if pid:
                member.board_member_id = pid

        db.flush()

        # Fase 3: admin-gebruikers voor bestuursleden
        created_users = 0
        skipped_no_email = []
        for name in all_bl_names:
            candidates = bl_index.get(name, [])
            if not candidates:
                continue
            best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
            if not best.get("email"):
                skipped_no_email.append(f"{best['voornaam']} {best['naam']}")
                continue
            pid = best.get("_person_id")
            if not pid:
                print(f"  WAARSCHUWING: persoon-id ontbreekt voor bestuurslid {name}.")
                continue
            existing = db.query(User).filter(User.email == best["email"]).first()
            if existing:
                print(f"  SKIP admin voor {name}: e-mail {best['email']} bestaat al.")
                continue
            user = User(email=best["email"], person_id=pid, is_active=True)
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_code="ADMIN"))
            created_users += 1
            print(f"  Admin aangemaakt: {best['voornaam']} {best['naam']} <{best['email']}>")

        if skipped_no_email:
            print(f"\n  Geen admin aangemaakt (geen e-mail): {', '.join(skipped_no_email)}")

        db.commit()
        print(f"\nKlaar.")
        print(f"  {len(imported_families)} gezinnen geïmporteerd.")
        print(f"  {sum(len(f) for _, f in imported_families)} personen geïmporteerd.")
        print(f"  {created_users} admin-gebruikers aangemaakt.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _sort_lidnr(lidnr: str) -> int:
    """Numerieke sorteering van lidnummers (lager = ouder lid)."""
    try:
        return int(lidnr)
    except ValueError:
        return 999999999


def _dry_run_report(families: list[list[dict]], bl_index: dict):
    all_bl_names = sorted(set(
        normalize(r["bestuurslid"]) for f in families for r in f if r.get("bestuurslid")
    ))
    print(f"{'—'*60}")
    for fam in families:
        eerste = fam[0]
        adres = f"{eerste['straat']} {eerste['huisnummer']}"
        if eerste["busnummer"]:
            adres += f" bus {eerste['busnummer']}"
        print(f"\nGezin: {adres}, {eerste['postcode']} {eerste['gemeente']}")
        bl = eerste.get("bestuurslid", "—")
        print(f"  Bestuurslid: {bl}")
        for p in fam:
            geb = p["geboortedatum"].isoformat() if p["geboortedatum"] else "—"
            email = p["email"] or "—"
            print(f"  [{p['_relatie']:8}] #{p['lidnr']:6}  {p['voornaam']} {p['naam']:20} "
                  f"geb:{geb}  {email}")

    print(f"\n{'—'*60}")
    print("Admin-gebruikers die worden aangemaakt:")
    for name in all_bl_names:
        candidates = bl_index.get(name, [])
        if not candidates:
            print(f"  ! '{name}': niet gevonden")
            continue
        best = min(candidates, key=lambda r: _sort_lidnr(r["lidnr"]))
        em = best.get("email") or "GEEN E-MAIL"
        marker = "" if best.get("email") else " ← SKIP (geen e-mail)"
        print(f"  {best['voornaam']} {best['naam']:20} <{em}>{marker}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", help="Pad naar het Excel-ledenrapport (.xls)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Droogloop: print rapport zonder DB-wijzigingen")
    parser.add_argument("--env", default="dev",
                        help="'prod' = alle leden; anders enkel testadressen (standaard)")
    args = parser.parse_args()

    run(
        excel_path=args.excel,
        dry_run=args.dry_run,
        is_prod=args.env.lower() == "prod",
    )

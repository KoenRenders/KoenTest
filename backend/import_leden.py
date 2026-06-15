"""Import leden uit het Excel-ledenrapport.

Gebruik:
    python3 import_leden.py <pad/naar/Ledenrapport.xls> [--dry-run] [--all-members]

De omgeving wordt bepaald door de container zelf via APP_ENV:
  - APP_ENV=prod  → ALLE leden worden geladen.
  - elke andere   → enkel de testgezinnen (Kerkebossenstraat 21 en
    (dev/hdev/uat)   Milostraat 40).

Wil je tóch alle leden laden buiten PROD (bv. om de volledige load te
repeteren op HDEV/UAT), gebruik dan --all-members. Dat vraagt een
expliciete bevestiging, zodat het nooit per ongeluk gebeurt.

Zonder --dry-run schrijft het script effectief naar de DB.
Met --dry-run wordt enkel een rapport geprint zonder DB-wijzigingen.

OPGELET: Het Excel-bestand bevat persoonsgegevens en mag NIET in git.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.services.member_import import upsert_families
from app.services.ledenrapport_excel import (
    read_excel,
    group_families,
    filter_test,
    build_bestuurslid_index,
    all_board_member_names,
)


def run(excel_path: str, dry_run: bool, load_all: bool, app_env: str, forced: bool):
    print(f"\n{'=== DROOGLOOP ===' if dry_run else '=== IMPORT ==='}")
    print(f"APP_ENV: {app_env}")
    if load_all:
        extra = "  (GEFORCEERD via --all-members)" if forced else ""
        print(f"Omgeving: ALLE LEDEN{extra}")
    else:
        print(f"Omgeving: NIET-PROD (enkel testadressen)")
    print(f"Excel: {excel_path}\n")

    rows = read_excel(excel_path)
    families = group_families(rows)

    if not load_all:
        families = filter_test(families)
        print(f"Testfilter actief: {len(families)} gezin(nen) geselecteerd.\n")

    print(f"Te importeren: {len(families)} gezinnen, "
          f"{sum(len(f) for f in families)} personen.\n")

    bl_index = build_bestuurslid_index(rows)

    # Waarschuwingen over dubbelgangers onder bestuursleden
    all_bl_names = all_board_member_names(rows)
    for name in all_bl_names:
        if len(bl_index.get(name, [])) > 1:
            print(f"  WAARSCHUWING: '{name}' komt {len(bl_index[name])} keer voor "
                  f"als persoon. Laagste lidnummer wordt gebruikt als bestuurslid-persoon.")

    # Een geforceerde volledige load buiten PROD vraagt expliciete bevestiging,
    # zodat dit nooit per ongeluk gebeurt. (Niet bij een droogloop.)
    if not dry_run and forced:
        antwoord = input(
            f"\nJe staat op het punt ALLE {sum(len(f) for f in families)} personen "
            f"te laden in omgeving '{app_env}'.\n"
            f"Typ '{app_env}' om te bevestigen: "
        ).strip()
        if antwoord != app_env:
            print("Geannuleerd — geen bevestiging.")
            return

    db = SessionLocal()
    try:
        # De Excel is de bron van waarheid: bestaande gezinnen worden bijgewerkt,
        # onbekende lidnummers ingevoegd, afwezige personen verwijderd (#74).
        report = upsert_families(
            db, families, bl_index, all_bl_names, apply=not dry_run,
        )

        for line in report.lines:
            print(line)
        for w in report.warnings:
            print(f"  WAARSCHUWING: {w}")

        if dry_run:
            db.rollback()
            print(f"\n{'—'*60}\n=== DROOGLOOP — niets weggeschreven ===")
        else:
            db.commit()
            print(f"\nKlaar.")

        print(f"  {report.new_families} nieuwe gezinnen, "
              f"{report.updated_families} bijgewerkt.")
        print(f"  {report.persons_added} personen toegevoegd, "
              f"{report.persons_updated} bijgewerkt, "
              f"{report.persons_removed} verwijderd.")
        print(f"  {report.memberships_created} lidmaatschappen aangemaakt, "
              f"{report.admins_created} admin-gebruikers.")
        if report.skipped:
            print(f"  {report.skipped} gezin(nen) overgeslagen.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", help="Pad naar het Excel-ledenrapport (.xls)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Droogloop: print rapport zonder DB-wijzigingen")
    parser.add_argument("--all-members", action="store_true",
                        help="Forceer het laden van ALLE leden, ook buiten PROD "
                             "(vraagt bevestiging). Bedoeld om de volledige load "
                             "te repeteren op bv. HDEV/UAT.")
    args = parser.parse_args()

    # De omgeving wordt bepaald door de container zelf (APP_ENV). Alleen in de
    # PROD-container worden standaard alle leden geladen; in elke andere omgeving
    # (dev/hdev/uat) enkel de testadressen. Een volledige load buiten PROD kan
    # enkel bewust via --all-members (met bevestiging), nooit per ongeluk.
    from app.config import settings
    app_env = settings.app_env
    is_prod = app_env == "prod"
    load_all = is_prod or args.all_members
    forced = args.all_members and not is_prod

    run(
        excel_path=args.excel,
        dry_run=args.dry_run,
        load_all=load_all,
        app_env=app_env,
        forced=forced,
    )

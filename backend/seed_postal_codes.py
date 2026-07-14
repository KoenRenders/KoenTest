"""Seed postal codes from docs/postal_codes_seed.csv."""
import csv
import os
import sys
from datetime import datetime, timezone

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.domains.registry import load_all_models
from app.domains.mdm.api import PostalCode

load_all_models()

CSV_PATH = os.path.join(os.path.dirname(__file__), "docs", "postal_codes_seed.csv")


def seed():
    db = SessionLocal()
    try:
        existing = db.query(PostalCode).count()
        if existing > 0:
            print(f"postal_codes table already has {existing} rows — skipping seed.")
            return

        now = datetime.now(timezone.utc)
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = [
                PostalCode(
                    postal_code=row["postal_code"],
                    municipality=row["municipality"],
                    created_at=now,
                    updated_at=now,
                )
                for row in reader
            ]

        db.bulk_save_objects(records)
        db.commit()
        print(f"Inserted {len(records)} postal codes.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

"""Eenmalige backfill van flyer_text voor bestaande posters (#206).

Posters die vóór deze feature werden opgeladen (v1.7.0) hebben nog geen
``flyer_text``. Dit script loopt alle activiteiten met een poster af en
(her)extraheert ze. ``update_activity_flyer_text`` heeft een hash-skip ingebouwd,
dus herhaald draaien is veilig en doet geen dubbel werk/kost.

Gebruik (in de backend-container):
    python backfill_flyer_text.py
"""
import logging

from app.database import SessionLocal
from app.models.asset import MediaAsset
from app.services.flyer_extraction import update_activity_flyer_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_flyer_text")


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(MediaAsset.activity_id)
            .filter(
                MediaAsset.kind == "activity_poster",
                MediaAsset.activity_id.isnot(None),
            )
            .distinct()
            .all()
        )
        activity_ids = [r[0] for r in rows]
    finally:
        db.close()

    logger.info("Posters gevonden voor %d activiteit(en).", len(activity_ids))
    for activity_id in activity_ids:
        update_activity_flyer_text(activity_id)
    logger.info("Backfill klaar.")


if __name__ == "__main__":
    main()

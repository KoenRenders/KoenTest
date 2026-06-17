"""Eenmalige backfill van extracted_text voor bestaande media (#206).

Posters/reglementen die vóór deze feature werden opgeladen (v1.7.0) hebben nog
geen ``extracted_text``. Dit script loopt alle extraheerbare media-assets af en
leest ze uit. ``update_media_extracted_text`` slaat assets met al een tekst over
(geen ``force``), dus herhaald draaien is veilig en doet geen dubbel werk/kost.

Gebruik (in de backend-container):
    python backfill_extracted_text.py
"""
import logging

from app.database import SessionLocal
from app.models.asset import MediaAsset
from app.services.media_extraction import EXTRACTABLE_KINDS, update_media_extracted_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_extracted_text")


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(MediaAsset.id)
            .filter(MediaAsset.kind.in_(EXTRACTABLE_KINDS))
            .all()
        )
        asset_ids = [r[0] for r in rows]
    finally:
        db.close()

    logger.info("Extraheerbare media-assets gevonden: %d.", len(asset_ids))
    for asset_id in asset_ids:
        update_media_extracted_text(asset_id)
    logger.info("Backfill klaar.")


if __name__ == "__main__":
    main()

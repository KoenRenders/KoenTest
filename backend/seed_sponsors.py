"""Seed sponsorlogo's in de assetbibliotheek (media_assets).

Idempotent: leest elk logo uit ``assets/seed/`` en voegt het toe als sponsor,
tenzij er al een sponsor met dezelfde titel bestaat. Ontbreekt een bestand, dan
wordt het stilletjes overgeslagen. Veilig om bij elke opstart te draaien.
"""
import os

from app.database import SessionLocal
from app.models.asset import MediaAsset
from app.services.images import process_image

_SEED_DIR = os.path.join(os.path.dirname(__file__), "assets", "seed")

# (bestandsnaam, sponsornaam, optionele website)
SPONSORS = [
    ("mona.png", "Mona", None),
]


def main():
    db = SessionLocal()
    try:
        for filename, title, link_url in SPONSORS:
            path = os.path.join(_SEED_DIR, filename)
            if not os.path.exists(path):
                print(f"  {filename} niet gevonden, overslaan.")
                continue

            exists = (
                db.query(MediaAsset)
                .filter(MediaAsset.kind == "sponsor", MediaAsset.title == title)
                .first()
            )
            if exists:
                print(f"  Sponsor '{title}' bestaat al, overslaan.")
                continue

            with open(path, "rb") as f:
                raw = f.read()
            processed = process_image(raw)

            order = db.query(MediaAsset).filter(MediaAsset.kind == "sponsor").count()
            db.add(MediaAsset(
                kind="sponsor",
                title=title,
                link_url=link_url,
                sort_order=order,
                is_active=True,
                **processed,
            ))
            db.commit()
            print(f"  Sponsor '{title}' geseed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

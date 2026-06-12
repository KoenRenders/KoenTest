from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    LargeBinary,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _now_utc():
    return datetime.now(timezone.utc)


class MediaAsset(Base):
    """Binaire assetbibliotheek, opgeslagen in Postgres (BYTEA).

    Eén tabel voor twee soorten media:
    - ``kind="sponsor"``  → logo's die in de footer/homepage verschijnen
      (optioneel met ``link_url`` als doorklik).
    - ``kind="activity_photo"`` → foto's bij een activiteit (``activity_id``),
      getoond in het archief.

    Naast het volledige (verkleinde) beeld bewaren we een aparte thumbnail,
    zodat galerij-grids licht blijven en niet telkens de grote blob laden.
    """

    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)  # sponsor | activity_photo
    activity_id = Column(
        Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Volledig beeld (verkleind) + losse thumbnail.
    data = Column(LargeBinary, nullable=False)
    content_type = Column(String(50), nullable=False)
    thumbnail = Column(LargeBinary, nullable=True)
    thumb_content_type = Column(String(50), nullable=True)

    byte_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    title = Column(String(255), nullable=True)        # alt-tekst / sponsornaam
    link_url = Column(String(500), nullable=True)     # doorklik voor sponsorlogo
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=_now_utc, nullable=False)

    activity = relationship("Activity")

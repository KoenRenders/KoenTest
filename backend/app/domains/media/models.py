from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.kernel.tenancy import TenantMixin


def _now_utc():
    return datetime.now(timezone.utc)


class MediaAsset(TenantMixin, Base):
    """Binaire assetbibliotheek, opgeslagen in Postgres (BYTEA).

    Eén tabel voor meerdere soorten media:
    - ``kind="sponsor"``  → logo's die in de footer/homepage verschijnen
      (optioneel met ``link_url`` als doorklik).
    - ``kind="activity_photo"`` → foto's bij een activiteit (``activity_id``),
      getoond in het archief.
    - ``kind="activity_poster"`` → de poster van één activiteit (``activity_id``):
      afbeelding óf PDF; primeert op ``Activity.poster_url`` (#223).
    - ``kind="component_info"`` → info/reglement bij één onderdeel (``component_id``):
      afbeelding óf PDF; primeert op ``ActivitySubRegistration.info_url`` (#223).

    PDF's worden ongewijzigd bewaard (geen thumbnail); afbeeldingen verkleind +
    voorzien van een aparte thumbnail. Geen soft delete (bewust, zoals #166): bij
    vervangen/verwijderen verdwijnt de blob écht — geen ballast in DB/back-up.
    """

    __tablename__ = "media_assets"
    __table_args__ = {"schema": "media"}

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)  # sponsor | activity_photo | activity_poster | component_info
    activity_id = Column(
        Integer, nullable=True, index=True  # soft-ref naar activities.activities (§8, migr. 081)
    )
    component_id = Column(
        Integer,  # soft-ref naar activities.activity_sub_registrations (§8, migr. 081)
        nullable=True, index=True,
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

    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    # Soft-refs (§8): geen DB-FK meer; expliciete primaryjoin + foreign() zodat
    # de ORM-relaties blijven werken zonder constraint.
    activity = relationship(
        "Activity",
        primaryjoin="foreign(MediaAsset.activity_id) == Activity.id",
        viewonly=True,
    )
    component = relationship(
        "ActivitySubRegistration",
        primaryjoin="foreign(MediaAsset.component_id) == ActivitySubRegistration.id",
        viewonly=True,
    )


class MediaThumbsUp(TenantMixin, Base):
    """Eén duimpje van één bezoeker op één foto (#883).

    De uniciteit staat op ``(asset_id, visitor_token)`` in de DATABANK (migratie 113) en
    niet alleen in de service: twee snelle kliks kruisen elkaar, en dan controleren beide
    "bestaat er al een rij?" vóór er één geland is.

    ``visitor_token`` is een lang toevalsgetal uit een first-party cookie. Geen IP, geen
    vingerafdruk, geen naam — dat is een grens en geen tekortkoming: met een identifier
    die van de bezoeker afgeleid is, had je een volgmechanisme gebouwd voor een duimpje
    op een dorpsfoto.

    Er wordt nooit per bezoeker uitgelezen. Het token bestaat alleen om nog eens klikken
    het duimpje te kunnen laten weghalen.
    """

    __tablename__ = "media_thumbs_up"
    __table_args__ = (UniqueConstraint("asset_id", "visitor_token",
                                       name="uq_thumb_per_visitor"),
                      {"schema": "media"})

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("media.media_assets.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    visitor_token = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.tenancy import TenantMixin


def _now_utc():
    return datetime.now(timezone.utc)


class MediaKind(CodeEnum):
    """What a stored file is for (CR-12 phase 4).

    Was a free `String(20)` guarded by `ck_media_assets_kind_valid`, the CHECK
    that migrations 057, 131, 134 and 151 each rebuilt to add a kind — and that a
    kind added in code without a migration kept tripping over. The foreign key
    says the same, so the CHECK goes; a new kind is one row in the code list and
    one member here.
    """

    SPONSOR = "sponsor"
    ACTIVITY_PHOTO = "activity_photo"
    ACTIVITY_POSTER = "activity_poster"
    COMPONENT_INFO = "component_info"
    TENANT_LOGO = "tenant_logo"
    NEWSLETTER_FILE = "newsletter_file"
    DESIGN_IMAGE = "design_image"
    DESIGN_RENDER = "design_render"
    PAGE_IMAGE = "page_image"
    # CR-21 (the webshop): a product's picture and a product's document (a size
    # chart). Neither is a library kind — they are added on the article itself.
    PRODUCT_PHOTO = "product_photo"
    PRODUCT_DOCUMENT = "product_document"


def as_media_kind(value) -> "MediaKind | None":
    """A kind as it arrives — a code from a form or a URL, or a member — as a
    member; None when it is no kind. The one conversion at the border of the
    media domain, so that everything inside compares members."""
    if isinstance(value, MediaKind):
        return value
    try:
        return MediaKind(str(value or "").strip())
    except ValueError:
        return None


class MediaAsset(TenantMixin, Base):
    """Binaire assetbibliotheek, opgeslagen in Postgres (BYTEA).

    Eén tabel voor meerdere soorten media:
    - ``kind="sponsor"``  → logo's die op een affiche en/of in de footer mogen
      verschijnen (optioneel met ``link_url`` als doorklik). Of ze in de footer
      staan, beslist ``show_in_footer`` per logo (#1057); de Design Studio biedt
      élk actief sponsorlogo aan.
    - ``kind="activity_photo"`` → foto's bij een activiteit (``activity_id``),
      getoond in het archief.
    - ``kind="activity_poster"`` → de poster van één activiteit (``activity_id``):
      afbeelding óf PDF; primeert op ``Activity.poster_url`` (#223).
    - ``kind="component_info"`` → info/reglement bij één onderdeel (``component_id``):
      afbeelding óf PDF; primeert op ``ActivitySubRegistration.info_url`` (#223).
    - ``kind="design_image"`` → een beeld dat in een affiche gaat (CR-10, #1005),
      soft-gekoppeld aan een activiteit. Wordt net als elke upload heropend en
      opnieuw gecodeerd, tot de ene maat van 2 400 px die elke upload sinds #1473
      heeft.
    - ``kind="design_render"`` → de gerenderde affiche (PDF/PNG/SVG) van één
      versie. Komt van de Design Studio zelf en nooit van een upload.

    PDF's worden ongewijzigd bewaard (geen thumbnail); afbeeldingen verkleind +
    voorzien van een aparte thumbnail. Geen soft delete (bewust, zoals #166): bij
    vervangen/verwijderen verdwijnt de blob écht — geen ballast in DB/back-up.
    """

    __tablename__ = "media_assets"
    __table_args__ = {"schema": "media"}

    id = Column(Integer, primary_key=True, index=True)
    kind: Mapped[MediaKind] = mapped_column(
        EnumColumn(MediaKind, length=20),
        ForeignKey("media.media_kind_codes.code"),
        nullable=False,
        index=True,
    )
    activity_id = Column(
        Integer,
        nullable=True,
        index=True,  # soft-ref naar activities.activities (§8, migr. 081)
    )
    component_id = Column(
        Integer,  # soft-ref naar activities.activity_sub_registrations (§8, migr. 081)
        nullable=True,
        index=True,
    )

    # Volledig beeld (verkleind) + losse thumbnail.
    data = Column(LargeBinary, nullable=False)
    content_type = Column(String(50), nullable=False)
    thumbnail = Column(LargeBinary, nullable=True)
    thumb_content_type = Column(String(50), nullable=True)

    byte_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    title = Column(String(255), nullable=True)  # alt-tekst / sponsornaam
    link_url = Column(String(500), nullable=True)  # doorklik voor sponsorlogo
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    # #1057: alleen zinvol bij ``kind="sponsor"``. Tot dan las de footer dezelfde
    # vlag als de Design Studio, dus een logo dat je enkel op een affiche wilde,
    # stond onvermijdelijk ook onder élke publieke pagina. Deze schakelaar zit
    # ÓNDER `is_active` en niet ernaast: uit betekent nog steeds nergens.
    # Standaard aan, zodat een gewone sponsor geen extra handeling vraagt.
    show_in_footer = Column(Boolean, nullable=False, default=True)

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
    # #1470: the tags a picture carries. Read-only here: the links are written
    # through `service.tag_asset` / `untag_asset`, the one way in.
    tags = relationship(
        "MediaTag",
        secondary="media.asset_tags",
        viewonly=True,
        order_by="MediaTag.name",
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
    __table_args__ = (
        UniqueConstraint("asset_id", "visitor_token", name="uq_thumb_per_visitor"),
        {"schema": "media"},
    )

    id = Column(Integer, primary_key=True)
    asset_id = Column(
        Integer, ForeignKey("media.media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visitor_token = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MediaKindCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "media_kind_codes"
    __table_args__ = {"schema": "media"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MediaKindLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "media_kind_labels"
    __table_args__ = {"schema": "media"}

    code = Column(String(20), ForeignKey("media.media_kind_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class MediaTag(TenantMixin, Base):
    """A tag the board gives pictures, with an optional parent (CR-15 §C4.2, #1470).

    IPTC's keyword given a parent: a picture carries several, and the library
    shows them as a tree — *Logo's › Sponsors*. A picture appears under every tag
    it carries and under every tag above those. The activity's own photos are no
    tags: they are a branch derived from the activity.

    The key is `UNIQUE NULLS NOT DISTINCT (tenant_id, parent_id, name)` (migration
    186): two top-level tags of one name are refused too.
    """

    __tablename__ = "tags"
    __table_args__ = {"schema": "media"}

    id = Column(Integer, primary_key=True)
    parent_id = Column(
        Integer, ForeignKey("media.tags.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    name = Column(String(80), nullable=False)


class MediaAssetTag(Base):
    """One tag on one picture (#1470). The primary key refuses the same tag twice;
    deleting the picture takes its links along, deleting a tag in use is refused."""

    __tablename__ = "asset_tags"
    __table_args__ = {"schema": "media"}

    asset_id = Column(
        Integer, ForeignKey("media.media_assets.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id = Column(
        Integer, ForeignKey("media.tags.id", ondelete="RESTRICT"), primary_key=True, index=True
    )

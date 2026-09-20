"""Design Studio: designs, versions, renditions and image generations (CR-10 B5).

Schema ``designstudio``. Three shapes decide the tables:

- **A design stores inputs, not renders.** Template, duo, design text, image
  choices and focal points are columns; the rendered files hang off a
  *version*, made when the person marks the design final. "Add a line a week
  later" is an edit plus a new version.
- **Facts stay on the activity.** Title, dates, place, price, deadline and
  organisers are never copied here; a version keeps a *fingerprint* of the
  facts it used so the Design Studio can say "verouderd" when they change,
  computed on read — nothing in ``activities`` calls back into this schema.
- **No cross-schema foreign keys.** ``activity_id``, ``media_asset_id`` and
  ``ai_call_log_id`` are soft references (§8, ``test_schema_boundaries``).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


STATUS_DRAFT = "draft"
STATUS_FINAL = "final"

LAYOUT_PRINT = "print_a"
LAYOUT_FEED = "feed_portrait"
LAYOUTS = (LAYOUT_PRINT, LAYOUT_FEED)

VARIANT_PDF = "pdf"
VARIANT_PNG = "png"
VARIANT_JPEG = "jpeg"
VARIANT_SVG = "svg"
VARIANT_SVG_EDITED = "svg_edited"

#: State machine of one generated variant (CR-10 §3.12).
GEN_REQUESTED = "requested"
GEN_FETCHED = "fetched"
GEN_PICKED = "picked"
GEN_DISCARDED = "discarded"
GEN_REFUSED = "refused"
GEN_FAILED = "failed"
GENERATION_STATES = (GEN_REQUESTED, GEN_FETCHED, GEN_PICKED, GEN_DISCARDED, GEN_REFUSED, GEN_FAILED)

#: Presets are block choices within the one template "Affiche" (CR-10 §3.4).
#: Two, since Koen's HDEV round of 19 September 2026: the four of the CR
#: (Beeld, Tekstflyer, Illustratie, Reeks) were three times the same flow —
#: a picture is a picture, and a series is a dates grid that appears by
#: itself when there is more than one date.
#: Round 3 adds ``eenvoudig``: one big picture over the full width with a few
#: highlights under it — the Bowlen poster, half of what the unit makes.
PRESETS = ("beeld", "tekst", "eenvoudig")


class Design(TenantMixin, Base):
    __tablename__ = "designs"
    __table_args__ = {"schema": "designstudio"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, nullable=False, index=True)  # soft ref → activities.activities
    template_key = Column(String(40), nullable=False, default="affiche")
    template_version = Column(Integer, nullable=False, default=1)
    preset = Column(String(20), nullable=False, default="beeld")
    duo_code = Column(String(60), nullable=False)
    status = Column(String(10), nullable=False, default=STATUS_DRAFT)

    # Design text — never a copy of a fact. Round 3 (Koen, 19 September 2026)
    # cut it to three: the subtitle bar, the handwritten line and
    # "Omschrijving anders" — empty when the activity's own description is used.
    tagline = Column(String(90), nullable=True)
    subtitle = Column(String(120), nullable=True)
    explanation_md = Column(Text, nullable=True)

    # Images: soft refs to media.media_assets (kind design_image); the focal
    # point is a fraction of width/height.
    main_image_id = Column(Integer, nullable=True)
    main_focus_x = Column(Numeric(4, 3), nullable=False, default=0.5)
    main_focus_y = Column(Numeric(4, 3), nullable=False, default=0.5)
    inset_image_id = Column(Integer, nullable=True)
    third_image_id = Column(Integer, nullable=True)

    published_version_id = Column(Integer, nullable=True)  # → designstudio.design_versions (set after insert)
    created_by = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    highlights = relationship("DesignHighlight", back_populates="design",
                              cascade="all, delete-orphan", order_by="DesignHighlight.sort_order")
    logos = relationship("DesignLogo", back_populates="design",
                         cascade="all, delete-orphan", order_by="DesignLogo.sort_order")
    versions = relationship("DesignVersion", back_populates="design",
                            cascade="all, delete-orphan", order_by="DesignVersion.number")
    edited_svgs = relationship("DesignRendition", back_populates="design",
                               primaryjoin="and_(DesignRendition.design_id == Design.id, "
                                           "DesignRendition.version_id.is_(None))",
                               cascade="all, delete-orphan", viewonly=False)
    generations = relationship("ImageGeneration", back_populates="design",
                               cascade="all, delete-orphan", order_by="ImageGeneration.id")


class DesignHighlight(TenantMixin, Base):
    """One icon line ("Gezellig samen wandelen en praten"), at most four of
    the unit's own — date and place come by themselves (Koen, 20 Sep 2026)."""
    __tablename__ = "design_highlights"
    __table_args__ = (
        UniqueConstraint("design_id", "sort_order", name="uq_design_highlight_order"),
        CheckConstraint("sort_order >= 0 AND sort_order < 4", name="ck_design_highlight_order"),
        {"schema": "designstudio"},
    )

    id = Column(Integer, primary_key=True)
    design_id = Column(Integer, ForeignKey("designstudio.designs.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False)
    icon_code = Column(String(30), nullable=False)
    text = Column(String(90), nullable=False)
    emphasis = Column(Boolean, nullable=False, default=False)

    design = relationship("Design", back_populates="highlights")


class DesignLogo(TenantMixin, Base):
    """The logo strip: at most two sponsor assets (Mona; Mol when borrowing)."""
    __tablename__ = "design_logos"
    __table_args__ = (
        UniqueConstraint("design_id", "sort_order", name="uq_design_logo_order"),
        CheckConstraint("sort_order IN (0, 1)", name="ck_design_logo_order"),
        {"schema": "designstudio"},
    )

    id = Column(Integer, primary_key=True)
    design_id = Column(Integer, ForeignKey("designstudio.designs.id", ondelete="CASCADE"), nullable=False, index=True)
    media_asset_id = Column(Integer, nullable=False)  # soft ref → media.media_assets (kind sponsor)
    sort_order = Column(Integer, nullable=False)

    design = relationship("Design", back_populates="logos")


class DesignVersion(TenantMixin, Base):
    """One "definitief": numbered, with the facts fingerprint of that moment and
    every rendition. Publishing points ``Design.published_version_id`` here."""
    __tablename__ = "design_versions"
    __table_args__ = (
        UniqueConstraint("design_id", "number", name="uq_design_version_number"),
        {"schema": "designstudio"},
    )

    id = Column(Integer, primary_key=True)
    design_id = Column(Integer, ForeignKey("designstudio.designs.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    facts_fingerprint = Column(String(64), nullable=False)
    # The sponsor assets this version carried, for the yearly count (R11).
    sponsor_asset_ids = Column(String(120), nullable=False, default="")
    created_by = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    design = relationship("Design", back_populates="versions")
    renditions = relationship("DesignRendition", back_populates="version",
                              cascade="all, delete-orphan", order_by="DesignRendition.id")


class DesignRendition(TenantMixin, Base):
    """A rendered file of a version — or, with ``version_id`` empty, the
    hand-edited SVG uploaded on the draft for one layout."""
    __tablename__ = "design_renditions"
    __table_args__ = (
        CheckConstraint("layout_code IN ('print_a', 'feed_portrait')", name="ck_design_rendition_layout"),
        {"schema": "designstudio"},
    )

    id = Column(Integer, primary_key=True)
    design_id = Column(Integer, ForeignKey("designstudio.designs.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(Integer, ForeignKey("designstudio.design_versions.id", ondelete="CASCADE"), nullable=True, index=True)
    layout_code = Column(String(20), nullable=False)
    variant = Column(String(12), nullable=False)
    size_code = Column(String(20), nullable=False, default="")
    media_asset_id = Column(Integer, nullable=False)  # soft ref → media.media_assets (kind design_render)
    # For a hand-edited SVG: the fingerprint of the facts when it was uploaded,
    # so a later change can be named rather than silently re-rendered.
    facts_fingerprint = Column(String(64), nullable=True)
    min_effective_dpi = Column(Integer, nullable=True)
    rendered_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    design = relationship("Design", back_populates="edited_svgs", foreign_keys=[design_id],
                          overlaps="renditions,version")
    version = relationship("DesignVersion", back_populates="renditions", overlaps="design,edited_svgs")


class ImageGeneration(TenantMixin, Base):
    """One generated variant. The provider, prompt, cost and duration live in
    ``ai.ai_call_log`` (#978); this row holds what the design needs: which call,
    which seed, where the bytes went, and the state."""
    __tablename__ = "image_generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','fetched','picked','discarded','refused','failed')",
            name="ck_image_generation_status"),
        {"schema": "designstudio"},
    )

    id = Column(Integer, primary_key=True)
    design_id = Column(Integer, ForeignKey("designstudio.designs.id", ondelete="CASCADE"), nullable=False, index=True)
    request_key = Column(String(64), nullable=False, index=True)  # one per click: four rows share it
    ai_call_log_id = Column(Integer, nullable=True)  # soft ref → ai.ai_call_log
    seed = Column(Integer, nullable=True)
    scene = Column(Text, nullable=False, default="")        # what was asked, for "wat wil je anders?"
    style = Column(String(10), nullable=False, default="lijn")  # lijn | kleur
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    status = Column(String(12), nullable=False, default=GEN_REQUESTED)
    failure_reason = Column(Text, nullable=False, default="")
    media_asset_id = Column(Integer, nullable=True)  # the fetched variant (kind design_image)
    reserved_cents = Column(Integer, nullable=False, default=0)  # budget reservation until the cost is known
    requested_by = Column(String(255), nullable=False, default="")
    requested_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    design = relationship("Design", back_populates="generations")

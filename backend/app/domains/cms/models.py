from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base
from app.kernel.tenancy import TenantMixin


class CmsPage(TenantMixin, Base):
    __tablename__ = "cms_pages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="ix_cms_pages_tenant_slug"),
        {"schema": "cms"},
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
    # CR-17 phase 1 (#1671): the pre-CR-17 HTML, still what the site renders
    # and what the Trix editor saves (slice 1 writes it through
    # `update_page`, as ever); slice 3 makes it read-only and the contract
    # migration, two releases later, drops it (review C4, #1673).
    content = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    # Toon de (gepubliceerde) pagina in de hoofdnavigatie. False voor juridische/
    # blok-pagina's zoals 'privacy' en 'home-intro' (#152).
    show_in_nav = Column(Boolean, default=True, nullable=False)
    # CR-19 (#1477): this page is the tenant's home page; `/` renders it.
    # At most one per tenant (a partial unique index, migration 189).
    is_home = Column(Boolean, default=False, nullable=False)
    # #1569: the (published) page is listed in the site's footer, by sort order.
    # Where a page appears is set on the page; this replaced the tenant setting
    # `privacy_url`.
    show_in_footer = Column(Boolean, default=False, server_default=false(), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CmsPageTranslation(Base):
    """A page's title and documents in one language (CR-17 phase 1, #1671).

    One row per (page, language); phase 1 has exactly the tenant's language.
    `draft_json` is what the editor saves; `published_json` is what the site
    shows, written only by publishing (C4.3). The stored document is validated
    against `cms/schema.py`; JSONB because the draft/publish comparison and
    the phase-4 import read the structure, not the bytes.
    """

    __tablename__ = "page_translations"
    __table_args__ = ({"schema": "cms"},)

    page_id = Column(
        Integer,
        ForeignKey("cms.cms_pages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    language = Column(String(5), primary_key=True)
    title = Column(String(200), nullable=False)
    # The menu's word for the page, when it differs from the title (phase 6).
    menu_label = Column(String(80), nullable=True)
    draft_json = Column(JSONB, nullable=True)
    published_json = Column(JSONB, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(String(255), nullable=True)


class CmsPageHistory(Base):
    """Every published and restored version of a page's document (C4.3): one
    row per publish/restore action, so a wrong publish is one Terugzetten
    away — the same history whether the button or the API published."""

    __tablename__ = "cms_page_history"
    __table_args__ = ({"schema": "cms"},)

    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(
        Integer,
        ForeignKey("cms.cms_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    language = Column(String(5), nullable=False)
    # 'published' by Publiceren; 'restored' by Terugzetten (into the draft).
    action = Column(String(20), nullable=False)
    document = Column(JSONB, nullable=False)
    at = Column(DateTime(timezone=True), nullable=False)
    by = Column(String(255), nullable=True)

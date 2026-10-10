from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import validates

from app.database import Base
from app.kernel.tenancy import TenantMixin


class PageIncomplete(ValueError):
    """A page without a title or without a slug. Not an HTTPException: that
    belongs to the door, not to the rule."""


class CmsPage(TenantMixin, Base):
    __tablename__ = "cms_pages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="ix_cms_pages_tenant_slug"),
        {"schema": "cms"},
    )

    @validates("title", "slug")
    def _has_text(self, _field: str, value: object) -> object:
        """A page has a title and a slug (CR-13 §B9.1, one field each): `NOT NULL`
        lets an empty string and a string of spaces through, and a page without
        a title has no name in the list, one without a slug no address. Until
        phase 4d the screen that makes a page decided this; it holds for every
        writer now."""
        if not isinstance(value, str) or not value.strip():
            from app.i18n import _

            raise PageIncomplete(_("Titel en slug zijn verplicht."))
        return value

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
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

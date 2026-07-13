from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.database import Base
from app.kernel.tenancy import TenantMixin


class CmsPage(TenantMixin, Base):
    __tablename__ = "cms_pages"
    __table_args__ = {"schema": "cms"}

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    content = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    # Toon de (gepubliceerde) pagina in de hoofdnavigatie. False voor juridische/
    # blok-pagina's zoals 'privacy' en 'home-intro' (#152).
    show_in_nav = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

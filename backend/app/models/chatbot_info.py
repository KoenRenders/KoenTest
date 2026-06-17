"""ChatbotInfo (#206, #205) — alle tekst die naar de chatbot gaat, in één tabel.

Bewust losgekoppeld van de domeintabellen (geen kolommen op activity/media/cms).
Een rij verwijst via een nullable FK naar een media-asset (poster/reglement) of
een CMS-pagina, of naar niets (een vrijstaande 'eigen AI-context'-notitie).

Velden met elk hun eigen bedoeling:
- ``extracted_text``  — de machine-lezing (PDF-tekstlaag/OCR); enkel media-rijen.
- ``text_override``   — vervangt de basis (machine-lezing of pagina-inhoud).
- ``text_addition``   — vult de basis aan (extra info, ook voor losse notities).

``is_active=False`` → de rij gaat niet naar de bot (bv. een CMS-pagina uitzetten).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _now_utc():
    return datetime.now(timezone.utc)


class ChatbotInfo(Base):
    __tablename__ = "chatbot_info"

    id = Column(Integer, primary_key=True, index=True)
    media_asset_id = Column(
        Integer, ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    cms_page_id = Column(
        Integer, ForeignKey("cms_pages.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    title = Column(String(255), nullable=True)
    extracted_text = Column(Text, nullable=True)
    text_override = Column(Text, nullable=True)
    text_addition = Column(Text, nullable=True)
    extracted_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    media_asset = relationship("MediaAsset", foreign_keys=[media_asset_id])
    cms_page = relationship("CmsPage", foreign_keys=[cms_page_id])

    @property
    def effective_text(self) -> str:
        """De tekst zoals de bot ze krijgt: COALESCE(override, basis) + addition.

        De 'basis' is provider-afhankelijk: voor media = extracted_text; voor een
        CMS-rij wordt de live pagina-inhoud apart toegevoegd (zie context.py), dus
        hier telt enkel override. Voor een losse notitie is er geen basis."""
        base = self.text_override or self.extracted_text or ""
        parts = [p for p in (base, self.text_addition) if p]
        return "\n\n".join(parts).strip()

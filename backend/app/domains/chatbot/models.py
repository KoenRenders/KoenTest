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
    CHAR, Column, Integer, Numeric, String, Text, DateTime, Boolean, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.kernel.tenancy import TenantMixin


def _now_utc():
    return datetime.now(timezone.utc)


class ChatbotInfo(TenantMixin, Base):
    __tablename__ = "chatbot_info"
    __table_args__ = {"schema": "ai"}

    id = Column(Integer, primary_key=True, index=True)
    # Soft-ref naar public.media_assets (§8, migr. 084) — geen DB-FK meer.
    media_asset_id = Column(Integer, nullable=True, index=True)
    # Soft-ref naar cms.cms_pages (§8, migr. 083) — geen DB-FK meer.
    cms_page_id = Column(Integer, nullable=True, index=True)
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

    media_asset = relationship(
        "MediaAsset",
        primaryjoin="foreign(ChatbotInfo.media_asset_id) == MediaAsset.id",
        viewonly=True,
    )
    cms_page = relationship(
        "CmsPage",
        primaryjoin="foreign(ChatbotInfo.cms_page_id) == CmsPage.id",
        viewonly=True,
    )

    @property
    def effective_text(self) -> str:
        """De tekst zoals de bot ze krijgt: COALESCE(override, basis) + addition.

        De 'basis' is provider-afhankelijk: voor media = extracted_text; voor een
        CMS-rij wordt de live pagina-inhoud apart toegevoegd (zie context.py), dus
        hier telt enkel override. Voor een losse notitie is er geen basis."""
        base = self.text_override or self.extracted_text or ""
        parts = [p for p in (base, self.text_addition) if p]
        return "\n\n".join(parts).strip()


class AiCallLog(TenantMixin, Base):
    """One outbound call to a language model (CR-07 §6.4).

    Written at the provider seam, so both Raakje's — the public bot and the back
    office assistant — land in the same table without either knowing about it.
    Append-only: nothing in the application updates or deletes a row; retention is
    a cleanup job's business, not a caller's.

    ``payload`` is the verbatim message list as it went out. It is what the "wat
    zag Mistral" fold-out shows, which is why it is stored at all: an admin who
    cannot inspect the promise has only been told one.
    """

    __tablename__ = "ai_call_log"
    __table_args__ = {"schema": "ai"}

    id = Column(Integer, primary_key=True, index=True)
    surface = Column(String(32), nullable=False)
    capability = Column(String(32), nullable=False, default="")
    actor = Column(String(255), nullable=False, default="")
    model = Column(String(64), nullable=False, default="")
    payload = Column(Text, nullable=False, default="")
    tokens_prompt = Column(Integer, nullable=True)
    tokens_completion = Column(Integer, nullable=True)
    blocked_reason = Column(Text, nullable=False, default="")
    # #978: which provider and API, how it went, and what it cost. `cost_credits`
    # is the provider's own unit; `cost_amount` + `cost_currency` (ISO 4217) is
    # the same cost in money, so a sum never adds credits to euros.
    provider = Column(String(32), nullable=False, default="")
    endpoint = Column(String(128), nullable=False, default="")
    provider_request_id = Column(String(128), nullable=False, default="")
    status = Column(String(16), nullable=False, default="")
    duration_ms = Column(Integer, nullable=True)
    cost_credits = Column(Numeric(12, 4), nullable=True)
    cost_amount = Column(Numeric(12, 6), nullable=True)
    cost_currency = Column(CHAR(3), nullable=True)
    output_megapixels = Column(Numeric(6, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

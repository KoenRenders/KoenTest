"""Documenttekst-extractie (#206): media-asset (afbeelding/PDF) → tekst.

De tekst gaat naar een **``chatbot_info``-rij** die naar het media-asset verwijst
(``media_asset_id``) — alle chatbot-tekst staat los van de domeintabellen.

Strategie, in volgorde van kost:
1. **PDF mét tekstlaag** → rechtstreeks uitlezen met ``pypdf`` (gratis, exact).
2. **Scan-PDF zonder bruikbare tekstlaag, of een afbeelding** → **Mistral OCR**
   (zelfde ``MISTRAL_API_KEY`` als de chatbot, EU-verwerker).

Eénmalig per asset: ``update_media_extracted_text`` draait als achtergrond-taak
na een upload. Een nieuwe upload is een nieuw record (de oude wordt hard
verwijderd), dus geen hash-logica nodig: een record met al een ``extracted_text``
wordt overgeslagen, tenzij ``force=True`` (de 'Opnieuw lezen'-knop).

Bronwaarheid blijft de DB: datum/prijs/locatie komen uit de structuurvelden en
winnen altijd; de geëxtraheerde tekst vult enkel de zachte info aan.
"""
from __future__ import annotations

import base64
import io
import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.database import SessionLocal
from app.domains.media.models import MediaAsset
from app.domains.chatbot.api import ChatbotInfo

logger = logging.getLogger(__name__)

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"

# Soorten media waarvan we tekst extraheren (documenten, geen sponsor/foto).
EXTRACTABLE_KINDS = {"activity_poster", "component_info"}

# Opkuis-patronen (#240). Mistral OCR zet per gedetecteerde figuur een
# markdown-image-referentie in de tekst (``![img-0.jpeg](img-0.jpeg)``) — ruis
# voor de bot. PDF-tekstlagen brengen layout-witruimte mee. Beide weg vóór opslag.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_INLINE_WS = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _clean_extracted_text(text: str) -> str:
    """Normaliseer geëxtraheerde tekst vóór opslag: minder ruis, minder tokens.

    - verwijdert markdown-image-placeholders die Mistral OCR voor figuren genereert;
    - klapt runs van spaties/tabs/non-breaking spaces samen tot één spatie en
      stript elke regel rechts af;
    - klapt 3+ lege regels samen tot één lege regel.

    De bot krijgt zo enkel de echte tekst; opmaak-ruis kost geen tokens meer.
    """
    if not text:
        return ""
    text = _MD_IMAGE.sub("", text)
    text = "\n".join(_INLINE_WS.sub(" ", line).strip() for line in text.splitlines())
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _extract_pdf_text_layer(raw: bytes) -> str:
    """Lees de ingebedde tekstlaag van een PDF (gratis, geen AI). Lege string
    als er geen tekstlaag is (een scan) of bij een leesfout."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        parts = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(parts).strip()
    except Exception as exc:  # corrupte/rare PDF → val terug op OCR
        logger.warning("PDF-tekstlaag lezen mislukte: %s", exc)
        return ""


def _ocr_via_mistral(raw: bytes, content_type: str) -> str:
    """Lees een afbeelding of scan-PDF uit via de Mistral OCR-API."""
    b64 = base64.b64encode(raw).decode("ascii")
    data_uri = f"data:{content_type};base64,{b64}"
    if content_type == "application/pdf":
        document = {"type": "document_url", "document_url": data_uri}
    else:
        document = {"type": "image_url", "image_url": data_uri}

    response = httpx.post(
        MISTRAL_OCR_URL,
        headers={
            "Authorization": f"Bearer {settings.mistral_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": settings.ocr_model, "document": document},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    pages = data.get("pages") or []
    return "\n\n".join((p.get("markdown") or "").strip() for p in pages).strip()


def _select_text(raw: bytes, content_type: str) -> str:
    """Kies het goedkoopste pad dat tekst oplevert (nog ongekuist).

    PDF met bruikbare tekstlaag → die tekst. Anders (scan/afbeelding) → OCR, mits
    er een key is en OCR aanstaat. Zonder key valt OCR weg en geven we terug wat
    de tekstlaag (eventueel) opleverde.
    """
    pdf_text = ""
    if content_type == "application/pdf":
        pdf_text = _extract_pdf_text_layer(raw)
        if len(pdf_text) >= settings.pdf_text_min_chars:
            return pdf_text  # tekstlaag volstaat → gratis, geen OCR

    can_ocr = settings.ocr_enabled and bool(settings.mistral_api_key)
    if not can_ocr:
        return pdf_text  # niets meer te doen zonder key (leeg voor afbeeldingen)

    try:
        return _ocr_via_mistral(raw, content_type)
    except httpx.HTTPError as exc:
        logger.warning("Mistral OCR mislukte: %s", exc)
        return pdf_text  # val terug op wat we al hadden


def extract_document_text(raw: bytes, content_type: str) -> str:
    """Geëxtraheerde tekst, opgekuist voor de bot (#240).

    Kiest het goedkoopste pad (tekstlaag of OCR) en normaliseert het resultaat:
    OCR-image-placeholders weg, witruimte/lege regels samengeklapt.
    """
    return _clean_extracted_text(_select_text(raw, content_type))


def update_media_extracted_text(asset_id: int, db=None, force: bool = False) -> None:
    """Achtergrond-taak: extraheer de tekst van één media-asset naar chatbot_info.

    Zonder ``db`` (als achtergrond-taak) → eigen sessie. Vindt-of-maakt de
    ``chatbot_info``-rij voor dit asset en vult ``extracted_text``. Slaat over als
    die al gevuld is, tenzij ``force`` (de 'Opnieuw lezen'-knop). Raakt nooit
    ``text_override``/``text_addition`` aan — handmatige bewerkingen blijven staan.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
        if not asset or not asset.data:
            return
        if asset.kind not in EXTRACTABLE_KINDS:
            return

        row = (
            db.query(ChatbotInfo)
            .filter(ChatbotInfo.media_asset_id == asset_id)
            .first()
        )
        if row and row.extracted_text and not force:
            return  # al uitgelezen → niets te doen

        text = extract_document_text(asset.data, asset.content_type)
        if row is None:
            row = ChatbotInfo(media_asset_id=asset_id, title=asset.title)
            db.add(row)
        row.extracted_text = text or None
        row.extracted_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "chatbot_info.extracted_text bijgewerkt voor media-asset %s (%d tekens)",
            asset_id,
            len(text or ""),
        )
    except Exception as exc:  # nooit de upload-flow breken
        logger.warning("Tekstextractie voor media-asset %s mislukte: %s", asset_id, exc)
        db.rollback()
    finally:
        if own_session:
            db.close()

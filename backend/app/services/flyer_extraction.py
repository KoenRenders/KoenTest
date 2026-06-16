"""Flyertekst-extractie (#206): poster (afbeelding/PDF) → tekst.

Strategie, in volgorde van kost:
1. **PDF mét tekstlaag** → rechtstreeks uitlezen met ``pypdf`` (gratis, exact).
2. **Scan-PDF zonder bruikbare tekstlaag, of een afbeelding** → **Mistral OCR**
   (zelfde ``MISTRAL_API_KEY`` als de chatbot, EU-verwerker).

Eénmalig per poster: ``update_activity_flyer_text`` draait als achtergrond-taak
na een upload, slaat de tekst op en bewaart een hash van de posterbytes zodat een
ongewijzigde poster niet opnieuw (en niet tegen kost) wordt geëxtraheerd.

Bronwaarheid blijft de DB: datum/prijs/locatie komen uit de structuurvelden en
winnen altijd; ``flyer_text`` vult enkel de zachte info aan.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.activity import Activity
from app.models.asset import MediaAsset

logger = logging.getLogger(__name__)

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"


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


def extract_flyer_text(raw: bytes, content_type: str) -> str:
    """Kies het goedkoopste pad dat tekst oplevert.

    PDF met bruikbare tekstlaag → die tekst. Anders (scan/afbeelding) → OCR, mits
    er een key is en OCR aanstaat. Zonder key valt OCR weg en geven we terug wat
    de tekstlaag (eventueel) opleverde.
    """
    pdf_text = ""
    if content_type == "application/pdf":
        pdf_text = _extract_pdf_text_layer(raw)
        if len(pdf_text) >= settings.flyer_pdf_text_min_chars:
            return pdf_text  # tekstlaag volstaat → gratis, geen OCR

    can_ocr = settings.flyer_ocr_enabled and bool(settings.mistral_api_key)
    if not can_ocr:
        return pdf_text  # niets meer te doen zonder key (leeg voor afbeeldingen)

    try:
        return _ocr_via_mistral(raw, content_type)
    except httpx.HTTPError as exc:
        logger.warning("Mistral OCR mislukte: %s", exc)
        return pdf_text  # val terug op wat we al hadden


def update_activity_flyer_text(activity_id: int, db=None) -> None:
    """Achtergrond-taak: (her)extraheer de poster van één activiteit naar tekst.

    Als achtergrond-taak zonder ``db`` aangeroepen → eigen sessie (de request-
    sessie is dan al gesloten). Tests geven een sessie mee. Slaat over als de
    poster sinds de vorige extractie niet wijzigde (hash-vergelijking).
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            return
        asset = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.kind == "activity_poster",
                MediaAsset.activity_id == activity_id,
            )
            .first()
        )
        if not asset or not asset.data:
            return

        new_hash = hashlib.sha256(asset.data).hexdigest()
        if activity.flyer_text_hash == new_hash and activity.flyer_text:
            return  # poster ongewijzigd → niets te doen

        text = extract_flyer_text(asset.data, asset.content_type)
        activity.flyer_text = text or None
        activity.flyer_text_hash = new_hash
        db.commit()
        logger.info(
            "flyer_text bijgewerkt voor activiteit %s (%d tekens)",
            activity_id,
            len(text or ""),
        )
    except Exception as exc:  # nooit de upload-flow breken
        logger.warning("Flyertekst-extractie voor activiteit %s mislukte: %s", activity_id, exc)
        db.rollback()
    finally:
        if own_session:
            db.close()

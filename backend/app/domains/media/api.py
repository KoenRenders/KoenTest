"""Publieke facade van de media-capaciteit (fase 4c, #404).

Opslag-adapter: vandaag LargeBinary in Postgres (mee in de ene backup);
`MediaAsset.data`/`thumbnail` zijn de enige opslagvelden — een latere
object-storage-adapter wisselt achter deze facade.
"""
from app.domains.media.extraction import (  # noqa: F401
    EXTRACTABLE_KINDS,
    _extract_pdf_text_layer,
    extract_document_text,
    update_media_extracted_text,
)
from app.domains.media.models import MediaAsset  # noqa: F401

__all__ = ["MediaAsset", "EXTRACTABLE_KINDS", "extract_document_text", "update_media_extracted_text"]

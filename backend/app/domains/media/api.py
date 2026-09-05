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
from app.domains.media.router import (  # noqa: F401
    reextract_media_text,
    delete_activity_poster,
    delete_component_info,
    upload_activity_poster,
    upload_component_info,
)

from app.domains.media.service import (  # noqa: F401
    MediaFout,
    activity_photo_covers,
    delete_media,
    list_activity_photos,
    list_media,
    update_media,
    upload_media,
)
from app.domains.media.service import (  # noqa: F401
    VALID_KINDS,
    activity_ids_with_media,
)

__all__ = [
    "MediaFout", "VALID_KINDS", "activity_ids_with_media",
    "activity_photo_covers", "delete_media",
    "list_activity_photos", "list_media", "update_media", "upload_media",
    "MediaAsset", "EXTRACTABLE_KINDS", "extract_document_text",
    "delete_activity_poster", "delete_component_info",
    "update_media_extracted_text", "upload_activity_poster",
    "upload_component_info", "reextract_media_text",
]

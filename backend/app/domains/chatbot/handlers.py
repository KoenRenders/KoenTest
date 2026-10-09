"""What the chatbot does when another domain says something happened
(`docs/architecture.md` §3.2.1). Imported by `app.main`, which registers it."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.chatbot.info_service import keep_extracted_text
from app.kernel.contracts.media import DocumentTextExtracted
from app.kernel.events import subscribe


@subscribe(DocumentTextExtracted)
def keep_text_of_document(event: DocumentTextExtracted, db: Session) -> None:
    """Media read a document: its text goes into the AI context's own row for it
    (CR-13 phase 4d, #1251) — in the reading job's transaction."""
    keep_extracted_text(
        db,
        event.asset_id,
        title=event.title,
        text=event.text,
        extracted_at=event.extracted_at,
    )

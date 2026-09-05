"""AI-context van Raakje: documenten, CMS-pagina's en notities (#635 I).

Deze functies stonden in `info_router.py` en werden door `chatbot/ui.py`
rechtstreeks geïmporteerd — de JSON-router als servicelaag. De routes daar zijn nu
dunne schillen.

Wat hier woont zijn de regels die het scherm niet hoort te kennen: welke bronnen
er in de context zitten (affiches, onderdeel-info, CMS-pagina's, notities), hoe een
document zijn label krijgt, en dat een rij zonder ChatbotInfo als "standaard aan"
telt.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.activities.api import Activity, ActivitySubRegistration
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
# media wordt per functie geïmporteerd: `media/extraction.py` importeert op
# modulniveau `ChatbotInfo` uit chatbot.api, dat op zijn beurt deze module laadt.
# Een module-level import hier zou EXTRACTABLE_KINDS opvragen terwijl
# media/api.py nog aan het initialiseren is.
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate


def _row(ci: Optional[ChatbotInfo]) -> Optional[dict]:
    if ci is None:
        return None
    return {
        "id": ci.id,
        "title": ci.title,
        "extracted_text": ci.extracted_text,
        "text_override": ci.text_override,
        "text_addition": ci.text_addition,
        "is_active": ci.is_active,
        "sort_order": ci.sort_order,
        "extracted_at": ci.extracted_at,
        "effective_text": ci.effective_text,
    }


def _document_label(db: Session, asset: "MediaAsset") -> str:
    if asset.kind == "activity_poster" and asset.activity_id:
        a = db.query(Activity).filter(Activity.id == asset.activity_id).first()
        return f"{a.name} — poster" if a else "poster"
    if asset.kind == "component_info" and asset.component_id:
        c = (
            db.query(ActivitySubRegistration)
            .filter(ActivitySubRegistration.id == asset.component_id)
            .first()
        )
        if c:
            an = c.activity.name if c.activity else "activiteit"
            return f"{an} — {c.name} (info)"
        return "reglement"
    return asset.kind


def list_chatbot_info(db: Session, _admin=None):
    from app.domains.media.api import EXTRACTABLE_KINDS, MediaAsset

    rows_by_asset = {
        ci.media_asset_id: ci
        for ci in db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id.isnot(None)).all()
    }
    documents = []
    for asset in (
        db.query(MediaAsset)
        .filter(MediaAsset.kind.in_(EXTRACTABLE_KINDS))
        .order_by(MediaAsset.id)
        .all()
    ):
        documents.append({
            "asset_id": asset.id,
            "kind": asset.kind,
            "is_pdf": asset.content_type == "application/pdf",
            "label": _document_label(db, asset),
            "info": _row(rows_by_asset.get(asset.id)),
        })

    # CMS: gepubliceerde pagina's + hun (optionele) override-rij.
    rows_by_page = {
        ci.cms_page_id: ci
        for ci in db.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id.isnot(None)).all()
    }
    cms = []
    for page in (
        db.query(CmsPage)
        .filter(CmsPage.is_published == True)  # noqa: E712
        .order_by(CmsPage.sort_order, CmsPage.id)
        .all()
    ):
        cms.append({
            "page_id": page.id,
            "title": page.title,
            "slug": page.slug,
            "info": _row(rows_by_page.get(page.id)),
        })

    # Vrije notities.
    notes = [
        _row(ci)
        for ci in db.query(ChatbotInfo)
        .filter(ChatbotInfo.media_asset_id.is_(None), ChatbotInfo.cms_page_id.is_(None))
        .order_by(ChatbotInfo.sort_order, ChatbotInfo.id)
        .all()
    ]
    return {"documents": documents, "cms": cms, "notes": notes}


def _apply_edit(ci: ChatbotInfo, data: ChatbotInfoEdit) -> None:
    if data.title is not None:
        ci.title = data.title
    ci.text_override = data.text_override
    ci.text_addition = data.text_addition
    ci.is_active = data.is_active
    if data.sort_order is not None:
        ci.sort_order = data.sort_order


def create_note(db: Session, data: NoteCreate, _admin=None):
    ci = ChatbotInfo(
        title=data.title, text_addition=data.text_addition, is_active=data.is_active,
    )
    db.add(ci)
    db.commit()
    db.refresh(ci)
    return _row(ci)


def update_row(db: Session, row_id: int, data: ChatbotInfoEdit, _admin=None):
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if not ci:
        raise LookupError("Rij niet gevonden")
    _apply_edit(ci, data)
    db.commit()
    db.refresh(ci)
    return _row(ci)


def delete_row(db: Session, row_id: int, _admin=None):
    """Verwijder een rij. Voor een cms-/media-rij = terug naar standaardgedrag;
    voor een notitie = de notitie wissen. (De machine-extractie van een document
    komt vanzelf terug bij een volgende upload/'Opnieuw lezen'.)"""
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if ci:
        db.delete(ci)
        db.commit()


def toggle_row(db: Session, row_id: int) -> ChatbotInfo:
    """Zet een contextrij aan of uit.

    Stond als drie regels in het scherm, inclusief de query. Wat "aan of uit"
    betekent voor Raakje — of de rij mee de context in gaat — is domeinkennis.
    """
    rij = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if rij is None:
        raise LookupError("Rij niet gevonden")
    rij.is_active = not rij.is_active
    db.commit()
    return rij


def get_row(db: Session, row_id: int) -> ChatbotInfo:
    rij = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if rij is None:
        raise LookupError("Rij niet gevonden")
    return rij

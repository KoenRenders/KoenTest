"""Admin-beheer van chatbot_info (#235) — de CRUD achter het 'Raakje — AI-context'-scherm.

Toont en beheert alles wat naar de chatbot gaat, in drie groepen:
- **documenten**: poster/reglement-assets met hun (machine) extracted_text +
  bewerkbare override/aanvulling;
- **cms**: gepubliceerde pagina's (opt-out: standaard mee, hier uit te zetten of te
  overschrijven);
- **notities**: vrijstaande 'eigen AI-context'.

Alle endpoints zijn admin-gated. Het effectieve gedrag zit in
``app/domains/chatbot/context.py`` en ``tools.py``.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domains.auth.api import get_current_admin
from app.database import get_db
from app.domains.activities.api import Activity
from app.domains.activities.api import ActivitySubRegistration
from app.models.asset import MediaAsset
from app.models.chatbot_info import ChatbotInfo
from app.domains.cms.api import CmsPage
from app.domains.auth.api import User
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate
from app.services.media_extraction import EXTRACTABLE_KINDS

router = APIRouter(tags=["chatbot-info"], dependencies=[Depends(get_current_admin)])


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


def _document_label(db: Session, asset: MediaAsset) -> str:
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


@router.get("/admin/chatbot-info")
def list_chatbot_info(db: Session = Depends(get_db), _admin: User = Depends(get_current_admin)):
    # Documenten: alle extraheerbare assets + hun chatbot_info-rij.
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


@router.put("/admin/chatbot-info/media/{asset_id}")
def upsert_media_info(
    asset_id: int, data: ChatbotInfoEdit,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset or asset.kind not in EXTRACTABLE_KINDS:
        raise HTTPException(status_code=404, detail="Media-asset niet gevonden")
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).first()
    if ci is None:
        ci = ChatbotInfo(media_asset_id=asset_id)
        db.add(ci)
    _apply_edit(ci, data)  # extracted_text blijft (machine); enkel override/addition
    db.commit()
    db.refresh(ci)
    return _row(ci)


@router.put("/admin/chatbot-info/cms/{page_id}")
def upsert_cms_info(
    page_id: int, data: ChatbotInfoEdit,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Pagina niet gevonden")
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id == page_id).first()
    if ci is None:
        ci = ChatbotInfo(cms_page_id=page_id)
        db.add(ci)
    _apply_edit(ci, data)
    db.commit()
    db.refresh(ci)
    return _row(ci)


@router.post("/admin/chatbot-info/notes", status_code=201)
def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    ci = ChatbotInfo(
        title=data.title, text_addition=data.text_addition, is_active=data.is_active,
    )
    db.add(ci)
    db.commit()
    db.refresh(ci)
    return _row(ci)


@router.patch("/admin/chatbot-info/{row_id}")
def update_row(
    row_id: int, data: ChatbotInfoEdit,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if not ci:
        raise HTTPException(status_code=404, detail="Rij niet gevonden")
    _apply_edit(ci, data)
    db.commit()
    db.refresh(ci)
    return _row(ci)


@router.delete("/admin/chatbot-info/{row_id}", status_code=204)
def delete_row(
    row_id: int,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    """Verwijder een rij. Voor een cms-/media-rij = terug naar standaardgedrag;
    voor een notitie = de notitie wissen. (De machine-extractie van een document
    komt vanzelf terug bij een volgende upload/'Opnieuw lezen'.)"""
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if ci:
        db.delete(ci)
        db.commit()

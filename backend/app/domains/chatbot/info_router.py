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
from app.domains.media.api import MediaAsset
from app.domains.chatbot import info_service as _service
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
from app.domains.auth.api import User
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate
from app.domains.media.api import EXTRACTABLE_KINDS
from app.i18n import _

router = APIRouter(tags=["chatbot-info"], dependencies=[Depends(get_current_admin)])






@router.get("/admin/chatbot-info")
def list_chatbot_info(db: Session = Depends(get_db),
                      _admin: User = Depends(get_current_admin)):
    return _service.list_chatbot_info(db)




@router.put("/admin/chatbot-info/media/{asset_id}")
def upsert_media_info(
    asset_id: int, data: ChatbotInfoEdit,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset or asset.kind not in EXTRACTABLE_KINDS:
        raise HTTPException(status_code=404, detail=_("Media-asset niet gevonden"))
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).first()
    if ci is None:
        ci = ChatbotInfo(media_asset_id=asset_id)
        db.add(ci)
    _service._apply_edit(ci, data)  # extracted_text blijft (machine); enkel override/addition
    db.commit()
    db.refresh(ci)
    return _service._row(ci)


@router.put("/admin/chatbot-info/cms/{page_id}")
def upsert_cms_info(
    page_id: int, data: ChatbotInfoEdit,
    db: Session = Depends(get_db), _admin: User = Depends(get_current_admin),
):
    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    ci = db.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id == page_id).first()
    if ci is None:
        ci = ChatbotInfo(cms_page_id=page_id)
        db.add(ci)
    _service._apply_edit(ci, data)
    db.commit()
    db.refresh(ci)
    return _service._row(ci)


@router.post("/admin/chatbot-info/notes", status_code=201)
def create_note(data: NoteCreate, db: Session = Depends(get_db),
                _admin: User = Depends(get_current_admin)):
    return _service.create_note(db, data)


@router.patch("/admin/chatbot-info/{row_id}")
def update_row(row_id: int, data: ChatbotInfoEdit,
               db: Session = Depends(get_db),
               _admin: User = Depends(get_current_admin)):
    try:
        return _service.update_row(db, row_id, data)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))


@router.delete("/admin/chatbot-info/{row_id}", status_code=204)
def delete_row(row_id: int, db: Session = Depends(get_db),
               _admin: User = Depends(get_current_admin)):
    try:
        _service.delete_row(db, row_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))
    return None

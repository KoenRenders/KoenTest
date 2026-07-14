"""Server-rendered Raakje (chat) en ai-context (fase 4c-2, #404 — §21).

- /raakje: publiek vraag-antwoordscherm (htmx-fragment i.p.v. de React-widget;
  antwoord komt volledig server-side terug — geen SSE nodig, §20.5-lijn).
- /admin/ai-context: beheer van wat Raakje weet — notities toevoegen/wissen,
  tekst-override en aan/uit per bron. Hergebruikt de bestaande admin-API.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, User, csrf_token_for, require_admin_ui, require_csrf,
)
from app.limiter import chat_limiter
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)


def _admin_user(db: Session, email: str) -> User:
    user = (db.query(User)
            .filter(func.lower(User.email) == email.lower(), User.is_active == True)
            .first())
    if user is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    return user


# ── Publiek: Raakje ────────────────────────────────────────────────────────────

@router.get("/raakje", response_class=HTMLResponse)
def raakje_page(request: Request):
    return templates.TemplateResponse(request, "raakje.html",
                                      {"enabled": settings.chat_enabled})


@router.post("/raakje/vraag", response_class=HTMLResponse,
             dependencies=[Depends(chat_limiter)])
def raakje_vraag(request: Request, db: Session = Depends(get_db),
                 vraag: str = Form("")):
    from app.domains.chatbot.context import build_system_prompt
    from app.domains.chatbot.providers import get_provider
    from app.domains.chatbot.router import chat_char_budget
    from app.domains.chatbot.service import run_chat

    vraag = vraag.strip()
    if not settings.chat_enabled:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    if not vraag:
        return templates.TemplateResponse(request, "_raakje_antwoord.html",
                                          {"vraag": vraag, "antwoord": None,
                                           "error": _("Typ eerst een vraag.")})
    chat_char_budget.charge(request, len(vraag))
    messages = [{"role": "system", "content": build_system_prompt(db)},
                {"role": "user", "content": vraag}]
    try:
        antwoord = run_chat(db, messages, get_provider(),
                            max_rounds=settings.chat_max_tool_rounds)
    except Exception:
        return templates.TemplateResponse(request, "_raakje_antwoord.html",
                                          {"vraag": vraag, "antwoord": None,
                                           "error": _("Sorry, er ging iets mis. Probeer later opnieuw.")})
    return templates.TemplateResponse(request, "_raakje_antwoord.html",
                                      {"vraag": vraag, "antwoord": antwoord,
                                       "error": None})


# ── Admin: ai-context ──────────────────────────────────────────────────────────

def _context_ctx(request: Request, db: Session, email: str) -> dict:
    from app.domains.chatbot.info_router import list_chatbot_info

    data = list_chatbot_info(db=db, _admin=_admin_user(db, email))
    return {
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        **data,
    }


@router.get("/admin/ai-context", response_class=HTMLResponse)
def ai_context_page(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "ai_context.html", {
        "nav_items": admin_nav("/admin/ai-context"), **_context_ctx(request, db, email)})


@router.get("/admin/ai-context/lijst", response_class=HTMLResponse)
def ai_context_lijst(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "_ai_context_lijst.html",
                                      _context_ctx(request, db, email))


@router.post("/admin/ai-context/notities", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def notitie_toevoegen(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      title: str = Form(""), text_addition: str = Form("")):
    from app.domains.chatbot.info_router import create_note
    from app.schemas.chatbot_info import NoteCreate

    if not title.strip() or not text_addition.strip():
        raise HTTPException(status_code=400, detail=_("Titel en tekst zijn verplicht."))
    create_note(NoteCreate(title=title.strip(), text_addition=text_addition.strip(),
                           is_active=True),
                db=db, _admin=_admin_user(db, email))
    return templates.TemplateResponse(request, "_ai_context_lijst.html",
                                      _context_ctx(request, db, email))


@router.post("/admin/ai-context/{row_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def rij_verwijderen(row_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    from app.domains.chatbot.info_router import delete_row

    delete_row(row_id, db=db, _admin=_admin_user(db, email))
    return templates.TemplateResponse(request, "_ai_context_lijst.html",
                                      _context_ctx(request, db, email))


@router.post("/admin/ai-context/{row_id}/toggle", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def rij_toggle(row_id: int, request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    from app.domains.chatbot.models import ChatbotInfo

    ci = db.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first()
    if ci is None:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))
    ci.is_active = not ci.is_active
    db.commit()
    return templates.TemplateResponse(request, "_ai_context_lijst.html",
                                      _context_ctx(request, db, email))

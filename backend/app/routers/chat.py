"""Publieke chatbot-endpoint: POST /api/v1/chat (SSE).

De doorman (HTTP-laag): rate-limiet + dagelijks tekenbudget + vorm-validatie via
het Pydantic-schema. De business-loop (provider + tools) zit in de service; de
security-grens in de tools. De API-sleutel blijft serverside.

Antwoord als Server-Sent Events zodat de widget het antwoord 'live' kan tonen.
We draaien de tool-loop af en streamen daarna het eindantwoord in stukjes
(typ-effect), gevolgd door een afsluitend 'done'-event.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.domains.chatbot.context import build_system_prompt
from app.domains.chatbot.providers import get_provider
from app.domains.chatbot.service import run_chat
from app.limiter import DailyCharBudget, chat_limiter
from app.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Dagelijks tekenbudget per IP (config-gestuurd). Eén gedeelde instantie zodat de
# teller over requests heen blijft staan.
chat_char_budget = DailyCharBudget(settings.chat_daily_char_budget)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat", dependencies=[Depends(chat_limiter)])
def chat(
    data: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    # Hoofdschakelaar (CHAT_ENABLED in .env). Uit → endpoint bestaat 'niet'.
    if not settings.chat_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden")

    # Dagbudget: tel enkel wat de bezoeker zelf typte (user-berichten).
    typed = sum(len(m.content) for m in data.messages if m.role == "user")
    chat_char_budget.charge(request, typed)

    # System-prompt + geschiedenis samenstellen.
    messages = [{"role": "system", "content": build_system_prompt(db)}]
    messages += [{"role": m.role, "content": m.content} for m in data.messages]

    provider = get_provider()

    def event_stream():
        try:
            answer = run_chat(
                db, messages, provider, max_rounds=settings.chat_max_tool_rounds
            )
        except Exception as exc:
            logger.warning("Chat-afhandeling mislukt: %s", exc)
            yield _sse(
                {
                    "delta": "Sorry, er ging iets mis. Probeer het later opnieuw.",
                }
            )
            yield _sse({"done": True})
            return

        # Eindantwoord in woord-stukjes streamen voor een typ-effect.
        for word in answer.split(" "):
            yield _sse({"delta": word + " "})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

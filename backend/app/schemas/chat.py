"""Pydantic-schema voor /api/v1/chat — vorm-validatie (de doorman).

Caps de berichtlengte en de geschiedenis hier (vorm), zodat 'pagina-droppen'
al op de HTTP-laag een nette 422 geeft. De inhoudelijke vangrails (dagbudget,
rate) zitten in de router via de limiters; de business-loop in de service.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config import settings


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _cap_length(cls, v: str) -> str:
        if len(v) > settings.chat_max_input_chars:
            raise ValueError(
                f"Bericht is te lang (max {settings.chat_max_input_chars} tekens). "
                "Stel je vraag korter."
            )
        return v


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def _validate_history(cls, msgs: list[ChatMessage]) -> list[ChatMessage]:
        if len(msgs) > settings.chat_max_history_messages:
            raise ValueError(
                f"Gesprek is te lang (max {settings.chat_max_history_messages} "
                "berichten). Begin een nieuw gesprek."
            )
        if msgs[-1].role != "user":
            raise ValueError("Het laatste bericht moet van de bezoeker komen.")
        return msgs

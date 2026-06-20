"""MistralProvider — de productie-/POC-provider (Mistral Small 4, EU).

Praat rechtstreeks met de Mistral chat-completions REST-API via ``httpx`` (al
in requirements; zelfde patroon als de Mollie-provider). Geen extra dependency,
dus ``check_imports`` blijft groen ook zonder de ``mistralai``-SDK.

De API-sleutel komt serverside uit de config (nooit naar de browser). Mistral is
OpenAI-compatibel, dus de berichten-/tool-dicts gaan ongewijzigd door.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.config import settings
from .base import AssistantMessage, LLMProvider, ToolCall

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


class MistralProvider(LLMProvider):
    name = "mistral"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> AssistantMessage:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,  # feitelijk, weinig fantasie
        }
        if tools:
            payload["tools"] = tools
            # 'any' = forceer een tool-aanroep (grounding, #anti-hallucinatie);
            # standaard 'auto' = het model beslist.
            payload["tool_choice"] = tool_choice or "auto"

        try:
            response = httpx.post(
                MISTRAL_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Mistral-aanroep mislukt: %s", exc)
            raise

        data = response.json()
        message = data["choices"][0]["message"]

        tool_calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=raw.get("id", ""), name=fn.get("name", ""), arguments=args)
            )

        return AssistantMessage(content=message.get("content"), tool_calls=tool_calls)


def build_mistral_provider() -> MistralProvider:
    """Construeer de provider uit de config. Roept alleen aan wie zeker is dat
    er een sleutel is (zie ``factory.get_provider``)."""
    assert settings.mistral_api_key is not None, "mistral_api_key ontbreekt"
    return MistralProvider(
        api_key=settings.mistral_api_key,
        model=settings.chat_model,
    )

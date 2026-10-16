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

from .base import AssistantMessage, LLMProvider, OcrResult, ToolCall

logger = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"


class MistralProvider(LLMProvider):
    name = "mistral"
    endpoint = "chat.completions"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        #: Read by the seam log — which model answered is half of what a cost
        #: question asks.
        self.model = model

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        json_answer: bool = False,
    ) -> AssistantMessage:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,  # feitelijk, weinig fantasie
        }
        if json_answer:
            # #1968: Mistral's JSON mode — the answer is one JSON object. The
            # prompt still says so in words; the mode asks for a prompt that does.
            payload["response_format"] = {"type": "json_object"}
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

        raw_usage = data.get("usage") or {}
        usage = {
            "prompt": int(raw_usage.get("prompt_tokens") or 0),
            "completion": int(raw_usage.get("completion_tokens") or 0),
        }

        return AssistantMessage(
            content=message.get("content"),
            tool_calls=tool_calls,
            usage=usage,
            request_id=str(data.get("id") or ""),
        )

    def ocr(self, document: bytes, content_type: str) -> OcrResult:
        """Read an image or a scanned PDF with Mistral's OCR (moved here from the
        document reader, CR-33 C4.6: the key and the address stay in this folder)."""
        import base64

        data_uri = f"data:{content_type};base64,{base64.b64encode(document).decode('ascii')}"
        if content_type == "application/pdf":
            source = {"type": "document_url", "document_url": data_uri}
        else:
            source = {"type": "image_url", "image_url": data_uri}
        response = httpx.post(
            MISTRAL_OCR_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.ocr_model, "document": source},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        pages = data.get("pages") or []
        return OcrResult(
            text="\n\n".join((p.get("markdown") or "").strip() for p in pages).strip(),
            request_id=str(data.get("id") or ""),
            pages_charged=(data.get("usage_info") or {}).get("pages_processed"),
        )


def build_mistral_provider(model: str = "") -> MistralProvider:
    """Construeer de provider uit de config. Roept alleen aan wie zeker is dat
    er een sleutel is (zie ``factory.get_provider``)."""
    assert settings.mistral_api_key is not None, "mistral_api_key ontbreekt"
    return MistralProvider(
        api_key=settings.mistral_api_key,
        model=model or settings.chat_model,
    )

"""Provider-naad: het minimale contract dat elke LLM-leverancier moet leveren.

Bewust dun gehouden. We praten in OpenAI-/Mistral-compatibele berichten-dicts
(``{"role": ..., "content": ...}`` en tool-resultaten met ``tool_call_id``),
zodat een nieuwe provider enkel ``complete()`` hoeft te implementeren.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """Eén door het model gevraagde tool-aanroep."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantMessage:
    """Het antwoord van het model op één ``complete()``-beurt.

    Ofwel ``content`` (een eindantwoord), ofwel ``tool_calls`` (het model wil
    eerst data ophalen). Beide kunnen voorkomen; de chat-loop handelt eerst de
    tool-aanroepen af en vraagt dan opnieuw om een eindantwoord.
    """

    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    """De enige naad tussen de chatbot en een concrete LLM-leverancier."""

    #: Korte, herkenbare naam voor logging en de privacyverklaring.
    name: str = "base"

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> AssistantMessage:
        """Vraag het model om één antwoord op de gespreksgeschiedenis.

        ``messages`` zijn OpenAI-/Mistral-compatibele dicts (system/user/
        assistant/tool). ``tools`` is de lijst function-tool-specs of None.
        ``tool_choice`` forceert het tool-gedrag ('any' = verplicht een tool
        kiezen, 'auto' = model beslist); None → 'auto' wanneer er tools zijn.
        """
        raise NotImplementedError

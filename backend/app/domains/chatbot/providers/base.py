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
    #: Token usage the provider reported, ``{"prompt": n, "completion": n}``.
    #: Mistral returns it with every response and it used to be dropped on the
    #: floor; the seam logs it now, so one query answers what the AI costs this
    #: month — for both surfaces at once (CR-07 §6.4).
    usage: dict[str, int] = field(default_factory=dict)
    #: The provider's own id for this response (#978), so a row in the log can
    #: be matched to a line on the provider's invoice.
    request_id: str = ""


@dataclass
class OcrResult:
    """What the provider read from a document: the text, the provider's own id for
    the call, and the pages it charged for when it says (#1212)."""

    text: str
    request_id: str = ""
    pages_charged: Optional[int] = None


class LLMProvider(ABC):
    """De enige naad tussen de chatbot en een concrete LLM-leverancier."""

    #: Korte, herkenbare naam voor logging en de privacyverklaring.
    name: str = "base"
    #: The API this provider calls, for the log (#978), e.g. "chat.completions".
    endpoint: str = ""

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        json_answer: bool = False,
    ) -> AssistantMessage:
        """Vraag het model om één antwoord op de gespreksgeschiedenis.

        ``messages`` zijn OpenAI-/Mistral-compatibele dicts (system/user/
        assistant/tool). ``tools`` is de lijst function-tool-specs of None.
        ``tool_choice`` forceert het tool-gedrag ('any' = verplicht een tool
        kiezen, 'auto' = model beslist); None → 'auto' wanneer er tools zijn.

        ``json_answer`` (#1968) asks for the answer as one JSON object, through
        the provider's own setting where it has one — the one place a fixed
        shape is asked for; the callers reach it through
        ``chatbot.answers.json_answer``. Asked only on a call without tools:
        whether a provider takes both in one call is not measured.
        """
        raise NotImplementedError

    def ocr(self, document: bytes, content_type: str) -> OcrResult:
        """Read the text of an image or a scan (CR-33 C4.6).

        The one door for the document reader: a provider that cannot read one
        says so. The document is free text from a person's own file — a poster —
        so it carries no attribute and the classification does not apply; the
        text that comes back keeps whatever the document held, contact data
        included (Koen, 15 October 2026), and stays free text under the pattern
        guard wherever it enters a prompt."""
        raise NotImplementedError(f"{self.name} cannot read documents")

"""MockProvider — afhankelijkheidsvrije fallback (CI/lokaal, geen key/kost).

Geen netwerk, geen API-sleutel. Deterministisch zodat tests het volledige
tool-loop-pad kunnen aflopen zonder een echte LLM: vraagt de bezoeker naar
activiteiten, dan vraagt de mock één keer de ``get_upcoming_activities``-tool
aan; zodra er een tool-resultaat in het gesprek zit, geeft hij een eindantwoord.
"""
from __future__ import annotations

from typing import Any, Optional

from .base import AssistantMessage, LLMProvider, ToolCall

_ACTIVITY_TRIGGERS = ("activiteit", "agenda", "wanneer", "evenement", "kalender")


class MockProvider(LLMProvider):
    name = "mock"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AssistantMessage:
        # Is er al een tool-resultaat? Dan ronden we af met een eindantwoord.
        if any(m.get("role") == "tool" for m in messages):
            return AssistantMessage(
                content=(
                    "Dit is een testantwoord van de mock-provider, gebaseerd op "
                    "de opgehaalde gegevens. Zet een MISTRAL_API_KEY om de echte "
                    "bot te activeren."
                )
            )

        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        text = (last_user or "").lower()

        tool_names = {t.get("function", {}).get("name") for t in (tools or [])}
        if "get_upcoming_activities" in tool_names and any(
            trigger in text for trigger in _ACTIVITY_TRIGGERS
        ):
            return AssistantMessage(
                tool_calls=[
                    ToolCall(id="mock-call-1", name="get_upcoming_activities", arguments={})
                ]
            )

        return AssistantMessage(
            content=(
                "Hallo, ik ben Raakje (mock-modus). Ik kan je informeren over "
                "Raak Millegem, onze activiteiten en het lidmaatschap, of je "
                "vraag/idee doorgeven. Zet een MISTRAL_API_KEY om de echte bot "
                "te activeren."
            )
        )

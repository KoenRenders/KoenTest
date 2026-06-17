"""Chat-orkestratie: de tool-loop tussen provider en tools.

Eén beurt = het model bevragen, eventuele tool-aanroepen uitvoeren, en opnieuw
bevragen tot er een eindantwoord is. Het aantal rondes is begrensd (kosten- en
lus-vangrail). De DB-toegang loopt uitsluitend via ``execute_tool`` — de
security-grens.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from .providers.base import LLMProvider
from .tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)

_FALLBACK = (
    "Sorry, dat lukt me even niet. Wil je het anders formuleren, of zal ik je "
    "vraag doorgeven?"
)

# Trefwoorden die wijzen op een vraag waarvoor de bot data móét ophalen
# (anti-hallucinatie, laag 3): dan forceren we een tool-aanroep i.p.v. het aan
# het model over te laten. Brede match; vals-positief = hooguit een extra (gratis)
# tool-aanroep, vals-negatief valt terug op de strikte system-prompt.
_ACTIVITY_HINTS = (
    "activiteit", "agenda", "evenement", "programma", "wanneer", "datum",
    "kinder", "gezin", "deelnem", "inschrijv", "te doen", "uitstap", "feest",
    "voorbije", "volgende", "eerstvolgende",
)


def _wants_activity_data(messages: list[dict[str, Any]]) -> bool:
    """Lijkt de laatste bezoekersvraag om activiteiten-/agendagegevens te vragen?"""
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    if not last_user:
        return False
    text = (last_user.get("content") or "").lower()
    return any(hint in text for hint in _ACTIVITY_HINTS)


def _assistant_dict(reply) -> dict[str, Any]:
    """Zet een AssistantMessage met tool-calls om naar het wire-formaat dat de
    provider bij de volgende beurt terugverwacht."""
    return {
        "role": "assistant",
        "content": reply.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in reply.tool_calls
        ],
    }


def run_chat(
    db: Session,
    messages: list[dict[str, Any]],
    provider: LLMProvider,
    max_rounds: int = 4,
) -> str:
    """Loop het gesprek af tot een eindantwoord en geef de antwoordtekst terug.

    ``messages`` bevat al de system-prompt + de geschiedenis (laatste = user).
    """
    force_first = _wants_activity_data(messages)
    for i in range(max_rounds):
        # Eerste ronde van een activiteiten-/agendavraag: dwing een tool-aanroep af,
        # zodat de bot grondt op echte data i.p.v. te verzinnen (laag 3).
        tool_choice = "any" if (i == 0 and force_first) else None
        reply = provider.complete(messages, tools=TOOL_SPECS, tool_choice=tool_choice)
        if not reply.tool_calls:
            return (reply.content or "").strip() or _FALLBACK

        messages.append(_assistant_dict(reply))
        for tc in reply.tool_calls:
            result = execute_tool(tc.name, tc.arguments, db)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                }
            )

    # Rondes op: forceer één eindantwoord zonder tools.
    try:
        final = provider.complete(messages, tools=None)
        return (final.content or "").strip() or _FALLBACK
    except Exception as exc:  # pragma: no cover - defensief
        logger.warning("Eindantwoord na max rondes mislukte: %s", exc)
        return _FALLBACK

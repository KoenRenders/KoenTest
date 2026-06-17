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
    for _ in range(max_rounds):
        reply = provider.complete(messages, tools=TOOL_SPECS)
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

"""MockProvider — afhankelijkheidsvrije fallback (CI/lokaal, geen key/kost).

Geen netwerk, geen API-sleutel, geen taalbegrip. Deterministisch zodat tests
het volledige tool-loop-pad kunnen aflopen zonder een echte LLM.

Data-bewust: vraagt de bezoeker naar activiteiten, dan vraagt de mock één keer
de ``get_upcoming_activities``-tool aan; zodra er een tool-resultaat binnen is,
formatteert hij de **echte** opgehaalde gegevens via een vast sjabloon. Zo toont
optie A (zonder key) je werkelijke data, alleen zonder vrije conversatie.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .base import AssistantMessage, LLMProvider, ToolCall

_ACTIVITY_TRIGGERS = ("activiteit", "agenda", "wanneer", "evenement", "kalender")

_MOCK_SUFFIX = "\n\n_(testmodus — zet een MISTRAL_API_KEY voor de echte bot.)_"


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    parts = iso.split("-")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else iso


def _first_date(activity: dict[str, Any]) -> str:
    dates = activity.get("dates") or []
    return _fmt_date(dates[0]["start_date"]) if dates else "datum nog te bepalen"


def _format_activities(data: dict[str, Any]) -> str:
    activities = data.get("activities") or []
    if not activities:
        return "Er staan momenteel geen komende activiteiten gepland."
    lines = ["Dit zijn de komende activiteiten:"]
    for a in activities:
        bits = [f"**{a.get('name')}** — {_first_date(a)}"]
        if a.get("location"):
            bits.append(f"locatie: {a['location']}")
        if a.get("price_from"):
            bits.append(f"vanaf €{a['price_from']}")
        if a.get("members_only"):
            bits.append("enkel voor leden")
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines)


def _format_detail(data: dict[str, Any]) -> str:
    if data.get("error"):
        return data["error"]
    lines = [f"**{data.get('name')}** — {_first_date(data)}"]
    if data.get("location"):
        lines.append(f"Locatie: {data['location']}")
    if data.get("price_from"):
        lines.append(f"Prijs vanaf: €{data['price_from']}")
    for comp in data.get("components") or []:
        price = comp.get("price")
        suffix = f" (€{price})" if price else " (gratis)"
        lines.append(f"- {comp.get('name')}{suffix}")
    if data.get("notes"):
        lines.append(data["notes"])
    return "\n".join(lines)


def _format_tool_result(name: str, content: str) -> Optional[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if name == "get_upcoming_activities":
        return _format_activities(data)
    if name == "get_activity_detail":
        return _format_detail(data)
    if name == "submit_idea":
        return data.get("message") or "Je bericht is doorgegeven."
    return None


class MockProvider(LLMProvider):
    name = "mock"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AssistantMessage:
        # Zijn er tool-resultaten? Formatteer de echte opgehaalde gegevens.
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if tool_msgs:
            parts = [
                formatted
                for m in tool_msgs
                if (formatted := _format_tool_result(m.get("name", ""), m.get("content", "")))
            ]
            body = "\n\n".join(parts) if parts else "Ik kon de gegevens niet ophalen."
            return AssistantMessage(content=body + _MOCK_SUFFIX)

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
                "vraag/idee doorgeven. Vraag me bijvoorbeeld welke activiteiten "
                "er binnenkort zijn." + _MOCK_SUFFIX
            )
        )

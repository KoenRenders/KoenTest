"""MockProvider — afhankelijkheidsvrije fallback (CI/lokaal, geen key/kost).

Geen netwerk, geen API-sleutel, geen taalbegrip. Deterministisch zodat tests
het volledige tool-loop-pad kunnen aflopen zonder een echte LLM.

Data-bewust: vraagt de bezoeker naar activiteiten, dan vraagt de mock één keer
de ``get_activities``-tool aan; zodra er een tool-resultaat binnen is,
formatteert hij de **echte** opgehaalde gegevens via een vast sjabloon. Zo toont
optie A (zonder key) je werkelijke data, alleen zonder vrije conversatie.

**Sinds CR-07 kan hij ook een selectie samenstellen.** De backoffice-assistent
moet testbaar zijn zonder sleutel — anders is het enige dat de lus, de
naadwachter, de tokenweigering en het scherm samen bewijst, een handmatige
sessie met een echte rekening. De mock kiest objecten op trefwoord, roept
``run_report`` aan en zet het resultaat om in een leesbaar antwoord. Dat is geen
taalbegrip en doet ook niet alsof: het is genoeg om het pad te laten lopen.
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
    if name == "get_activities":
        return _format_activities(data)
    if name == "get_activity_detail":
        return _format_detail(data)
    if name == "submit_idea":
        return data.get("message") or "Je bericht is doorgegeven."
    if name == "run_report":
        return _format_report(data)
    if name == "list_values":
        if data.get("error"):
            return f"Dat lukt niet: {data['error']}"
        waarden = data.get("values") or []
        return ("Mogelijke waarden: " + ", ".join(waarden)) if waarden \
            else (data.get("note") or "Geen waarden.")
    return None


# Trefwoord → objecten, voor de backoffice-assistent. Klein en stom met opzet: een
# slimmere mock zou een model nabootsen, en dan test je de imitatie.
_REPORT_RECIPES: tuple[tuple[tuple[str, ...], list[str]], ...] = (
    (("gemeente", "waar", "woon"), ["member_municipality", "member_total_count"]),
    (("betal", "omzet", "geld", "openstaand"),
     ["payment_status", "payment_amount", "payment_amount_paid"]),
    (("activiteit", "inschrijving", "deelnem"),
     ["activity", "registration_count", "registration_quantity"]),
    (("naam", "hoofdlid", "wie"), ["member_head_name"]),  # de weigering, met opzet
)


def _report_objects(text: str) -> Optional[list[str]]:
    for triggers, objects in _REPORT_RECIPES:
        if any(t in text for t in triggers):
            return objects
    return None


def _format_report(data: dict[str, Any]) -> str:
    if data.get("error"):
        return f"Dat lukt niet: {data['error']}"
    columns = data.get("columns") or []
    rows = data.get("rows") or []
    if not rows:
        return "Daar zijn geen gegevens voor."
    kop = " · ".join(c.get("name", "") for c in columns)
    lines = [f"Op basis van: {kop}.", ""]
    for row in rows[:10]:
        lines.append("- " + " · ".join(str(row.get(c["key"], "")) for c in columns))
    if data.get("threshold_applied"):
        lines.append("")
        lines.append("Kleine groepen samengevoegd (privacydrempel).")
    if data.get("truncated"):
        lines.append("")
        lines.append(data["truncated"])
    return "\n".join(lines)


class MockProvider(LLMProvider):
    name = "mock"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
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
        if "run_report" in tool_names:
            objects = _report_objects(text)
            if objects:
                return AssistantMessage(
                    tool_calls=[ToolCall(id="mock-report-1", name="run_report",
                                         arguments={"objects": objects})]
                )
            return AssistantMessage(
                content=(
                    "Ik ben Raakje in testmodus: zonder sleutel stel ik zelf geen "
                    "selectie samen. Vraag me iets over gemeentes, betalingen of "
                    "inschrijvingen, dan draai ik een echt rapport." + _MOCK_SUFFIX
                )
            )
        if "get_activities" in tool_names and any(
            trigger in text for trigger in _ACTIVITY_TRIGGERS
        ):
            return AssistantMessage(
                tool_calls=[
                    ToolCall(id="mock-call-1", name="get_activities", arguments={})
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

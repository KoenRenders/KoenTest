"""Chat-orkestratie: de tool-loop tussen provider en tools.

Eén beurt = het model bevragen, eventuele tool-aanroepen uitvoeren, en opnieuw
bevragen tot er een eindantwoord is. Het aantal rondes is begrensd (kosten- en
lus-vangrail). De DB-toegang loopt uitsluitend via de meegegeven dispatcher — de
security-grens.

**De lus is domeinvrij (CR-07 §4.3).** Ze kreeg haar tools vroeger uit een import
en kon dus maar één ding zijn: de publieke bot. Sinds de assistent bestaat, krijgt
ze tools én dispatcher als parameter — één lus, twee configuraties. Er is dus geen
tweede Raakje: de publieke bot is zelf het eerste pakket op deze lus, en de
backoffice-assistent is dezelfde lus met een andere gereedschapskist.

Wat hier NIET in staat is even belangrijk. De naadwachter en het logboek zitten
bij de provider (`seam.py`), niet in deze lus: daar passeert elke oproep van elk
toekomstig pakket, en een controle die in de lus zou staan, zou een pakket dat
zijn eigen lus schrijft stilzwijgend mislopen.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from .providers.base import LLMProvider
from .seam import SeamBlocked

# De publieke gereedschapskist wordt LAZY geïmporteerd, in `run_public_chat`. Op
# modulehoogte zou ze `media.api` binnenhalen, dat op zijn beurt `chatbot.api`
# importeert voor de poster-extractie — en sinds de facade de naad exporteert,
# loopt die kring terug hierheen. Een domeinvrije lus die zijn eerste pakket
# importeert had die kring sowieso niet mogen hebben; dit is de import die dat
# zichtbaar maakte.

#: Wat een dispatcher moet kunnen: een naam en argumenten omzetten in het
#: tool-resultaat als tekst. De security-grens van een pakket zit hierin — hij
#: weigert elke naam buiten zijn eigen allowlist.
Dispatcher = Callable[[str, dict[str, Any], Session], str]

logger = logging.getLogger(__name__)

class ChatTimeout(RuntimeError):
    """De wandklok liep af vóór er een antwoord was (CR-07 §4.3).

    Een eigen fout en geen leeg antwoord: een gesprek dat vastloopt hoort te
    eindigen met een zin die zegt wat er gebeurd is, niet met een spinner die
    blijft draaien of een antwoord dat nergens op slaat.
    """


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
    *,
    tools: list[dict[str, Any]],
    dispatch: Dispatcher,
    force_first: bool = False,
    fallback: str = _FALLBACK,
    deadline: float | None = None,
) -> str:
    """Loop het gesprek af tot een eindantwoord en geef de antwoordtekst terug.

    ``messages`` bevat al de system-prompt + de geschiedenis (laatste = user).
    ``tools``/``dispatch`` bepalen welk pakket draait; ``force_first`` dwingt in de
    eerste ronde een tool-aanroep af, zodat een antwoord op echte data staat in
    plaats van op wat het model zich herinnert. ``deadline`` is een
    ``time.monotonic()``-tijdstip: is dat gepasseerd, dan stopt de lus tussen twee
    rondes. Tussen rondes en niet middenin, want een halve HTTP-post afbreken
    levert geen antwoord en wél een half beeld in het logboek.
    """
    for i in range(max_rounds):
        if deadline is not None and time.monotonic() > deadline:
            raise ChatTimeout(
                "Deze vraag duurde te lang. Probeer ze in stukken te knippen — "
                "vraag bijvoorbeeld eerst één getal en dan de opsplitsing."
            )
        tool_choice = "any" if (i == 0 and force_first) else None
        reply = provider.complete(messages, tools=tools, tool_choice=tool_choice)
        if not reply.tool_calls:
            return (reply.content or "").strip() or fallback

        messages.append(_assistant_dict(reply))
        for tc in reply.tool_calls:
            result = dispatch(tc.name, tc.arguments, db)
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
        return (final.content or "").strip() or fallback
    except SeamBlocked:
        # De naadwachter hoort de gebruiker te bereiken, niet in een vangnet te
        # verdwijnen: een geblokkeerde oproep is een boodschap, geen storing.
        raise
    except Exception as exc:  # pragma: no cover - defensief
        logger.warning("Eindantwoord na max rondes mislukte: %s", exc)
        return fallback


def run_public_chat(db: Session, messages: list[dict[str, Any]],
                    provider: LLMProvider, max_rounds: int = 4) -> str:
    """De publieke bot: de gedeelde lus met zijn eigen kist en zijn eigen zet.

    De trefwoord-heuristiek hoort hier en niet in de lus: ze gaat over agenda's en
    activiteiten, en dat is precies het soort domeinkennis dat een gedeelde lus niet
    mag dragen.
    """
    from .tools import TOOL_SPECS, execute_tool

    return run_chat(db, messages, provider, max_rounds=max_rounds,
                    tools=TOOL_SPECS, dispatch=execute_tool,
                    force_first=_wants_activity_data(messages))

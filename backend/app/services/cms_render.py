"""Vervang placeholders in CMS-inhoud door actuele waarden uit de configuratie.

Beheerders typen in de CMS-editor codes zoals ``{{lidgeld_vol}}`` of
``{{halfprijs_start}}``. Bij het tonen op de publieke site worden die vervangen
door de echte waarden uit de app-configuratie (en dus uit de .env). Zo blijft de
tekst in sync met de ingestelde prijzen/datums zonder dat een beheerder de
bedragen handmatig moet bijwerken.

Let op: vervanging gebeurt alleen op de PUBLIEKE leesendpoints. De admin-/
editor-endpoints geven de ruwe codes terug, zodat ze bewerkbaar blijven.
"""
from typing import Dict, Optional


# Lijst met beschikbare codes — ook gebruikt om een legende in de editor te tonen.
PLACEHOLDER_LABELS = {
    "membership_price_full": "Lidgeld volledig (bv. 35,00)",
    "membership_price_half": "Lidgeld halftarief (bv. 17,50)",
    "half_price_start": "Startdatum halftarief (bv. 16 april)",
    "half_price_end": "Einddatum halftarief (bv. 16 september)",
    "next_year_from": "Vanaf deze datum lid voor volgend jaar (bv. 17 september)",
}

_MAANDEN = ["", "januari", "februari", "maart", "april", "mei", "juni",
            "juli", "augustus", "september", "oktober", "november", "december"]


def _format_price(value) -> str:
    """Belgische notatie: punt → komma, twee decimalen."""
    return f"{value:.2f}".replace(".", ",")


def _format_md(md: str) -> str:
    """"MM-DD" → "16 april"."""
    month, day = md.split("-")
    return f"{int(day)} {_MAANDEN[int(month)]}"


def _values() -> Dict[str, str]:
    from app.config import settings
    return {
        "membership_price_full": _format_price(settings.membership_price_full),
        "membership_price_half": _format_price(settings.membership_price_half),
        "half_price_start": _format_md(settings.membership_half_price_start_md),
        "half_price_end": _format_md(settings.membership_half_price_end_md),
        "next_year_from": _format_md(settings.membership_next_year_from_md),
    }


def render_cms_content(content: Optional[str]) -> Optional[str]:
    """Vervang elke ``{{code}}`` door de bijbehorende configuratiewaarde."""
    if not content:
        return content
    for code, value in _values().items():
        content = content.replace(f"{{{{{code}}}}}", value)
    return content

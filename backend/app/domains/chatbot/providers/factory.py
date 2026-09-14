"""Provider-keuze op basis van config — de enige plek die beslist welke LLM draait.

``CHAT_LLM_PROVIDER``:
- ``auto`` (default): Mistral zodra er een ``MISTRAL_API_KEY`` staat, anders Mock.
- ``mistral``: forceer Mistral (faalt expliciet zonder sleutel).
- ``mock``: forceer de afhankelijkheidsvrije mock (CI/lokaal).
"""
from __future__ import annotations

from app.config import settings
from .base import LLMProvider
from .mock import MockProvider


def get_provider(model: str = "") -> LLMProvider:
    """De provider voor deze oproep, eventueel op een ander model.

    ``model`` overschrijft `CHAT_MODEL`. De backoffice-assistent stelt een selectie
    samen en dat is zwaarder werk dan een opzoeking, dus die draait op een groter
    model dan de publieke bot (CR-07 §4.4) — dezelfde leverancier, dezelfde naad,
    alleen een andere keuze. Eén plek die de provider bouwt blijft eraan vasthouden.
    """
    choice = (settings.chat_llm_provider or "auto").lower()
    has_key = bool(settings.mistral_api_key)

    if choice == "mock":
        return MockProvider()

    if choice == "mistral" or (choice == "auto" and has_key):
        if not has_key:
            raise RuntimeError(
                "CHAT_LLM_PROVIDER=mistral maar er is geen MISTRAL_API_KEY gezet."
            )
        # Lazy import: geen Mistral-config nodig om de mock te draaien.
        from .mistral import build_mistral_provider

        return build_mistral_provider(model=model)

    return MockProvider()

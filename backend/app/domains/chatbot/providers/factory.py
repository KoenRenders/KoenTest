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


def get_provider() -> LLMProvider:
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

        return build_mistral_provider()

    return MockProvider()

"""Provider-keuze op basis van config — de enige plek die beslist welke STT-bron
draait. Spiegelt ``app/domains/chatbot/providers/factory.py``.

``STT_PROVIDER``:
- ``auto`` (default): Voxtral zodra er een ``MISTRAL_API_KEY`` staat, anders Mock.
- ``voxtral``: forceer Voxtral Realtime (faalt expliciet zonder sleutel).
- ``mock``: forceer de afhankelijkheidsvrije mock (CI/lokaal).
"""
from __future__ import annotations

from app.config import settings

from .base import SttProvider
from .mock import MockSttProvider


def get_stt_provider() -> SttProvider:
    choice = (settings.stt_provider or "auto").lower()
    has_key = bool(settings.mistral_api_key)

    if choice == "mock":
        return MockSttProvider()

    if choice == "voxtral" or (choice == "auto" and has_key):
        if not has_key:
            raise RuntimeError(
                "STT_PROVIDER=voxtral maar er is geen MISTRAL_API_KEY gezet."
            )
        # Lazy import: geen websockets/Mistral-config nodig om de mock te draaien.
        from .voxtral import VoxtralRealtimeProvider

        return VoxtralRealtimeProvider(
            api_key=settings.mistral_api_key,
            model=settings.stt_model,
            base_url=settings.stt_base_url,
            sample_rate=settings.stt_sample_rate,
        )

    return MockSttProvider()

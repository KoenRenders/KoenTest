"""Provider-keuze op basis van config — de enige plek die beslist welke STT-bron
draait. Spiegelt ``app/domains/chatbot/providers/factory.py``.

``STT_PROVIDER``:
- ``voxtral`` (default): Voxtral Realtime (Mistral, EU); vereist een ``MISTRAL_API_KEY``.
- ``mock``: de afhankelijkheidsvrije mock — enkel voor CI/dev (geen netwerk).

Wélke browsers de provider gebruiken, beslist ``STT_MODE`` (zie ``app/routers/stt.py``);
deze factory levert enkel de provider zodra die nodig is.
"""
from __future__ import annotations

from app.config import settings

from .base import SttProvider
from .mock import MockSttProvider


def get_stt_provider() -> SttProvider:
    choice = (settings.stt_provider or "voxtral").lower()

    if choice == "mock":
        return MockSttProvider()

    # voxtral (en elke andere niet-mock waarde): vereist een sleutel.
    if not settings.mistral_api_key:
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

"""Afhankelijkheidsvrije mock-STT (#282).

Draait in CI/lokaal en wanneer er geen ``MISTRAL_API_KEY`` is. Verbruikt de
audiostroom (zodat de vangrails/idle-logica realistisch lopen) en geeft een
deterministisch resultaat terug: één partial per ontvangen chunk en een
afsluitende final. Geen netwerk, geen Mistral.
"""
from __future__ import annotations

from typing import AsyncIterator

from .base import SttProvider, TranscriptEvent


class MockSttProvider(SttProvider):
    name = "mock"

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        chunks = 0
        async for _chunk in audio:
            chunks += 1
            yield TranscriptEvent(text=f"(mock partial {chunks})", is_final=False)
        yield TranscriptEvent(text="mock transcriptie", is_final=True)

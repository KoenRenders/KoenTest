"""Provider-naad voor realtime spraak-naar-tekst (#282).

Zelfde idee als de chatbot-laag: één dun contract zodat de WebSocket-route niet
weet wie transcribeert. Een provider krijgt een async-stroom audiochunks (bytes)
binnen en levert een async-stroom transcript-events terug (partial → final), zodat
een nieuwe leverancier enkel ``stream()`` hoeft te implementeren.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class TranscriptEvent:
    """Eén transcript-update. ``is_final`` markeert het afgewerkte resultaat;
    tussentijdse (``partial``) updates laten de UI live meelezen."""

    text: str
    is_final: bool = False


class SttProvider(ABC):
    """De enige naad tussen de STT-route en een concrete spraak-naar-tekst-bron."""

    #: Korte, herkenbare naam voor logging en de privacyverklaring.
    name: str = "base"

    @abstractmethod
    def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        """Transcribeer een live audiostroom.

        ``audio`` levert opeenvolgende audiochunks (bytes) tot ze uitgeput is
        (einde opname). De implementatie is een async generator die
        ``TranscriptEvent``-objecten yield't naarmate er tekst beschikbaar komt.
        """
        raise NotImplementedError

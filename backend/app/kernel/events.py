"""Synchrone, in-transactie event-dispatcher — event-ladder trede 1 (§5.8).

Semantiek (bewust, vastgelegd in het architectuurdoc):
- ``publish()`` roept alle handlers DIRECT aan, in dezelfde DB-transactie als de
  publicerende code. Een handler-fout propageert en rolt de bron mee terug —
  er bestaat geen "misschien ooit"-semantiek.
- Per event-type is de bezorging binair: hier synchroon. Pas bij extractie van
  een component komt het transactional-outbox-patroon (trede 2) in beeld.

Gebruik:
    @subscribe(SubmissionCreated)
    def on_submission(event: SubmissionCreated, db: Session) -> None: ...

    publish(SubmissionCreated(submission_id=7), db)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KernelEvent:
    """Basisklasse voor alle events; concrete events zijn frozen dataclasses
    in ``kernel/contracts`` of in de contracts van het publicerende component."""


E = TypeVar("E", bound=KernelEvent)

_subscribers: dict[type, list[Callable]] = defaultdict(list)


def subscribe(event_type: type[E]) -> Callable[[Callable], Callable]:
    """Registreer een handler voor een event-type (decorator)."""

    def decorator(handler: Callable) -> Callable:
        _subscribers[event_type].append(handler)
        return handler

    return decorator


def publish(event: KernelEvent, db: Session) -> None:
    """Bezorg het event synchroon aan alle handlers, in de lopende transactie."""
    handlers = _subscribers.get(type(event), [])
    logger.debug("event %s -> %d handler(s)", type(event).__name__, len(handlers))
    for handler in handlers:
        handler(event, db)


def reset_subscribers() -> None:
    """Enkel voor tests: maak het abonneeregister leeg."""
    _subscribers.clear()

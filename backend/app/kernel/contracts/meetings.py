"""Events the meetings component publishes (contract, see meetings/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class CircleStartChosen(KernelEvent):
    """The secretary chose since when someone counts for the meeting circle (#1346).

    Published by the meetings service when the circle screen stores a start date;
    `mdm`, which owns the circle relation, subscribes and writes it. A subscriber
    that refuses — a start after the end — raises, and nothing is stored.

    `start_date` is ISO: events are plain data.
    """

    relation_id: int
    start_date: str

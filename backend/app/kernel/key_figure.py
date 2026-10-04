"""A key figure of a list's title row — one figure, one short label.

CR-11 block 2 (Koen, 2 October 2026; `docs/design-system-end-state.md` §3.8): a
key figure is read, not clicked, and it never stacks two amounts or a pair. Two
things to do are two figures — "Nog te ontvangen" and "Nog terug te betalen" —
and a count beside an amount is a figure of its own. The value object refuses
anything else when it is built, so a screen that passes a pair fails at render
(CR-11 B7 test 18) instead of in a review.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyFigure:
    """One figure as the screen shows it (`value`, already formatted), its
    label of two or three words, the full definition for the hover (`title`),
    and whether it asks for attention (`warning`: an open amount above zero,
    nothing else)."""

    value: str
    label: str
    title: str = ""
    warning: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(f"a key figure is one formatted value, not {self.value!r}")
        if "·" in self.value or self.value.count("€") > 1 or "\n" in self.value:
            raise TypeError(f"a key figure is one figure, not a pair: {self.value!r}")
        if not self.label.strip() or "·" in self.label or "\n" in self.label:
            raise TypeError(f"a key figure has one short label, not {self.label!r}")
        if not self.title:
            object.__setattr__(self, "title", self.label)

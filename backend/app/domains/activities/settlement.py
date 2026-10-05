"""How a product is settled, as ONE choice (#1608; end state §3.3, CR-11 Q64).

A product stores two flags, `is_free` and `pay_on_site`, and they exclude each
other: a product is paid for with the registration, or it is free, or it is paid
on the spot. The screen showed the two flags as two switches (K5) and so could
show a state the service refuses. Koen, 5 October 2026: *"Waarom is dit geen
dropdown met de 3 keuzes gebleven?"* — it is one choice of three again.

The model keeps its two flags (no migration; the public price block and the JSON
API read them as they did). This module is the translation between the choice
the screen shows and the flags the model stores, in one place: the fiche's
context asks it for the choice of a product, the form's reader for the flags of
a choice. The service still refuses both flags at once, for a caller that sends
flags.
"""

from __future__ import annotations

from app.i18n import _

#: The three ways a product is settled. Form values: stored nowhere, so no code
#: list and no enum — the model's two flags are what is stored.
PAID = "paid"
FREE = "free"
ON_SITE = "on_site"
CHOICES = (PAID, FREE, ON_SITE)


def settlement_of(is_free: object, pay_on_site: object) -> str:
    """The choice these two flags are. Both set is a state the service refuses
    and no product holds; read as "free", the flag that makes the price nothing."""
    if is_free:
        return FREE
    if pay_on_site:
        return ON_SITE
    return PAID


def flags_of(choice: str) -> tuple[bool, bool]:
    """`(is_free, pay_on_site)` for a choice; `ValueError` for anything else."""
    if choice not in CHOICES:
        raise ValueError(choice)
    return choice == FREE, choice == ON_SITE


def settlement_options() -> list[tuple[str, str]]:
    """The three choices with their words, in the order the screen shows them.
    Labels are not shortened (decision 05)."""
    return [(PAID, _("Betalend")), (FREE, _("Gratis")), (ON_SITE, _("Ter plaatse"))]

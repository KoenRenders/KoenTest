"""The document of a tenant's home page (CR-32 R16, R17, F15).

The home page is a page of the CMS since CR-32 phase 5, flagged as the tenant's
home (CR-19). What it holds is what `home.html` composed: the editorial intro, the
membership band — the fee and the year it runs to as values, *Word lid* and
*Contacteer ons* — and the upcoming activities. This module builds that document
from the pieces a tenant has, as ONE pure function, so the seed of a new tenant
and the migration that gave the existing tenants their page cannot compose
differently. A piece whose module is off is absent, not empty (CR-19).

The band is the kit's section in the accent tone with columns: the intro at the
left, at the right the fee and the buttons (B8.10). The buttons are ordinary
buttons: the switch to *Mijn gezin* for a signed-in member with a household is
one rule of the button resolver, not of this document (B8.9).
"""

from __future__ import annotations

from typing import Any

#: How many upcoming activities the seeded block shows at most (the block's own
#: maximum, 50): the old home showed every upcoming activity, and a home that
#: stops at twelve loses the rest for a tenant with more.
ACTIVITIES_SHOWN = 50


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _paragraph(*inline: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(inline)}


def _value(code: str) -> dict[str, Any]:
    return {"type": "value", "attrs": {"code": code}}


def home_document(
    intro_blocks: list[dict[str, Any]],
    *,
    membership: bool,
    activities: bool,
    contact_slug: str | None,
) -> dict[str, Any]:
    """The home page's document: `intro_blocks` are the blocks of the old
    `home-intro` page (as stored); `membership` and `activities` say whether
    those modules are on, `contact_slug` is the slug of the contact form when the
    forms module is on (None: no contact button)."""
    blocks: list[dict[str, Any]] = []

    right: list[dict[str, Any]] = []
    if membership:
        right.append(_paragraph(_value("membership_price_full")))
        right.append(
            _paragraph(_text("per gezin, geldig tot en met "), _value("membership_valid_until"))
        )
        right.append(
            {
                "type": "button",
                "attrs": {"label": "Word lid", "variant": "primary", "screen": "lid-worden"},
            }
        )
    if contact_slug:
        right.append(
            {
                "type": "button",
                "attrs": {
                    "label": "Contacteer ons",
                    "variant": "secondary",
                    "form_slug": contact_slug,
                },
            }
        )

    if intro_blocks and right:
        band_content: list[dict[str, Any]] = [
            {
                "type": "columns",
                "attrs": {"align": "middle"},
                "content": [
                    {"type": "column", "content": list(intro_blocks)},
                    {"type": "column", "content": right},
                ],
            }
        ]
    else:
        band_content = list(intro_blocks) or right
    if band_content:
        blocks.append({"type": "section", "attrs": {"tone": "accent"}, "content": band_content})

    if activities:
        blocks.append(
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [_text("Activiteiten")],
            }
        )
        blocks.append({"type": "activities", "attrs": {"count": ACTIVITIES_SHOWN}})

    return {"type": "doc", "content": blocks}

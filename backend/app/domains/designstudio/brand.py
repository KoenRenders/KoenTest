"""The Raak house style as data (CR-10 §3.3).

The style guide names eight colours, all equal, and twelve permitted text/
background duos, usable in both directions. Templates refer to colours **by
name**, never by hex; this module is the only place that knows the hex values,
and :func:`check_template` is the gate that fails a template using anything
else. The CMYK and PMS values are recorded for a later print-shop step; nothing
renders them today.

Three duos are enabled for the picker (Koen, 16 September 2026 — the ones the
unit uses today); enabling another is a one-line change in ``ENABLED_DUOS``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Colour:
    code: str
    name: str
    hex: str
    cmyk: tuple[int, int, int, int]
    pms: str


COLOURS: dict[str, Colour] = {
    c.code: c for c in (
        Colour("golden_yellow", "Golden Yellow", "#ffce00", (0, 18, 100, 0), "Yellow 012"),
        Colour("pumpkin_orange", "Pumpkin Orange", "#f16532", (0, 75, 89, 0), "1645"),
        Colour("cool_green", "Cool Green", "#3aba9b", (70, 0, 51, 0), "3255"),
        Colour("dark_green", "Dark Green", "#005d29", (100, 0, 100, 56), "348"),
        Colour("hot_pink", "Hot Pink", "#f17fb2", (0, 64, 0, 0), "237"),
        Colour("ocean_blue", "Ocean Blue", "#0051a4", (100, 77, 0, 0), "2935"),
        Colour("watermelon_red", "Watermelon Red", "#ee3a37", (0, 92, 84, 0), "Red 032"),
        Colour("indigo", "Indigo", "#460359", (68, 100, 0, 47), "2617"),
    )
}

WHITE = "#ffffff"
BLACK = "#000000"

#: The twelve permitted duos of the guide, as (light, dark). Each is usable in
#: both directions: light text on the dark colour, or dark text on the light one.
DUOS: tuple[tuple[str, str], ...] = (
    ("golden_yellow", "ocean_blue"),
    ("golden_yellow", "indigo"),
    ("golden_yellow", "dark_green"),
    ("golden_yellow", "pumpkin_orange"),
    ("golden_yellow", "watermelon_red"),
    ("cool_green", "ocean_blue"),
    ("cool_green", "indigo"),
    ("cool_green", "dark_green"),
    ("hot_pink", "ocean_blue"),
    ("hot_pink", "indigo"),
    ("hot_pink", "dark_green"),
    ("watermelon_red", "indigo"),
)

#: A duo code is "<tile>-<accent>": the tile is the colour of the frame and the
#: logo field, the accent the colour of the baseline and the highlights.
ENABLED_DUOS: tuple[str, ...] = (
    "dark_green-golden_yellow",
    "ocean_blue-golden_yellow",
    "golden_yellow-indigo",
)

#: The guide's general rule: at most four or five colours per design. Counted
#: on the template's own elements (fields, text, ornaments), never on photos.
MAX_COLOURS_PER_TEMPLATE = 5


def is_permitted_duo(tile: str, accent: str) -> bool:
    """A duo is permitted in either direction."""
    return (tile, accent) in DUOS or (accent, tile) in DUOS


def split_duo(code: str) -> tuple[str, str]:
    tile, _, accent = code.partition("-")
    if tile not in COLOURS or accent not in COLOURS:
        raise ValueError(f"unknown colour in duo {code!r}")
    if not is_permitted_duo(tile, accent):
        raise ValueError(f"duo {code!r} is not permitted by the style guide")
    return tile, accent


def palette_for(duo_code: str,
                accents: tuple[str, str, str] = ("hot_pink", "cool_green", "watermelon_red")) -> dict[str, str]:
    """The named colours a template may use for one design: the duo plus three
    accents and white — five brand colours, the guide's maximum. Templates take
    colours from this mapping only."""
    tile, accent = split_duo(duo_code)
    return {
        "tile": COLOURS[tile].hex,
        "accent": COLOURS[accent].hex,
        "accent2": COLOURS[accents[0]].hex,
        "accent3": COLOURS[accents[1]].hex,
        "accent4": COLOURS[accents[2]].hex,
        "white": WHITE,
        "ink": COLOURS[tile].hex if tile != "golden_yellow" else COLOURS[accent].hex,
    }


_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def hex_values(text: str) -> set[str]:
    """Every six-digit hex colour in a text, lower-cased; three-digit ones expanded."""
    out = set()
    for m in _HEX.finditer(text):
        v = m.group(0).lower()
        if len(v) == 4:
            v = "#" + "".join(ch * 2 for ch in v[1:])
        out.add(v)
    return out


ALLOWED_HEX = frozenset({c.hex for c in COLOURS.values()} | {WHITE, BLACK})


def check_template(svg_text: str) -> list[str]:
    """The gate: a template may only use the eight colours, white and black,
    and no more than :data:`MAX_COLOURS_PER_TEMPLATE` of the eight.

    Returns the violations as sentences; an empty list means the template
    passes. Data URIs (photos) are cut out before checking, because they are
    images, not template elements.
    """
    text = re.sub(r"data:[^\"']+", "", svg_text)
    found = hex_values(text)
    problems = []
    for value in sorted(found - ALLOWED_HEX):
        problems.append(f"colour {value} is not a Raak colour")
    brand_used = {v for v in found if v in ALLOWED_HEX and v not in (WHITE, BLACK)}
    if len(brand_used) > MAX_COLOURS_PER_TEMPLATE:
        problems.append(
            f"{len(brand_used)} brand colours used; the guide allows at most {MAX_COLOURS_PER_TEMPLATE}"
        )
    return problems

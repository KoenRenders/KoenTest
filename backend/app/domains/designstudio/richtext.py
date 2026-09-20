"""Formatted text for posters (CR-10 §3.16, point 2).

Koen asked for "geformatteerde tekst" in the explanation, the practical box and
the programme: paragraphs, **bold** and bullet lists — and nothing else. Fonts,
sizes and colours are the house style's, so the input format cannot carry them.

Input is a small Markdown subset stored as text:

- every line break starts a new line on the poster (Koen, 20 September 2026:
  "als in de omschrijving een enter staat, kan je dat dan ook op de affiche
  doen?");
- a blank line leaves a blank line;
- a line starting with ``- `` or ``* `` is a bullet;
- ``**bold**`` marks bold runs.

Everything else is literal text. Output is a list of *lines*, each a list of
runs ``(text, bold)``, wrapped to a width measured with the real font metrics —
so the estimate the editor shows and the width Inkscape draws agree within the
tolerance measured in iteration 16 (the estimate lies a few percent above the
ink width).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont

FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"
BODY_FONT = FONTS_DIR / "RadioCanadaBig-VariableFont_wght.ttf"

#: Inkscape (Pango) lays small text out wider than the font's advances say —
#: measured on 18 September 2026 (iteration 17, `--query-all` against fontTools):
#: +5.5 % regular and +7.9 % bold at 6.4 mm, +3.9 % bold at 8.2 mm, −0.5 % at
#: 7.4 mm upper case, −5.5 % on a 51 mm title (advance vs ink). The drift
#: shrinks with the size, as glyph-position rounding does, so the bound grows
#: with 1/size: 0.55 / size keeps every sample under the estimate. Inkscape
#: stays the authority; this only keeps the wrap and the quick check honest.
INK_SLACK_PER_MM = 0.55

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BULLET = re.compile(r"^[-*]\s+")
_ALLOWED_INLINE = re.compile(r"[^\S\n]+")


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False


#: Line spacing of body text. A little more than the 1.3 it was, because the
#: poster now keeps typed line breaks and those read better with air between
#: them (Koen, 20 September 2026).
LINE_HEIGHT = 1.4


@dataclass(frozen=True)
class Block:
    """One typed line: a paragraph, a bullet, or a line after an Enter."""
    runs: tuple[Run, ...]
    bullet: bool = False
    #: Preceded by a blank line, so it gets a blank line before it.
    gap: bool = False


HAND_FONT = FONTS_DIR / "Caveat-VariableFont_wght.ttf"


@lru_cache(maxsize=8)
def _metrics(font_path: str, weight: int) -> tuple[dict, dict, int]:
    """cmap, advance widths and units-per-em of one static instance of the
    variable font. Bold is the real 700 instance, not a surcharge on regular:
    Radio Canada Big Bold runs about 8 % wider than Regular, and a guessed
    factor is exactly the kind of estimate Inkscape then contradicts."""
    from fontTools.varLib.instancer import instantiateVariableFont

    font = TTFont(font_path)
    if "fvar" in font:
        axes = {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes}
        if "wght" in axes:
            lo, hi = axes["wght"]
            font = instantiateVariableFont(font, {"wght": max(lo, min(hi, weight))})
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


def text_width(text: str, size: float, *, bold: bool = False, tracking: float = 0.0,
               font: Path = BODY_FONT) -> float:
    """Advance width of ``text`` at ``size`` (same unit as the result), from the
    ``hmtx`` table of the weight that is drawn (400 or 700), plus the slack
    Inkscape adds at small sizes (:data:`INK_SLACK_PER_MM`) — an upper bound
    of the ink width, which is what an overflow check needs; proven against
    Inkscape in ``test_designstudio_engine``."""
    cmap, hmtx, upm = _metrics(str(font), 700 if bold else 400)
    advance = 0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            name = cmap.get(ord("n"), ".notdef")
        advance += hmtx[name][0]
    width = advance / upm * size * (1 + INK_SLACK_PER_MM / size)
    return width + tracking * max(len(text) - 1, 0)


def parse(source: str) -> list[Block]:
    """Parse the Markdown subset. Unknown markup stays literal; there is no way
    to smuggle in a font, a colour or markup."""
    blocks: list[Block] = []
    gap = False
    for raw in (source or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            gap = bool(blocks)      # a blank line before the first line means nothing
            continue
        bullet = bool(_BULLET.match(line))
        text = _BULLET.sub("", line, count=1) if bullet else line
        blocks.append(Block(runs=_runs(text), bullet=bullet, gap=gap))
        gap = False
    return blocks


def _runs(text: str) -> tuple[Run, ...]:
    runs: list[Run] = []
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            runs.append(Run(text[pos:m.start()]))
        runs.append(Run(m.group(1), bold=True))
        pos = m.end()
    if pos < len(text):
        runs.append(Run(text[pos:]))
    return tuple(r for r in runs if r.text)


def wrap(blocks: list[Block], *, width: float, size: float, bullet_indent: float = 0.0) -> list[list[Run]]:
    """Wrap blocks into lines that fit ``width`` at ``size``. A bullet block
    gets its marker as the first run of its first line and continuation lines
    indented by ``bullet_indent`` (handled by the caller through an empty run).
    A blank line separates blocks."""
    lines: list[list[Run]] = []
    for i, block in enumerate(blocks):
        if i and block.gap:
            lines.append([])
        words: list[tuple[str, bool]] = []
        for run in block.runs:
            for w in _ALLOWED_INLINE.split(run.text):
                if w:
                    words.append((w, run.bold))
        avail = width - (bullet_indent if block.bullet else 0.0)
        current: list[tuple[str, bool]] = []
        current_w = 0.0
        first = True
        for word, bold in words:
            ww = text_width(word, size, bold=bold)
            space = text_width(" ", size) if current else 0.0
            if current and current_w + space + ww > avail:
                lines.append(_line(current, bullet=block.bullet and first))
                first = False
                current, current_w = [], 0.0
                space = 0.0
            current.append((word, bold))
            current_w += space + ww
        if current:
            lines.append(_line(current, bullet=block.bullet and first))
    return lines


def _line(words: list[tuple[str, bool]], *, bullet: bool) -> list[Run]:
    """Words back into runs; the space between two words of different weight
    stays with the earlier run, so a bold run starts on its first letter."""
    runs: list[Run] = [Run("• ", False)] if bullet else []
    for j, (word, bold) in enumerate(words):
        if runs and runs[-1].bold == bold and not (bullet and j == 0):
            runs[-1] = Run(runs[-1].text + (" " if j else "") + word, bold)
        elif j and bold:
            runs[-1] = Run(runs[-1].text + " ", runs[-1].bold)
            runs.append(Run(word, bold))
        else:
            runs.append(Run((" " if j else "") + word, bold))
    return runs


def line_count(source: str, *, width: float, size: float) -> int:
    """How many lines the text takes at this width — what the planner needs to
    reserve room before anything is drawn."""
    return len(wrap(parse(source), width=width, size=size, bullet_indent=size * 1.1))


def to_svg(source: str, *, x: float, y: float, width: float, size: float,
           line_height: float = LINE_HEIGHT, fill: str, max_lines: int | None = None,
           element_id: str = "") -> tuple[str, int]:
    """Render formatted text as one ``<text>`` element with ``<tspan>`` lines.

    Returns the SVG fragment and the number of lines it holds. Bold runs get
    ``font-weight="bold"``. The caller decides what to do when the line count
    exceeds the block's box (shrink, refuse); ``max_lines`` cuts the output so
    the preview never draws outside the block.
    """
    lines = wrap(parse(source), width=width, size=size, bullet_indent=size * 1.1)
    if max_lines is not None:
        lines = lines[:max_lines]
    step = size * line_height
    parts = []
    for i, line in enumerate(lines):
        dy = f"{step:.3f}" if i else "0"
        inner = "".join(
            f'<tspan font-weight="bold">{escape(r.text)}</tspan>' if r.bold else escape(r.text)
            for r in line
        )
        parts.append(f'<tspan x="{x:.3f}" dy="{dy}">{inner or " "}</tspan>')
    id_attr = f' id="{element_id}"' if element_id else ""
    fragment = (f'<text{id_attr} x="{x:.3f}" y="{y:.3f}" font-size="{size:.3f}" fill="{fill}" '
                f'xml:space="preserve">{"".join(parts)}</text>')
    return fragment, len(lines)


def plain_text(source: str) -> str:
    """The text without markup, for fingerprints and previews."""
    return "\n".join("".join(r.text for r in b.runs) for b in parse(source))

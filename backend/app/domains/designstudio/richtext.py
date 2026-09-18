"""Formatted text for posters (CR-10 §3.16, point 2).

Koen asked for "geformatteerde tekst" in the explanation, the practical box and
the programme: paragraphs, **bold** and bullet lists — and nothing else. Fonts,
sizes and colours are the house style's, so the input format cannot carry them.

Input is a small Markdown subset stored as text:

- a blank line separates paragraphs;
- a line starting with ``- `` or ``* `` is a bullet;
- ``**bold**`` marks bold runs;
- a single line break inside a paragraph is a soft break (joined with a space).

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

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BULLET = re.compile(r"^[-*]\s+")
_ALLOWED_INLINE = re.compile(r"[^\S\n]+")


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False


@dataclass(frozen=True)
class Block:
    """One paragraph or one bullet item."""
    runs: tuple[Run, ...]
    bullet: bool = False


HAND_FONT = FONTS_DIR / "Caveat-VariableFont_wght.ttf"


@lru_cache(maxsize=4)
def _metrics(font_path: str) -> tuple[dict, dict, int]:
    font = TTFont(font_path)
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


def text_width(text: str, size: float, *, bold: bool = False, tracking: float = 0.0,
               font: Path = BODY_FONT) -> float:
    """Advance width of ``text`` at ``size`` (same unit as the result), from the
    font's ``hmtx`` table. The variable font's default instance is used for both
    weights, with a 4 % surcharge for bold: measured on iteration 16, the
    estimate then lies 0.3–3.4 % above the ink width Inkscape draws — an upper
    bound, which is what an overflow check needs."""
    cmap, hmtx, upm = _metrics(str(font))
    advance = 0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            name = cmap.get(ord("n"), ".notdef")
        advance += hmtx[name][0]
    width = advance / upm * size + tracking * max(len(text) - 1, 0)
    return width * 1.04 if bold else width


def parse(source: str) -> list[Block]:
    """Parse the Markdown subset. Unknown markup stays literal; there is no way
    to smuggle in a font, a colour or markup."""
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block(runs=_runs(" ".join(paragraph))))
            paragraph.clear()

    for raw in (source or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        if _BULLET.match(line):
            flush()
            blocks.append(Block(runs=_runs(_BULLET.sub("", line, count=1)), bullet=True))
            continue
        paragraph.append(line)
    flush()
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
        if i:
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
           line_height: float = 1.3, fill: str, max_lines: int | None = None,
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

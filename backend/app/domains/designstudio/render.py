"""Merge, check, export (CR-10 §3.2, B1.3).

Three steps, each usable on its own:

1. :func:`merge` — plan the blocks, render the Jinja SVG template, give back
   the SVG text and the text boxes that may overflow.
2. :func:`check` — the overflow check. First the font metrics (fast, no
   process), then Inkscape's ``--query-all`` as the authority when asked
   (``authority=True``; a version is never made without it).
3. :func:`export` — Inkscape as a subprocess, PDF (text kept, fonts
   embedded) or PNG at a given pixel width. Never ``--export-text-to-path``:
   Inkscape 1.4 reads ``=false`` as true (iteration 15).

Inkscape runs with a clean, minimal environment and a timeout; it reads one
file in a private temporary directory and writes one file next to it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import segno
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.domains.designstudio import brand, richtext
from app.domains.designstudio.blocks import Plan, plan_affiche, speckle_pattern
from app.domains.designstudio.content import PosterContent
from app.domains.designstudio.icons import icon_svg

TEMPLATES = Path(__file__).resolve().parent / "templates"
POSTERS = TEMPLATES / "posters"
BRAND = TEMPLATES / "brand"
# Deliberately not a setting and not an environment variable (#1018, the
# env gate's first real catch): the binary ships in the image via apt and sits
# on PATH; nobody points at another Inkscape today. A knob would cost a
# Settings field, four compose lines, four example lines and a handover step
# for something never turned. Need it to vary one day (another base image, a
# test rig)? Then it becomes a field on `Settings` like the five AI settings —
# never a bare `os.environ.get` here.
INKSCAPE = "inkscape"
INKSCAPE_TIMEOUT = 240

SVG_NS = "http://www.w3.org/2000/svg"


class RenderError(RuntimeError):
    """Inkscape failed or is missing; the message is safe to show."""


@dataclass(frozen=True)
class Merged:
    svg: str
    boxes: dict[str, float]
    violations: tuple[str, ...]   # from the planner: vertical overflow, missing title
    width_mm: float
    height_mm: float


@lru_cache(maxsize=8)
def contract(template_key: str) -> dict:
    return json.loads((POSTERS / template_key / "contract.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(POSTERS)), autoescape=True, undefined=StrictUndefined)
    env.globals["speckles"] = speckle_pattern
    env.globals["icon"] = lambda code, fg, bg, x, y, s: icon_svg(code, fg=fg, bg=bg, x=x, y=y, size=s)
    return env


@lru_cache(maxsize=1)
def _lockup() -> str:
    return (BRAND / "raak-millegem-lockup.svg").read_text(encoding="utf-8")


def wordmark(pal: dict[str, str], *, x: float, y: float, width: float) -> str:
    """The unit lockup without its tile, recoloured for the duo: the yellow of
    the source becomes the accent, white stays white. Cropped to the wordmark
    and baseline (measured bounds, iteration 12)."""
    svg = _lockup().split("?>", 1)[-1].strip()
    tile = 'd="M0 0H701.945V451.248H0Z" fill="#0051a4"'
    if svg.count(tile) != 1:
        raise RenderError("lockup: tile path not found")
    svg = svg.replace(tile, 'd="M0 0H701.945V451.248H0Z" fill="none"')
    old_vb = 'viewBox="0 0 701.945 451.249"'
    if svg.count(old_vb) != 1 or svg.count('width="701.945" height="451.249"') != 1:
        raise RenderError("lockup: unexpected size attributes")
    svg = svg.replace(old_vb, 'viewBox="106 106.2 491 245"')
    height = width * 245 / 491
    svg = svg.replace('width="701.945" height="451.249"',
                      f'x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}"')
    accent = pal["accent"] if pal["tile"] != brand.COLOURS["golden_yellow"].hex else pal["ink"]
    svg = svg.replace("#ffce00", accent)
    # Only the root's own attributes go (a poster has one lockup and one
    # title). The glyph ids stay: the baseline "Beleef meer in Millegem" is
    # <use href="#font_…"> per letter — strip those ids and the baseline
    # silently vanishes (Koen, 19 September 2026).
    head, rest = svg.split(">", 1)
    head = re.sub(r'\s(?:id|aria-labelledby|role)="[^"]*"', "", head)
    return head + ">" + rest


def qr_fragment(url: str, dark: str) -> str:
    """The QR as a nested ``<svg>``; the template adds x/y/width/height. Error
    level M, one-module border — the white box in the template is the quiet
    zone."""
    inline = segno.make(url, error="m").svg_inline(scale=1, border=1, dark=dark, light=None,
                                                    omitsize=True, svgclass=None, lineclass=None)
    return inline.split("<svg", 1)[1]


def merge(content: PosterContent, *, layout: str, template_key: str = "affiche",
          title: str = "Affiche", qr_url: str = "") -> Merged:
    spec = contract(template_key)["layouts"][layout]
    pal = brand.palette_for(content.duo_code)
    p: Plan = plan_affiche(content, layout=layout, width=spec["width_mm"], height=spec["height_mm"], pal=pal)
    svg = _env().get_template(f"{template_key}/{template_key}.svg.j2").render(
        p=p, title=title,
        wordmark=wordmark(pal, x=p.frame + 3, y=p.frame + 3.13, width=72),
        qr=qr_fragment(qr_url, pal["tile"]) if qr_url else "",
    )
    return Merged(svg=svg, boxes=dict(p.boxes), violations=tuple(p.violations),
                  width_mm=spec["width_mm"], height_mm=spec["height_mm"])


# ── Overflow ──────────────────────────────────────────────────────────────

def _texts(svg: str) -> dict[str, ET.Element]:
    root = ET.fromstring(svg)
    return {eid: el for el in root.iter(f"{{{SVG_NS}}}text") if (eid := el.get("id"))}


def _lines_of(el: ET.Element) -> list[list[tuple[str, bool]]]:
    """The runs per visual line, each with its weight: a ``tspan`` with an
    ``x`` starts a line, a ``tspan`` with ``font-weight="bold"`` is a bold
    run. Its tail text belongs to the enclosing line again."""
    base_bold = el.get("font-weight") in ("bold", "700")
    lines: list[list[tuple[str, bool]]] = [[(el.text or "", base_bold)]]

    def walk(node: ET.Element, bold: bool) -> None:
        for child in node:
            if child.tag == f"{{{SVG_NS}}}tspan" and child.get("x") is not None:
                lines.append([])
            child_bold = bold or child.get("font-weight") in ("bold", "700")
            lines[-1].append((child.text or "", child_bold))
            walk(child, child_bold)
            if child.tail:
                lines[-1].append((child.tail, bold))

    walk(el, base_bold)
    kept = [ln for ln in lines if "".join(r[0] for r in ln).strip()]
    return kept or [[("", base_bold)]]


def estimate(merged: Merged) -> list[str]:
    """Font-metric estimate per box: an upper bound of the ink width (iteration
    16), so a box that passes here almost always passes Inkscape too."""
    margin = contract("affiche")["overflow_margin"]
    problems = []
    for eid, el in _texts(merged.svg).items():
        max_w = merged.boxes.get(eid)
        if max_w is None:
            continue
        size = float(el.get("font-size", "0"))
        tracking = float(el.get("letter-spacing", "0") or 0)
        font = richtext.HAND_FONT if "Caveat" in (el.get("font-family") or "") else richtext.BODY_FONT
        widest = max(sum(richtext.text_width(run, size, bold=bold, tracking=tracking, font=font) for run, bold in ln)
                     for ln in _lines_of(el))
        if widest * margin > max_w:
            problems.append(f"{eid}: {widest:.1f} mm geschat, {max_w:.1f} mm beschikbaar")
    return problems


def query_all(svg_path: Path) -> dict[str, tuple[float, float, float, float]]:
    """Inkscape's measured bounding boxes per id, in mm. Units of
    ``--query-all`` are user units scaled by the document; the reference
    rectangle of 100 mm gives the factor (iteration 16)."""
    result = _run([str(svg_path), "--query-all"])
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(",")
        if len(parts) != 5:
            continue
        try:
            boxes[parts[0]] = tuple(float(v) for v in parts[1:])  # type: ignore[assignment]
        except ValueError:
            continue
    ref = boxes.get("ref100mm")
    if not ref or ref[2] <= 0:
        raise RenderError("Inkscape gaf geen referentiemaat terug")
    scale = 100.0 / ref[2]
    return {k: (v[0] * scale, v[1] * scale, v[2] * scale, v[3] * scale) for k, v in boxes.items()}


def check(merged: Merged, *, authority: bool = False) -> list[str]:
    """All violations: the planner's, the estimate's, and — with ``authority``
    — Inkscape's measurement. Rotated texts get their declared overshoot."""
    problems = list(merged.violations) + estimate(merged)
    if not authority:
        return problems
    rotated = set(contract("affiche")["rotated_text_ids"])
    with tempfile.TemporaryDirectory(prefix="designstudio-") as tmp:
        path = Path(tmp) / "poster.svg"
        path.write_text(merged.svg, encoding="utf-8")
        measured = query_all(path)
    for eid, max_w in merged.boxes.items():
        box = measured.get(eid)
        if box is None:
            continue
        allow = max_w * (1.06 if eid in rotated else 1.0)
        if box[2] > allow:
            problems.append(f"{eid}: {box[2]:.1f} mm gemeten door Inkscape, {max_w:.1f} mm beschikbaar")
    return problems


# ── Export ────────────────────────────────────────────────────────────────

FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"


@lru_cache(maxsize=1)
def _fontconfig_file() -> str:
    """A fontconfig that adds the app's own fonts to the system's.

    The poster fonts (Radio Canada Big, Caveat) ship in the repo; Inkscape must
    find them on every host — the image, CI, a laptop — without anyone
    installing them. A private config that includes the system one and adds
    ``static/fonts`` does that; ``FONTCONFIG_FILE`` points Inkscape at it. Its
    cache lands next to it, never in a user's home.
    """
    home = Path(tempfile.gettempdir()) / "designstudio-fontconfig"
    home.mkdir(exist_ok=True)
    conf = home / "fonts.conf"
    conf.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>'
        '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
        f'<dir>{FONTS_DIR}</dir><cachedir>{home / "cache"}</cachedir></fontconfig>\n',
        encoding="utf-8")
    return str(conf)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    if shutil.which(INKSCAPE) is None:
        raise RenderError("Inkscape is niet geïnstalleerd op deze server")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir(),
           "LANG": "C.UTF-8", "INKSCAPE_PROFILE_DIR": tempfile.gettempdir(),
           "FONTCONFIG_FILE": _fontconfig_file()}
    try:
        result = subprocess.run([INKSCAPE, *args], capture_output=True, text=True,
                                timeout=INKSCAPE_TIMEOUT, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RenderError("Inkscape deed er te lang over") from exc
    if result.returncode != 0:
        raise RenderError(f"Inkscape faalde (code {result.returncode}): {result.stderr.strip()[-300:]}")
    return result


_PAGE = re.compile(r'<svg\b[^>]*?\swidth="([0-9.]+)(mm|px)?"\sheight="([0-9.]+)(mm|px)?"')


def page_size_mm(svg: str) -> tuple[float, float]:
    """The page size of an SVG in mm, from its root ``width``/``height``
    (px are converted at 96 dpi). Raises when the root carries none."""
    m = _PAGE.search(svg)
    if not m:
        raise RenderError("SVG zonder paginaformaat")
    w, h = float(m.group(1)), float(m.group(3))
    if m.group(2) != "mm":
        w *= 25.4 / 96
    if m.group(4) != "mm":
        h *= 25.4 / 96
    return w, h


def resize_page(svg: str, width_mm: float, height_mm: float) -> str:
    """Another paper size for the same design: only the ``width``/``height``
    attributes change, the viewBox scales everything (A3 → A4)."""
    new, n = re.subn(r'(<svg\b[^>]*?)\swidth="[^"]+"\sheight="[^"]+"',
                     lambda m: f'{m.group(1)} width="{width_mm}mm" height="{height_mm}mm"', svg, count=1)
    if n != 1:
        raise RenderError("SVG zonder paginaformaat")
    return new


def export(svg: str, kind: str, *, png_width_px: int | None = None) -> bytes:
    """``kind`` is ``pdf`` or ``png``. The PDF keeps text as text."""
    if kind not in ("pdf", "png"):
        raise ValueError(kind)
    with tempfile.TemporaryDirectory(prefix="designstudio-") as tmp:
        src = Path(tmp) / "poster.svg"
        out = Path(tmp) / f"poster.{kind}"
        src.write_text(svg, encoding="utf-8")
        args = [str(src), f"--export-type={kind}", f"--export-filename={out}"]
        if kind == "png":
            args.append(f"--export-width={png_width_px or 1754}")
            args.append("--export-background=#ffffff")
        _run(args)
        if not out.exists():
            raise RenderError("Inkscape schreef geen bestand")
        return out.read_bytes()

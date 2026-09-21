"""The content-driven blocks of the template "Affiche" (CR-10 §3.4) and the
flow that places them.

The look of the page — frame, corner tile, title, band — lives in the SVG
template (``templates/posters/affiche/affiche.svg.j2``). What varies with the
content lives here: how many highlights, whether there is an inset photo, a
dates grid or a text box, and where each of those lands. The planner walks two
columns from the title down to the band; a block that does not fit is a
violation the editor shows ("te veel inhoud"), never a silent cut.

Every text that can overflow horizontally gets an ``id`` and a maximum width
in :attr:`Plan.boxes`; the renderer checks those with the font metrics first
and with Inkscape as the authority (``--query-all``) before a version is made.
"""
from __future__ import annotations

import base64
import random
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from app.domains.designstudio import richtext
from app.domains.designstudio.content import Highlight, ImageBytes, PosterContent
from app.domains.designstudio.icons import icon_svg

FONT = "Radio Canada Big"
HAND = "Caveat"


@dataclass
class Plan:
    """Everything the SVG template needs, computed before drawing."""
    width: float
    height: float
    frame: float
    pal: dict[str, str]
    seed: int
    paper_path: str = ""
    title: list[dict] = field(default_factory=list)
    joiner: dict | None = None
    bar: dict | None = None
    left: str = ""      # SVG fragments, already positioned
    right: str = ""
    full: str = ""
    band: dict = field(default_factory=dict)
    logos: str = ""
    lockup: dict = field(default_factory=dict)   # x, y, width of the lockup in the band
    boxes: dict[str, float] = field(default_factory=dict)  # text id → max width in mm
    violations: list[str] = field(default_factory=list)
    band_y: float = 0.0


# ── Helpers the template and the blocks share ─────────────────────────────

def data_uri(image: ImageBytes) -> str:
    return f"data:{image.mime};base64," + base64.b64encode(image.data).decode()


#: How much wider than its own proportions a box may be before the picture
#: is shown whole instead of cropped. Tried at 2.6 for the hero on
#: 21 September 2026 so the text could take more room; Koen, on the result:
#: "de visualisatie van de foto is echt niet OK". A hero cropped to a band
#: reads as a mistake, so one value for every picture again.
CROP_TOLERANCE = 1.6


def aspect_for(image: ImageBytes, box_w: float = 0.0, box_h: float = 0.0,
               tolerance: float = CROP_TOLERANCE) -> str:
    """Map the focal point to SVG's nine-point crop. When the box is much
    wider than the picture (an Instagram hero squeezed by the rest of the
    page), the picture is shown whole instead of cut in half — a drawing on
    white loses nothing that way (Koen, 20 September 2026)."""
    fx = "Min" if image.focus_x < 1 / 3 else "Max" if image.focus_x > 2 / 3 else "Mid"
    fy = "Min" if image.focus_y < 1 / 3 else "Max" if image.focus_y > 2 / 3 else "Mid"
    if image.width and image.height and box_w and box_h:
        if (box_w / box_h) > (image.width / image.height) * tolerance:
            return "xMidYMid meet"
    return f"x{fx}Y{fy} slice"


def speckle_pattern(pid: str, seed: int, base: str, white: str, w: float = 300, h: float = 80) -> str:
    """One tile large enough to cover a whole title: a tiled pattern shows
    hairline seams in poppler-based viewers (Okular) and on some printers."""
    rnd = random.Random(seed)
    n = int(w * h / 144 * 34)
    dots = "".join(
        f'<circle cx="{rnd.uniform(0, w):.2f}" cy="{rnd.uniform(0, h):.2f}" '
        f'r="{rnd.choice((0.18, 0.25, 0.32, 0.42)):.2f}"/>' for _ in range(n))
    return (f'<pattern id="{pid}" patternUnits="userSpaceOnUse" x="0" y="50" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="{base}"/>'
            f'<g fill="{white}" fill-opacity="0.85">{dots}</g></pattern>')


def rough_band(x: float, y: float, w: float, h: float, seed: int = 11, jag: float = 1.6) -> str:
    rnd = random.Random(seed)
    top = [(x + i * w / 40, y + rnd.uniform(-0.6, 0.6)) for i in range(41)]
    right = [(x + w + rnd.uniform(-jag * 2, jag), y + j * h / 10) for j in range(1, 10)]
    bottom = [(x + w - i * w / 40, y + h + rnd.uniform(-0.6, 0.6)) for i in range(41)]
    left = [(x + rnd.uniform(-jag, jag * 2), y + h - j * h / 10) for j in range(1, 10)]
    return "M" + " L".join(f"{a:.2f} {c:.2f}" for a, c in top + right + bottom + left) + " Z"


def fit_size(text: str, max_width: float, max_size: float, min_size: float,
             *, tracking_per_em: float = 0.0, bold: bool = True) -> float:
    """The largest font size at which ``text`` fits ``max_width``, between the
    two bounds. Below ``min_size`` the planner reports a violation instead."""
    size = max_size
    while size > min_size:
        if richtext.text_width(text, size, bold=bold, tracking=tracking_per_em * size) <= max_width:
            return size
        size -= 0.5
    return min_size


def text_el(eid: str, text: str, x: float, y: float, size: float, fill: str, *,
            weight: str = "600", anchor: str = "start", tracking: float = 0.0,
            family: str = FONT, extra: str = "") -> str:
    ls = f' letter-spacing="{tracking:.2f}"' if tracking else ""
    fam = f' font-family="{family}"' if family != FONT else ""
    return (f'<text id="{eid}" x="{x:.3f}" y="{y:.3f}" font-size="{size:.3f}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{ls}{fam}{extra}>{escape(text)}</text>')


# ── The blocks ────────────────────────────────────────────────────────────

ROW_H = 27.5   # six rows (two automatic, four own) sit easily in the left column of A3
ICON_S = 19

#: The QR block in the band: the code, its quiet-zone box, and room for the
#: caption under it. Koen, 20 September 2026: his phone could not read the
#: 20 mm code off a computer screen. A QR is read at a distance proportional
#: to its size, so the fix is millimetres.
#: The air between two stacked blocks in a column. Reserved and spent
#: through this one name: the picture's share is computed from what the text
#: needs *including* these gaps, and reserving less than is spent is exactly
#: how the feed image ended up with a line of 6 mm text under a picture that
#: had taken everything (Koen, 21 September 2026).
BLOCK_GAP = 6.0

#: Every row in the band is set in one size, the smallest of the four that
#: used to be there (deadline 6.6, website and e-mail 6.2, a contact 5.6).
#: Koen, 21 September 2026: "is de lettergrootte van alles onder 'Meer info
#: en inschrijven' dezelfde? Dat zou wel de bedoeling moeten zijn." They are
#: one list of ways to reach us, so nothing in it outranks the rest.
BAND_TEXT = 5.6
#: And with a little more air between them, now that they are smaller. The
#: last row drops one millimetre further still, so the block does not end
#: flush against the bottom of the band ("je kan misschien de onderste regel
#: ook nog een milimeter laten zakken").
BAND_ROW_STEP = 7.2

QR_MM = 26.0
QR_BOX = QR_MM + 2
QR_BLOCK = QR_BOX + 6


def highlight_rows(plan: Plan, content: PosterContent, x: float, y: float, w: float,
                   *, index_offset: int = 0) -> tuple[str, float]:
    """Icon + one or two lines each, a dotted rule between rows."""
    pal = plan.pal
    out: list[str] = []
    text_x = x + ICON_S + 5
    text_w = w - ICON_S - 5
    accents = (pal["tile"], pal["accent3"], pal["accent2"], pal["tile"], pal["accent"], pal["tile"])
    for i, hl in enumerate(content.highlights, start=index_offset):
        size = 7.4   # one size, upper case, bold for every row (Koen, 20 September 2026)
        # The first line is drawn bold: wrap on the bold metrics so it fits too.
        lines = richtext.wrap(richtext.parse("**" + hl.text.replace("*", "").upper() + "**"), width=text_w, size=size)
        if len(lines) > 2:
            plan.violations.append(f"Kernpunt {i + 1} past niet in twee regels op deze breedte")
            lines = lines[:2]
        bg = accents[i % len(accents)]
        fg = pal["white"] if bg != pal["accent"] else pal["ink"]
        out.append(icon_svg(hl.icon, fg=fg, bg=bg, x=x, y=y, size=ICON_S))
        # Centre the text block on the icon: one line sits on the icon's
        # middle, two lines straddle it (Koen, 19 September 2026).
        line_step = size * 1.05 + 1
        block_h = size * 0.72 + (len(lines) - 1) * line_step
        ly = y + (ICON_S - block_h) / 2 + size * 0.72
        for j, line in enumerate(lines):
            txt = "".join(r.text for r in line)
            eid = f"t-hl-{i}-{j}"
            out.append(text_el(eid, txt.upper(), text_x, ly, size, pal["ink"], weight="bold"))
            plan.boxes[eid] = text_w
            ly += line_step
        if i - index_offset < len(content.highlights) - 1:
            out.append(f'<line x1="{x}" y1="{y + 23.5}" x2="{x + w}" y2="{y + 23.5}" stroke="{pal["ink"]}" '
                       f'stroke-width="0.4" stroke-dasharray="0.5 1.2" stroke-linecap="round"/>')
        y += ROW_H
    return "".join(out), y


def welcome_row(plan: Plan, content: PosterContent, x: float, y: float, w: float,
                *, icon: float = ICON_S, max_size: float = 10.5) -> tuple[str, float]:
    """Always on the poster (Koen, 19 September 2026): "IEDEREEN WELKOM!" —
    or "ENKEL LEDEN" when the activity is members-only."""
    pal = plan.pal
    text = "ENKEL LEDEN" if content.members_only else "IEDEREEN WELKOM!"
    out = [icon_svg("heart", fg=pal["white"], bg=pal["accent2"], x=x, y=y, size=icon)]
    text_x = x + icon + 5
    text_w = w - icon - 5
    size = fit_size(text, text_w, max_size, 6)
    out.append(text_el("t-welcome-0", text, text_x, y + icon / 2 + size * 0.36, size, pal["ink"], weight="bold"))
    plan.boxes["t-welcome-0"] = text_w
    return "".join(out), y + icon + 5


def welcome_badge(plan: Plan, content: PosterContent, x: float, y: float) -> tuple[str, float]:
    """"IEDEREEN WELKOM!" as an accent, not a row (Koen, 20 September 2026):
    one line on a brush stroke in the light green, with three sparkle
    strokes; "ENKEL LEDEN" the same on the red. Sits above the tile."""
    pal = plan.pal
    members_only = content.members_only
    text = "ENKEL LEDEN" if members_only else "IEDEREEN WELKOM!"
    size = 8.5   # "iets kleiner" (Koen, 20 September 2026)
    tw = richtext.text_width(text, size, bold=True, tracking=0.2)
    band_w = tw + 12
    brush = pal["accent4"] if members_only else pal["accent3"]
    ink = pal["white"] if members_only else pal["ink"]
    out = [f'<path d="{rough_band(x, y, band_w, 12, seed=plan.seed + 7, jag=2.0)}" fill="{brush}" '
           f'fill-opacity="{1 if members_only else 0.45}" filter="url(#rough)"/>',
           text_el("t-welcome-0", text, x + 6, y + 8.6, size, ink, weight="bold", tracking=0.2)]
    plan.boxes["t-welcome-0"] = band_w - 8
    sx = x + band_w + 2.5
    out.append(f'<g stroke="{brush if members_only else pal["ink"]}" stroke-width="1.0" stroke-linecap="round" fill="none">'
               f'<path d="M{sx:.1f} {y + 3:.1f} l3.2 -2.8 M{sx + 1:.1f} {y + 6.3:.1f} l4 0 M{sx:.1f} {y + 9.5:.1f} l3.2 2.8"/></g>')
    return "".join(out), y + 12


def full_bleed_floor(image: ImageBytes, box_w: float, cap: float, floor: float) -> float:
    """The shortest box in which this picture still fills the width.

    Below it, :func:`aspect_for` stops cropping and shows the picture whole,
    so it sits letterboxed in a band of white — "de visualisatie van de foto
    is echt niet OK" (Koen, 21 September 2026). The hero is never given a
    height under this one; the text gives way instead.

    A picture too tall to fill the width inside ``cap`` (a portrait photo in
    a wide box) is letterboxed whatever we do, and keeps the plain floor.
    """
    if not (image.width and image.height):
        return floor
    edge = box_w / (CROP_TOLERANCE * (image.width / image.height))
    return max(floor, edge) if edge <= cap else floor


def hero_height(image: ImageBytes, box_w: float, available: float, *, cap: float, floor: float) -> float:
    """The height the picture wants at this width, clamped to what is left.

    Koen, 20 September 2026: a photo he had cropped shorter still filled a
    tall box, so it was cut at the sides and took the whole page. A picture
    whose pixel size is known now gets the height of its own proportions —
    a wide photo a low strip, a tall one a taller block — and only a picture
    that would not fit at all is cropped."""
    wanted = box_w * image.height / image.width if image.width and image.height else cap
    # Never below the floor: a page that is already full must report its
    # overflow, not shrink the picture into nothing.
    return max(floor, min(wanted, cap, max(available, floor)))


def main_image_block(plan: Plan, image: ImageBytes, x: float, y: float, w: float, h: float) -> tuple[str, float]:
    """The hero photo or drawing with a ragged edge: the filter sits on a mask,
    never on the image (a displaced photo looks warped; a displaced mask looks
    torn)."""
    mask_id = "ragmask-main"
    out = (f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" width="{plan.width}" height="{plan.height}">'
           f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="white" filter="url(#ragged)"/></mask>'
           f'<image x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
           f'preserveAspectRatio="{aspect_for(image, w, h)}" '
           f'mask="url(#{mask_id})" href="{data_uri(image)}"/>')
    return out, y + h


def polaroid_block(plan: Plan, image: ImageBytes, x: float, y: float, w: float, angle: float = -4) -> tuple[str, float]:
    h = w * 0.72
    cx, cy = x + w / 2, y + h / 2
    out = (f'<g transform="rotate({angle} {cx:.2f} {cy:.2f})">'
           f'<rect x="{x}" y="{y}" width="{w}" height="{h:.2f}" fill="#000000" fill-opacity="0.25" transform="translate(1.5 1.8)" filter="url(#paint)"/>'
           f'<rect x="{x}" y="{y}" width="{w}" height="{h:.2f}" fill="{plan.pal["white"]}"/>'
           f'<image x="{x + 2.5}" y="{y + 2.5}" width="{w - 5}" height="{h - 5:.2f}" preserveAspectRatio="{aspect_for(image)}" '
           f'href="{data_uri(image)}"/></g>')
    return out, y + h + 2


def polaroid_on(plan: Plan, image: ImageBytes, rect: tuple[float, float, float, float],
                corner: str, width: float, *, angle: float = 4) -> tuple[str, float]:
    """The polaroid on one corner of the main picture, and the bottom it
    reaches.

    Koen, 20 September 2026: it always sat bottom right, so on a photo whose
    subject is in that corner it covered exactly what mattered. The corner is
    the person's choice now. Bottom corners break the picture's edge by a
    centimetre — that overlap is what makes it look laid on rather than
    pasted in; top corners stay inside."""
    rx, ry, rw, rh = rect
    h = width * 0.72
    x = rx + 6 if corner.endswith("_left") else rx + rw - width - 6
    y = ry + 6 if corner.startswith("top_") else max(ry + 6, ry + rh - h + 10)
    frag, _below = polaroid_block(plan, image, x, y, width, angle=angle if corner.endswith("_right") else -angle)
    return frag, max(ry + rh, y + h)


def dates_grid(plan: Plan, content: PosterContent, x: float, y: float, w: float) -> tuple[str, float]:
    """Up to twelve dates in two columns, the heading on a coloured lid.
    Print only: a feed image carries one line instead (Koen, 20 Sep 2026)."""
    pal = plan.pal
    cols = 2
    dates = content.dates[:12]
    rows = (len(dates) + cols - 1) // cols
    col_w = (w - 4 * cols) / cols
    h = 10 + rows * 14 + 3
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{pal["white"]}" stroke="{pal["ink"]}" stroke-width="0.6"/>',
           f'<rect x="{x}" y="{y}" width="{w}" height="10" fill="{pal["tile"]}"/>',
           text_el("t-dates-head", content.dates_heading or "DATA", x + w / 2, y + 7.3, 7.4,
                   pal["white"] if pal["tile"] != pal["accent"] else pal["ink"], weight="bold", anchor="middle", tracking=0.2)]
    plan.boxes["t-dates-head"] = w - 8
    for i, d in enumerate(dates):
        col, row = i // rows, i % rows
        cx, cy = x + 4 + col * (col_w + 4), y + 13 + row * 14
        out.append(icon_svg("calendar", fg=pal["white"], bg=pal["tile"], x=cx, y=cy + 1.5, size=8))
        eid = f"t-date-{i}"
        out.append(text_el(eid, d, cx + 11, cy + 8, 6.4, pal["accent4"], weight="bold", tracking=0.1))
        plan.boxes[eid] = col_w - 12
        if row < rows - 1:
            out.append(f'<line x1="{cx}" y1="{cy + 13.5}" x2="{cx + col_w - 4}" y2="{cy + 13.5}" stroke="{pal["ink"]}" '
                       f'stroke-width="0.3" stroke-dasharray="0.4 1"/>')
    for c in range(1, cols):
        vx = x + 4 + c * (col_w + 4) - 2
        out.append(f'<line x1="{vx:.2f}" y1="{y + 12}" x2="{vx:.2f}" y2="{y + h - 3}" stroke="{pal["ink"]}" '
                   f'stroke-width="0.3" stroke-dasharray="0.4 1"/>')
    return "".join(out), y + h + 3


def tagline_block(plan: Plan, text: str, x_right: float, y: float, w: float) -> tuple[str, float]:
    """Handwritten line, right-aligned, with the arrow and the underline."""
    pal = plan.pal
    size: float = 10
    tw = richtext.text_width(text, size, bold=True, font=richtext.HAND_FONT)
    if tw > w - 30:
        size = fit_size(text, w - 30, 10, 7, bold=True)
        tw = richtext.text_width(text, size, bold=True, font=richtext.HAND_FONT)
    x0 = x_right - tw
    out = [text_el("t-tagline", text, x_right, y + 9.5, size, pal["accent"] if pal["accent"] != pal["white"] else pal["ink"],
                   weight="bold", anchor="end", family=HAND)]
    plan.boxes["t-tagline"] = w - 30
    ink = pal["ink"]
    out.append(f'<path d="M{x0 - 22:.1f} {y + 1.5} C {x0 - 18:.1f} {y + 8.5}, {x0 - 12:.1f} {y + 10.5}, {x0 - 4:.1f} {y + 6.5} '
               f'M{x0 - 10:.1f} {y + 3.5} L{x0 - 4:.1f} {y + 6.5} L{x0 - 9:.1f} {y + 10.5}" fill="none" stroke="{ink}" '
               f'stroke-width="0.9" stroke-linecap="round" stroke-linejoin="round"/>')
    out.append(f'<path d="M{x0 + 2:.1f} {y + 11.6} C {x0 + tw * 0.4:.1f} {y + 10.8}, {x0 + tw * 0.75:.1f} {y + 12.6}, {x_right:.1f} {y + 11.2}" '
               f'fill="none" stroke="{ink}" stroke-width="0.6" stroke-linecap="round"/>')
    return "".join(out), y + 12.5


def richtext_block(plan: Plan, eid: str, source: str, x: float, y: float, w: float, size: float,
                   *, boxed: bool = False, heading: str = "", trailing: float = 5.0) -> tuple[str, float]:
    pal = plan.pal
    pad = 4 if boxed else 0
    inner_w = w - 2 * pad
    head_h = 8 if heading else 0
    h = (2 * pad + head_h + richtext.text_height(source, width=inner_w, size=size)
         + (1.5 if boxed else 0))
    out = []
    if boxed:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h:.2f}" fill="{pal["white"]}" stroke="{pal["ink"]}" stroke-width="0.6"/>')
    if heading:
        out.append(text_el(f"{eid}-head", heading, x + pad, y + pad + 5.5, 6.4, pal["ink"], weight="bold", tracking=0.2))
        plan.boxes[f"{eid}-head"] = inner_w
    frag, _ = richtext.to_svg(source, x=x + pad, y=y + pad + head_h + size, width=inner_w, size=size,
                              fill=pal["ink"], element_id=eid)
    plan.boxes[eid] = inner_w
    out.append(frag)
    return "".join(out), y + h + trailing


#: Height of the box a sponsor logo is fitted into; it may be twice as wide.
#: Was 16 mm, which left a logo with a tagline under it — MONA's, on Koen's
#: Bowlen poster — too small to read: "kan dat een klein beetje groter worden
#: gemaakt (niet hoger, niet rechtser, dus een beetje meer uitrekken naar
#: links en naar onder, bvb. 20%)?" (21 September 2026).
LOGO_H = 19.2


def logo_strip(plan: Plan, logos: tuple[ImageBytes, ...], x_right: float, y: float, h: float) -> str:
    """Sponsor logos, right-aligned, each at most 2:1 wide.

    Right edge fixed (``xMax``) and centred in its box (``YMid``): a taller
    box therefore grows to the left and a little downwards, which is what
    Koen asked for — not higher, not further right.
    """
    out = []
    x = x_right
    for i, logo in enumerate(logos[:2]):
        w = h * 2
        x -= w
        out.append(f'<image id="logo-{i}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                   f'preserveAspectRatio="xMaxYMid meet" href="{data_uri(logo)}"/>')
        x -= 6
    return "".join(out)


# ── The planner ───────────────────────────────────────────────────────────

def _dates_grid_height(n: int) -> float:
    rows = (n + 1) // 2
    return 10 + rows * 14 + 3 + 3


def _richtext_height(source: str, w: float, size: float) -> float:
    return richtext.text_height(source, width=w, size=size) + 5


def fit_richtext_size(source: str, w: float, available: float, *, max_size: float, min_size: float) -> float:
    """The largest body size whose wrapped text still fits ``available``.

    Koen, 20 September 2026: his Bowlen poster was "vrij leeg" — the text sat
    at its smallest size under a picture that no longer filled the page. The
    body now grows into the room that is left, down to ``min_size`` when
    there is more text than room (the planner reports that as overflow).

    It measures the text itself, not the reserved block around it. Measuring
    the block cost a size step of head-room that nobody could see and that
    the reader would rather have as ink — "gewoon de ruimte onderaan meer
    benutten, bvb. door de fontsize 1 of 2 pixels te doen groeien"
    (21 September 2026).
    """
    size = max_size
    while size > min_size:
        if richtext.text_height(source, width=w, size=size) <= available:
            return round(size, 1)
        size -= 0.2
    return min_size


def when_line(content: PosterContent) -> str:
    """The date line both layouts print, derived once (#1097).

    One date gives the activity's own line; a series gives the count and
    sends the reader to the website, because nobody reads twelve dates off a
    poster. It lived in two branches that had already drifted apart — one
    fell back to "DATA", the other printed an empty heading.
    """
    if content.date_line:
        return content.date_line
    if len(content.dates) > 1:
        return f"{len(content.dates)} {content.dates_heading or 'DATA'} · zie de website"
    return ""


def fact_rows(content: PosterContent) -> tuple[Highlight, ...]:
    """Date and place as icon rows — what the simple preset shows in place of
    typed highlights, on print and on the feed alike (#1097).

    Whoever picks ``eenvoudig`` types no highlights: that is the point of the
    preset. So the feed image drew an empty list and lost the two facts that
    matter most.
    """
    when = when_line(content)
    return tuple(hl for hl in (Highlight("calendar", when, True) if when else None,
                               Highlight("map-pin", content.location) if content.location else None)
                 if hl is not None)


def _two_column_highlights(p: Plan, content: PosterContent, y: float, cols, limit_n: int = 4) -> float:
    shown = content.highlights[:limit_n]
    col_y: list[float] = [y, y]
    for i, hl in enumerate(shown):
        cx, cw_ = cols[i % 2]
        one = PosterContent(duo_code=content.duo_code, highlights=(hl,))
        frag, ny = highlight_rows(p, one, cx, col_y[i % 2], cw_, index_offset=i)
        p.full += frag
        col_y[i % 2] = ny
    if len(content.highlights) > limit_n:
        p.violations.append(f"Deze opmaak toont ten hoogste {limit_n} kernpunten")
    return max(col_y)


def plan_affiche(content: PosterContent, *, layout: str, width: float, height: float,
                 pal: dict[str, str]) -> Plan:
    """Round 3 (Koen, 19 September 2026): the title at the top over the full
    width, both lines the same size; the lockup in the band at the bottom
    left; one picture fills the whole right column; "iedereen welkom" always;
    the third picture takes the bottom-left spot unless sponsor logos do.
    Three presets: ``beeld`` (picture right, highlights left), ``tekst``
    (highlights left, description right) and ``eenvoudig`` (one big picture
    over the full width, a few highlights under it — the Bowlen poster,
    half of what the unit makes)."""
    frame = 9.0
    p = Plan(width=width, height=height, frame=frame, pal=pal, seed=content.seed)
    x0, y0, x1, y1 = frame, frame, width - frame, height - frame

    # ── Title: one or two lines, one size, at the top ─────────────────────
    title_w = width - 2 * frame - 16
    lines = [t for t in content.title_lines if t][:2]
    if not lines:
        p.violations.append("Geen titel")
    with_badge = bool(content.title_joiner) and len(lines) == 2
    line_widths = (title_w, title_w - (62 if with_badge else 0))
    max_size = 51.0 if layout == "print_a" else 44.0
    size = max_size
    for i, text in enumerate(lines):
        size = min(size, fit_size(text, line_widths[i], max_size, 24, tracking_per_em=-0.016))
    for i, text in enumerate(lines):
        if richtext.text_width(text, size, bold=True, tracking=-0.016 * size) > line_widths[i]:
            p.violations.append(f"Titelregel {i + 1} is te lang voor de affiche")
    base1 = frame + 12 + size * 0.72          # cap height ≈ 0.72 em
    step = size * 1.08
    baselines = [base1 + i * step for i in range(len(lines))]
    for i, text in enumerate(lines):
        # One line is centred; two lines keep the staggered left/right of the
        # house style (Koen, 20 September 2026).
        if len(lines) == 1:
            anchor, x = "middle", width / 2
        else:
            anchor = "start" if i == 0 else "end"
            x = 17 if i == 0 else width - 17
        p.title.append({"id": f"t-title-{i}", "text": text, "x": x, "y": baselines[i], "size": size,
                        "anchor": anchor, "tracking": -0.016 * size, "pattern": f"sp{i + 1}",
                        "stroke": pal["tile"] if i == 0 else pal["accent4"]})
        p.boxes[f"t-title-{i}"] = line_widths[i]
    if with_badge:
        p.joiner = {"text": content.title_joiner, "cx": 44, "cy": baselines[1] - size * 0.36}
        p.boxes["t-joiner"] = 44
    y_after_title = (baselines[-1] if lines else frame + 40) + 6
    if content.bar_text:
        bar_w = 130.0
        bsize = fit_size(content.bar_text, bar_w - 12, 12.5, 7, tracking_per_em=0.024)
        p.bar = {"path": rough_band(width - frame - 8 - bar_w, y_after_title, bar_w, 17, seed=content.seed + 3),
                 "text": content.bar_text, "x": width - frame - 8 - bar_w / 2, "y": y_after_title + 12.3, "size": bsize}
        p.boxes["t-bar"] = bar_w - 12
        y_after_title += 17
    top_y: float = y_after_title + 10

    # ── Bottom: the lockup in a rounded corner tile at the left (the arc Koen
    #    liked at the top, now bottom-left), the rough info band to its right ──
    # The band's rows, one per line: the website always; the association's
    # e-mail and gsm only when nobody is a contact person (CR-10 §3.9 — with a
    # contact person the association's own lines stay off the poster; Koen,
    # 20 September 2026); else one row per contact, "Naam · gsm · e-mail".
    # The band's own geometry does not depend on its rows, and a contact row
    # needs to know how wide it may be before it is built.
    lockup_w = 66.0
    lockup_h = lockup_w * 245 / 491
    cw, r = lockup_w + 14, 18.0
    band_x = x0 + cw + 5
    col_x = band_x + 7
    text_left = col_x + 8
    qr_left = width - frame - 2 - QR_BOX - 8
    row_w = qr_left - text_left - 4

    rows: list[dict[str, object]] = []
    if content.deadline_text:
        # The one line that asks for something (Koen, 20 September 2026):
        # above the address it points at. White like the rows under it — its
        # accent-coloured ticket icon carries the emphasis (Koen, 20 Sep, second look).
        rows.append({"id": "t-deadline", "icon": "ticket", "bg": pal["accent"], "fg": pal["ink"],
                     "text": content.deadline_text, "size": BAND_TEXT, "colour": pal["white"]})
    rows.append({"id": "t-website", "icon": "globe", "bg": pal["accent3"], "fg": pal["white"],
                 "text": content.website, "size": BAND_TEXT, "colour": pal["white"]})
    if content.contacts:
        for i, c in enumerate(content.contacts[:3]):
            # Name, mobile and address on one line while it fits, and over two
            # when it does not: "Natascha Furleo · 0123 456 789 ·
            # furleonatascha@hotmail.com" measures 171 mm against a column of
            # 133. Shrinking it is what put two sizes in one band; the second
            # line keeps every row in the one size (Koen, 21 September 2026).
            parts = [part for part in (c.name, c.mobile, c.email) if part]
            row = {"id": f"t-contact-{i}", "icon": "users", "bg": pal["accent"], "fg": pal["ink"],
                   "text": " · ".join(parts), "size": BAND_TEXT, "colour": pal["white"]}
            if len(parts) > 1 and richtext.text_width(str(row["text"]), BAND_TEXT) > row_w:
                row["text"] = " · ".join(parts[:-1])
                rows.append(row)
                # The address alone, under the name, with no icon of its own:
                # it is the same contact, not a second one.
                rows.append({"id": f"t-contact-{i}-b", "icon": "", "bg": pal["accent"], "fg": pal["ink"],
                             "text": parts[-1], "size": BAND_TEXT, "colour": pal["white"]})
            else:
                rows.append(row)
    else:
        if content.email:
            rows.append({"id": "t-email", "icon": "mail", "bg": pal["accent2"], "fg": pal["white"],
                         "text": content.email, "size": BAND_TEXT, "colour": pal["white"]})
        if content.association_mobile:
            rows.append({"id": "t-mobile", "icon": "mobile", "bg": pal["accent"], "fg": pal["ink"],
                         "text": content.association_mobile, "size": BAND_TEXT, "colour": pal["white"]})
    # The band never gets shorter than the QR block: a sparse poster with one
    # row used to squeeze the code half out of the band.
    band_h: float = max(20 + BAND_ROW_STEP * len(rows), QR_BLOCK + 2)
    band_y: float = y1 - band_h - 2
    p.band_y = band_y
    ch = max(band_h + 2, lockup_h + 7)
    # The paper: the frame's inner rectangle minus the corner tile bottom-left.
    p.paper_path = (f"M{x0} {y0} H{x1} V{y1} H{x0 + cw} V{y1 - ch + r} "
                    f"A{r} {r} 0 0 0 {x0 + cw - r} {y1 - ch} H{x0} Z")
    # The lockup sits flush: the R starts on the paper's left edge, the
    # baseline's bottom on the frame's bottom bar (Koen, 20 September 2026).
    tile_top = y1 - ch
    # The R starts 4 mm in from the paper's left edge, the baseline's bottom
    # on the frame's bottom bar; little purple above and right of it.
    p.lockup = {"x": x0 + 4, "y": y1 - 2 - lockup_h, "width": lockup_w}
    # The welcome badge sits above the tile; the left column stops above it.
    welcome_y = tile_top - 14
    left_limit = welcome_y - 2
    for row in rows:
        # A long row shrinks a little rather than overflow.
        # Only a row too long for its width drops below the one size.
        row["size"] = fit_size(str(row["text"]), row_w, float(row["size"]), 4.4, bold=False)  # type: ignore[arg-type]
        p.boxes[str(row["id"])] = row_w
    p.band = {"path": rough_band(band_x, band_y, x1 - 2 - band_x, band_h, seed=content.seed + 5, jag=2.5),
              "y": band_y, "h": band_h, "rows": rows, "label": content.more_info_label,
              "icon_x": col_x, "text_x": text_left,
              "row_step": BAND_ROW_STEP,
              "qr_x": qr_left, "qr_y": band_y + (band_h - QR_BLOCK) / 2, "qr_caption": "Scan voor meer info",
              "qr_box": QR_BOX, "qr_mm": QR_MM,
              "row_y": band_y + 2}

    # ── Content between title and band ─────────────────────────────────────
    limit: float = band_y - 3
    lx, lw = 19.0, 119.0
    rx, rw = 151.0, width - frame - 4 - 151
    full_w = width - lx - frame - 4 - 6
    left: list[str] = []
    right: list[str] = []
    y: float
    if content.logos:
        limit -= 22
        p.logos = logo_strip(p, content.logos, width - frame - 4, band_y - 21, LOGO_H)

    if content.preset == "eenvoudig":
        # Koen, 19 September 2026 (evening): one big picture, then the
        # activity's text over the full width, and a smaller "iedereen
        # welkom" low on the page. Since 20 September the feed image is laid
        # out the same way — "zou je instagram voor de eenvoudige opmaak niet
        # gelijk trekken aan de A3?" — because it was two thirds empty
        # without the text, and the facts hung under the picture instead of
        # above it. Only three numbers differ; the shape does not.
        feed = layout == "feed_portrait"
        if feed and content.logos:
            # The sponsor strip sits *beside* the welcome badge, not under the
            # text: it runs from 21 mm above the band to 5 mm above it, and
            # the column already stops 16 mm above the band. Only those last
            # five millimetres overlap. Reserving 22 mm for it (which is what
            # this did) kept a band of white under every text on a design
            # with a sponsor — Koen, 21 September 2026: "ik zou denken dat de
            # tekst onder de foto nog één fontgrootte groter kan".
            left_limit -= 5
        hero_cap, hero_floor, polaroid_w = (120.0, 50.0, 84.0) if feed else (200.0, 60.0, 91.0)
        # The picture takes its own share first and the text fills what is
        # left. Round 20 turned that around — the text was promised a
        # comfortable size and the picture paid for it — and the picture
        # ended up a band. Koen, 21 September 2026: "de tekst moest niet
        # zoveel groter, gewoon de ruimte onderaan meer benutten".
        # 5.0 on a feed image is about 18 pixels of a 1080-wide post: small,
        # but it is what keeps a crowded square inside its edges.
        min_text, max_text = (5.0, 10.0) if feed else (7.2, 11.0)
        y = top_y - 4
        # When and where above the picture, in the same icon rows the other
        # presets use — date left, place right (Koen, 20 September 2026).
        top_rows = fact_rows(content)
        if top_rows:
            y = _two_column_highlights(p, PosterContent(duo_code=content.duo_code, highlights=top_rows),
                                       y, ((lx, lw), (rx, rw))) + 3
        # What the text needs at its smallest, so the picture cannot take the
        # whole column.
        min_h = _richtext_height(content.explanation_md, full_w, min_text) if content.explanation_md else 0.0
        if content.main_image:
            hero_top = y
            space = left_limit - y - 2 * BLOCK_GAP - (10 if content.inset_image else 0)
            # The picture is never given a height at which it would be shown
            # whole with white beside it. On a crowded page the text gives
            # way instead, and if even that is not enough the planner reports
            # the overflow — it does not turn the hero into a letterboxed
            # block to make the numbers work.
            frag, y = main_image_block(
                p, content.main_image, lx, y, full_w,
                hero_height(content.main_image, full_w, space - min_h, cap=hero_cap,
                            floor=full_bleed_floor(content.main_image, full_w, hero_cap, hero_floor)))
            p.full += frag
            if content.inset_image:
                # The polaroid lies on the big picture, in the chosen corner;
                # the big picture stays the same size with or without it.
                frag, bottom = polaroid_on(p, content.inset_image, (lx, hero_top, full_w, y - hero_top),
                                           content.inset_corner, polaroid_w)
                p.full += frag
                y = bottom
            y += BLOCK_GAP
        if content.explanation_md:
            # The real room under the picture: the block starts 2 mm lower
            # and must end before the welcome badge.
            text_size = fit_richtext_size(content.explanation_md, full_w, left_limit - y - 4,
                                          max_size=max_text, min_size=min_text)
            # Nothing follows this block but the welcome badge, which keeps
            # its own margin, so it does not need a trailing gap of its own.
            frag, y = richtext_block(p, "t-rt-explanation", content.explanation_md, lx, y + 2, full_w,
                                     text_size, trailing=0.0)
            p.full += frag
        frag, _wy = welcome_badge(p, content, lx, welcome_y)
        p.full += frag
        if y > left_limit + (0.5 if feed else 0.0):
            p.violations.append(f"Te veel inhoud: {y - left_limit:.0f} mm te veel")
    elif layout == "feed_portrait":
        # Instagram (Koen, 20 September 2026): title, one picture over the
        # full width with the polaroid on it, every highlight row in two
        # columns, the dates grid, the welcome badge above the tile. The
        # description and the third picture stay off the feed image.
        y = top_y - 4
        n = min(len(content.highlights), 6)
        hl_rows = (n + 1) // 2
        series = len(content.dates) > 1
        if content.logos:
            left_limit -= 22   # the logo strip sits in the flow's way on a feed image
        below = hl_rows * ROW_H + 6 + (ROW_H if series else 0) + (10 if content.inset_image else 0)
        if content.main_image:
            avail = left_limit - y - below
            hero_top = y
            frag, y = main_image_block(p, content.main_image, lx, y, full_w,
                                       hero_height(content.main_image, full_w, avail, cap=120.0, floor=50.0))
            p.full += frag
            if content.inset_image:
                frag, bottom = polaroid_on(p, content.inset_image, (lx, hero_top, full_w, y - hero_top),
                                           content.inset_corner, 84.0)
                p.full += frag
                y = bottom
            y += 6
        y = _two_column_highlights(p, content, y, ((lx, lw), (rx, rw)), limit_n=6)
        if series:
            # Koen, 20 September 2026: nobody reads twelve dates while
            # scrolling, and the QR already leads to the site. One row in the
            # highlights' own typography, over the full width.
            summary = PosterContent(duo_code=content.duo_code,
                                    highlights=(Highlight("calendar", when_line(content), True),))
            frag, y = highlight_rows(p, summary, lx, y, full_w, index_offset=6)
            p.full += frag
        frag, _wy = welcome_badge(p, content, lx, welcome_y)
        p.full += frag
        if y > left_limit + 0.5:
            p.violations.append(f"Te veel inhoud: {y - left_limit:.0f} mm te veel")
    else:
        ly: float = top_y
        ry: float = top_y
        if content.highlights:
            frag, ly = highlight_rows(p, content, lx, ly, lw)
            left.append(frag)
        if content.third_image and content.preset != "tekst":
            frag, ly = polaroid_block(p, content.third_image, lx + 8, ly + 4, 88, angle=3)
            left.append(frag)
        frag, _wy = welcome_badge(p, content, lx, welcome_y)
        left.append(frag)

        if content.preset == "tekst":
            if content.dates and len(content.dates) > 1:
                frag, ry = dates_grid(p, content, rx, ry, rw)
                right.append(frag)
            if content.tagline:
                frag, ry = tagline_block(p, content.tagline, rx + rw, ry, rw)
                right.append(frag)
            if content.explanation_md:
                frag, ry = richtext_block(p, "t-rt-explanation", content.explanation_md, rx, ry + 2, rw, 7.2)
                right.append(frag)
        else:
            # The picture takes what the other right-hand blocks leave.
            fixed = 0.0
            if content.inset_image:
                fixed += 88 * 0.72 + 2 - 45 + 2
            if content.dates and len(content.dates) > 1:
                fixed += _dates_grid_height(len(content.dates[:12]))
            if content.tagline:
                fixed += 12.5
            if content.explanation_md:
                fixed += _richtext_height(content.explanation_md, rw, 6.4)
            hero_h = limit - ry - fixed - 6
            hero_rect: tuple[float, float, float, float] | None = None
            if content.main_image:
                hero_top = ry - 2
                frag, ry = main_image_block(p, content.main_image, rx + 3, hero_top, rw - 8,
                                            hero_height(content.main_image, rw - 8, hero_h, cap=240.0, floor=60.0))
                right.append(frag)
                hero_rect = (rx + 3, hero_top, rw - 8, ry - hero_top)
            if content.inset_image and hero_rect:
                frag, ry = polaroid_on(p, content.inset_image, hero_rect, content.inset_corner, 105.0)
                right.append(frag)
            elif content.inset_image:
                frag, ry = polaroid_block(p, content.inset_image, rx, ry + 2, 105.0)
                right.append(frag)
            elif content.main_image:
                ry += 6
            if content.dates and len(content.dates) > 1:
                frag, ry = dates_grid(p, content, rx, ry, rw)
                right.append(frag)
            if content.tagline:
                frag, ry = tagline_block(p, content.tagline, rx + rw, ry, rw)
                right.append(frag)
            if content.explanation_md:
                frag, ry = richtext_block(p, "t-rt-explanation", content.explanation_md, rx, ry, rw, 6.4)
                right.append(frag)
        for name, bottom, bound in (("links", ly, left_limit), ("rechts", ry, limit)):
            if bottom > bound + 0.5:   # half a millimetre is rounding, not overflow
                p.violations.append(f"Te veel inhoud in de kolom {name}: {bottom - bound:.0f} mm te veel")
    p.left, p.right = "".join(left), "".join(right)
    return p

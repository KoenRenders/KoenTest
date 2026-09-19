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
from app.domains.designstudio.content import ImageBytes, PosterContent
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


def aspect_for(image: ImageBytes) -> str:
    """Map the focal point to SVG's nine-point crop. Coarse, and honest about
    it: a finer crop needs the image size, which the renderer does not read."""
    fx = "Min" if image.focus_x < 1 / 3 else "Max" if image.focus_x > 2 / 3 else "Mid"
    fy = "Min" if image.focus_y < 1 / 3 else "Max" if image.focus_y > 2 / 3 else "Mid"
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

ROW_H = 27.5
ICON_S = 19


def highlight_rows(plan: Plan, content: PosterContent, x: float, y: float, w: float,
                   *, index_offset: int = 0) -> tuple[str, float]:
    """Icon + one or two lines each, a dotted rule between rows."""
    pal = plan.pal
    out: list[str] = []
    text_x = x + ICON_S + 5
    text_w = w - ICON_S - 5
    accents = (pal["tile"], pal["accent3"], pal["accent2"], pal["tile"], pal["accent"], pal["tile"])
    for i, hl in enumerate(content.highlights, start=index_offset):
        size = 8.2 if hl.emphasis else 7.4
        # The first line is drawn bold: wrap on the bold metrics so it fits too.
        lines = richtext.wrap(richtext.parse("**" + hl.text.replace("*", "") + "**"), width=text_w, size=size)
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
            out.append(text_el(eid, txt, text_x, ly, size, pal["ink"], weight="bold" if hl.emphasis or j == 0 else "600"))
            plan.boxes[eid] = text_w
            ly += line_step
        if i - index_offset < len(content.highlights) - 1:
            out.append(f'<line x1="{x}" y1="{y + 23.5}" x2="{x + w}" y2="{y + 23.5}" stroke="{pal["ink"]}" '
                       f'stroke-width="0.4" stroke-dasharray="0.5 1.2" stroke-linecap="round"/>')
        y += ROW_H
    return "".join(out), y


def welcome_row(plan: Plan, content: PosterContent, x: float, y: float, w: float) -> tuple[str, float]:
    """Always on the poster (Koen, 19 September 2026): "IEDEREEN WELKOM!" —
    or "ENKEL LEDEN" when the activity is members-only."""
    pal = plan.pal
    text = "ENKEL LEDEN" if content.members_only else "IEDEREEN WELKOM!"
    out = [icon_svg("heart", fg=pal["white"], bg=pal["accent2"], x=x, y=y, size=ICON_S)]
    text_x = x + ICON_S + 5
    text_w = w - ICON_S - 5
    size = fit_size(text, text_w, 10.5, 7)
    out.append(text_el("t-welcome-0", text, text_x, y + 9.5, size, pal["ink"], weight="bold"))
    plan.boxes["t-welcome-0"] = text_w
    return "".join(out), y + 24


def main_image_block(plan: Plan, image: ImageBytes, x: float, y: float, w: float, h: float) -> tuple[str, float]:
    """The hero photo or drawing with a ragged edge: the filter sits on a mask,
    never on the image (a displaced photo looks warped; a displaced mask looks
    torn)."""
    mask_id = "ragmask-main"
    out = (f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" width="{plan.width}" height="{plan.height}">'
           f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="white" filter="url(#ragged)"/></mask>'
           f'<image x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" preserveAspectRatio="{aspect_for(image)}" '
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


def dates_grid(plan: Plan, content: PosterContent, x: float, y: float, w: float) -> tuple[str, float]:
    """Up to twelve dates in two columns, the heading on a coloured lid."""
    pal = plan.pal
    dates = content.dates[:12]
    rows = (len(dates) + 1) // 2
    col_w = (w - 8) / 2
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
    if rows > 1 or len(dates) > 1:
        out.append(f'<line x1="{x + w / 2}" y1="{y + 12}" x2="{x + w / 2}" y2="{y + h - 3}" stroke="{pal["ink"]}" '
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
                   *, boxed: bool = False, heading: str = "") -> tuple[str, float]:
    pal = plan.pal
    pad = 4 if boxed else 0
    inner_w = w - 2 * pad
    lines = richtext.line_count(source, width=inner_w, size=size)
    step = size * 1.3
    head_h = 8 if heading else 0
    h = 2 * pad + head_h + lines * step + (1.5 if boxed else 0)
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
    return "".join(out), y + h + 5


def logo_strip(plan: Plan, logos: tuple[ImageBytes, ...], x_right: float, y: float, h: float) -> str:
    """Sponsor logos, right-aligned, each at most 2:1 wide."""
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
    return richtext.line_count(source, width=w, size=size) * size * 1.3 + 5


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
    contacts: list[dict[str, object]] = [
        {"text": " · ".join(part for part in (c.name, c.mobile, c.email) if part),
         "icon": "users" if c.name else "mobile"} for c in content.contacts[:3]]
    # Rows: heading, website, e-mail, one per contact — stacked, since the
    # tile takes a third of the width.
    band_h: float = 33 + 6.5 * len(contacts)
    band_y: float = y1 - band_h - 2
    p.band_y = band_y
    cw, r = 92.0, 22.0
    ch = band_h + 8
    # The paper: the frame's inner rectangle minus the corner tile bottom-left.
    p.paper_path = (f"M{x0} {y0} H{x1} V{y1} H{x0 + cw} V{y1 - ch + r} "
                    f"A{r} {r} 0 0 0 {x0 + cw - r} {y1 - ch} H{x0} Z")
    lockup_w = 66.0
    lockup_h = lockup_w * 245 / 491
    p.lockup = {"x": x0 + (cw - r / 2 - lockup_w) / 2 + 2, "y": y1 - ch + (ch - lockup_h) / 2, "width": lockup_w}
    band_x = x0 + cw + 5
    col_x = band_x + 7
    text_left = col_x + 8
    qr_left = width - frame - 2 - 24
    p.band = {"path": rough_band(band_x, band_y, x1 - 2 - band_x, band_h, seed=content.seed + 5, jag=2.5),
              "y": band_y, "h": band_h, "website": content.website, "email": content.email,
              "contacts": contacts, "label": content.more_info_label,
              "icon_x": col_x, "text_x": text_left,
              "qr_x": qr_left, "qr_y": band_y + (band_h - 22) / 2,
              "row_y": band_y + 2}
    row_w = qr_left - text_left - 4
    p.boxes["t-website"] = row_w
    p.boxes["t-email"] = row_w
    for i, line in enumerate(contacts):
        # A long name with gsm and e-mail shrinks a little rather than overflow.
        line["size"] = fit_size(str(line["text"]), row_w, 5.6, 4.4, bold=False)
        p.boxes[f"t-contact-{i}"] = row_w

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
        p.logos = logo_strip(p, content.logos, width - frame - 4, band_y - 21, 16)

    if layout == "feed_portrait" or content.preset == "eenvoudig":
        # One picture over the full width, a few highlights under it, welcome,
        # and (print only) the description under that.
        y = top_y - 4
        n = min(len(content.highlights), 4)
        rows = (n + 1) // 2
        with_text = layout == "print_a" and bool(content.explanation_md)
        below = rows * ROW_H + 24 + 6 + (_richtext_height(content.explanation_md, full_w, 6.6) + 4 if with_text else 0)
        if content.main_image:
            avail = limit - y - below
            cap = 110.0 if layout == "feed_portrait" else 190.0
            frag, y = main_image_block(p, content.main_image, lx, y, full_w, max(50.0, min(cap, avail)))
            p.full += frag
            y += 6
        y = _two_column_highlights(p, content, y, ((lx, lw), (rx, rw)))
        frag, y = welcome_row(p, content, lx, y, lw)
        p.full += frag
        if with_text:
            frag, y = richtext_block(p, "t-rt-explanation", content.explanation_md, lx, y + 2, full_w, 6.6)
            p.full += frag
        if y > limit:
            p.violations.append(f"Te veel inhoud: {y - limit:.0f} mm te veel")
    else:
        ly: float = top_y
        ry: float = top_y
        if content.highlights:
            frag, ly = highlight_rows(p, content, lx, ly, lw)
            left.append(frag)
        frag, ly = welcome_row(p, content, lx, ly, lw)
        left.append(frag)
        if content.third_image and not content.logos and content.preset != "tekst":
            frag, ly = polaroid_block(p, content.third_image, lx + 8, ly + 4, 88, angle=3)
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
            if content.main_image:
                frag, ry = main_image_block(p, content.main_image, rx + 3, ry - 2, rw - 8,
                                            max(60.0, min(hero_h, 240.0)))
                right.append(frag)
            if content.inset_image:
                overlap = 45 if content.main_image else 0
                frag, ry = polaroid_block(p, content.inset_image, rx, ry - overlap + 2, 88)
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
        for name, bottom in (("links", ly), ("rechts", ry)):
            if bottom > limit:
                p.violations.append(f"Te veel inhoud in de kolom {name}: {bottom - limit:.0f} mm te veel")
    p.left, p.right = "".join(left), "".join(right)
    return p

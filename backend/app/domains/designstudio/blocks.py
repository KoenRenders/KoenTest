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
    kicker: str = ""
    title: list[dict] = field(default_factory=list)
    joiner: dict | None = None
    bar: dict | None = None
    left: str = ""      # SVG fragments, already positioned
    right: str = ""
    full: str = ""
    band: dict = field(default_factory=dict)
    logos: str = ""
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
        ly = y + 8.2
        for j, line in enumerate(lines):
            txt = "".join(r.text for r in line)
            eid = f"t-hl-{i}-{j}"
            out.append(text_el(eid, txt, text_x, ly, size, pal["ink"], weight="bold" if hl.emphasis or j == 0 else "600"))
            plan.boxes[eid] = text_w
            ly += size * 1.05 + 1
        if i - index_offset < len(content.highlights) - 1:
            out.append(f'<line x1="{x}" y1="{y + 23.5}" x2="{x + w}" y2="{y + 23.5}" stroke="{pal["ink"]}" '
                       f'stroke-width="0.4" stroke-dasharray="0.5 1.2" stroke-linecap="round"/>')
        y += ROW_H
    return "".join(out), y


def welcome_row(plan: Plan, content: PosterContent, x: float, y: float, w: float) -> tuple[str, float]:
    pal = plan.pal
    out = [icon_svg("heart", fg=pal["white"], bg=pal["accent2"], x=x, y=y, size=ICON_S)]
    text_x = x + ICON_S + 5
    text_w = w - ICON_S - 5
    size = fit_size("IEDEREEN WELKOM!", text_w, 10.5, 7)
    out.append(text_el("t-welcome-0", "IEDEREEN WELKOM!", text_x, y + 8.2, size, pal["ink"], weight="bold"))
    plan.boxes["t-welcome-0"] = text_w
    if content.welcome_line:
        out.append(text_el("t-welcome-1", content.welcome_line, text_x, y + 8.2 + 5.8, 4.6, pal["ink"]))
        plan.boxes["t-welcome-1"] = text_w
    return "".join(out), y + 22


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


def price_block(plan: Plan, text: str, x: float, y: float, w: float) -> tuple[str, float]:
    pal = plan.pal
    size = fit_size(text, w - 16, 12, 7)
    out = [icon_svg("euro", fg=pal["white"], bg=pal["accent3"], x=x, y=y, size=ICON_S),
           text_el("t-price", text, x + ICON_S + 5, y + 12.5, size, pal["ink"], weight="bold")]
    plan.boxes["t-price"] = w - ICON_S - 5
    return "".join(out), y + 24


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

def plan_affiche(content: PosterContent, *, layout: str, width: float, height: float,
                 pal: dict[str, str]) -> Plan:
    frame = 9.0
    p = Plan(width=width, height=height, frame=frame, pal=pal, seed=content.seed)
    x0, y0, x1, y1 = frame, frame, width - frame, height - frame
    cw, ch, r = 92.0, 50.0, 22.0
    p.paper_path = (f"M{x0 + cw} {y0} H{x1} V{y1} H{x0} V{y0 + ch} H{x0 + cw - r} "
                    f"A{r} {r} 0 0 0 {x0 + cw} {y0 + ch - r} Z")
    p.kicker = content.kicker

    # Title: one or two lines, each fitted to the paper width.
    title_w = width - 2 * frame - 16
    lines = [t for t in content.title_lines if t][:2]
    if not lines:
        p.violations.append("Geen titel")
    top: float = 101 if len(lines) == 2 else 118
    for i, text in enumerate(lines):
        size = fit_size(text, title_w if i == 0 else title_w - 10, 51 if i == 0 else 46, 24, tracking_per_em=-0.016)
        if richtext.text_width(text, size, bold=True, tracking=-0.016 * size) > (title_w if i == 0 else title_w - 10):
            p.violations.append(f"Titelregel {i + 1} is te lang voor de affiche")
        anchor = "start" if i == 0 else "end"
        x = 17 if i == 0 else width - 17
        ty = top if i == 0 else top + 46
        p.title.append({"id": f"t-title-{i}", "text": text, "x": x, "y": ty, "size": size, "anchor": anchor,
                        "tracking": -0.016 * size, "pattern": f"sp{i + 1}",
                        "stroke": pal["tile"] if i == 0 else pal["accent4"]})
        p.boxes[f"t-title-{i}"] = title_w if i == 0 else title_w - 10
    if len(lines) == 2 and content.title_joiner:
        p.joiner = {"text": content.title_joiner, "cx": 44, "cy": 131}
        p.boxes["t-joiner"] = 44
    if content.bar_text:
        bar_y = 152 if len(lines) == 2 else 128
        size = fit_size(content.bar_text, 118, 12.5, 7, tracking_per_em=0.024)
        p.bar = {"path": rough_band(147, bar_y, 130, 17, seed=content.seed + 3), "text": content.bar_text,
                 "x": 212, "y": bar_y + 12.3, "size": size}
        p.boxes["t-bar"] = 118

    # Band at the bottom, one left-aligned column of rows: the heading, then
    # website and e-mail side by side (icon + text), then one row per contact
    # person — "Naam · gsm · e-mail" — so the band grows 6.5 mm per contact
    # (at most three, #1004) and nothing floats. The QR sits at the right,
    # centred on the band's height.
    contacts = [" · ".join(part for part in (c.name, c.mobile, c.email) if part) for c in content.contacts[:3]]
    band_h: float = 26 + 6.5 * len(contacts)
    band_y: float = y1 - band_h - 2
    p.band_y = band_y
    text_left = frame + 2 + 13          # after a 6 mm icon at frame + 2 + 5
    qr_left = width - frame - 2 - 24
    p.band = {"path": rough_band(frame + 2, band_y, width - 2 * frame - 4, band_h, seed=content.seed + 5, jag=2.5),
              "y": band_y, "h": band_h, "website": content.website, "email": content.email,
              "contacts": contacts, "label": content.more_info_label,
              "icon_x": frame + 2 + 5, "text_x": text_left, "col2_icon_x": 132, "col2_text_x": 140,
              "qr_x": qr_left, "qr_y": band_y + (band_h - 22) / 2}
    p.boxes["t-website"] = 132 - text_left - 4
    p.boxes["t-email"] = qr_left - 140 - 4
    for i, _line in enumerate(contacts):
        p.boxes[f"t-contact-{i}"] = qr_left - text_left - 4

    # Content area between the title and the band, two columns.
    top_y: float = 186 if (len(lines) == 2 or content.bar_text) else 150
    limit: float = band_y - 1
    lx, lw = 19.0, 119.0
    rx, rw = 151.0, width - frame - 4 - 151
    left: list[str] = []
    right: list[str] = []
    full: list[str] = []
    y: float

    if content.logos:
        limit -= 22
        p.logos = logo_strip(p, content.logos, width - frame - 4, band_y - 21, 16)

    if layout == "feed_portrait":
        y = top_y - 4
        shown = content.highlights[:4]
        rows = (len(shown) + 1) // 2
        if content.main_image:
            # The hero takes what the highlights and the band leave: a taller
            # band (contact rows) shortens the photo, never the checks.
            avail = limit - y - 6 - rows * ROW_H
            frag, y = main_image_block(p, content.main_image, lx, y, width - lx - frame - 4 - 6,
                                       max(50.0, min(85.0, avail)))
            full.append(frag)
            y += 6
        cols = ((lx, lw), (rx, rw))
        col_y: list[float] = [y, y]
        for i, hl in enumerate(shown):
            cx, cw_ = cols[i % 2]
            one = PosterContent(duo_code=content.duo_code, highlights=(hl,))
            frag, ny = highlight_rows(p, one, cx, col_y[i % 2], cw_, index_offset=i)
            full.append(frag)
            col_y[i % 2] = ny
        if len(content.highlights) > 4:
            p.violations.append("Instagram toont ten hoogste vier kernpunten")
        p.full = "".join(full)
        y = max(col_y)
        if y > limit:
            p.violations.append(f"Te veel inhoud: {y - limit:.0f} mm te veel")
    elif content.preset == "tekst":
        y = top_y
        if content.highlights:
            frag, y = highlight_rows(p, content, lx, y, lw)
            left.append(frag)
            y2 = top_y
            if content.dates and len(content.dates) > 1:
                frag, y2 = dates_grid(p, content, rx, y2, rw)
                right.append(frag)
            y = max(y, y2)
        if content.explanation_md:
            frag, y = richtext_block(p, "t-rt-explanation", content.explanation_md, lx, y + 2, width - lx - frame - 4, 7.2)
            full.append(frag)
        if content.programme_md:
            frag, y = richtext_block(p, "t-rt-programme", content.programme_md, lx, y, width - lx - frame - 4, 6.6,
                                     boxed=True, heading="PROGRAMMA")
            full.append(frag)
        if content.practical_md:
            frag, y = richtext_block(p, "t-rt-practical", content.practical_md, lx, y, width - lx - frame - 4, 6.6,
                                     boxed=True, heading="PRAKTISCH")
            full.append(frag)
        if content.price_text:
            frag, y = price_block(p, content.price_text, lx, y, lw)
            full.append(frag)
        if content.welcome_line:
            frag, y = welcome_row(p, content, lx, y, lw)
            full.append(frag)
        p.full = "".join(full)
        if y > limit:
            p.violations.append(f"Te veel inhoud: {y - limit:.0f} mm te veel")
    else:
        ly: float = top_y
        ry: float = top_y
        if content.highlights:
            frag, ly = highlight_rows(p, content, lx, ly, lw)
            left.append(frag)
        if content.main_image:
            frag, ry = main_image_block(p, content.main_image, rx + 3, ry - 4, rw - 8, 102)
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
        if content.practical_md:
            frag, ry = richtext_block(p, "t-rt-practical", content.practical_md, rx, ry, rw, 6.2,
                                      boxed=True, heading="PRAKTISCH")
            right.append(frag)
        if content.price_text:
            frag, ly = price_block(p, content.price_text, lx, ly, lw)
            left.append(frag)
        if content.programme_md:
            frag, ly = richtext_block(p, "t-rt-programme", content.programme_md, lx, ly, lw, 6.2,
                                      boxed=True, heading="PROGRAMMA")
            left.append(frag)
        if content.welcome_line:
            frag, ly = welcome_row(p, content, lx, ly, lw)
            left.append(frag)
        if content.third_image:
            frag, ly = polaroid_block(p, content.third_image, lx + 8, ly + 2, 88, angle=3)
            left.append(frag)
        for name, bottom in (("links", ly), ("rechts", ry)):
            if bottom > limit:
                p.violations.append(f"Te veel inhoud in de kolom {name}: {bottom - limit:.0f} mm te veel")
    p.left, p.right = "".join(left), "".join(right)
    return p

"""Design Studio — the rendering engine without a database (CR-10 B8, #1007).

Brand gate, formatted text, the poster sanitiser and the merge/check/export
chain with the real Inkscape. Every gate here is proven the way CLAUDE.md asks:
one violation, the intended message, then the clean case.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.domains.designstudio import brand, render, richtext, svgsafe
from app.domains.designstudio.blocks import fit_size
from app.domains.designstudio.content import Contact, Highlight, ImageBytes, PosterContent
from app.domains.media import svg as logo_svg

HERE = Path(__file__).resolve().parent
INKSCAPE = shutil.which(render.INKSCAPE) is not None
needs_inkscape = pytest.mark.skipif(not INKSCAPE, reason="inkscape not installed")

# A 1×1 white JPEG and a 2×2 PNG — enough for an <image> element.
PNG_2x2 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000020000000208060000007" "2b60d24"
    "0000001049444154789c63f8cfc0f01f0a0003fe03fd" "a35a3b6e" "0000000049454e44ae426082")


def _content(**overrides) -> PosterContent:
    base = {
        "duo_code": "dark_green-golden_yellow", "preset": "reeks",
        "title_lines": ("STAPPEN", "KLAPPEN"), "title_joiner": "EN", "bar_text": "SAMEN WANDELEN",
        "tagline": "Zet het in je agenda!",
        "highlights": (Highlight("calendar", "IEDERE 2DE MAANDAG VAN DE MAAND", True),
                       Highlight("map-pin", "VERTREK AAN HET MILOHEEM")),
        "welcome_line": "ook als je (nog) geen lid bent",
        "dates_heading": "DATA IN 2026", "dates": ("13 JULI", "10 AUGUSTUS", "14 SEPTEMBER"),
        "main_image": ImageBytes(PNG_2x2, "image/png"),
        "website": "www.raakmillegem.be", "email": "info@example.com",
        "contacts": (Contact("Voornaam Naam", "0470 00 00 00"),),
        "seed": 3,
    }
    base.update(overrides)
    return PosterContent(**base)


# ── Brand ───────────────────────────────────────────────────────────────────

def test_brand_gate_refuses_a_foreign_colour_and_passes_the_palette():
    """Broken on purpose: one `#123456` in a template. The gate must name it."""
    good = '<svg><rect fill="#005d29"/><text fill="#ffce00">x</text></svg>'
    assert brand.check_template(good) == []
    bad = good.replace("#ffce00", "#123456")
    assert brand.check_template(bad) == ["colour #123456 is not a Raak colour"]


def test_brand_gate_counts_at_most_five_brand_colours_and_ignores_photos():
    six = "".join(f'<rect fill="{c.hex}"/>' for c in list(brand.COLOURS.values())[:6])
    problems = brand.check_template(f"<svg>{six}</svg>")
    assert problems == ["6 brand colours used; the guide allows at most 5"]
    # A photo's data URI may contain anything that looks like a hex colour.
    photo = '<svg><image href="data:image/png;base64,AAAA#123456BBBB"/><rect fill="#005d29"/></svg>'
    assert brand.check_template(photo) == []


def test_every_enabled_duo_is_a_permitted_duo_and_the_palette_has_five_colours():
    for code in brand.ENABLED_DUOS:
        pal = brand.palette_for(code)
        used = {v for k, v in pal.items() if k != "white" and k != "ink"}
        assert len(used) == 5
        assert used <= {c.hex for c in brand.COLOURS.values()}
    with pytest.raises(ValueError):
        brand.split_duo("hot_pink-golden_yellow")  # not in the guide
    with pytest.raises(ValueError):
        brand.split_duo("blue-yellow")  # not a colour code


def test_the_rendered_poster_passes_the_brand_gate():
    merged = render.merge(_content(), layout="print_a")
    assert brand.check_template(merged.svg) == []


# ── Formatted text ──────────────────────────────────────────────────────────

def test_richtext_subset_parses_bold_bullets_and_paragraphs_and_nothing_else():
    blocks = richtext.parse("Eerste **vet** woord\nzelfde alinea\n\n- punt één\n- punt **twee**\n\n<b>geen html</b>")
    assert [b.bullet for b in blocks] == [False, True, True, False]
    assert [r.bold for r in blocks[0].runs] == [False, True, False]
    assert "".join(r.text for r in blocks[0].runs) == "Eerste vet woord zelfde alinea"
    assert "".join(r.text for r in blocks[3].runs) == "<b>geen html</b>"
    fragment, lines = richtext.to_svg("a **b** <c>", x=0, y=0, width=100, size=5, fill="#000000")
    assert "&lt;c&gt;" in fragment and '<tspan font-weight="bold">b</tspan>' in fragment
    assert lines == 1


def test_richtext_wraps_on_font_metrics_and_the_estimate_is_an_upper_bound():
    text = "Gezellig samen wandelen en praten in het Miloheem"
    one_line = richtext.wrap(richtext.parse(text), width=200, size=6)
    assert len(one_line) == 1
    narrow = richtext.wrap(richtext.parse(text), width=40, size=6)
    assert len(narrow) > 1
    for line in narrow:
        assert richtext.text_width("".join(r.text for r in line), 6) <= 40
    assert richtext.text_width("STAPPEN", 51, bold=True) > richtext.text_width("STAPPEN", 51)
    assert fit_size("STAPPEN", 260, 51, 24) == 51
    assert fit_size("EEN VEEL TE LANGE TITEL VOOR DEZE AFFICHE", 260, 51, 24) < 51


# ── Sanitiser ───────────────────────────────────────────────────────────────

def test_poster_allowlist_is_a_superset_of_the_logo_allowlist():
    """The two lists live apart on purpose (a poster embeds photos and filters,
    a logo may not); this keeps them from drifting the wrong way."""
    assert logo_svg.ALLOWED_ELEMENTS <= svgsafe.ALLOWED_ELEMENTS
    assert logo_svg.ALLOWED_ATTRIBUTES - {"type"} <= svgsafe.ALLOWED_ATTRIBUTES


def test_poster_sanitiser_drops_script_events_foreign_objects_and_external_refs():
    raw = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           b'width="297mm" height="420mm" onload="alert(1)">'
           b'<script>alert(1)</script><foreignObject><div>x</div></foreignObject>'
           b'<a href="https://evil.example"><text>klik</text></a>'
           b'<image href="https://evil.example/x.png" width="1" height="1"/>'
           b'<image href="data:image/png;base64,AAAA" width="1" height="1"/>'
           b'<use xlink:href="https://evil.example/#x"/>'
           b'<style>@import url(https://evil.example/x.css)</style>'
           b'<rect style="fill:url(https://evil.example/p)" width="1" height="1"/>'
           b'<text>blijft</text></svg>')
    cleaned, w, h = svgsafe.clean_poster_svg(raw)
    text = cleaned.decode()
    for gone in ("script", "foreignObject", "onload", "<a", "evil.example", "@import"):
        assert gone not in text
    assert "blijft" in text
    assert text.count("<image") == 1 and "data:image/png" in text
    assert (round(w), round(h)) == (297, 420)


def test_poster_sanitiser_refuses_what_it_cannot_read():
    with pytest.raises(svgsafe.SvgError):
        svgsafe.clean_poster_svg(b"")
    with pytest.raises(svgsafe.SvgError):
        svgsafe.clean_poster_svg(b"<html/>")
    with pytest.raises(svgsafe.SvgError):
        svgsafe.clean_poster_svg(b'<svg xmlns="http://www.w3.org/2000/svg"/>')  # no page size
    with pytest.raises(svgsafe.SvgError):
        svgsafe.clean_poster_svg(b'<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>'
                                 b'<svg xmlns="http://www.w3.org/2000/svg" width="1mm" height="1mm">&b;</svg>')


def test_the_rendered_poster_survives_its_own_sanitiser():
    """Download → upload of an unedited SVG must keep every layer, photo and
    filter; otherwise "handmatig bewerkt" would lose what it was given."""
    merged = render.merge(_content(), layout="print_a", qr_url="https://www.raakmillegem.be")
    cleaned, w, h = svgsafe.clean_poster_svg(merged.svg.encode())
    text = cleaned.decode()
    assert (w, h) == (297, 420)
    for kept in ("feTurbulence", "feDisplacementMap", "<pattern", "data:image/png", 'inkscape:label="Inhoud (bewerkbaar)"',
                 "t-title-0", "ref100mm"):
        assert kept in text
    assert text.count("<text") == merged.svg.count("<text")


# ── Merge and the overflow check ────────────────────────────────────────────

def test_merge_places_every_content_block_and_promises_a_box_per_text():
    merged = render.merge(_content(), layout="print_a", qr_url="https://www.raakmillegem.be")
    svg = merged.svg
    for expected in ("STAPPEN", "KLAPPEN", ">EN<", "SAMEN WANDELEN", "IEDERE 2DE MAANDAG", "DATA IN 2026",
                     "13 JULI", "Zet het in je agenda!", "IEDEREEN WELKOM!", "www.raakmillegem.be",
                     "Voornaam Naam 0470 00 00 00", 'preserveAspectRatio="xMidYMid slice"', "<svg x="):
        assert expected in svg, expected
    assert merged.violations == ()
    assert render.estimate(merged) == []
    for eid in ("t-title-0", "t-title-1", "t-bar", "t-tagline", "t-hl-0-0", "t-date-0", "t-website", "t-contacts"):
        assert eid in merged.boxes and f'id="{eid}"' in svg


def test_the_estimate_catches_a_title_that_cannot_fit():
    long_title = "EEN ONMOGELIJK LANGE ACTIVITEITSTITEL DIE NERGENS OP PAST"
    merged = render.merge(_content(title_lines=(long_title,)), layout="print_a")
    assert any("Titelregel 1" in v for v in merged.violations)
    assert any(p.startswith("t-title-0") for p in render.estimate(merged))


def test_too_much_content_is_reported_never_cut():
    many = tuple(Highlight("smile", f"Kernpunt nummer {i} met wat tekst erbij") for i in range(6))
    merged = render.merge(_content(highlights=many, programme_md="\n\n".join(["Een alinea tekst."] * 12)),
                          layout="print_a")
    assert any(v.startswith("Te veel inhoud in de kolom links") for v in merged.violations)
    assert "Kernpunt nummer 5" in merged.svg


def test_feed_layout_keeps_four_highlights_and_says_so():
    many = tuple(Highlight("smile", f"Kernpunt {i}") for i in range(5))
    merged = render.merge(_content(highlights=many), layout="feed_portrait")
    assert merged.height_mm == 371.25
    assert "Instagram toont ten hoogste vier kernpunten" in merged.violations
    assert "t-hl-3-0" in merged.boxes and "t-hl-4-0" not in merged.boxes


def test_a_focal_point_moves_the_crop():
    left = render.merge(_content(main_image=ImageBytes(PNG_2x2, "image/png", 0.1, 0.9)), layout="print_a")
    assert 'preserveAspectRatio="xMinYMax slice"' in left.svg


def test_resize_page_changes_only_the_page_attributes():
    merged = render.merge(_content(), layout="print_a")
    a4 = render.resize_page(merged.svg, 210, 297)
    assert 'width="210mm" height="297mm" viewBox="0 0 297 420"' in a4
    assert a4.count("<text") == merged.svg.count("<text")
    with pytest.raises(render.RenderError):
        render.resize_page("<svg><rect/></svg>", 210, 297)


def test_wordmark_is_recoloured_per_duo_and_loses_its_ids():
    green = render.wordmark(brand.palette_for("dark_green-golden_yellow"), x=0, y=0, width=72)
    assert "#ffce00" in green and 'id="' not in green and 'viewBox="106 106.2 491 245"' in green
    yellow = render.wordmark(brand.palette_for("golden_yellow-indigo"), x=0, y=0, width=72)
    assert "#ffce00" not in yellow and "#460359" in yellow


# ── Inkscape ────────────────────────────────────────────────────────────────

@needs_inkscape
def test_inkscape_measures_what_the_estimate_promised_and_names_an_overflow():
    """The authority: `--query-all` in mm via the reference rectangle. Then one
    box is shrunk by hand and Inkscape must name it."""
    merged = render.merge(_content(), layout="print_a", qr_url="https://www.raakmillegem.be")
    assert render.check(merged, authority=True) == []
    boxes = dict(merged.boxes)
    boxes["t-bar"] = 20.0
    shrunk = render.Merged(svg=merged.svg, boxes=boxes, violations=(), width_mm=297, height_mm=420)
    problems = render.check(shrunk, authority=True)
    assert any(p.startswith("t-bar") and "gemeten door Inkscape" in p for p in problems)


@needs_inkscape
def test_the_estimate_stays_above_inkscape_for_small_and_large_text(tmp_path):
    """The font-metric estimate must be an upper bound of what Inkscape draws,
    for lower case at 6.4 mm as much as for a 51 mm title (iteration 17: Pango
    lays small text out up to 8 % wider than the advances). If a font or an
    Inkscape upgrade changes that, this goes red before a poster does."""
    samples = [("Een rustige tocht langs de kanaaldijk en door", False, 6.4), ("Helm aanbevolen.", True, 6.4),
               ("IEDERE 2DE MAANDAG VAN DE MAAND", True, 8.2), ("VERTREK AAN HET MILOHEEM", False, 7.4),
               ("Kinderen fietsen mee onder begeleiding van", False, 6.4), ("STAPPEN", True, 51)]
    parts = ['<rect id="ref100mm" x="0" y="0" width="100" height="1" fill="none"/>']
    for i, (text, bold, size) in enumerate(samples):
        parts.append(f'<text id="t{i}" x="10" y="{20 + i * 20}" font-size="{size}" '
                     f'font-weight="{"bold" if bold else "normal"}">{text}</text>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="200mm" viewBox="0 0 297 200" '
           f'font-family="Radio Canada Big">{"".join(parts)}</svg>')
    path = tmp_path / "measure.svg"
    path.write_text(svg)
    boxes = render.query_all(path)
    for i, (text, bold, size) in enumerate(samples):
        estimate = richtext.text_width(text, size, bold=bold)
        ink = boxes[f"t{i}"][2]
        assert ink <= estimate, f"{text!r} at {size}: Inkscape {ink:.2f} mm > estimate {estimate:.2f} mm"
        assert ink >= estimate * 0.85, f"{text!r}: the estimate is far too loose ({estimate:.2f} vs {ink:.2f})"


@needs_inkscape
def test_inkscape_exports_a_pdf_with_text_and_a_png_of_the_asked_width():
    merged = render.merge(_content(), layout="print_a")
    pdf = render.export(merged.svg, "pdf")
    assert pdf.startswith(b"%PDF") and b"/Font" in pdf
    png = render.export(merged.svg, "png", png_width_px=300)
    assert png.startswith(b"\x89PNG")
    # IHDR: width is bytes 16–20 big-endian.
    assert int.from_bytes(png[16:20], "big") == 300
    with pytest.raises(ValueError):
        render.export(merged.svg, "gif")


def test_missing_inkscape_is_a_named_error(monkeypatch):
    monkeypatch.setattr(render, "INKSCAPE", "/nonexistent/inkscape")
    with pytest.raises(render.RenderError, match="niet geïnstalleerd"):
        render.export("<svg/>", "pdf")

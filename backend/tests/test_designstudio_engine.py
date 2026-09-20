"""Design Studio — the rendering engine without a database (CR-10 B8, #1007).

Brand gate, formatted text and the merge/check/export chain with the real
Inkscape. (Uploaded SVGs are cleaned by media, #1011 — tested there.) Every gate here is proven the way CLAUDE.md asks:
one violation, the intended message, then the clean case.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from app.domains.designstudio import brand, render, richtext
from app.domains.designstudio.blocks import fit_size
from app.domains.designstudio.content import Contact, Highlight, ImageBytes, PosterContent

HERE = Path(__file__).resolve().parent
INKSCAPE = shutil.which(render.INKSCAPE) is not None
needs_inkscape = pytest.mark.skipif(not INKSCAPE, reason="inkscape not installed")



def _png(size: tuple[int, int] = (2, 2), colour: str = "white") -> bytes:
    """A real PNG (media validates data URIs by decoding them, #1011)."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


PNG_2x2 = _png()


def _content(**overrides) -> PosterContent:
    base = {
        "duo_code": "dark_green-golden_yellow", "preset": "beeld",
        "title_lines": ("STAPPEN", "KLAPPEN"), "title_joiner": "EN", "bar_text": "SAMEN WANDELEN",
        "tagline": "Zet het in je agenda!",
        "highlights": (Highlight("calendar", "IEDERE 2DE MAANDAG VAN DE MAAND", True),
                       Highlight("map-pin", "VERTREK AAN HET MILOHEEM")),
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


# ── Merge and the overflow check ────────────────────────────────────────────

def test_merge_places_every_content_block_and_promises_a_box_per_text():
    merged = render.merge(_content(), layout="print_a", qr_url="https://www.raakmillegem.be")
    svg = merged.svg
    for expected in ("STAPPEN", "KLAPPEN", ">EN<", "SAMEN WANDELEN", "IEDERE 2DE MAANDAG", "DATA IN 2026",
                     "13 JULI", "Zet het in je agenda!", "IEDEREEN WELKOM!", "www.raakmillegem.be",
                     "Voornaam Naam · 0470 00 00 00", 'preserveAspectRatio="xMidYMid slice"', "<svg x="):
        assert expected in svg, expected
    assert merged.violations == ()
    assert render.estimate(merged) == []
    for eid in ("t-title-0", "t-title-1", "t-bar", "t-tagline", "t-hl-0-0", "t-date-0", "t-website", "t-contact-0"):
        assert eid in merged.boxes and f'id="{eid}"' in svg
    # With a contact person the association's e-mail stays off the poster (Koen, 20 Sep 2026).
    assert "info@example.com" not in svg
    alone = render.merge(_content(contacts=(), association_mobile="0499 00 00 00"), layout="print_a").svg
    assert "info@example.com" in alone and "0499 00 00 00" in alone and "t-contact-" not in alone
    for eid in ():
        assert eid in merged.boxes and f'id="{eid}"' in svg


def test_the_estimate_catches_a_title_that_cannot_fit():
    long_title = "EEN ONMOGELIJK LANGE ACTIVITEITSTITEL DIE NERGENS OP PAST"
    merged = render.merge(_content(title_lines=(long_title,)), layout="print_a")
    assert any("Titelregel 1" in v for v in merged.violations)
    assert any(p.startswith("t-title-0") for p in render.estimate(merged))


def test_too_much_content_is_reported_never_cut():
    many = tuple(Highlight("smile", f"Kernpunt nummer {i} met wat tekst erbij") for i in range(6))
    merged = render.merge(_content(highlights=many, explanation_md="\n\n".join(["Een alinea tekst die lang genoeg is."] * 30)),
                          layout="print_a")
    assert any(v.startswith("Te veel inhoud in de kolom rechts") for v in merged.violations)
    assert "KERNPUNT NUMMER 5" in merged.svg and merged.svg.count("Een alinea tekst") == 30


def test_feed_layout_shows_every_row_the_grid_the_polaroid_and_the_badge():
    """Koen, 20 September 2026: Instagram shows all six rows (two automatic,
    four own), the dates grid, the polaroid on the picture and the same
    welcome badge as print; the description and the third picture stay off."""
    six = tuple(Highlight("smile", f"Kernpunt {i}") for i in range(6))
    merged = render.merge(_content(highlights=six, inset_image=ImageBytes(PNG_2x2, "image/png"),
                                   third_image=ImageBytes(PNG_2x2, "image/png"), explanation_md="Tekst."),
                          layout="feed_portrait")
    assert merged.height_mm == 371.25
    assert all(f"t-hl-{i}-0" in merged.boxes for i in range(6)) and "Deze opmaak toont" not in " ".join(merged.violations)
    assert 'id="t-welcome-0"' in merged.svg
    # The dates grid gives way to one row (Koen, 20 September 2026).
    assert 'id="t-dates-head"' not in merged.svg
    assert "3 DATA IN 2026 · ZIE DE WEBSITE" in merged.svg
    assert merged.svg.count("<image") == 2 and 'id="t-rt-explanation"' not in merged.svg


def test_every_contact_gets_its_own_row_with_name_gsm_and_email_and_the_band_grows():
    """Koen, 19 September 2026: the e-mail address was missing and the
    contact line floated under the icons. One row per contact, left-aligned
    under the same icon column, "Naam · gsm · e-mail"; the band grows 6.5 mm
    per contact and the content limit moves with it."""
    three = tuple(Contact(f"Persoon {i}", f"047{i} 00 00 00", f"persoon{i}@example.com") for i in range(3))
    none = render.merge(_content(contacts=()), layout="print_a")
    with_three = render.merge(_content(contacts=three), layout="print_a")
    for i in range(3):
        assert f'id="t-contact-{i}"' in with_three.svg
        assert f"Persoon {i} · 047{i} 00 00 00 · persoon{i}@example.com" in with_three.svg
    assert 't-contact-3' not in with_three.svg and "t-contact-" not in none.svg
    # Same x for the website row and every contact row: nothing floats.
    xs = set(re.findall(r'id="t-(?:website|contact-\d)" x="([0-9.]+)"', with_three.svg))
    assert len(xs) == 1
    assert render.estimate(with_three) == []


def test_welcome_is_a_badge_above_the_tile_and_members_only_turns_it_red():
    """Koen, 19/20 September 2026: "iedereen welkom" is not a field and not a
    row — a brush-stroke badge above the tile on every poster; "ENKEL
    LEDEN" the same on the red."""
    svg = render.merge(_content(), layout="print_a").svg
    assert "IEDEREEN WELKOM!" in svg
    y = float(re.search(r'id="t-welcome-0" x="[0-9.]+" y="([0-9.]+)"', svg).group(1))
    assert 355 < y < 380
    members = render.merge(_content(members_only=True), layout="print_a").svg
    assert "ENKEL LEDEN" in members and "IEDEREEN WELKOM" not in members
    assert f'fill="{brand.COLOURS["watermelon_red"].hex}" fill-opacity="1"' in members


def test_both_title_lines_share_one_size_and_the_lockup_sits_in_the_band():
    merged = render.merge(_content(title_lines=("STAPPEN", "KLAPPEN"), title_joiner="EN"), layout="print_a")
    sizes = set(re.findall(r'id="t-title-\d" x="[0-9.]+" y="[0-9.]+" font-size="([0-9.]+)"', merged.svg))
    assert len(sizes) == 1
    # The lockup's y lies inside the band, not at the top-left corner.
    m = re.search(r'viewBox="106 106.2 491 245"', merged.svg)
    assert m is not None
    lockup_y = float(re.search(r'x="[0-9.]+" y="([0-9.]+)" width="66.000"', merged.svg).group(1))
    assert lockup_y > 350


def test_the_third_picture_and_the_sponsor_logos_do_not_collide():
    """Third picture bottom-left under the highlights, logos bottom-right
    above the band — both may be there (Koen, 20 September 2026)."""
    both = render.merge(_content(inset_image=ImageBytes(PNG_2x2, "image/png"),
                                 third_image=ImageBytes(PNG_2x2, "image/png", 0.2, 0.2),
                                 logos=(ImageBytes(PNG_2x2, "image/png"),)), layout="print_a").svg
    assert both.count("<image") == 4 and 'id="logo-0"' in both and 'preserveAspectRatio="xMinYMin slice"' in both


def test_the_simple_preset_puts_one_picture_and_the_text_over_the_full_width():
    """Half of the unit's posters are a Bowlen: one big picture, the
    activity's text, "iedereen welkom" small and low — no icon rows."""
    simple = render.merge(_content(preset="eenvoudig", dates=(), explanation_md="De **tekst** van de activiteit."),
                          layout="print_a")
    assert simple.violations == ()
    m = re.search(r'<image x="19.00" y="[0-9.]+" width="([0-9.]+)" height="([0-9.]+)"', simple.svg)
    assert m is not None and float(m.group(1)) > 250 and float(m.group(2)) > 100
    assert "t-hl-0-0" not in simple.svg and 'id="t-rt-explanation"' in simple.svg
    # A polaroid lies on the big picture; the big picture keeps its size.
    with_inset = render.merge(_content(preset="eenvoudig", dates=(), explanation_md="De tekst.",
                                       inset_image=ImageBytes(PNG_2x2, "image/png")), layout="print_a")
    assert with_inset.violations == () and with_inset.svg.count("<image") == 2
    hero = re.search(r'<image x="19.00" y="[0-9.]+" width="[0-9.]+" height="([0-9.]+)"', simple.svg).group(1)
    hero2 = re.search(r'<image x="19.00" y="[0-9.]+" width="[0-9.]+" height="([0-9.]+)"', with_inset.svg).group(1)
    assert abs(float(hero) - float(hero2)) < 12
    # The lockup sits 4 mm in from the paper's left edge, its bottom level with the band's.
    x, y, w = (float(v) for v in re.search(r'x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="[0-9.]+" viewBox="106', simple.svg).groups())
    assert x == 13.0 and abs(y + w * 245 / 491 - 409) < 0.01


def test_six_highlight_rows_fit_the_left_column():
    """Date, place and four own rows (Koen, 20 September 2026: six in total,
    rows five and six structurally gone) — all six on the print poster, room
    to spare."""
    six = tuple(Highlight("smile", f"Kernpunt {i} met een tweede regel erbij", i == 0) for i in range(6))
    merged = render.merge(_content(highlights=six, inset_image=None, dates=()), layout="print_a")
    assert all(f't-hl-{i}-0' in merged.svg for i in range(6))
    assert not any(v.startswith("Te veel inhoud in de kolom links") for v in merged.violations), merged.violations


def test_every_highlight_row_is_upper_case_bold_and_one_size():
    """Koen, 20 September 2026: the place row looked smaller and lighter
    than the others. One size, upper case, bold — whatever was typed."""
    merged = render.merge(_content(highlights=(Highlight("map-pin", "Miloheem"), Highlight("users", "gezellig samen"))),
                          layout="print_a")
    rows = re.findall(r'<text id="t-hl-\d-0" x="[0-9.]+" y="[0-9.]+" font-size="([0-9.]+)" font-weight="(\w+)"[^>]*>([^<]*)</text>', merged.svg)
    assert len(rows) == 2
    assert {r[0] for r in rows} == {"7.400"} and {r[1] for r in rows} == {"bold"}
    assert [r[2] for r in rows] == ["MILOHEEM", "GEZELLIG SAMEN"]


def test_a_wide_picture_in_a_squeezed_box_is_shown_whole():
    """Koen's feed image had the drawing cut in half. A picture whose known
    size is much wider than its box is letterboxed; an unknown size crops as
    before, and a normal box always crops."""
    from app.domains.designstudio.blocks import aspect_for

    wide = ImageBytes(PNG_2x2, "image/png", 0.5, 0.5, 1440, 1248)
    assert aspect_for(wide, 260, 60) == "xMidYMid meet"       # squeezed: whole
    assert aspect_for(wide, 260, 200) == "xMidYMid slice"     # normal: crop
    assert aspect_for(ImageBytes(PNG_2x2, "image/png"), 260, 60) == "xMidYMid slice"   # size unknown: crop
    assert 'preserveAspectRatio="xMidYMid slice"' in render.merge(_content(main_image=wide), layout="print_a").svg


def test_a_focal_point_moves_the_crop():
    left = render.merge(_content(main_image=ImageBytes(PNG_2x2, "image/png", 0.1, 0.9)), layout="print_a")
    assert 'preserveAspectRatio="xMinYMax slice"' in left.svg


def test_page_size_is_read_from_the_root_in_mm_or_px():
    assert render.page_size_mm('<svg width="297mm" height="420mm" viewBox="0 0 297 420"/>') == (297, 420)
    w, h = render.page_size_mm('<svg width="96" height="192"/>')
    assert (round(w, 1), round(h, 1)) == (25.4, 50.8)
    with pytest.raises(render.RenderError):
        render.page_size_mm("<svg><rect/></svg>")


def test_resize_page_changes_only_the_page_attributes():
    merged = render.merge(_content(), layout="print_a")
    a4 = render.resize_page(merged.svg, 210, 297)
    assert 'width="210mm" height="297mm" viewBox="0 0 297 420"' in a4
    assert a4.count("<text") == merged.svg.count("<text")
    with pytest.raises(render.RenderError):
        render.resize_page("<svg><rect/></svg>", 210, 297)


def test_wordmark_is_recoloured_per_duo_and_keeps_the_baseline_glyphs():
    """Koen, 19 September 2026: "Beleef meer in Millegem" had vanished. The
    baseline is one <use href="#font_…"> per letter; every referenced glyph
    must still be defined in the wordmark, and the root loses only its own
    id/role attributes."""
    green = render.wordmark(brand.palette_for("dark_green-golden_yellow"), x=0, y=0, width=72)
    assert "#ffce00" in green and 'viewBox="106 106.2 491 245"' in green
    assert not re.search(r'<svg[^>]*\sid="', green) and 'aria-labelledby' not in green
    uses = re.findall(r'href="#(font_[^"]+)"', green)
    used = set(uses)
    assert len(uses) >= 20 and len(used) >= 10, "the baseline's letters are missing"
    defined = set(re.findall(r'id="(font_[^"]+)"', green))
    assert used <= defined, used - defined
    yellow = render.wordmark(brand.palette_for("golden_yellow-indigo"), x=0, y=0, width=72)
    assert "#ffce00" not in yellow and "#460359" in yellow


# ── AI drawings ─────────────────────────────────────────────────────────────

def test_dutch_scenes_are_translated_and_logged_english_ones_pass(monkeypatch):
    """Koen, 20 September 2026: type Dutch, the model gets English, the
    translation lands in the AI log."""
    from app.domains.designstudio import imaging
    from app.domains.chatbot import api as chatbot_api

    class FakeAnswer:
        content = "two adults and two children on bicycles"
        usage = {"prompt": 30, "completion": 9}

    class FakeProvider:
        name, endpoint, model = "mistral", "chat.completions", "mistral-small-latest"

        def complete(self, messages, tools=None, tool_choice=None):
            assert messages[-1]["content"] == "twee volwassenen en twee kinderen op de fiets"
            return FakeAnswer()

    logged: list[dict] = []
    monkeypatch.setattr(chatbot_api, "get_provider", lambda model="": FakeProvider())
    monkeypatch.setattr(chatbot_api, "sink_for", lambda actor="": (lambda **kw: logged.append(kw)))
    english, translated = imaging.translate_scene("twee volwassenen en twee kinderen op de fiets", actor="x")
    assert translated and english == "two adults and two children on bicycles"
    assert logged and logged[0]["capability"] == "translate" and logged[0]["surface"] == "designstudio"
    assert "twee volwassenen" in logged[0]["payload"]
    assert imaging.translate_scene("two adults on bicycles") == ("two adults on bicycles", False)
    assert imaging.looks_dutch("een gezin met twee kinderen op de fiets") and not imaging.looks_dutch("a family on bikes")


def test_three_styles_and_their_wording():
    from app.domains.designstudio import imaging

    assert set(imaging.STYLES) == {"lijn", "lijnkleur", "kleur"} == set(imaging.STYLE_LABELS)
    assert "flat colour accents" in imaging.build_prompt("a family on bicycles", "lijnkleur")
    assert all("realistic proportions" in s and "no cartoon" in s for s in imaging.STYLES.values())


def test_whitening_pushes_the_near_white_ground_to_white_and_keeps_the_lines():
    from io import BytesIO

    from PIL import Image

    from app.domains.designstudio.handlers import whiten

    img = Image.new("RGB", (4, 1))
    img.putdata([(253, 253, 253), (0, 0, 0), (200, 200, 200), (245, 250, 248)])
    buf = BytesIO()
    img.save(buf, format="PNG")
    with Image.open(BytesIO(whiten(buf.getvalue()))) as out:
        assert list(out.getdata()) == [(255, 255, 255), (0, 0, 0), (200, 200, 200), (255, 255, 255)]


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


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fontconfig not installed")
def test_inkscape_gets_the_poster_fonts_from_the_repo_not_from_the_host():
    """The renderer's private fontconfig must resolve both poster faces to the
    files in app/static/fonts. Without that config CI fell back to DejaVu and
    every bar text measured 10 % too wide (run 35357001948); with an empty
    fonts directory `fc-list` shows neither face — so this goes red the moment
    the directory drops out of the config."""
    import subprocess

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(Path(tempfile.gettempdir())),
           "FONTCONFIG_FILE": render._fontconfig_file()}
    for family in ("Radio Canada Big", "Caveat"):
        out = subprocess.run(["fc-match", "-f", "%{file}", family], capture_output=True, text=True,
                             env=env, check=True).stdout
        assert Path(out).resolve().parent == render.FONTS_DIR.resolve(), f"{family} resolved to {out}"


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

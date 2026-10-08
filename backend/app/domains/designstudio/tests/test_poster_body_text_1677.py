"""The poster's running text: black, and inside its space (#1677).

Koen, 6 October 2026, on the poster of a cycling weekend: the text under the
photo was green and longer than its space — it ran on behind the label
("IEDEREEN WELKOM!", "ENKEL LEDEN") and the bottom block.

The order the planner now follows when a text grows (measured below on one
picture, the text one sentence longer each time):

1. as before #1677: the picture takes the room the page leaves it, down to
   the height at which it still fills the width, and the text the largest
   size that fits, down to the size that was the smallest until now — what
   every poster that fitted before still gets, unchanged;
2. the picture gives way: a lower band over the full width, cropped around its
   stored centre, down to half its normal height;
3. the text steps down to the smallest size that still reads in print;
4. the text ends on a whole line above the label, and the editor says so — a
   warning, not a refusal.

Broken on purpose (7 October 2026), each red for its own reason: the band's
lower bound taken away → the picture goes under half; the band skipped → the
text goes smaller under a full picture (step 2 never appears); the cut taken
out → the text's box ends under the label's top; the fill back to the ink
colour → the colour test; the warning made a violation → the export test.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.domains.designstudio import brand, render
from app.domains.designstudio.blocks import (
    BAND_SHARE,
    DOES_NOT_FIT,
    SMALLEST_BODY,
    band_crop,
    plan_affiche,
)
from app.domains.designstudio.content import Contact, Highlight, ImageBytes, PosterContent

needs_inkscape = pytest.mark.skipif(
    shutil.which(render.INKSCAPE) is None, reason="inkscape not installed"
)
SENTENCE = "We rijden in groepen van tien deelnemers langs rustige wegen en stoppen onderweg."
#: 1600 × 1200 in a column of 259 mm: 194 mm high by its own proportions.
NORMAL = 259.0 * 1200 / 1600
#: The lowest the picture went before #1677 (`full_bleed_floor`, tolerance 1.6).
FULL_BLEED = 259.0 / (1.6 * 1600 / 1200)


def _photo() -> ImageBytes:
    buf = BytesIO()
    Image.new("RGB", (16, 12), "white").save(buf, format="PNG")
    return ImageBytes(buf.getvalue(), "image/png", width=1600, height=1200)


def _poster(sentences: int, **more) -> PosterContent:
    fields = dict(
        duo_code="dark_green-golden_yellow",
        preset="eenvoudig",
        title_lines=("FIETSWEEKEND",),
        date_line="VRIJDAG 7 MEI",
        location="DORPSPLEIN",
        explanation_md="\n\n".join([SENTENCE] * sentences),
        main_image=_photo(),
        contacts=(Contact("Voornaam Naam", "0470 00 00 00"),),
        website="www.example.com",
        seed=3,
    )
    return PosterContent(**(fields | more))


def _state(svg: str) -> tuple[bool, float, float]:
    """(the picture is a band, its height, the text's size) of a rendered poster."""
    picture = re.search(
        r'<(?:image|svg) x="19.00" y="[0-9.]+" width="259.00" height="([0-9.]+)"', svg
    )
    size = re.search(r'id="t-rt-explanation"[^>]*font-size="([0-9.]+)"', svg)
    return "data-band" in svg, float(picture.group(1)), float(size.group(1))


def test_the_four_steps_come_in_their_order_as_the_text_grows():
    """One sentence more each time, on the print layout: every step is seen, in
    order, and none is skipped."""
    steps: list[int] = []
    seen: dict[int, tuple] = {}
    for sentences in range(1, 80):
        merged = render.merge(_poster(sentences), layout="print_a")
        band, height, size = _state(merged.svg)
        warned = DOES_NOT_FIT in merged.warnings
        assert merged.violations == (), (sentences, merged.violations)
        assert height >= NORMAL * BAND_SHARE - 0.1, f"the picture went under half: {height}"
        assert size >= SMALLEST_BODY["print"]
        if warned:
            step = 4
        elif size < 7.2:
            step = 3
        elif band:
            step = 2
        else:
            step = 1
        if step == 3 or step == 4:
            assert band and height == pytest.approx(NORMAL * BAND_SHARE, abs=0.1), (
                "the text went smaller, or was cut, before the picture had given all it may"
            )
        if step == 1:
            # As before #1677: the picture has the room the page leaves it, and
            # is never lower than the height at which it still fills the width
            # uncropped by more than the tolerance (`full_bleed_floor`).
            assert height >= FULL_BLEED - 0.1, "a text that fits turned the picture into a band"
        if not steps or steps[-1] != step:
            steps.append(step)
            seen[step] = (sentences, band, round(height, 1), size)
    print("MEASURE the steps (sentences, band, picture mm, text mm):", seen)
    assert steps == [1, 2, 3, 4], f"the steps came as {steps}"


@pytest.mark.parametrize("focus_y", [0.0, 0.25, 0.5, 0.9, 1.0])
def test_the_band_is_cropped_around_the_pictures_own_centre(focus_y):
    image = ImageBytes(b"", "image/png", focus_x=0.5, focus_y=focus_y, width=1600, height=1200)
    left, top, width, height = band_crop(image, 259.0, 97.0)
    assert (left, width) == (0.0, 1600.0), "a band keeps the full width of the picture"
    assert height == pytest.approx(1600 * 97.0 / 259.0)
    assert 0.0 <= top <= 1200 - height, "the crop left the picture"
    centre = top + height / 2
    wanted = min(max(focus_y * 1200, height / 2), 1200 - height / 2)
    assert centre == pytest.approx(wanted), "the crop does not follow the stored centre"


def test_the_running_text_is_black_and_the_title_and_the_rows_keep_their_colour():
    pal = brand.palette_for("dark_green-golden_yellow")
    svg = render.merge(_poster(2), layout="print_a").svg
    body = re.search(r'<text id="t-rt-explanation"[^>]*fill="([^"]+)"', svg).group(1)
    row = re.search(r'<text id="t-hl-0-0"[^>]*fill="([^"]+)"', svg).group(1)
    assert body == brand.BLACK and pal["ink"] != brand.BLACK
    assert row == pal["ink"], "a highlight row lost the brand colour"


@pytest.mark.parametrize("preset", ["eenvoudig", "beeld", "tekst"])
@pytest.mark.parametrize("members_only", [False, True])
def test_a_text_that_does_not_fit_warns_and_does_not_refuse_the_export(preset, members_only):
    """Every layout that carries the text, with either label."""
    merged = render.merge(
        _poster(
            120,
            preset=preset,
            members_only=members_only,
            highlights=(Highlight("smile", "KERNPUNT"),),
        ),
        layout="print_a",
    )
    assert merged.warnings == (DOES_NOT_FIT,)
    assert not [v for v in merged.violations if v.startswith("Te veel inhoud")]
    drawn = merged.svg.count(SENTENCE[:30])
    assert 0 < drawn < 120, "the text is drawn whole, or not at all"
    assert DOES_NOT_FIT in render.check(merged), "the editor is not told"


@needs_inkscape
@pytest.mark.parametrize("members_only", [False, True])
@pytest.mark.parametrize("sentences", [2, 8, 120])
def test_the_text_ends_above_the_label_and_the_bottom_block(sentences, members_only):
    """Measured by Inkscape on the rendered poster: a short text, one that fits
    after the steps, one that does not — with each label."""
    content = _poster(sentences, members_only=members_only)
    merged = render.merge(content, layout="print_a")
    plan = plan_affiche(
        content, layout="print_a", width=297, height=420, pal=brand.palette_for(content.duo_code)
    )
    with tempfile.TemporaryDirectory(prefix="poster-1677-") as tmp:
        path = Path(tmp) / "poster.svg"
        path.write_text(merged.svg, encoding="utf-8")
        boxes = render.query_all(path)
    text, label = boxes["t-rt-explanation"], boxes["t-welcome-0"]
    print(
        "MEASURE", sentences, members_only, "text", text, "label", label, "band y", plan.band["y"]
    )
    assert text[2] > 50 and text[3] > 3, "the text box is empty: the measurement proves nothing"
    bottom = text[1] + text[3]
    assert bottom <= label[1], f"the text ends {bottom - label[1]:.1f} mm under the label's top"
    assert bottom <= plan.band["y"], "the text reaches the bottom block"

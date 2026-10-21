"""#2184 — an RGBA picture reduced 2x or more is reduced exactly, as before Pillow 13.

Pillow 13 applies `reducing_gap` to RGBA and LA images too, and `thumbnail()` defaults it
to 2.0: a logo shrunk by two or more gets a cheaper, slightly less exact result at its
edges (measured: 1-3 of 255 on average). Koen chose "exact zoals vandaag" (21 October
2026), so `_resized` passes `reducing_gap=None`.

Proven red on Pillow 13.0.0 by removing the argument from `_resized`: both sizes differ (reduced 4x and 5.3x)
from the exact reference.
"""

import random

import pytest
from PIL import Image, ImageDraw

from app.domains.media.images import _resized


def _logo() -> Image.Image:
    rng = random.Random(1)
    img = Image.new("RGBA", (1600, 1200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for _ in range(200):
        x, y = rng.randrange(1600), rng.randrange(1200)
        draw.ellipse(
            [x, y, x + rng.randrange(10, 200), y + rng.randrange(10, 200)],
            fill=(
                rng.randrange(256),
                rng.randrange(256),
                rng.randrange(256),
                rng.randrange(40, 256),
            ),
        )
    return img


@pytest.mark.parametrize("max_side", [400, 300])
def test_an_rgba_reduced_two_times_or_more_equals_the_exact_resize(max_side):
    img = _logo()
    got = _resized(img, max_side)
    exact = img.resize(got.size, Image.Resampling.LANCZOS, reducing_gap=None)
    assert got.size[0] == max_side
    assert got.tobytes() == exact.tobytes()

"""The pixel comparison itself, without a browser (#1605; CR-11 B7 test 11).

`tests_e2e/pixels.py` decides whether two renderings of a screen are the same.
These tests pin what "the same" means, on images made here:

- a few steps of a channel (antialiasing between two machines) pass;
- **an element shifted by 2 px is red**, and the difference says where — the
  acceptance of the issue. Proven red the other way round too: with the channel
  tolerance raised to 255 the shifted button passes, and this test fails;
- a page that grew or shrank is red, whatever its pixels;
- the diff image marks the differing pixels and only those;
- **the run refuses everything but localhost**: a baseline is a picture of
  people and payments in a public repository, so it may only ever be a picture
  of the seed.
"""

import io

import pytest
from PIL import Image, ImageDraw

from tests_e2e import pixels


def _png(image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _screen(button_x: int = 100, height: int = 300, ink=(33, 45, 58)) -> bytes:
    """A made-up screen: a white card on a grey ground, a line of "text" and a
    filled button of 120 × 34 px."""
    image = Image.new("RGB", (400, height), (244, 246, 248))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (16, 16, 384, 200), radius=14, fill=(255, 255, 255), outline=(216, 224, 230)
    )
    draw.rectangle((32, 40, 260, 52), fill=ink)
    draw.rounded_rectangle((button_x, 120, button_x + 120, 154), radius=6, fill=(37, 78, 115))
    return _png(image)


def test_the_same_screen_is_equal():
    same = pixels.compare(_screen(), _screen())
    assert same.same_size and same.pixels == 0 and same.worst == 0 and same.box is None
    assert same.within(0) and same.describe().startswith("equal")


def test_a_few_steps_of_a_channel_pass():
    """Antialiasing: every "text" pixel a little lighter — inside the tolerance."""
    nudged = pixels.compare(_screen(), _screen(ink=(43, 55, 68)))
    assert nudged.worst == 10 and nudged.pixels == 0
    assert nudged.within(0)


def test_a_colour_that_changed_is_red():
    recoloured = pixels.compare(_screen(), _screen(ink=(133, 45, 58)))
    assert recoloured.worst == 100 and recoloured.pixels > 2000
    assert not recoloured.within(0)


def test_an_element_shifted_by_two_pixels_is_red_and_the_difference_says_where():
    shifted = pixels.compare(_screen(button_x=100), _screen(button_x=102))
    assert shifted.same_size
    # Two columns of 35 px on either side of the button, corners aside.
    assert 100 <= shifted.pixels <= 160, shifted.pixels
    assert not shifted.within(pixels.ALLOWED_PIXELS)
    left, top, right, bottom = shifted.box
    assert (left, right) == (100, 223) and 118 <= top <= 122 and 153 <= bottom <= 156, shifted.box
    assert "pixels differ" in shifted.describe() and "x 100–223" in shifted.describe()


def test_the_default_threshold_is_what_makes_the_shift_red():
    """The other half of the proof: tolerant enough, the comparison sees nothing
    — so it is the threshold, not an accident, that catches the shift."""
    blind = pixels.compare(_screen(button_x=100), _screen(button_x=102), tolerance=255)
    assert blind.pixels == 0 and blind.worst > pixels.CHANNEL_TOLERANCE
    assert pixels.CHANNEL_TOLERANCE < 64, "a tolerance this wide lets a grey label vanish"
    assert pixels.ALLOWED_PIXELS < 100, "the shifted button's ~140 pixels must stay above it"


def test_a_page_that_grew_is_red_whatever_its_pixels():
    grown = pixels.compare(_screen(height=300), _screen(height=340))
    assert not grown.same_size and not grown.within(10**9)
    assert grown.describe() == "the size changed: baseline 400 × 300, now 400 × 340"


def test_the_diff_image_marks_the_differing_pixels_and_only_those():
    shifted = pixels.compare(_screen(button_x=100), _screen(button_x=102))
    image = Image.open(io.BytesIO(shifted.image)).convert("RGB")
    assert image.size == (400, 300)
    magenta = sum(1 for pixel in image.getdata() if pixel == (255, 0, 255))
    assert magenta == shifted.pixels
    assert image.getpixel((100, 137)) == (255, 0, 255), "the button's old left edge is not marked"
    assert image.getpixel((160, 137)) != (255, 0, 255), "the button's middle did not change"


@pytest.mark.parametrize(
    "url",
    [
        "https://hdev.example.org",
        "https://www.example.be:8443/",
        "http://10.0.0.5:8000",
        "http://localhost.example.org:8001",
        "",
    ],
)
def test_the_run_refuses_everything_but_localhost(url, monkeypatch):
    monkeypatch.delenv("PIXEL_BASE_URL", raising=False)
    with pytest.raises(pixels.NotLocal):
        pixels.local_base(url)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8001", "http://localhost:8001/", "http://[::1]:8001"]
)
def test_the_local_server_is_accepted(url):
    assert pixels.local_base(url) == url.rstrip("/")


def test_writing_baselines_refuses_a_remote_server(monkeypatch, capsys):
    """The tool that writes the baselines, pointed at an environment: nothing is
    rendered and nothing is written."""
    monkeypatch.setenv("PIXEL_BASE_URL", "https://hdev.example.org")
    before = sorted(p.name for p in pixels.BASELINES.glob("*.png"))
    assert pixels.write([]) == 2
    assert "refused" in capsys.readouterr().err
    assert sorted(p.name for p in pixels.BASELINES.glob("*.png")) == before


def test_every_screen_has_a_key_of_its_own_and_a_known_session():
    keys = [screen.key for screen in pixels.SCREENS]
    assert len(keys) == len(set(keys)) and keys, keys
    roles = {None, "admin", "lid", "lid-verlopen", "lid-vernieuwd", "lid-overschrijving"}
    for screen in pixels.SCREENS:
        assert screen.session in roles, (screen.key, screen.session)
        assert screen.widths, screen.key
    with pytest.raises(SystemExit):
        pixels.pairs(["no-such-screen"])

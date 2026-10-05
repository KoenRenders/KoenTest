"""The pixel comparison of the pilot screens (#1605; CR-11 B7 test 11).

A screen is rendered against a FROZEN clock and compared with its baseline PNG
in `tests_e2e/baselines/`. A screen that shifts makes the pixel run red, and the
diff image says where.

**The stability protocol** (CR-11 B7 test 11), and where each part lives:

| part | where |
|---|---|
| fixed seed data, only read | `scripts/pixel-local.sh` and the CI step: a database of its own, seeded once, never written by a test |
| the clock frozen | `PIXEL_NOW` below: the seed and the server run under `faketime` at that moment, and the browser's own clock is set to it (`render`) |
| a fixed viewport and device scale | `SCREENS` (the widths) and `context_options` (scale 1) |
| fonts self-hosted, the browser pinned | `requirements-e2e.txt` |
| a threshold per screen | `Screen.allowed` — a few pixels of antialiasing pass, a shifted label does not |
| dynamic regions masked | an element with `data-screenshot="mask"` is painted as a flat block (`FREEZE_CSS`) |
| the baseline-update rule | `python -m tests_e2e.pixels --write`, one command; the new PNGs ship in the same pull request as the design change |

**Seed data only.** A baseline is a picture of people and their payments, in a
public repository. So this module renders against the local pixel server and
nothing else: `local_base()` refuses any host but localhost, and that refusal is
tested (`test_pixel_compare.py`). The seed's names are invented.

**Why the frozen moment lies in the past.** A session cookie carries its own
expiry (`now + SESSION_MAX_AGE`), minted by the test process in real time. For a
server whose clock stands still in the past that expiry is always still ahead;
for one in the future every cookie would have expired.
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

#: The frozen moment of the pixel run, Brussels wall time as `faketime` reads it.
#: `scripts/pixel-local.sh` and the CI step read THIS line; nothing else names it.
PIXEL_NOW = "2026-09-15 10:00:00"

BASELINES = Path(__file__).resolve().parent / "baselines"

#: A pixel differs when one of its channels is further off than this (0–255).
#: Antialiasing at the edge of a glyph moves a channel by a few steps between two
#: machines; a pixel that changed its meaning (text where there was none) moves
#: it by far more.
CHANNEL_TOLERANCE = 24

#: How many differing pixels a screen may have before it is red, unless the
#: screen says otherwise (`Screen.allowed`).
ALLOWED_PIXELS = 0

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")

# What `tests_e2e/screenshots.py` freezes, plus the mask of B7 test 11.
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
#nprogress { display: none !important; }
[data-screenshot="mask"] { background: #b0b0b0 !important; color: transparent !important; }
[data-screenshot="mask"] * { visibility: hidden !important; }
"""


class NotLocal(RuntimeError):
    """The pixel run was pointed at something that is not the local server."""


def local_base(url: Optional[str] = None) -> str:
    """The address of the local pixel server, or a refusal.

    Against HDEV, UAT or PROD these images would show real members and their
    payments — and a baseline is committed to a public repository."""
    base = url if url is not None else os.environ.get("PIXEL_BASE_URL", "")
    if not base:
        raise NotLocal("PIXEL_BASE_URL is not set — the pixel run has its own server")
    host = urlparse(base).hostname or ""
    if host not in LOCAL_HOSTS:
        raise NotLocal(
            f"refused: PIXEL_BASE_URL points at {host!r} — the pixel run renders "
            "seeded LOCAL screens only, never a live environment"
        )
    return base.rstrip("/")


# ── The comparison ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Difference:
    """What two renderings of one screen differ in."""

    #: (width, height) of the baseline and of the rendering.
    baseline_size: tuple[int, int]
    actual_size: tuple[int, int]
    #: Pixels with a channel further off than `CHANNEL_TOLERANCE`.
    pixels: int
    #: The largest channel difference anywhere (0–255), tolerated or not.
    worst: int
    #: The box around every differing pixel: (left, top, right, bottom), or None.
    box: Optional[tuple[int, int, int, int]]
    #: The baseline, dimmed, with every differing pixel in magenta — a PNG.
    image: bytes

    @property
    def same_size(self) -> bool:
        return self.baseline_size == self.actual_size

    def within(self, allowed: int) -> bool:
        return self.same_size and self.pixels <= allowed

    def describe(self) -> str:
        if not self.same_size:
            return (
                f"the size changed: baseline {self.baseline_size[0]} × {self.baseline_size[1]}, "
                f"now {self.actual_size[0]} × {self.actual_size[1]}"
            )
        if not self.pixels:
            return f"equal (largest channel difference {self.worst})"
        left, top, right, bottom = self.box or (0, 0, 0, 0)
        return (
            f"{self.pixels} pixels differ (largest channel difference {self.worst}), "
            f"inside x {left}–{right}, y {top}–{bottom}"
        )


def compare(baseline: bytes, actual: bytes, tolerance: int = CHANNEL_TOLERANCE) -> Difference:
    """Compare two PNGs pixel by pixel.

    Of two sizes the overlap is compared and what one has more counts as
    different: a page that grew is a page that changed."""
    from PIL import Image, ImageChops

    old = Image.open(io.BytesIO(baseline)).convert("RGB")
    new = Image.open(io.BytesIO(actual)).convert("RGB")
    width, height = max(old.width, new.width), max(old.height, new.height)

    def on_canvas(image):
        if image.size == (width, height):
            return image
        # Magenta where an image ends: against any real pixel that differs.
        canvas = Image.new("RGB", (width, height), (255, 0, 255))
        canvas.paste(image, (0, 0))
        return canvas

    a, b = on_canvas(old), on_canvas(new)
    delta = ImageChops.difference(a, b)
    # Per pixel the largest of its three channel differences.
    red, green, blue = delta.split()
    largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    worst = largest.getextrema()[1]
    beyond = largest.point(lambda value: 255 if value > tolerance else 0)
    pixels = beyond.histogram()[255]
    box = beyond.getbbox()

    dimmed = Image.blend(a, Image.new("RGB", (width, height), (255, 255, 255)), 0.6)
    marked = Image.composite(Image.new("RGB", (width, height), (255, 0, 255)), dimmed, beyond)
    out = io.BytesIO()
    marked.save(out, format="PNG")
    return Difference(old.size, new.size, pixels, worst, box, out.getvalue())


# ── The screens ──────────────────────────────────────────────────────────────

WIDE = (1920, 1080)
DESKTOP = (1440, 900)
PHONE = (390, 844)


@dataclass(frozen=True)
class Screen:
    """One screen of the set: where it is, who looks, at which widths."""

    key: str
    path: str
    #: None (nobody signed in), "admin", or a member of the seed ("lid", …) —
    #: the roles of `screenshots._sessiewaarden`.
    session: Optional[str] = None
    widths: tuple[tuple[int, int], ...] = (PHONE, DESKTOP)
    #: Runs after the page has loaded: open a panel, switch to edit mode.
    action: Optional[Callable] = None
    #: Differing pixels this screen may have (the threshold per screen).
    allowed: int = ALLOWED_PIXELS
    #: The window only, not the whole page: a screen with something over it.
    viewport_only: bool = False


#: The set. Pilot A at 1 920, 1 440 and 390 px; pilot B at 390 and 1 440 px.
SCREENS: tuple[Screen, ...] = (
    Screen("betalingen", "/admin/betalingen", session="admin", widths=(WIDE, DESKTOP, PHONE)),
    Screen("public-home", "/"),
    Screen("public-activiteiten", "/activiteiten"),
)


def baseline_path(screen: Screen, width: tuple[int, int]) -> Path:
    return BASELINES / f"{screen.key}-{width[0]}.png"


def pairs(keys: Optional[list[str]] = None) -> list[tuple[Screen, tuple[int, int]]]:
    """Every (screen, width) of the set, or of the screens named."""
    known = {screen.key for screen in SCREENS}
    unknown = sorted(set(keys or []) - known)
    if unknown:
        raise SystemExit(
            f"unknown screen(s): {', '.join(unknown)} — known: {', '.join(sorted(known))}"
        )
    return [(s, w) for s in SCREENS if not keys or s.key in keys for w in s.widths]


def context_options() -> dict:
    """What every rendering shares: the screenshot flag of the shell (no
    environment band), the Dutch locale, no motion, and a device scale of 1 —
    a baseline may not depend on the screen of whoever recorded it."""
    from tests_e2e.screenshots import context_opties

    return {**context_opties(), "device_scale_factor": 1}


def render(page, screen: Screen, width: tuple[int, int], sessions: dict[str, str]) -> bytes:
    """One rendering of one screen at one width, frozen."""
    from tests_e2e.schermen import login_met_sessie

    base = local_base()
    page.context.clear_cookies()
    if screen.session:
        login_met_sessie(page, sessions[screen.session], base)
    # The browser's own clock: a page that reads `new Date()` sees the moment
    # the server lives in.
    page.clock.set_fixed_time(datetime.fromisoformat(PIXEL_NOW))
    page.set_viewport_size({"width": width[0], "height": width[1]})
    page.goto(base + screen.path)
    page.wait_for_load_state("networkidle")
    if screen.action:
        screen.action(page)
    page.add_style_tag(content=FREEZE_CSS)
    # Webfonts shift every line when they land late, and `fonts.ready` resolves
    # trivially for a face nobody asked for yet: load the weights first.
    page.evaluate(
        """Promise.all(['400', '500', '600', '700'].map(w => document.fonts.load(w + ' 1em Inter')))
             .then(() => document.fonts.ready).then(() => null)"""
    )
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')"
        " && document.getAnimations().length === 0"
    )
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    return page.screenshot(full_page=not screen.viewport_only)


def launch(playwright):
    """The pinned browser, started in Dutch (a native date field takes its field
    order from the language of the browser PROCESS, `screenshots.launch_opties`)."""
    from tests_e2e.screenshots import launch_opties

    options = dict(launch_opties())
    exe = os.environ.get("E2E_CHROMIUM_PATH")
    if exe:
        options["executable_path"] = exe
    return playwright.chromium.launch(**options)


def sessions() -> dict[str, str]:
    from tests_e2e.screenshots import _sessiewaarden

    return _sessiewaarden()


# ── Writing the baselines: a deliberate act ──────────────────────────────────


def write(keys: list[str]) -> int:
    """Render the screens (all, or the ones named) and write their baselines.

    Each screen is rendered twice and written only when the two renderings
    are the same by the comparison's own measure (not to the byte: measured,
    two renderings a second apart can differ by 2 of 255 in a channel): a
    baseline that the same machine cannot reproduce would be red on its first
    comparison."""
    from playwright.sync_api import sync_playwright

    try:
        base = local_base()
    except NotLocal as refusal:
        print(refusal, file=sys.stderr)
        return 2
    BASELINES.mkdir(parents=True, exist_ok=True)
    unstable = []
    with sync_playwright() as pw:
        browser = launch(pw)
        context = browser.new_context(base_url=base, **context_options())
        page = context.new_page()
        values = sessions()
        for screen, width in pairs(keys):
            first = render(page, screen, width, values)
            second = render(page, screen, width, values)
            target = baseline_path(screen, width)
            twice = compare(first, second)
            if not twice.within(0):
                unstable.append(f"{target.name}: {twice.describe()}")
                continue
            changed = not target.exists() or target.read_bytes() != first
            target.write_bytes(first)
            print(f"{'wrote' if changed else 'same '} {target.name}  {len(first) // 1024} kB")
        browser.close()
    for line in unstable:
        print(f"NOT WRITTEN, two renderings differ — {line}", file=sys.stderr)
    return 1 if unstable else 0


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments or arguments[0] != "--write":
        print("usage: python -m tests_e2e.pixels --write [screen ...]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(write(arguments[1:]))

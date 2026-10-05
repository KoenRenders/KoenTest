"""The pilot screens against their baselines (#1605; CR-11 B7 test 11).

Each screen of `pixels.SCREENS` is rendered at each of its widths against the
frozen pixel server and compared with `tests_e2e/baselines/<key>-<width>.png`.
More differing pixels than the screen allows is red; the message says how many
and where, and the rendering and a diff image are left in `PIXEL_OUT` (the CI
job uploads that directory when the comparison is red).

**This file needs the pixel server** (`PIXEL_BASE_URL`): a database of its own,
seeded and served under the frozen clock — `scripts/pixel-local.sh` locally,
its own steps in the CI job. Among the ordinary e2e's (real time, a seed the
tests consume) these tests are skipped, and they say so; where the pixel run is
meant (`PIXEL_REQUIRED=1`) a missing server is a failure, not a skip — a gate
that skips is green forever.

Renewing a baseline is a deliberate act: `scripts/pixel-local.sh --write
[screen …]`, and the new PNG ships in the pull request of the design change.
"""

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests_e2e import pixels

OUT = Path(os.environ.get("PIXEL_OUT", "/tmp/pixel-out"))


def _server() -> str:
    try:
        return pixels.local_base()
    except pixels.NotLocal as refusal:
        if os.environ.get("PIXEL_REQUIRED") == "1":
            pytest.fail(f"the pixel run is required here and has no server: {refusal}")
        pytest.skip(f"no pixel server ({refusal}) — run scripts/pixel-local.sh")


@pytest.fixture(scope="module")
def page():
    base = _server()
    with sync_playwright() as pw:
        browser = pixels.launch(pw)
        context = browser.new_context(base_url=base, **pixels.context_options())
        yield context.new_page()
        browser.close()


@pytest.fixture(scope="module")
def sessions():
    _server()
    return pixels.sessions()


def test_the_server_lives_in_the_frozen_moment(page):
    """The whole run rests on it: a server in real time renders today's dates
    and every baseline is red tomorrow. Read from the server's own `Date`
    header."""
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    response = page.request.get(pixels.local_base() + "/")
    served = parsedate_to_datetime(response.headers["date"]).astimezone(timezone.utc)
    frozen = datetime.fromisoformat(pixels.PIXEL_NOW)
    assert served.date() == frozen.date(), (
        f"the pixel server answers on {served.date()}, the baselines are of {frozen.date()}"
    )


def test_every_screen_has_its_baselines_and_no_baseline_is_an_orphan():
    expected = {pixels.baseline_path(s, w).name for s, w in pixels.pairs()}
    present = {p.name for p in pixels.BASELINES.glob("*.png")}
    assert expected - present == set(), "a screen without a baseline: run pixel-local.sh --write"
    assert present - expected == set(), "a baseline no screen of the set renders"


@pytest.mark.parametrize(
    ("screen", "width"),
    pixels.pairs(),
    ids=[f"{s.key}-{w[0]}" for s, w in pixels.pairs()],
)
def test_the_screen_is_its_baseline(page, sessions, screen, width):
    baseline = pixels.baseline_path(screen, width)
    assert baseline.exists(), f"no baseline {baseline.name} — pixel-local.sh --write {screen.key}"
    actual = pixels.render(page, screen, width, sessions)
    difference = pixels.compare(baseline.read_bytes(), actual)
    if not difference.within(screen.allowed):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{screen.key}-{width[0]}-actual.png").write_bytes(actual)
        (OUT / f"{screen.key}-{width[0]}-diff.png").write_bytes(difference.image)
        pytest.fail(
            f"{baseline.name}: {difference.describe()} (allowed: {screen.allowed}). "
            f"The rendering and the diff are in {OUT}. Meant? "
            f"scripts/pixel-local.sh --write {screen.key}"
        )

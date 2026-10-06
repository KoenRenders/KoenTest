"""The pilot screens against their measurement baselines (#1605; CR-11 B7 test 11).

Each screen of `measures.SCREENS` is measured at each of its widths against the
frozen measurement server and compared with `tests_e2e/baselines/<key>.json`.
An element that moved or changed its size by more than 1 px, or that appears
another number of times, is red; the message names the screen, the width, the
element and the two numbers.

**This file needs the measurement server** (`MEASURE_BASE_URL`): a database of
its own, seeded and served under the frozen clock — `scripts/measure-run.sh`,
which `scripts/measure-local.sh` and one step of the CI job call. Among the ordinary e2e's (real time, a
seed the tests consume) these tests are skipped, and they say so; where the
measurement run is meant (`MEASURE_REQUIRED=1`) a missing server is a failure,
not a skip — a gate that skips is green forever.

Renewing a baseline is a deliberate act: `scripts/measure-local.sh --write
[screen …]`, and the changed numbers ship in the pull request of the design
change, where the diff shows which element moved.

Proven red (on this branch, each an added violation, restored after): the key
figures' strip given 2 px of margin above it → "betalingen @1440 — content
row: y 253 → 255; key figure: y 96 → 98; table: y 216 → 218; toolbar: y 166 →
168; …"; the date tile of a public card given 2 px of margin at its left →
"public-activiteiten @390 — … card title: x 101 → 103; … date tile: x 41 →
43"; the toolbar's hook removed from the kit macro → "required element(s) not
on the screen: toolbar ([data-toolbar])"; a baseline file moved away → "no
baseline betalingen.json @1440" and "a screen without a baseline".
"""

import os

import pytest
from playwright.sync_api import sync_playwright

from tests_e2e import measures


def _server() -> str:
    try:
        return measures.local_base()
    except measures.NotLocal as refusal:
        if os.environ.get("MEASURE_REQUIRED") == "1":
            pytest.fail(f"the measurement run is required here and has no server: {refusal}")
        pytest.skip(f"no measurement server ({refusal}) — run scripts/measure-local.sh")


@pytest.fixture(scope="module")
def context():
    base = _server()
    with sync_playwright() as pw:
        browser = measures.launch(pw)
        yield browser.new_context(base_url=base, **measures.context_options())
        browser.close()


@pytest.fixture(scope="module")
def sessions():
    _server()
    return measures.sessions()


def test_the_server_lives_in_the_frozen_moment(context):
    """The whole run rests on it: a server in real time renders today's dates
    and counts, and every baseline is red tomorrow. Read from the server's own
    `Date` header."""
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    response = context.request.get(measures.local_base() + "/")
    served = parsedate_to_datetime(response.headers["date"]).astimezone(timezone.utc)
    frozen = datetime.fromisoformat(measures.MEASURE_NOW)
    assert served.date() == frozen.date(), (
        f"the measurement server answers on {served.date()}, the baselines are of {frozen.date()}"
    )


def test_every_screen_has_its_baseline_and_no_baseline_is_an_orphan():
    _server()
    expected = {measures.baseline_path(screen).name for screen in measures.SCREENS}
    present = {path.name for path in measures.BASELINES.glob("*.json")}
    assert expected - present == set(), "a screen without a baseline: measure-local.sh --write"
    assert present - expected == set(), "a baseline no screen of the set measures"
    for screen in measures.SCREENS:
        widths = set(measures.read_baseline(screen))
        assert widths == {str(width[0]) for width in screen.widths}, (
            f"{screen.key}: the baseline holds {sorted(widths)}, the screen is measured at "
            f"{sorted(str(w[0]) for w in screen.widths)}"
        )


@pytest.mark.parametrize(
    ("screen", "width"),
    measures.pairs(),
    ids=[f"{s.key}-{w[0]}" for s, w in measures.pairs()],
)
def test_the_screen_measures_as_its_baseline(context, sessions, screen, width):
    base = measures.local_base()
    baseline = measures.read_baseline(screen).get(str(width[0]))
    assert baseline, (
        f"no baseline {measures.baseline_path(screen).name} @{width[0]} — "
        f"scripts/measure-local.sh --write {screen.key}"
    )
    # A baseline that does not hold what the screen requires measures nothing.
    for name in screen.required:
        assert name in baseline, f"{screen.key} @{width[0]}: the baseline lacks {name!r}"
    actual = measures.measure(context, screen, width, sessions, base)
    # Where the run asks for it: one line per screen and width with the largest
    # difference, also when it is within the tolerance — what this machine
    # measures against the machine that wrote the baseline.
    report = os.environ.get("MEASURE_REPORT")
    if report:
        with open(report, "a") as out:
            out.write(f"{screen.key} @{width[0]}: {measures.largest(baseline, actual)} px\n")
    lines = measures.differences(baseline, actual)
    assert not lines, (
        f"{screen.key} @{width[0]} — "
        + "; ".join(lines)
        + f". Meant? scripts/measure-local.sh --write {screen.key}"
    )

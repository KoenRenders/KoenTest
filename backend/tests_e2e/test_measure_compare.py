"""The measurement baseline's own rules, without a browser (#1605; CR-11 Q60).

What the comparison calls a difference, what the run refuses to measure, and
what may stand in `tests_e2e/`:

- a position or a size 1 px off passes, 2 px off is named with both numbers;
- another count is a difference, and so is an element that came or went;
- only the LOCAL measurement server is measured;
- every element is named by a `data-…` hook, never by a class;
- no image is committed under `tests_e2e/` — the baselines are numbers.

Proven red (on this branch, restored after): `TOLERANCE` set to 2 → the 2 px
test fails; `"toolbar": ".toolbar"` put in `ADMIN_HOOKS` → the hook test names
it; an empty `x.png` laid in `tests_e2e/baselines/` → the image test names it.
"""

import json

import pytest

from tests_e2e import measures

BOX = {"count": 1, "x": 16, "y": 152, "w": 358, "h": 40}


def _moved(**changes):
    return {"element": {**BOX, **changes}}


def test_one_pixel_passes_and_two_are_named_with_both_numbers():
    baseline = {"element": dict(BOX)}
    assert measures.differences(baseline, _moved()) == []
    for part in ("x", "y", "w", "h"):
        assert measures.differences(baseline, _moved(**{part: BOX[part] + 1})) == []
        assert measures.differences(baseline, _moved(**{part: BOX[part] - 1})) == []
        assert measures.differences(baseline, _moved(**{part: BOX[part] + 2})) == [
            f"element: {part} {BOX[part]} → {BOX[part] + 2}"
        ]
    assert measures.TOLERANCE == 1


def test_another_count_is_a_difference_whatever_the_box():
    baseline = {"key figure": {**BOX, "count": 3}}
    assert measures.differences(baseline, {"key figure": {**BOX, "count": 4}}) == [
        "key figure: count 3 → 4"
    ]


def test_an_element_that_came_or_went_is_named():
    assert measures.differences({"toolbar": dict(BOX)}, {}) == ["toolbar: count 1 → 0"]
    assert measures.differences({}, {"action bar": dict(BOX)}) == ["action bar: count 0 → 1"]


def test_every_difference_of_a_screen_is_listed_not_only_the_first():
    baseline = {"a": dict(BOX), "b": dict(BOX), "c": dict(BOX)}
    actual = {"a": {**BOX, "y": 160}, "b": {**BOX, "h": 48, "count": 2}, "c": dict(BOX)}
    assert measures.differences(baseline, actual) == [
        "a: y 152 → 160",
        "b: count 1 → 2",
        "b: h 40 → 48",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://hdev.example.org",
        "https://www.example.org",
        "http://10.0.0.5:8000",
        "http://backend:8000",
        "",
    ],
)
def test_only_the_local_server_is_measured(url):
    with pytest.raises(measures.NotLocal):
        measures.local_base(url)


def test_the_local_server_is_accepted():
    assert measures.local_base("http://127.0.0.1:8001/") == "http://127.0.0.1:8001"
    assert measures.local_base("http://localhost:8001") == "http://localhost:8001"


def test_every_element_is_named_by_a_data_hook_and_never_by_a_class():
    hooks = {**measures.ADMIN_HOOKS, **measures.PUBLIC_HOOKS}
    assert len(hooks) >= 20, f"only {len(hooks)} hooks — the check would look nowhere"
    wrong = {name: sel for name, sel in hooks.items() if not _is_data_hook(sel)}
    assert not wrong, f"an element measured by something that is not a data hook: {wrong}"
    assert not _is_data_hook(".toolbar") and not _is_data_hook("[data-toolbar] .row")
    assert not _is_data_hook("#main") and _is_data_hook("[data-toolbar]")


def _is_data_hook(selector: str) -> bool:
    import re

    return re.fullmatch(r"\[data-[a-z][a-z-]*\]", selector) is not None


def test_what_a_screen_requires_is_an_element_of_its_shell():
    assert len(measures.SCREENS) >= 12
    keys = [screen.key for screen in measures.SCREENS]
    assert len(keys) == len(set(keys)), "two screens share a key, and so a baseline file"
    for screen in measures.SCREENS:
        assert screen.required, f"{screen.key} requires nothing — it could measure an empty page"
        unknown = [name for name in screen.required if name not in screen.hooks]
        assert not unknown, f"{screen.key} requires {unknown}, which its shell does not name"


def test_no_image_is_committed_under_tests_e2e():
    """Koen, 5 October 2026: no baseline images in the repository — a rendering
    of a screen is a picture of people and their payments. The baselines are
    JSON; a screenshot stays outside the checkout."""
    root = measures.BASELINES.parent
    images = sorted(
        str(path.relative_to(root))
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp")
        for path in root.rglob(pattern)
    )
    assert not images, f"an image under tests_e2e/: {images}"


def test_a_baseline_file_is_numbers_and_nothing_else():
    """What a baseline may hold: per width, per element name, a count and four
    integers. No text of a screen — no name, no amount — can be in it."""
    files = sorted(measures.BASELINES.glob("*.json"))
    assert files, "no baseline was found — the check would look nowhere"
    names = set(measures.ADMIN_HOOKS) | set(measures.PUBLIC_HOOKS) | {"page"}
    for path in files:
        for width, elements in json.loads(path.read_text()).items():
            assert width.isdigit(), (path.name, width)
            for name, box in elements.items():
                assert name in names, f"{path.name} @{width}: {name!r} is no element of the set"
                assert set(box) == {"count", "x", "y", "w", "h"}, (path.name, name, sorted(box))
                assert all(type(value) is int for value in box.values()), (path.name, name, box)


@pytest.mark.parametrize("database", ["raake2e", "raaktest_x", "raakmillegem_hdev", "postgres"])
def test_the_run_refuses_a_database_that_is_not_its_own(database):
    """`scripts/measure-run.sh` migrates and SEEDS its database: pointed at the
    e2e's or at a real one it must stop before it touches anything. Red with the
    `case` taken out of the script (it went on to alembic)."""
    import os
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "measure-run.sh"
    done = subprocess.run(
        ["bash", str(script)],
        env={
            **os.environ,
            "DATABASE_URL": f"postgresql+psycopg2://nobody:none@127.0.0.1:1/{database}",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 2, (done.returncode, done.stderr[-300:])
    assert "REFUSED" in done.stderr and "alembic" not in done.stderr

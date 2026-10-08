"""CR-29 R7 — the fixture `one_render_per_input` keeps an answer per INPUT, and only that.

The Design Studio's service tests render through it: Inkscape and the SVG preview
run once for an input and the answer is reused. That is only the same test as
before if a different input still reaches the real renderer — a fixture that
answered a new poster with an old render would turn every one of those tests
green for the wrong picture. So the fixture has a test of its own: what counts as
"the same input", what does not, and that a failure is never kept.

The real functions are replaced by counters BEFORE the fixture wraps them, so
this runs without Inkscape and counts exactly the calls that got through.

Broken to check these can go red (run, restored):
  * the export's key reduced to `(svg, kind)` → the width test fails: a PNG of
    another width came back from the first one;
  * `_INKSCAPE_EXPORTS[key] = …` moved before the real call's result is known
    (the answer stored from a `try/finally`) → the error test fails.
"""

import pytest

from app.domains.designstudio import render
from app.domains.media import svg as media_svg

pytestmark = pytest.mark.ui_agnostisch


@pytest.fixture
def calls(monkeypatch, request, tmp_path):
    """The three real functions as counters, wrapped by the fixture under test."""
    seen: list[tuple] = []

    def export(svg, kind, *, png_width_px=None):
        seen.append(("export", svg, kind, png_width_px))
        if svg == "broken":
            raise render.RenderError("no file")
        return f"{kind}:{png_width_px}:{len(seen)}".encode()

    def query_all(svg_path):
        seen.append(("query", svg_path.read_text(encoding="utf-8")))
        return {"title": (0.0, 0.0, 1.0, float(len(seen)))}

    def render_png(svg, width, height):
        seen.append(("preview", svg, width, height))
        return b"png%d" % len(seen)

    monkeypatch.setattr(render, "export", export)
    monkeypatch.setattr(render, "query_all", query_all)
    monkeypatch.setattr(media_svg, "render_png", render_png)
    request.getfixturevalue("one_render_per_input")
    return seen


def _unique(request, text: str) -> str:
    """An input no other test has asked: the answers are kept for the whole process."""
    return f"<svg><!-- {request.node.nodeid} --><text>{text}</text></svg>"


def test_the_same_export_is_made_once_and_gives_the_same_bytes(calls, request):
    svg = _unique(request, "a")

    first = render.export(svg, "pdf")
    second = render.export(svg, "pdf")

    assert first == second
    assert len(calls) == 1


def test_another_poster_another_kind_or_another_width_is_rendered_for_real(calls, request):
    svg = _unique(request, "a")

    answers = [
        render.export(svg, "pdf"),
        render.export(_unique(request, "b"), "pdf"),
        render.export(svg, "png", png_width_px=300),
        render.export(svg, "png", png_width_px=600),
    ]

    assert len(calls) == 4, "an input that was not asked before did not reach the renderer"
    assert len(set(answers)) == 4


def test_a_failed_render_is_not_kept(calls):
    for _ in range(2):
        with pytest.raises(render.RenderError):
            render.export("broken", "pdf")

    assert len(calls) == 2, "the failure was answered from memory the second time"


def test_a_measurement_is_kept_per_file_content_not_per_path(calls, request, tmp_path):
    one, two, other = tmp_path / "one.svg", tmp_path / "two.svg", tmp_path / "other.svg"
    one.write_text(_unique(request, "a"), encoding="utf-8")
    two.write_text(_unique(request, "a"), encoding="utf-8")
    other.write_text(_unique(request, "b"), encoding="utf-8")

    boxes = render.query_all(one)
    assert render.query_all(two) == boxes
    assert render.query_all(other) != boxes
    assert [call[0] for call in calls] == ["query", "query"]

    # What a caller does with its answer does not reach the next caller.
    boxes["title"] = (9.0, 9.0, 9.0, 9.0)
    assert render.query_all(one) != boxes


def test_a_preview_is_kept_per_svg_and_size(calls, request):
    svg = _unique(request, "a").encode()

    same = {media_svg.render_png(svg, 297.0, 420.0), media_svg.render_png(svg, 297.0, 420.0)}
    other_size = media_svg.render_png(svg, 210.0, 297.0)
    other_svg = media_svg.render_png(_unique(request, "b").encode(), 297.0, 420.0)

    assert len(same) == 1
    assert len({*same, other_size, other_svg}) == 3
    assert len(calls) == 3

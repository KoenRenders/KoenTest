"""E2E: the x labels of a chart stay readable for the number of bars a report has (#1978).

Koen, 13 October 2026, on "Opbrengst per activiteit" with seven activities: the
labels under the axis ran into each other. The kit's chart (`_chart_frame` in
`_macros.html`, shared by the bar, line and stacked charts) set them
horizontally, each in a slot of 608 / n units of the viewBox.

The chart is rendered here by the kit's own macro, in the frame the report panel
gives it (a card with a scroll box), on a page of the running application so its
stylesheet and font are the ones a visitor gets. Measured in the browser for 3, 7,
12 and 20 bars with labels of 8, 18 and 30 characters, at 390, 1 440 and 1 920 px:
no two x labels intersect, and none leaves the chart's box.

`MEASURE` lines print what was measured. Set `E2E_PRINTS` to a folder to keep a
print of each chart (outside the repository).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

#: The width of the report panel's content at each window (the card's inside).
CONTENT = {390: 326, 1440: 1100, 1920: 1500}
BARS = (3, 7, 12, 20)
LENGTHS = (8, 18, 30)

#: Each label's own box, turned as it is drawn: its four corners on the screen
#: (`getBBox` in its own coordinates, through `getScreenCTM`). Two labels touch
#: when no axis of either box separates them (the separating axis test) — the
#: screen's upright rectangles around slanted text always overlap, so they
#: cannot tell. Outside: a corner beyond the chart's svg.
_MEASURE = """(kind) => {
  const svg = document.querySelector('#meting svg');
  const box = svg.getBoundingClientRect();
  const quads = [...svg.querySelectorAll('text[data-x-label]')].map(t => {
    const b = t.getBBox(), m = t.getScreenCTM();
    return [[b.x, b.y], [b.x + b.width, b.y], [b.x + b.width, b.y + b.height], [b.x, b.y + b.height]]
      .map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
  });
  const axes = q => [0, 1].map(i => { const [a, b] = [q[i], q[i + 1]]; return [b[1] - a[1], a[0] - b[0]]; });
  const span = (q, [x, y]) => { const d = q.map(([px, py]) => px * x + py * y); return [Math.min(...d), Math.max(...d)]; };
  const touch = (p, q) => [...axes(p), ...axes(q)].every(ax => {
    const [a0, a1] = span(p, ax), [b0, b1] = span(q, ax); return a1 > b0 + 0.5 && b1 > a0 + 0.5; });
  let overlaps = 0;
  for (let i = 1; i < quads.length; i++) if (touch(quads[i - 1], quads[i])) overlaps++;
  const outside = quads.filter(q => q.some(([x, y]) =>
    x < box.left - 1 || x > box.right + 1 || y < box.top - 1 || y > box.bottom + 1)).length;
  return {labels: quads.length, overlaps, outside, svg_w: Math.round(box.width), svg_h: Math.round(box.height)};
}"""


def _label(i: int, length: int) -> str:
    stem = f"{i + 1:02d} Activiteit van de vereniging met een lange naam"
    return stem[:length]


def _chart_html(kind: str, bars: int, length: int) -> str:
    from app.ui import templates

    chart = {
        "title": f"Meting {bars} × {length}",
        "description": "Een meting van de labels (#1978).",
        "x_labels": [_label(i, length) for i in range(bars)],
        "series": [
            {
                "name": "Opbrengst",
                "points": [10 + 5 * (i % 7) for i in range(bars)],
                "color": "var(--brand-ocean)",
            },
            {
                "name": "Kosten",
                "points": [5 + 3 * (i % 5) for i in range(bars)],
                "color": "var(--brand-teal)",
            },
        ],
        "y_min": 0,
        "y_max": 50,
        "y_ticks": [0, 25, 50],
        "money": True,
    }
    source = (
        '{% import "_macros.html" as ui %}'
        '<div class="bg-white border border-gray-200 rounded-xl p-4"><div class="overflow-x-auto">'
        "{{ ui.chart_" + kind + '(chart, id="meting-chart") }}</div></div>'
    )
    return templates.env.from_string(source).render(chart=chart)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("kind", ["bar", "line", "stacked"])
@pytest.mark.parametrize("width", sorted(CONTENT))
def test_the_x_labels_never_touch_and_stay_in_the_chart(browser, width, kind):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    found = {}
    try:
        page.goto("/")
        pagina_klaar(page)
        for bars in BARS:
            for length in LENGTHS:
                html = _chart_html(kind, bars, length)
                page.evaluate(
                    """([html, w]) => { document.body.innerHTML =
                         `<div id="meting" style="width:${w}px;margin:16px">${html}</div>`; }""",
                    [html, CONTENT[width]],
                )
                m = page.evaluate(_MEASURE, kind)
                found[(bars, length)] = m
                folder = os.environ.get("E2E_PRINTS")
                if folder and kind == "bar":
                    os.makedirs(folder, exist_ok=True)
                    page.locator("#meting").screenshot(
                        path=os.path.join(folder, f"1978-{kind}-{width}-{bars}x{length}.png")
                    )
    finally:
        page.close()
    for (bars, length), m in found.items():
        print(f"MEASURE {kind} @{width} {bars} bars × {length} chars: {m}")
    bad = {
        key: m for key, m in found.items() if m["overlaps"] or m["outside"] or m["labels"] != key[0]
    }
    assert not bad, f"{kind} @{width}: labels touch or leave the chart: {bad}"

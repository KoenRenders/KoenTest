"""The kit pager has one wording: "x–y van n" (#1391, CR-11 W8).

The "Pagina n" branch for lists that did not count is gone, so a caller must
pass `per_page` and `total`. Proven red by putting the old `{{ _("Pagina") }}`
line back in the macro (the first test) and by dropping the `param` argument
(the second).
"""

from pathlib import Path

from app.ui import templates

APP = Path(__file__).resolve().parents[1] / "app"


def _render(body: str) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render()


def test_the_pager_says_x_to_y_of_n_and_never_page_n():
    html = _render("{{ ui.pager(2, 50, 132, hx_get='/x', hx_target='#t') }}")
    assert "51–100 van 132" in html
    assert "Pagina" not in html.replace("Paginering", "")
    assert 'hx-get="/x?page=3"' in html and 'hx-target="#t"' in html


def test_the_parameter_name_and_the_inherited_target():
    html = _render("{{ ui.pager(1, 50, 60, hx_get='/p?report=4', param='goto') }}")
    assert 'hx-get="/p?report=4&amp;goto=2"' in html
    assert "hx-target" not in html and "hx-swap" not in html


def test_no_list_passes_the_old_arguments():
    """has_prev/has_next belonged to the "Pagina n" mode; a caller still passing
    them would fail at render time, but only on the screen that pages."""
    scanned = 0
    offenders = []
    for path in APP.rglob("*.html"):
        text = path.read_text()
        if "ui.pager(" not in text:
            continue
        scanned += 1
        call = text[text.index("ui.pager(") :]
        call = call[: call.index("}}")]
        if "has_prev" in call or "has_next" in call:
            offenders.append(str(path.relative_to(APP)))
    assert scanned >= 6, f"found only {scanned} pager callers"
    assert not offenders, offenders

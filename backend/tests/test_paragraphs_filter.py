"""Plain text as paragraphs: the `alineas` filter (#1647; CR-11 Q83).

The public activity page shows an activity's description as reading text. The
description is PLAIN text: a blank line in it is a paragraph, a single line
break a line break — and nothing in it reaches the page as markup.

Red against master `4747a136`: there was no such filter; the page rendered the
text in one block with `white-space: pre-line`.
"""

from __future__ import annotations

from app.ui import templates


def _render(text) -> str:
    return templates.env.from_string("{{ text | alineas }}").render(text=text)


def test_a_blank_line_is_a_paragraph_and_a_single_enter_a_line_of_its_own():
    """#1688: a line after one Enter is an element the page can give a little
    space — until then it was a `<br>`, and a statement that wrapped could not
    be told from the next one. Red against master: `<br>`."""
    html = _render("Eerste alinea.\nTweede regel ervan.\n\nTweede alinea.")
    assert html == (
        "<p><span data-line>Eerste alinea.</span><span data-line>Tweede regel ervan.</span></p>"
        "<p>Tweede alinea.</p>"
    )


def test_seven_statements_with_one_enter_each_are_seven_lines_in_one_paragraph():
    html = _render("\n".join(f"Punt {n}." for n in range(1, 8)))
    assert html.count("<p>") == 1 and html.count("<span data-line>") == 7
    assert "<br>" not in html


def test_windows_line_ends_and_a_line_of_spaces_make_no_empty_line():
    html = _render("Een.\r\nTwee.\r\n   \r\nDrie.\r\n")
    assert html == "<p><span data-line>Een.</span><span data-line>Twee.</span></p><p>Drie.</p>"


def test_more_blank_lines_and_windows_breaks_give_no_empty_paragraph():
    html = _render("\n\nEen.\r\n\r\n\r\n  \r\nTwee.\n\n")
    assert html == "<p>Een.</p><p>Twee.</p>"


def test_nothing_in_the_text_reaches_the_page_as_markup():
    html = _render(
        '<script>alert(1)</script>\n\n<b>vet</b> & "aanhaling" <img src=x onerror=y>\n</span><p data-line>regel'
    )
    assert "<script" not in html and "<b>" not in html and "<img" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;vet&lt;/b&gt; &amp; " in html
    # Only what the filter writes itself is markup.
    stripped = html
    for own in ("<p>", "</p>", "<span data-line>", "</span>"):
        stripped = stripped.replace(own, "")
    assert "<" not in stripped and ">" not in stripped


def test_no_text_is_no_paragraph():
    assert _render(None) == "" and _render("") == "" and _render("  \n \n") == ""

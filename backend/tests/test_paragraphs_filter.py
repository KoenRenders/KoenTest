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


def test_a_blank_line_is_a_paragraph_and_a_single_break_a_line_break():
    html = _render("Eerste alinea.\nTweede regel ervan.\n\nTweede alinea.")
    assert html == "<p>Eerste alinea.<br>Tweede regel ervan.</p><p>Tweede alinea.</p>"


def test_more_blank_lines_and_windows_breaks_give_no_empty_paragraph():
    html = _render("\n\nEen.\r\n\r\n\r\n  \r\nTwee.\n\n")
    assert html == "<p>Een.</p><p>Twee.</p>"


def test_nothing_in_the_text_reaches_the_page_as_markup():
    html = _render('<script>alert(1)</script>\n\n<b>vet</b> & "aanhaling" <img src=x onerror=y>')
    assert "<script" not in html and "<b>" not in html and "<img" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;vet&lt;/b&gt; &amp; " in html
    # Only what the filter writes itself is markup.
    stripped = html.replace("<p>", "").replace("</p>", "").replace("<br>", "")
    assert "<" not in stripped and ">" not in stripped


def test_no_text_is_no_paragraph():
    assert _render(None) == "" and _render("") == "" and _render("  \n \n") == ""

"""Reading a refusal as the screen gets it (#1831).

A form that refuses answers the kit's `refusal_response`: an HTML 422 that htmx
swaps into the form's message line (`HX-Retarget`) — the banner alone. A test
that only read a status and a JSON `detail` proved the server refused, not that
the screen says why: a bare JSON error is not swapped, and the page shows its
general message instead.

These two read what the page will show and where.
"""

from __future__ import annotations

import html
import re

_SENTENCE = re.compile(r'<p class="mt-1">(.*?)</p>', re.S)
_HEADING = re.compile(r'<p class="font-semibold">(.*?)</p>', re.S)


def said(answer) -> list[str]:
    """The sentences under the heading of the kit's refusal banner, as text. Fails
    when the answer is not that banner — a JSON error says nothing on a screen."""
    kind = answer.headers.get("content-type", "")
    assert "text/html" in kind, f"not an HTML answer ({kind}): the screen shows its general message"
    assert "data-save-refusal" in answer.text, "not the kit's refusal banner"
    return [html.unescape(" ".join(found.split())) for found in _SENTENCE.findall(answer.text)]


def heading(answer) -> str:
    return html.unescape(" ".join(_HEADING.search(answer.text).group(1).split()))


def message_line(answer) -> str:
    """The selector of the message line the banner is swapped into."""
    line = answer.headers.get("HX-Retarget")
    assert line, "the refusal names no message line (HX-Retarget)"
    assert answer.headers.get("HX-Reselect") == "[data-save-refusal]"
    return line

"""The action bar's optional second save (`extra_label`, #2120).

Two promises. Without the parameter the bar is what it was, byte for byte — the four
hashes below were taken from the macro of master before the change, on four bars (a plain
one, one with Verwijderen, a sent one, one with a refused Verwijderen). With it, a second
submit of the same form stands between Annuleren and Opslaan, carrying its own name and
value, and the first save is untouched.

Proven red by dropping the `-` of `{%- if extra_label %}` in the macro: the plain bar then
gains a blank line and its hash changes.
"""

import hashlib
import re

from app.ui import templates

BARS = {
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True) }}": "3ba9b876da0bfa19",
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, delete_attrs='hx-post=\"/x\"', delete_confirm='Zeker?') }}": "ee875e319768949e",
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, send=True, save_label='Inschrijven', busy_label='Bezig…') }}": "6767a7286b554035",
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, delete_refused='Nee', delete_refused_title='Waarom') }}": "4f887b70d3e70c5f",
}


def _render(call: str) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + call).render()


def test_a_bar_without_the_parameter_renders_as_it_always_did():
    for call, expected in BARS.items():
        got = hashlib.sha256(_render(call).encode()).hexdigest()[:16]
        assert got == expected, f"the bar changed without `extra_label`: {call}"


def test_the_second_save_stands_between_annuleren_and_opslaan():
    html = _render(
        "{{ ui.action_bar(form='f', cancel_href='/terug', record=True,"
        " extra_label='Bewaren en voorbeeld vernieuwen', extra_name='blijven') }}"
    )
    bar = html[: html.index("<template data-save-failed>")]
    assert (
        bar.index("data-form-cancel")
        < bar.index("data-form-save-extra")
        < bar.index("data-form-save ")
    )
    extra = re.search(r"<button[^>]*data-form-save-extra[^>]*>", bar).group(0)
    assert 'type="submit"' in extra and 'form="f"' in extra
    assert 'name="blijven"' in extra and 'value="1"' in extra
    assert "Bewaren en voorbeeld vernieuwen" in bar and "Bewaren en voorbeeld vernieuwen…" in bar
    # the first save is still the one the keyboard and the gate know
    assert bar.count("data-form-save ") == 1
    assert "Opslaan" in bar


def test_a_second_save_without_a_name_posts_nothing_extra():
    html = _render(
        "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, extra_label='Nog een') }}"
    )
    extra = re.search(r"<button[^>]*data-form-save-extra[^>]*>", html).group(0)
    assert "name=" not in extra

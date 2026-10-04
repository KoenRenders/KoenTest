"""The record head is one macro, its actions data (CR-11 block 5, #1557).

`design-system-end-state.md` §3.9: a screen hands `ui.record_header` its actions
as a list and the macro places them; a screen cannot draw a button of its own in
the head. §2.2: the way back is the macro's too — a screen never writes that link
itself.

The gate reads every template that calls the macro (a *head partial*) and every
page that includes one. It was proven red on the real file by adding
`{{ ui.btn_secondary("Extra", href="/x") }}` under the macro call in
`_aa_recordkop.html` (an additive violation), and the tests below keep that proof
on a synthetic source.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

MACRO = "ui.record_header("

#: What a screen may not draw beside the macro: any control of its own, the way
#: back, or the old tab strip.
FORBIDDEN = [
    (r"\bui\.btn_\w+\(", "a `btn_*` beside the macro"),
    (r"\bui\.button\(", "a `button` beside the macro"),
    (r"\bui\.link_action\(", "a `link_action` beside the macro"),
    (r"\bui\.row_actions\(", "`row_actions` beside the macro"),
    (r"\bui\.back_link\(", "a way back of its own"),
    (r"\bui\.tabs\(", "the old tab strip (`related_tabs` is the record's)"),
    (r"<button\b", "a raw <button>"),
    (r"<a\b", "a raw <a>"),
]

#: The one `{% call %}` body the macro accepts, per head partial: what it may
#: contain and the issue that takes it away. Empty since K8 (#1562): the
#: per-screen assistant overlay left the activity's head with the shell's panel
#: (§3.15). A list that only shrinks.
CALL_BODY_EXCEPTIONS: dict[str, tuple[str, str]] = {}


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def head_violations(rel: str, source: str) -> list[str]:
    """What `source` (a template that calls the macro) draws beside it."""
    text = _without_comments(source)
    found = []
    call = re.search(
        r"\{%-?\s*call\s+ui\.record_header\(.*?%\}(.*?)\{%-?\s*endcall\s*-?%\}", text, re.S
    )
    if call:
        body = call.group(1)
        allowed, _issue = CALL_BODY_EXCEPTIONS.get(rel, (None, None))
        statements = re.findall(r"\{\{(.*?)\}\}", body, re.S)
        if allowed is None:
            found.append(
                f"{rel}: a `{{% call %}}` body in the record head, and no exception names it"
            )
        elif not statements or any(allowed not in s for s in statements):
            found.append(f"{rel}: the `{{% call %}}` body holds more than `{allowed}…)`")
        # The body is judged above; the rest of the file by the list below.
        text = text.replace(body, "")
    for pattern, what in FORBIDDEN:
        if re.search(pattern, text):
            found.append(f"{rel}: {what}")
    return found


def _templates() -> dict[str, str]:
    return {
        str(p.relative_to(APP)): p.read_text()
        for p in APP.rglob("templates/**/*.html")
        if p.name != "_macros.html" and p.name != "design_system.html"
    }


def _head_partials() -> dict[str, str]:
    return {rel: src for rel, src in _templates().items() if MACRO in _without_comments(src)}


def test_the_gate_finds_the_record_heads():
    """A gate that looks nowhere is green forever: the activity's head is on the
    macro, and the gate must see it."""
    partials = _head_partials()
    assert "domains/activities/templates/_aa_recordkop.html" in partials, sorted(partials)


def test_no_screen_draws_a_control_beside_the_record_header():
    violations = [v for rel, src in _head_partials().items() for v in head_violations(rel, src)]
    assert violations == []


def test_a_page_with_a_record_head_writes_no_way_back_of_its_own():
    """The page that includes a head partial leaves the way back to it: a
    `back_link` (or a second header) above the include is the old frame."""
    partials = {Path(rel).name for rel in _head_partials()}
    pages = {
        rel: _without_comments(src)
        for rel, src in _templates().items()
        if any(f'include "{name}"' in src for name in partials)
    }
    assert len(pages) >= 3, sorted(pages)  # the activity's three tab pages
    violations = [
        f"{rel}: {call}"
        for rel, text in pages.items()
        for call in ("ui.back_link(", "ui.page_header(")
        if call in text
    ]
    assert violations == []


def test_a_page_with_a_record_head_starts_with_it():
    """W16 for a page on the macro: the head — and so the way back — is the first
    thing it renders. Comments, `{% import %}`, `{% set %}` and a wrapper that only
    names the head for an out-of-band swap render nothing before it."""
    partials = {Path(rel).name for rel in _head_partials()}
    checked = 0
    for rel, src in _templates().items():
        if not any(f'include "{name}"' in src for name in partials):
            continue
        text = _without_comments(src)
        if "{% block content %}" not in text:
            continue  # a fragment that carries the head along, not a page
        lines = [
            line.strip()
            for line in text.split("{% block content %}", 1)[1].splitlines()
            if line.strip() and not line.strip().startswith(("{% import", "{% set"))
        ]
        if re.fullmatch(r'<div id="[\w-]+">', lines[0]):
            lines = lines[1:]
        assert any(lines[0] == f'{{% include "{name}" %}}' for name in partials), (
            f"{rel}: {lines[0]!r}"
        )
        checked += 1
    assert checked >= 3


def test_every_exception_still_exists():
    """An exception whose file no longer uses it must leave the list (#1562
    removes the overlay and this entry together)."""
    for rel, (allowed, _issue) in CALL_BODY_EXCEPTIONS.items():
        assert allowed in _without_comments((APP / rel).read_text()), rel


# ── The red proof, kept: the checker on a synthetic head ─────────────────────

CLEAN = (
    '{% import "_macros.html" as ui %}\n{{ ui.record_header(head.title, actions=head.actions) }}\n'
)


def test_a_clean_head_passes():
    assert head_violations("x/_head.html", CLEAN) == []


def test_a_button_beside_the_macro_is_red():
    source = CLEAN + '{{ ui.btn_secondary("Extra", href="/x") }}\n'
    assert head_violations("x/_head.html", source) == ["x/_head.html: a `btn_*` beside the macro"]


def test_a_commented_button_is_not_a_button():
    source = CLEAN + '{# {{ ui.btn_secondary("Extra", href="/x") }} #}\n'
    assert head_violations("x/_head.html", source) == []


def test_a_call_body_without_an_exception_is_red():
    source = '{% call ui.record_header(head.title) %}{{ raakje.overlay("AI", "/x", "", m) }}{% endcall %}'
    assert head_violations("x/_head.html", source) == [
        "x/_head.html: a `{% call %}` body in the record head, and no exception names it"
    ]


def test_since_k8_no_head_has_a_call_body_at_all():
    """#1562 took the overlay out of the activity's head and the exception with
    it: the list is empty, so the head that carried it is refused like any
    other — and the mechanism still tells one allowed body from more (kept as
    the red proof of the exception's own rule)."""
    assert not CALL_BODY_EXCEPTIONS
    rel = "domains/activities/templates/_aa_recordkop.html"
    was = '{% call ui.record_header(t) %}{% if on %}{{ raakje.overlay("AI", "/x", "", m) }}{% endif %}{% endcall %}'
    assert head_violations(rel, was) == [
        f"{rel}: a `{{% call %}}` body in the record head, and no exception names it"
    ]

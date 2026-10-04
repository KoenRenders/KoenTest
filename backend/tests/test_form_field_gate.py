"""The kit owns the field (CR-11 block 6, #1558; B7 tests 8, 9 and 19).

`design-system-end-state.md` §3.1, §3.2, §3.4, §3.5:

- a form control comes from `ui.field`; a raw `<label>`, `<input>`, `<select>` or
  `<textarea>` in a domain template is the old way. Inside a kit `section` it is
  red outright. Across the templates the counts — raw elements, raw checkboxes —
  are ratchets per file in `test_ui_ratchets.py` (#1563), which replaced the two
  integers that stood here with room to grow;
- the kind decides the width: a `url`, `email`, `textarea` or `upload` field with
  `span="half"` or `span="quarter"` is red;
- `rare_settings` is the last slot: a `section` after it is red.

Each rule was proven red on a real template with an additive violation (noted at
the rule), and the checkers keep that proof on synthetic sources.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

FULL_KINDS = {"url", "email", "textarea", "upload", "checkbox_group", "radio_group"}

_RAW = re.compile(r"<(label|select|textarea)\b|<input\b(?![^>]*type=\"hidden\")")


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _domain_templates() -> dict[str, str]:
    found = {
        str(p.relative_to(APP)): _without_comments(p.read_text())
        for p in (APP / "domains").rglob("templates/**/*.html")
    }
    assert len(found) > 100, f"only {len(found)} domain templates found — the glob looks nowhere"
    return found


def _all_templates() -> dict[str, str]:
    return {
        str(p.relative_to(APP)): _without_comments(p.read_text())
        for p in APP.rglob("templates/**/*.html")
        if p.name != "_macros.html"
    }


# ── The checkers ─────────────────────────────────────────────────────────────


def raw_in_sections(rel: str, text: str) -> list[str]:
    """Raw form elements between `{% call ui.section(…) %}` (or
    `ui.rare_settings`) and its `{% endcall %}`."""
    found = []
    for body in re.findall(
        r"\{%-?\s*call\s+ui\.(?:section|rare_settings)\(.*?%\}(.*?)\{%-?\s*endcall\s*-?%\}",
        text,
        re.S,
    ):
        for m in _RAW.finditer(body):
            found.append(f"{rel}: a raw <{m.group(1) or 'input'}> inside a kit section")
    return found


def _field_calls(text: str) -> list[tuple[str, str, str]]:
    """(name, kind, span) of every `ui.field(…)` call with literal arguments."""
    calls = []
    for m in re.finditer(r"ui\.field\((.*?)\)\s*\}\}", text, re.S):
        args = m.group(1)
        name = re.match(r"\s*\"([^\"]*)\"", args)
        kind = re.search(r"\bkind=\"(\w+)\"", args)
        span = re.search(r"\bspan=\"(\w+)\"", args)
        calls.append(
            (
                name.group(1) if name else "?",
                kind.group(1) if kind else "text",
                span.group(1) if span else "",
            )
        )
    return calls


def narrowed_fields(rel: str, text: str) -> list[str]:
    return [
        f"{rel}: field {name!r} of kind {kind} with span={span!r} — the kind decides the width"
        for name, kind, span in _field_calls(text)
        if kind in FULL_KINDS and span in ("half", "quarter")
    ]


def section_after_rare(rel: str, text: str) -> list[str]:
    rare = text.find("ui.rare_settings(")
    if rare != -1 and "ui.section(" in text[rare:]:
        return [f"{rel}: a `section` after `rare_settings` — the rare section is the last slot"]
    return []


# ── The rules on the real templates ──────────────────────────────────────────


def test_the_gate_finds_the_forms_on_the_kit():
    """A gate that finds nothing is green forever: the activity's fiche calls
    `ui.section` and `ui.field`, and the gate must see both."""
    text = _domain_templates()["domains/activities/templates/_aa_detail.html"]
    assert text.count("ui.section(") >= 3
    assert len(_field_calls(text)) >= 8


def test_no_raw_form_element_inside_a_kit_section():
    """Proven red by adding `<input name="x">` inside the section *Publiek* of
    `_aa_detail.html`."""
    found = [v for rel, text in _all_templates().items() for v in raw_in_sections(rel, text)]
    assert found == []


def test_no_long_field_is_narrowed():
    """Proven red by adding `span="half"` to the description field of
    `_aa_detail.html`."""
    found = [v for rel, text in _all_templates().items() for v in narrowed_fields(rel, text)]
    assert found == []


def test_the_rare_section_is_the_last():
    """Proven red by moving the section *Intern* of `_aa_detail.html` under the
    rare section — on a copy, see the synthetic test."""
    found = [v for rel, text in _all_templates().items() for v in section_after_rare(rel, text)]
    assert found == []


# ── The red proofs, kept ─────────────────────────────────────────────────────

FORM = (
    '{% call ui.section("A") %}{{ ui.field("name", "Naam", value=a.name) }}\n'
    '{{ ui.field("description", "Omschrijving", kind="textarea", value=a.description) }}{% endcall %}\n'
    '{% call ui.rare_settings("Extern") %}{{ ui.field("poster_url", "URL", kind="url") }}{% endcall %}\n'
)


def test_a_clean_form_passes():
    assert raw_in_sections("x.html", FORM) == []
    assert narrowed_fields("x.html", FORM) == []
    assert section_after_rare("x.html", FORM) == []


def test_a_raw_input_inside_a_section_is_red():
    source = FORM.replace("{% endcall %}", '<input name="x">{% endcall %}', 1)
    assert raw_in_sections("x.html", source) == ["x.html: a raw <input> inside a kit section"]
    hidden = FORM.replace("{% endcall %}", '<input type="hidden" name="x">{% endcall %}', 1)
    assert raw_in_sections("x.html", hidden) == [], "a hidden input is no control"


def test_a_narrowed_textarea_is_red_and_a_narrowed_number_is_not():
    source = FORM.replace('kind="textarea"', 'kind="textarea", span="half"')
    assert narrowed_fields("x.html", source) == [
        "x.html: field 'description' of kind textarea with span='half' — the kind decides the width"
    ]
    number = FORM + '{{ ui.field("max", "Maximum", kind="number", span="quarter") }}'
    assert narrowed_fields("x.html", number) == []


def test_a_section_after_the_rare_section_is_red():
    source = FORM + '{% call ui.section("B") %}{% endcall %}'
    assert section_after_rare("x.html", source) == [
        "x.html: a `section` after `rare_settings` — the rare section is the last slot"
    ]

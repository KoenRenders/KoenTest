"""The kit's field, section and rare section (CR-11 block 6, #1558).

Norm: `docs/design-system-end-state.md` §3.1, §3.2, §3.4, §3.5. The sizes — a
half field of 361 px, a control of 40 px, one column under 532 px — are
measured in a browser (`tests_e2e/test_form_fields.py`); here the markup and the
rules the macro decides are pinned.
"""

import re

import pytest

from app.ui import templates


def _render(body: str, **ctx) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render(**ctx)


def _field(**kwargs) -> str:
    args = {"name": "veld", "label": "Veld", **kwargs}
    return _render("{{ ui.field(**args) }}", args=args)


def _span(html: str) -> str:
    return re.search(r'data-span="(\w+)"', html).group(1)


# ── The kind decides the width ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind", ["url", "email", "textarea", "upload", "checkbox_group", "radio_group"]
)
def test_a_long_kind_is_full_whatever_the_template_asks(kind):
    """A template may not narrow a long field: the macro renders it full, and
    the gate (`test_form_field_gate.py`) names the template."""
    for span in (None, "half", "quarter"):
        assert _span(_field(kind=kind, span=span)) == "full", (kind, span)


@pytest.mark.parametrize(
    "kind", ["text", "slug", "phone", "select", "switch", "segmented", "number", "date", "time"]
)
def test_a_short_kind_is_half_and_may_be_widened(kind):
    assert _span(_field(kind=kind)) == "half"
    assert _span(_field(kind=kind, span="full")) == "full"


def test_only_a_short_kind_may_be_a_quarter():
    """A short text joined them with #1590: a house number and a bus stand a
    quarter wide beside the street (end state §2.6)."""
    for kind in ("number", "date", "time", "select", "switch", "text"):
        assert _span(_field(kind=kind, span="quarter")) == "quarter", kind
    for kind in ("slug", "phone", "segmented"):
        assert _span(_field(kind=kind, span="quarter")) == "half", kind


def test_a_long_text_field_is_full():
    assert _span(_field(kind="text", long=True)) == "full"


# ── The anatomy of a field ───────────────────────────────────────────────────


def test_the_label_stands_above_its_control_and_names_it():
    html = _field(name="location", label="Locatie", value="Parochiezaal")
    assert html.index("<label") < html.index("<input")
    assert 'for="location"' in html and 'id="location"' in html and 'name="location"' in html
    assert 'value="Parochiezaal"' in html


def test_required_marks_the_label_in_red_and_the_control():
    html = _field(required=True)
    assert '<span class="text-red-600">*</span>' in html
    assert re.search(r"<input[^>]*\brequired\b", html)
    assert "*" not in _field()


def test_help_stands_under_the_control_and_is_tied_to_it():
    html = _field(help="Kort en duidelijk.")
    assert html.index("<input") < html.index("data-field-help")
    assert 'aria-describedby="veld-help"' in html and 'id="veld-help"' in html


def test_an_error_replaces_the_help_and_colours_the_border():
    html = _field(help="Kort en duidelijk.", error="Vul dit veld in.")
    assert "data-field-error" in html and "data-field-help" not in html
    assert 'aria-invalid="true"' in html and 'aria-describedby="veld-error"' in html
    control = re.search(r"<input[^>]*>", html).group(0)
    assert "border-red-700" in control and "border-control-line" not in control
    label = re.search(r"<label[^>]*>", html).group(0)
    assert "red" not in label, "the label stays ink"


def test_a_slug_is_not_capitalised_or_spell_checked():
    html = _field(kind="slug", value="zomerfeest-2031")
    assert 'autocapitalize="none"' in html and 'spellcheck="false"' in html
    assert "autocapitalize" not in _field(kind="text")


def test_a_number_carries_its_unit_inside_the_control():
    html = _field(kind="number", value="12.50", unit="€")
    assert html.index('aria-hidden="true"') < html.index("<input")
    assert ">€</span>" in html and "pl-8" in html


def test_a_control_outside_its_form_names_the_form():
    assert 'form="aa-act-form"' in _field(kind="url", form="aa-act-form")
    assert 'form="aa-act-form"' in _field(kind="textarea", form="aa-act-form")


def test_a_textarea_is_the_kits_own_and_grows_with_its_text():
    """#1027: every multi-line box grows. The field must not bring a second,
    static textarea into the kit."""
    html = _field(kind="textarea", value="Een tekst.")
    assert "groei()" in html and ">Een tekst.</textarea>" in html


# ── The switch: the knob at the left, the label at its right ─────────────────


def _checkbox(html: str) -> str:
    return re.search(r'<input type="checkbox"[^>]*>', html).group(0)


def test_the_switch_has_its_knob_at_the_left_of_its_label():
    """Block 6 (Koen, 4 October 2026): as a checkbox reads, 8 px apart — two
    half-width switches on one row never put a knob beside the wrong label.

    Proven red with `justify-between` on the switch's label (the knob at the far
    right of the field).
    """
    html = _field(kind="switch", name="members_only", label="Enkel leden", value=True)
    assert (
        html.index('type="checkbox"')
        < html.index("data-switch-track")
        < html.index("data-switch-label")
    )
    track = re.search(r"<span data-switch-track[^>]*>", html).group(0)
    assert 'class="relative h-6 w-11' in track, (
        "the track carries its classes — without them it is not drawn"
    )
    wrapper = re.search(r"<label[^>]*>", html).group(0)
    assert "gap-2" in wrapper, "8 px between the knob and the label"
    assert "justify-between" not in wrapper and "flex-row-reverse" not in wrapper
    box = _checkbox(html)
    assert 'role="switch"' in box and "checked" in box
    assert 'name="members_only"' in box and 'value="1"' in box
    assert "checked" not in _checkbox(_field(kind="switch", value=False))


def test_the_field_switch_is_the_kits_one_switch():
    """One switch in the kit (#1568): a form section shows the macro a settings
    card shows, not a second drawing of it."""
    field = _field(kind="switch", name="members_only", label="Enkel leden", value=True)
    macro = _render("{{ ui.switch('members_only', 'Enkel leden', checked=True) }}")
    assert macro.strip() in field
    outside = _field(kind="switch", name="members_only", label="Enkel leden", form="aa-act-form")
    assert outside.count('form="aa-act-form"') == 2, (
        "the off value and the checkbox both name the form"
    )


# ── The upload: the kit's own button ─────────────────────────────────────────


def test_the_upload_shows_its_own_button_and_never_the_browsers():
    html = _field(
        kind="upload",
        name="file",
        label="Affiche",
        current_url="/x.pdf",
        current_label="affiche.pdf",
    )
    assert "Bestand kiezen" in html
    file_input = re.search(r'<input type="file"[^>]*>', html).group(0)
    assert "opacity-0" in file_input, "the browser's button is not shown"
    assert 'href="/x.pdf"' in html and "affiche.pdf" in html


# ── Read mode: the same block, the value as text ─────────────────────────────


def _value(html: str) -> str:
    return re.search(r"<p data-value[^>]*>(.*?)</p>", html, re.S).group(1).strip()


def test_read_mode_shows_text_and_no_control():
    html = _field(value="Parochiezaal", edit=False, help="Alleen bij het bewerken.")
    assert _value(html) == "Parochiezaal"
    assert "<input" not in html and "<label" not in html
    assert "data-field-help" not in html
    assert _span(html) == "half", "the same place on the grid as in the editor"


@pytest.mark.parametrize(
    "kind", ["text", "textarea", "number", "date", "url", "email", "upload", "select"]
)
def test_an_empty_field_reads_as_a_dash(kind):
    assert (
        _value(
            _field(kind=kind, value="", edit=False, options=[("", "— niet ingevuld —"), ("a", "A")])
        )
        == "—"
    )


def test_a_switch_reads_in_words():
    assert _value(_field(kind="switch", value=True, edit=False)) == "ja"
    assert _value(_field(kind="switch", value=False, edit=False)) == "nee"


def test_a_choice_reads_as_its_label():
    options = [("", "— niet ingevuld —"), ("families", "Gezinnen"), ("seniors", "Senioren")]
    assert (
        _value(_field(kind="select", value="families", options=options, edit=False)) == "Gezinnen"
    )
    days = [("sat", "Zaterdag"), ("sun", "Zondag"), ("wed", "Woensdag")]
    assert (
        _value(_field(kind="checkbox_group", value=["sat", "sun"], options=days, edit=False))
        == "Zaterdag, Zondag"
    )


def test_read_mode_may_show_a_formatted_value_and_a_promise():
    html = _field(kind="date", value="2031-06-14", display="14 juni 2031", edit=False)
    assert _value(html) == "14 juni 2031"
    promise = _field(
        kind="textarea",
        value="Sleutel bij de buur.",
        edit=False,
        help="Alleen het bestuur.",
        help_in_read=True,
    )
    assert "data-field-help" in promise and "Alleen het bestuur." in promise


# ── Section and rare section ─────────────────────────────────────────────────


def test_a_section_is_one_card_with_its_heading_over_the_grid():
    html = _render("{% call ui.section('Publiek') %}{{ ui.field('a', 'A') }}{% endcall %}")
    assert html.count("data-form-section") == 1 and html.count("data-form-grid") == 1
    assert html.index("Publiek</h2>") < html.index("data-form-grid") < html.index("data-field")
    heading = re.search(r"<h2[^>]*>", html).group(0)
    assert "text-base" in heading and "font-semibold" in heading and "mb-4" in heading


def test_the_rare_section_is_closed_and_says_what_is_set_inside():
    html = _render(
        "{% call ui.rare_settings('Externe koppelingen', summary='1 externe link', note='De oude weg.') %}"
        "{{ ui.field('poster_url', 'Poster-URL', kind='url') }}{% endcall %}"
    )
    opening = re.search(r"<details[^>]*>", html).group(0)
    assert "data-rare-settings" in opening and " open" not in opening
    summary = re.search(r"<summary.*?</summary>", html, re.S).group(0)
    assert "Externe koppelingen" in summary and "1 externe link" in summary
    assert html.index("</summary>") < html.index("De oude weg.") < html.index("data-field")
    bare = _render("{% call ui.rare_settings('Externe koppelingen') %}{% endcall %}")
    assert "data-rare-summary" not in bare, "nothing set, nothing said"

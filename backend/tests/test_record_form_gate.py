"""A record form has one save, in the kit's action bar (CR-11 block 9, #1561; B7 tests 4 and 10).

`design-system-end-state.md` §3.6, §3.18, §3.19. A screen that edits a record
as a whole marks its form `data-record-form`, and then:

- it has exactly one `ui.action_bar(…, record=True)` — the bar under the last
  section — and no other submit: an "Opslaan" in a card or a row is a second
  transaction boundary (decision 09);
- nothing in it saves by itself: a field that posts on `change` or `input` is
  the document model (autosave), not the record model;
- the form names its message line (`data-message`) and leaves validation to the
  save (`novalidate`): the browser's own bubble would stop the form before the
  server can name every field at once;
- the bar's words are the macro's: Opslaan · Annuleren · Verwijderen. A custom
  save label is for a named consequence, which a record's save is not.

Each rule was proven red on the activity's fiche with an additive violation
(noted at the rule); the checkers keep that proof on synthetic sources.
"""

import re
from pathlib import Path

from app.ui import templates

APP = Path(__file__).resolve().parents[1] / "app"
MARK = "data-record-form"


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _record_forms() -> dict[str, str]:
    found = {}
    scanned = 0
    for path in (APP / "domains").rglob("templates/**/*.html"):
        scanned += 1
        text = _without_comments(path.read_text())
        if MARK in text:
            found[str(path.relative_to(APP))] = text
    assert scanned > 100, f"only {scanned} domain templates found — the glob looks nowhere"
    return found


# ── The checkers ─────────────────────────────────────────────────────────────


def one_bar(rel: str, text: str) -> list[str]:
    bars = re.findall(r"ui\.action_bar\((.*?)\)\s*\}\}", text, re.S)
    found = []
    if len(bars) != 1:
        found.append(f"{rel}: {len(bars)} action bars — a record form has exactly one")
    for call in bars:
        if not re.search(r"\brecord\s*=\s*True\b", call):
            found.append(f"{rel}: an action bar without `record=True` in a record form")
        if "save_label" in call:
            found.append(f"{rel}: a custom save label — a record's save is 'Opslaan'")
    return found


def other_submits(rel: str, text: str) -> list[str]:
    found = []
    if re.search(r"\bui\.btn_primary\(", text):
        found.append(f"{rel}: a primary button beside the action bar — one save per record form")
    if re.search(r'type\s*=\s*"submit"', text):
        found.append(f"{rel}: a submit of its own — the action bar holds the one save")
    return found


def autosave(rel: str, text: str) -> list[str]:
    found = []
    for tag in re.findall(r"<[a-zA-Z][^<>]*hx-(?:post|put|patch|delete)=[^<>]*>", text, re.S):
        if re.search(r'hx-trigger="[^"]*\b(?:change|input|keyup|blur)\b', tag):
            found.append(f"{rel}: a field that saves by itself — that is the document model")
    return found


def form_contract(rel: str, text: str) -> list[str]:
    found = []
    for tag in re.findall(r"<form\b[^>]*data-record-form[^>]*>", text, re.S):
        if "data-message=" not in tag:
            found.append(f"{rel}: a record form without its message line (`data-message`)")
        if "novalidate" not in tag:
            found.append(f"{rel}: a record form without `novalidate` — the save names the fields")
    return found


CHECKS = (one_bar, other_submits, autosave, form_contract)


# ── The rules on the real templates ──────────────────────────────────────────


def test_the_gate_finds_the_record_forms():
    """A gate that finds nothing is green forever: the activity's fiche is one."""
    assert "domains/activities/templates/_aa_detail.html" in _record_forms()


def test_a_record_form_has_one_save_in_the_action_bar():
    """Proven red on `_aa_detail.html` by adding `{{ ui.btn_primary("Opslaan") }}`
    inside the dates group, and by a second `ui.action_bar()`."""
    found = [
        v for rel, text in _record_forms().items() for check in CHECKS for v in check(rel, text)
    ]
    assert found == []


# ── The macros themselves ────────────────────────────────────────────────────


def _render(body: str, **ctx) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render(**ctx)


BAR = (
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, delete_attrs=delete,"
    " delete_title='“Wandeling” verwijderen?', delete_confirm='De activiteit verdwijnt.') }}"
)


def test_the_bars_words_and_order_are_the_macros():
    """B7 test 10: Verwijderen · Annuleren · Opslaan, in that order, no other words."""
    html = _render(BAR, delete='hx-post="/x"')
    bar = html[: html.index("<template data-save-failed>")]
    assert (
        bar.index("data-form-delete") < bar.index("data-form-cancel") < bar.index("data-form-save")
    )
    words = [w.strip() for w in re.findall(r">([^<>{}]+)<", bar) if w.strip()]
    assert words == ["Verwijderen", "Annuleren", "Opslaan", "Opslaan…"], words
    save = re.search(r"<button[^>]*data-form-save[^>]*>", bar).group(0)
    assert 'type="submit"' in save and 'form="f"' in save and "bg-blue-700" in save, "filled"
    cancel = re.search(r"<a[^>]*data-form-cancel[^>]*>", bar).group(0)
    assert 'href="/terug"' in cancel and "bg-transparent" in cancel, "a text button"
    delete = re.search(r"<button[^>]*data-form-delete[^>]*>", bar).group(0)
    assert "text-red-700" in delete and "bg-transparent" in delete, "red text, not filled"


def test_verwijderen_in_the_bar_asks_with_the_delete_dialog():
    """§3.18: the dialog names the record, "Definitief verwijderen" is its button.
    Proven red by dropping `data-confirm-tone` from the macro."""
    delete = re.search(
        r"<button[^>]*data-form-delete[^>]*>", _render(BAR, delete='hx-post="/x"')
    ).group(0)
    assert 'data-confirm="De activiteit verdwijnt."' in delete
    assert 'data-confirm-tone="delete"' in delete
    assert 'data-confirm-ok="Definitief verwijderen"' in delete
    assert 'data-confirm-title="“Wandeling” verwijderen?"' in delete
    assert 'hx-post="/x"' in delete
    assert "data-form-delete" not in _render(BAR, delete=""), "no delete without its action"


def test_a_refused_delete_says_why_instead_of_asking():
    """#1561: the bar's button opens a notice — no request, no question — and the
    item in Acties is no button at all. Proven red by rendering the asking
    button also when `delete_refused` is given."""
    html = _render(
        "{{ ui.action_bar(form='f', cancel_href='/terug', record=True, delete_attrs='hx-post=\"/x\"',"
        " delete_confirm='Alles weg.', delete_refused='Er is 1 inschrijving.',"
        " delete_refused_title='Kan niet verwijderd worden') }}"
    )
    assert html.count("data-form-delete") == 1
    button = re.search(r"<button[^>]*data-form-delete[^>]*>", html, re.S).group(0)
    assert 'data-notice="Er is 1 inschrijving."' in button
    assert 'data-notice-title="Kan niet verwijderd worden"' in button
    assert "hx-post" not in button and "data-confirm" not in button

    menu = _render(
        "{% call ui.record_header('Wandeling', actions=[{'kind': 'delete', 'label': 'Verwijderen',"
        " 'attrs': 'hx-post=\"/weg\"', 'confirm': 'Alles weg.', 'disabled': 'Er is 1 inschrijving.'}]) %}{% endcall %}"
    )
    assert 'hx-post="/weg"' not in menu and "data-confirm=" not in menu
    refused = re.search(r"<div[^>]*data-menu-refused[^>]*>.*?</div>", menu, re.S).group(0)
    assert 'aria-disabled="true"' in refused and "Er is 1 inschrijving." in refused

    host = _render("{{ ui.confirm_host() }}")
    assert "tone !== 'notice'" in re.search(r"<button[^>]*data-dialog-ok[^>]*>", host, re.S).group(
        0
    )
    assert "closest('[data-notice]')" in host and "Sluiten" in host


def test_the_bar_carries_the_words_of_its_two_questions():
    """The script asks; the words are the macro's, so they are translated."""
    html = _render(BAR, delete="")
    for words in (
        'data-discard-title="Wijzigingen weggooien?"',
        'data-discard-ok="Wijzigingen weggooien"',
        'data-discard-stay="Verder bewerken"',
        'data-leave-title="Deze pagina verlaten?"',
        'data-leave-ok="Weggooien"',
        'data-leave-stay="Blijven"',
    ):
        assert words in html, words
    assert "Opslaan en verlaten" not in html


def test_the_action_bar_of_a_card_is_what_it_was():
    """Forty screens still use the bar of a card; `record=True` is the only way in."""
    html = _render("{{ ui.action_bar(form='f', cancel_href='/terug') }}")
    assert "data-action-bar" not in html and "record-bar" not in html
    assert ">Annuleren<" in html and ">Opslaan<" in html


REFUSAL = "{{ ui.save_refusal(errors) }}"


def test_the_refusal_banner_counts_the_fields_and_links_each_one():
    two = _render(
        REFUSAL,
        errors=[
            {"field": "name", "message": "De activiteit heeft een naam nodig."},
            {"field": "c.7.max_participants", "message": "Het maximum moet groter zijn dan nul."},
        ],
    )
    assert "Opslaan kan nog niet: controleer 2 velden." in two
    assert "Je andere wijzigingen zijn behouden." in two
    assert re.findall(r'data-error-for="([^"]+)"', two) == ["name", "c.7.max_participants"]
    assert 'role="alert"' in two and "border-l-[3px]" in two and "p-4" in two

    one = _render(REFUSAL, errors=[{"field": "slug", "message": "Die URL is bezet."}])
    assert "controleer 1 veld." in one


def test_a_refusal_without_a_field_is_a_failure_with_its_reason():
    html = _render(REFUSAL, errors=[{"field": "", "message": "Een datum bestaat niet meer."}])
    assert "Opslaan is niet gelukt." in html and "Een datum bestaat niet meer." in html
    assert "data-error-for" not in html and "controleer" not in html


HEAD = (
    "{% call ui.record_header('Wandeling', editing=editing, primary={'label': 'Bewerken', 'href': '/x'},"
    " actions=[{'kind': 'record', 'verb': 'copy', 'label': 'Kopiëren', 'href': '/k'},"
    " {'kind': 'delete', 'label': 'Verwijderen', 'attrs': 'hx-post=\"/weg\"', 'confirm': 'Alles verdwijnt.',"
    " 'confirm_title': '“Wandeling” verwijderen?', 'confirm_ok': 'Definitief verwijderen'}]) %}{% endcall %}"
)


def test_verwijderen_is_in_acties_only_while_reading():
    """§3.6: in edit mode it lives in the bar and not also in Acties. Proven red
    by leaving the `editing` test out of `record_header`."""
    read = _render(HEAD, editing=False)
    item = re.search(r'<button role="menuitem"[^>]*hx-post="/weg"[^>]*>', read).group(0)
    assert 'data-confirm-tone="delete"' in item and "text-red-700" in item
    assert 'data-confirm-title="“Wandeling” verwijderen?"' in item
    assert 'data-confirm-ok="Definitief verwijderen"' in item
    edit = _render(HEAD, editing=True)
    assert 'hx-post="/weg"' not in edit and ">Kopiëren<" in edit


def test_the_dialog_has_three_tones_and_the_safe_button_is_focused():
    """`keep`: the filled button is the one that stays. Proven red by swapping the
    two classes of the cancel button (e2e reads the rendered colours)."""
    html = _render("{{ ui.confirm_host() }}")
    cancel = re.search(r"<button[^>]*data-dialog-cancel[^>]*>", html, re.S).group(0)
    ok = re.search(r"<button[^>]*data-dialog-ok[^>]*>", html, re.S).group(0)
    assert re.search(r"tone === 'keep' \? '[^']*bg-blue-700", cancel), "stay is filled"
    assert re.search(r"tone === 'keep' \? '[^']*bg-white", ok), "discard is an outline"
    assert re.search(r"tone === 'delete' \? '[^']*bg-red-600", ok), "delete is filled red"
    assert "[data-dialog-cancel]').focus()" in html, "the safe button gets the focus"
    assert html.count("<button") == 2, "never a third button"
    for attribute in ("data-confirm-title", "data-confirm-tone", "data-confirm-cancel"):
        assert f"getAttribute('{attribute}')" in html, attribute


# ── The red proofs, kept ─────────────────────────────────────────────────────

CLEAN = (
    '<form id="f" data-record-form data-message="#m" novalidate hx-post="/x">'
    "{{ ui.field('name', 'Naam') }}</form>"
    '{{ ui.search(hx_get="/zoek", hx_target="#k") }}'
    "{{ ui.action_bar(form='f', cancel_href='/terug', record=True) }}"
)


def _all(text: str) -> list[str]:
    return [v for check in CHECKS for v in check("x.html", text)]


def test_a_clean_record_form_passes():
    assert _all(CLEAN) == []


def test_an_opslaan_in_a_card_is_red():
    assert _all(CLEAN + '{{ ui.btn_primary("Opslaan") }}') == [
        "x.html: a primary button beside the action bar — one save per record form"
    ]
    assert _all(CLEAN + '<button type="submit">Bewaar</button>') == [
        "x.html: a submit of its own — the action bar holds the one save"
    ]


def test_a_second_bar_and_a_bar_of_a_card_are_red():
    assert _all(CLEAN + "{{ ui.action_bar(form='f') }}") == [
        "x.html: 2 action bars — a record form has exactly one",
        "x.html: an action bar without `record=True` in a record form",
    ]
    assert _all(CLEAN.replace("record=True", "record=True, save_label='Bewaren'")) == [
        "x.html: a custom save label — a record's save is 'Opslaan'"
    ]


def test_a_field_that_saves_by_itself_is_red():
    """B7 test 4: a screen declaring "record" that uses the autosave form."""
    autosaving = CLEAN + '<select name="x" hx-post="/x" hx-trigger="change"></select>'
    assert _all(autosaving) == ["x.html: a field that saves by itself — that is the document model"]
    assert (
        _all(CLEAN + '<input name="q" hx-get="/zoek" hx-trigger="input changed delay:300ms">') == []
    )


def test_a_record_form_without_its_contract_is_red():
    assert _all(CLEAN.replace(' data-message="#m"', "")) == [
        "x.html: a record form without its message line (`data-message`)"
    ]
    assert _all(CLEAN.replace(" novalidate", "")) == [
        "x.html: a record form without `novalidate` — the save names the fields"
    ]

"""Gate: a public form page is built from the kit, and only from the kit
(#1589, CR-11 pilot B; `docs/design-system-end-state.md` §2.6; B7 tests 2 and 10).

A page that stands on `ui.public_form_page` — and every partial it includes —

- writes **no card by hand**: a section of fields is `ui.section`, a card of
  words `ui.flow_card`. A `<section>` or a card's classes in the template is how
  the registration page came to look different from the form's own page (#1380);
- writes **no button by hand** and holds **no submit of its own**: the one act
  stands in `ui.action_bar(record=True, send=True)`;
- carries **no "* Verplicht veld" legend**: the asterisk on the label says it
  (decision 12, point 2);
- has **no steps**: one long page, however many sections.

The rules read the templates; what a browser shows stands in
`tests_e2e/test_public_registration_page.py` and `test_public_form_page.py`.

Proven red with ADDITIVE violations on a made-up page (the parametrised test
below: each addition must give its message), and once on a real page: a line
`<p>* Verplicht veld</p>` added to `_inschrijf_velden.html` — a partial, so the
gate must follow the include to see it — made
`test_the_public_form_pages_are_built_from_the_kit` fail on
`inschrijven.html` and on `admin_inschrijving_nieuw.html`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

APP = Path(__file__).resolve().parents[1] / "app"
MARK = "ui.public_form_page("

#: The pages this gate must find — a gate that finds nothing is green forever.
EXPECTED = {
    "domains/activities/templates/inschrijven.html",
    "domains/activities/templates/admin_inschrijving_nieuw.html",
    "domains/forms/templates/formulier.html",
    "domains/forms/templates/formulier_klaar.html",
    "domains/cms/templates/betaling_resultaat.html",
    # #1590: the household's three pages.
    "domains/membership/templates/lid_worden.html",
    "domains/membership/templates/lidmaatschap_vernieuwen.html",
    "domains/membership/templates/gezin_portaal.html",
}

#: A page on the frame that SAVES a record instead of sending a form: its bar is
#: the record's ("Opslaan"), and the page reads back what was saved. Page → why.
#: Everything else on the frame is sent.
SAVES = {
    "domains/membership/templates/gezin_portaal.html": (
        "Mijn gezin is a record the member keeps: read first, one Opslaan, then read "
        "again (end state §2.6; master CLI, 5 October 2026)"
    ),
}


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _templates() -> dict[str, Path]:
    found = {}
    for path in list((APP / "domains").rglob("templates/**/*.html")) + list(
        (APP / "ui" / "templates").glob("*.html")
    ):
        found.setdefault(path.name, path)
    assert len(found) > 100, f"only {len(found)} templates found — the glob looks nowhere"
    return found


def _pages() -> dict[str, str]:
    """Each page on the frame, with the text of every partial it includes or
    imports from a domain (the kit itself is not a page)."""
    by_name = _templates()
    pages = {}
    for path in by_name.values():
        rel = str(path.relative_to(APP))
        if rel.startswith("ui/templates/"):
            continue  # the kit, its demo page and the shells
        text = _without_comments(path.read_text())
        if MARK not in text:
            continue
        seen, queue, whole = {path.name}, [text], [text]
        while queue:
            for name in re.findall(r'\{%-?\s*(?:include|from)\s+"([^"]+)"', queue.pop()):
                if name in seen or name == "_macros.html" or name not in by_name:
                    continue
                seen.add(name)
                part = _without_comments(by_name[name].read_text())
                whole.append(part)
                queue.append(part)
        pages[rel] = "\n".join(whole)
    return pages


# ── The checkers ─────────────────────────────────────────────────────────────


def hand_written_cards(rel: str, text: str) -> list[str]:
    found = []
    if re.search(r"<section\b", text):
        found.append(f"{rel}: a <section> written by hand — `ui.section` or `ui.flow_card`")
    if re.search(r'class="[^"]*\brounded-2xl\b[^"]*\bborder\b', text) or "ui.card(" in text:
        found.append(f"{rel}: a card of its own — `ui.section` or `ui.flow_card`")
    return found


def hand_written_buttons(rel: str, text: str) -> list[str]:
    found = []
    if re.search(r"<button\b", text):
        found.append(f"{rel}: a <button> written by hand — the kit's buttons")
    if re.search(r'type\s*=\s*"submit"', text):
        found.append(f"{rel}: a submit of its own — the action bar holds the one act")
    return found


def legend(rel: str, text: str) -> list[str]:
    if re.search(r"Verplicht(?:e)? veld", text, re.I):
        return [f"{rel}: a '* Verplicht veld' legend — the asterisk on the label says it"]
    return []


def steps(rel: str, text: str) -> list[str]:
    if re.search(r'x-show="step\b|formWizard|\bVolgende\b|\bVorige\b', text):
        return [f"{rel}: a trace of steps — a public form is one long page"]
    return []


def one_send(rel: str, text: str) -> list[str]:
    """A page with a form has one bar, and it is the bar of a form that is sent."""
    if "data-record-form" not in text:
        return []
    bars = re.findall(r"ui\.action_bar\((.*?)\)\s*\}\}", text, re.S)
    if len(bars) != 1:
        return [f"{rel}: {len(bars)} action bars — a public form has exactly one"]
    record = re.search(r"\brecord\s*=\s*True\b", bars[0])
    send = re.search(r"\bsend\s*=\s*True\b", bars[0])
    if rel in SAVES:
        if not record or send:
            return [f"{rel}: named as a page that saves — its bar is `record=True` without `send`"]
        return []
    if not record or not send:
        return [f"{rel}: the bar is not `record=True, send=True` — a public form is sent"]
    return []


CHECKS = (hand_written_cards, hand_written_buttons, legend, steps, one_send)


def _all(rel: str, text: str) -> list[str]:
    return [v for check in CHECKS for v in check(rel, text)]


# ── The rules on the real pages ──────────────────────────────────────────────


def test_the_gate_finds_the_public_form_pages():
    pages = _pages()
    assert EXPECTED <= set(pages), f"not found: {sorted(EXPECTED - set(pages))}"
    # The partials are read with their page: the registration's fields and bar.
    registration = pages["domains/activities/templates/inschrijven.html"]
    assert 'ui.field("contact_name"' in registration and "ui.action_bar(" in registration
    assert "ui.field(key, f.label" in pages["domains/forms/templates/formulier.html"]


def test_the_public_form_pages_are_built_from_the_kit():
    found = [v for rel, text in _pages().items() for v in _all(rel, text)]
    assert found == []


# ── The rules on made-up templates ───────────────────────────────────────────

CLEAN = (
    "{% call ui.public_form_page('Titel') %}"
    '<form data-record-form novalidate>{% call ui.section("Contact") %}'
    '{{ ui.field("naam", "Naam", required=True) }}{% endcall %}</form>'
    "{{ ui.action_bar(record=True, send=True, cancel_href='/') }}{% endcall %}"
)


def test_a_clean_page_passes():
    assert _all("x.html", CLEAN) == []


@pytest.mark.parametrize(
    ("addition", "message"),
    [
        ('<section class="p-4">x</section>', "a <section> written by hand"),
        ('<div class="bg-white rounded-2xl shadow-sm border p-4">x</div>', "a card of its own"),
        ("{% call ui.card() %}x{% endcall %}", "a card of its own"),
        ('<button type="button">x</button>', "a <button> written by hand"),
        ('<input type="submit">', "a submit of its own"),
        ("<p>* Verplicht veld</p>", "a '* Verplicht veld' legend"),
        ('<div x-show="step === 0">x</div>', "a trace of steps"),
        ("{{ ui.action_bar(record=True, cancel_href='/') }}", "2 action bars"),
    ],
)
def test_each_violation_is_red(addition, message):
    found = _all("x.html", CLEAN + addition)
    assert any(message in v for v in found), found


def test_a_page_named_as_a_save_has_the_records_bar_and_exists():
    """#1590. The one exemption from "a public form is sent" is by name, with its
    reason; a named page that sends after all, or that is gone, is red.

    Proven red by putting `send=True` on the bar of `gezin_portaal.html`.
    """
    pages = _pages()
    for rel, reason in SAVES.items():
        assert rel in pages, f"{rel} is no page on the frame any more — remove it from SAVES"
        assert reason.strip()
    save = CLEAN.replace(", send=True", "")
    name = next(iter(SAVES))
    assert one_send(name, save) == []
    assert one_send(name, CLEAN) == [
        f"{name}: named as a page that saves — its bar is `record=True` without `send`"
    ]


def test_a_bar_that_is_not_a_send_is_red():
    found = _all("x.html", CLEAN.replace(", send=True", ""))
    assert found == ["x.html: the bar is not `record=True, send=True` — a public form is sent"]

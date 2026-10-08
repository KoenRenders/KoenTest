"""E2E: a public form is one long page on the public form page (#1589, CR-11
pilot B, P2; `docs/design-system-end-state.md` §2.6).

It replaces `test_formulier_wizard_stap.py`: the steps ‹ › are gone. What a
server test cannot see:

- **three sections are three cards on one page**, all visible, under the name
  card and Contact; no step buttons; one label style (14 px medium) on every
  label of the page; nothing scrolls sideways at 390 and at 1 440;
- **an empty required question** is refused with the banner, the link in it
  brings the focus to the question, the question carries its reason, and what
  was typed elsewhere is still there;
- **after a good send** the thank-you page takes the form's place and its title
  has the focus;
- **a form that branches** shows only the sections on the path the answers
  lead along — the skipped section disappears when "B" is chosen and comes back
  with "A" — and a required question in the skipped section blocks nothing
  (the check that the page is never stricter than the server's path).

Proven red (each on this branch, restored after):
- `x-show="shown(…)"` taken off the cards → the branching test fails (the
  skipped section stays visible);
- `walk()` no longer called on a change → the same test fails;
- `HX-Retarget` taken off `app.ui.refusal_response` → the refusal test fails
  (the banner never reaches the message line, so nothing is named or marked).
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

#: The guard drops a submission sent within two seconds of the page's load —
#: silently, with the ordinary thanks (#1297). A person takes longer, because a
#: person TYPES: the last answer of each test is typed key by key at a quick
#: typist's pace (as `test_a_person_can_send_a_public_form.py` does), which
#: takes its three seconds without a wait on the clock.
KEY_DELAY_MS = 100
AN_ANSWER = "een antwoord dat iemand echt intypt"


def _type(locator, text: str = AN_ANSWER) -> None:
    locator.press_sequentially(text, delay=KEY_DELAY_MS)


def _sections(db, form, titles):
    from app.domains.forms.models import FormSection

    made = []
    for position, title in enumerate(titles):
        section = FormSection(form_id=form.id, title=title, position=position)
        db.add(section)
        made.append(section)
    db.flush()
    return made


@pytest.fixture(scope="module")
def forms():
    """A form of three plain sections that asks name and e-mail, and a branching
    one: A leads to section 2, B skips it and goes to 3. Every section has a
    required question."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField, FormFieldOption

    db = SessionLocal()
    plain = Form(
        title="E2E Drie delen",
        description="Drie korte vragen.",
        status="open",
        is_anonymous=False,
        share_token="e2e1589-" + secrets.token_urlsafe(6),
    )
    db.add(plain)
    db.flush()
    for section, label in zip(_sections(db, plain, ("Eerst", "Dan", "Tot slot")), "ABC"):
        db.add(
            FormField(
                form_id=plain.id,
                section_id=section.id,
                field_type="text",
                label=f"Vraag {label}",
                position=0,
                required=True,
            )
        )

    branching = Form(
        title="E2E Vertakt",
        status="open",
        is_anonymous=True,
        share_token="e2e1589-" + secrets.token_urlsafe(6),
    )
    db.add(branching)
    db.flush()
    route, only_a, last = _sections(db, branching, ("Route", "Alleen bij A", "Slot"))
    choice = FormField(
        form_id=branching.id,
        section_id=route.id,
        field_type="radio",
        label="Welke route?",
        position=0,
        required=True,
    )
    db.add(choice)
    db.flush()
    db.add(FormFieldOption(field_id=choice.id, label="A", position=0))
    db.add(FormFieldOption(field_id=choice.id, label="B", position=1, skip_to_section_id=last.id))
    for section, label in ((only_a, "Waarom A?"), (last, "Slotvraag")):
        db.add(
            FormField(
                form_id=branching.id,
                section_id=section.id,
                field_type="text",
                label=label,
                position=0,
                required=True,
            )
        )
    db.commit()
    out = {
        "plain": f"/formulier/{plain.share_token}",
        "branching": f"/formulier/{branching.share_token}",
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, path, width=390, height=844):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto(path)
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    return page


def _field(page, label):
    """The field (`[data-field]`) of the question with this label."""
    return page.locator("[data-field]").filter(has_text=label).first


@pytest.mark.parametrize("width,height,column,x", [(390, 844, 358, 16), (1440, 900, 768, 336)])
def test_three_sections_are_three_cards_on_one_page(browser, forms, width, height, column, x):
    page = _open(browser, forms["plain"], width, height)
    m = page.evaluate(
        """() => {
      const flow = document.querySelector('[data-form-flow]');
      const frame = document.querySelector('[data-public-form-page]').getBoundingClientRect();
      const labels = [...flow.querySelectorAll('[data-field] > label, [data-field] > p[id$="-label"]')];
      return {
        heads: [...flow.querySelectorAll('[data-form-section] > h2')].filter(h => h.checkVisibility()).map(h => h.textContent.trim()),
        name: flow.querySelector('[data-form-name] h1').textContent.trim(),
        labels: [...new Set(labels.map(l => getComputedStyle(l).fontSize + '/' + getComputedStyle(l).fontWeight))],
        count: labels.length,
        buttons: [...document.querySelectorAll('#main button')].filter(b => b.checkVisibility()).map(b => b.innerText.trim()),
        x: Math.round(frame.left), w: Math.round(frame.width),
        scroll: document.documentElement.scrollWidth,
      };
    }"""
    )
    page.close()
    assert m["name"] == "E2E Drie delen"
    assert m["heads"] == ["Contact", "Eerst", "Dan", "Tot slot"], m["heads"]
    assert m["count"] == 5 and m["labels"] == ["14px/500"], m["labels"]
    assert m["buttons"] == ["Verzenden"], f"another button than the one in the bar: {m['buttons']}"
    assert (m["w"], m["x"]) == (column, x), (m["w"], m["x"])
    assert m["scroll"] == width, "the page scrolls sideways"


def test_an_empty_required_question_is_named_and_marked(browser, forms):
    page = _open(browser, forms["plain"])
    page.fill("#submitter_name", "Marie Jommeke")
    page.fill("#submitter_email", "marie@example.com")
    first = _field(page, "Vraag A").locator("input")
    third = _field(page, "Vraag C").locator("input")
    first.fill("een antwoord")
    _type(third)

    page.click("[data-form-save]")

    banner = page.locator("[data-save-refusal]")
    expect(banner).to_contain_text("Verzenden kan nog niet: controleer 1 veld.")
    refused = _field(page, "Vraag B")
    expect(refused.locator("[data-refused-message]")).to_contain_text("verplicht")
    assert refused.locator("input").get_attribute("aria-invalid") == "true"
    focused = "() => document.activeElement.closest('[data-field]').textContent"
    assert "Vraag B" in page.evaluate(focused), "the focus is not on the refused question"
    # Nothing typed is lost, and the page is still the form.
    assert first.input_value() == "een antwoord" and third.input_value() == AN_ANSWER
    assert page.input_value("#submitter_name") == "Marie Jommeke"
    # The link of the banner brings the focus back to the question.
    page.locator("#submitter_name").focus()
    banner.locator("[data-error-for]").click()
    assert "Vraag B" in page.evaluate(focused)

    # Answered: the send goes through and the thank-you page takes the form's place.
    refused.locator("input").fill("het ontbrekende antwoord")
    page.click("[data-form-save]")
    head = page.locator("[data-public-form-page][data-result] h1")
    expect(head).to_have_text("Bedankt voor je reactie")
    expect(page.locator("[data-form-thanks]")).to_contain_text("goed ontvangen")
    assert page.locator("form[data-record-form]").count() == 0
    # The title takes the focus when the swap has SETTLED, a moment after the
    # thanks are on the page: wait for it, do not read it at once (#1591).
    expect(head).to_be_focused()
    page.close()


def test_a_branching_form_shows_the_sections_on_the_path(browser, forms):
    page = _open(browser, forms["branching"])
    shown = "() => [...document.querySelectorAll('[data-step]')].map(e => e.checkVisibility())"
    assert page.evaluate(shown) == [True, True, True], (
        "before a choice every section is on the path"
    )

    page.get_by_label("B", exact=True).check()
    page.wait_for_function(f"() => JSON.stringify(({shown})()) === '[true,false,true]'")
    page.get_by_label("A", exact=True).check()
    page.wait_for_function(f"() => JSON.stringify(({shown})()) === '[true,true,true]'")

    # With B, the required question of the skipped section blocks nothing.
    page.get_by_label("B", exact=True).check()
    page.wait_for_function(f"() => JSON.stringify(({shown})()) === '[true,false,true]'")
    _type(_field(page, "Slotvraag").locator("input"))
    page.click("[data-form-save]")
    expect(page.locator("[data-public-form-page][data-result] h1")).to_have_text(
        "Bedankt voor je reactie"
    )
    assert page.locator("[data-save-refusal]").count() == 0
    page.close()


def test_a_question_on_the_path_is_asked_for(browser, forms):
    """The other half: with A the middle section is on the path, and its empty
    required question is refused — the page hides nothing the server judges."""
    page = _open(browser, forms["branching"])
    page.get_by_label("A", exact=True).check()
    _type(_field(page, "Slotvraag").locator("input"))
    page.click("[data-form-save]")
    expect(page.locator("[data-save-refusal]")).to_contain_text("controleer 1 veld")
    expect(_field(page, "Waarom A?").locator("[data-refused-message]")).to_be_visible()
    page.close()

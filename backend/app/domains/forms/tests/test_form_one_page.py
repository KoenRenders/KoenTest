"""A public form is ONE long page (#1589, CR-11 pilot B; end state §2.6).

Until #1589 a form with two or more sections was a wizard: one section per
step, ‹ Vorige and Volgende ›, the name card and the intro bound to step 0, a
check per step in JavaScript and a page that reopened on the step of the
refused question (#454, #688, #724). Koen decided the steps away — "één lange
pagina, ook met veel secties". These tests replace
`test_formulier_wizard_stap_nul.py` and `test_formulier_wizard_startstap.py`;
what those protected and still matters is kept here:

- the name and e-mail card stands once, and a submission without a name or with
  an invalid address is refused AND not stored (#688, the safety net under the
  attribute);
- a required question left empty is refused by the server and named (#724) —
  now by its field, in the banner, for the page to mark;
- a required question in a section the answers skip blocks nothing (#336).

Presence proves little here (`x-show` hides in the browser, the text is in the
HTML either way), so the page tests count cards and look for the BINDINGS of a
step; what the browser shows is `tests_e2e/test_public_form_page.py`.

Proven red:
- an element with `x-show="step === 0"` added to `formulier.html` →
  `test_three_sections_…` fails on the step binding (and the page gate too);
- `_submitter_refusals` handed a name and an address that are fine → the three
  refusal tests fail (nothing is refused at the field);
- `path=path` taken off `vragen_kaarten` → the branching test fails (no card
  carries its place).
"""

from __future__ import annotations

import re

import pytest

from app.domains.forms.models import FormSubmission
from tests import forms_door
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_serverrendered

INTRO = "Lees dit eerst aandachtig."
SOMEBODY = {"submitter_name": "Jan", "submitter_email": "jan@example.com"}


def _form(client, sections: int = 3, branch: bool = False, **settings):
    """A form that asks name and e-mail, one required text question per section.
    `branch`: section 1 asks a choice, and its option "B" skips to the last."""
    fields = [
        {
            "field_type": "text",
            "label": f"Vraag {i + 1}",
            "required": True,
            "position": i,
            "section_index": i,
        }
        for i in range(sections)
    ]
    if branch:
        fields[0] = {
            "field_type": "radio",
            "label": "Welke route?",
            "required": True,
            "position": 0,
            "section_index": 0,
            "options": [
                {"label": "A", "position": 0},
                {"label": "B", "position": 1, "skip_to_section_index": sections - 1},
            ],
        }
    payload = {
        "title": "Enquête",
        "status": "open",
        "is_anonymous": False,
        "description": INTRO,
        "sections": [{"title": f"Deel {i + 1}", "position": i} for i in range(sections)],
        "fields": fields,
        **settings,
    }
    r = forms_door.create_form(client, payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _page(client, form) -> str:
    r = client.get(f"/formulier/{form['share_token']}")
    assert r.status_code == 200, r.text[:300]
    return r.text


def _stored(db, form) -> int:
    return db.query(FormSubmission).filter(FormSubmission.form_id == form["id"]).count()


def _field_id(form, label: str) -> int:
    return next(f["id"] for f in form["fields"] if f["label"] == label)


# ── One page ─────────────────────────────────────────────────────────────────


def test_three_sections_are_three_cards_on_one_page(client):
    html = _page(client, _form(client, sections=3))
    flow = html[html.index("data-form-flow") : html.index("data-action-bar")]

    # The name card, Contact, and one card per section — in that order.
    assert flow.count("data-form-name") == 1
    heads = re.findall(r"<h2 [^>]*>([^<]+)</h2>", flow)
    assert heads == ["Contact", "Deel 1", "Deel 2", "Deel 3"], heads
    assert flow.count("data-form-section") == 5, "the name card, Contact and three sections"
    for n in (1, 2, 3):
        assert f">Vraag {n} <" in flow, f"question {n} is not on the page"
    # No steps: no step binding, no step buttons, no step script.
    for trace in ('x-show="step', "formWizard", "Volgende", "Vorige", "data-step"):
        assert trace not in html, f"a trace of the steps: {trace}"


def test_the_name_card_holds_the_title_and_the_intro_once(client):
    html = _page(client, _form(client, sections=2))
    card = html[html.index("data-form-name") : html.index('id="formulier-melding"')]
    assert re.search(r'<h1 [^>]*class="public-form-title">Enquête</h1>', card)
    assert INTRO in card and html.count(INTRO) == 1
    assert html.count("<h1") == 1


def test_name_and_e_mail_are_asked_once_as_fields_of_the_kit(client):
    html = _page(client, _form(client, sections=2))
    assert html.count('data-field="submitter_name"') == 1
    assert html.count('data-field="submitter_email"') == 1
    # The asterisk says it; there is no "* Verplicht veld" legend (§2.6).
    name = html[html.index('data-field="submitter_name"') :]
    assert 'Naam <span class="text-red-600">*</span>' in name[:400]
    assert "Verplicht veld" not in html


def test_an_anonymous_form_asks_no_name(client):
    html = _page(client, _form(client, sections=2, is_anonymous=True))
    assert "submitter_name" not in html and ">Contact</h2>" not in html


def test_the_form_is_a_form_of_the_kit_with_one_bar(client):
    html = _page(client, _form(client, sections=2))
    tag = re.search(r"<form\b[^>]*data-record-form[^>]*>", html, re.S).group(0)
    assert 'data-message="#formulier-melding"' in tag and "novalidate" in tag
    assert 'hx-target="#formulier-pagina"' in tag
    assert html.count("data-action-bar") == 1
    assert "data-save-idle>Verzenden<" in html and "</span>Verzenden…</span>" in html
    assert html.count('type="submit"') == 1


# ── The safety net under the page ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("data", "fields"),
    [
        ({"submitter_name": "", "submitter_email": ""}, ["submitter_name", "submitter_email"]),
        ({"submitter_name": "Jan", "submitter_email": "geen-adres"}, ["submitter_email"]),
        ({"submitter_name": "", "submitter_email": "jan@example.com"}, ["submitter_name"]),
    ],
)
def test_without_a_name_or_an_address_the_form_is_refused_at_the_field(
    client, db_session, data, fields
):
    """The attribute was the friendly variant, never the rule (#688). Nothing is
    stored: a banner AND a stored row would look the same from outside."""
    form = _form(client, sections=2)

    r = client.post(f"/formulier/{form['share_token']}", data={**form_guard_fields(), **data})

    assert r.status_code == 422, r.text[:300]
    assert r.headers["HX-Retarget"] == "#formulier-melding"
    assert re.findall(r'data-error-for="([^"]+)"', r.text) == fields
    assert "Verzenden kan nog niet: controleer" in r.text
    assert "<input" not in r.text and "<form" not in r.text, "the answer redraws the form"
    assert _stored(db_session, form) == 0


def test_an_empty_required_question_is_refused_and_named(client, db_session):
    """The browser's check never replaced the server's (#724): a post that goes
    past the page is refused, and the banner names the question by its field."""
    form = _form(client, sections=2)

    r = client.post(
        f"/formulier/{form['share_token']}",
        data={**form_guard_fields(), **SOMEBODY, f"f{_field_id(form, 'Vraag 1')}": "antwoord"},
    )

    assert r.status_code == 422, r.text[:300]
    assert re.findall(r'data-error-for="([^"]+)"', r.text) == [f"f{_field_id(form, 'Vraag 2')}"]
    assert "verplicht" in r.text.lower()
    assert _stored(db_session, form) == 0


def test_a_good_submission_gets_the_thank_you_page(client, db_session):
    form = _form(client, sections=2)
    answers = {f"f{f['id']}": "antwoord" for f in form["fields"]}

    r = client.post(
        f"/formulier/{form['share_token']}", data={**form_guard_fields(), **SOMEBODY, **answers}
    )

    assert r.status_code == 200, r.text[:300]
    assert 'id="formulier-pagina"' in r.text, "the page a good answer swaps is not in the answer"
    assert ">Bedankt voor je reactie</h1>" in r.text
    assert "We hebben je inzending goed ontvangen." in r.text
    assert 'id="formulier-form"' not in r.text
    assert _stored(db_session, form) == 1


# ── A form that branches ─────────────────────────────────────────────────────


def test_only_a_branching_form_carries_a_path(client):
    plain = _page(client, _form(client, sections=3))
    assert "formPath" not in plain and "data-step" not in plain

    html = _page(client, _form(client, sections=3, branch=True))
    assert re.findall(r'data-step="(\d)" x-show="shown\((\d)\)"', html) == [
        ("0", "0"),
        ("1", "1"),
        ("2", "2"),
    ]
    steps = re.search(r"x-data='formPath\((.*?)\)' @change=\"walk\(\)\"", html, re.S)
    assert steps, "the flow does not walk the path"
    import html as html_lib
    import json

    path = json.loads(html_lib.unescape(steps.group(1)))
    assert [len(step["skips"]) for step in path] == [1, 0, 0]
    assert path[0]["skips"][0]["section"] == 2 and path[0]["skips"][0]["end"] is False


def test_a_section_or_an_option_that_ends_the_form_is_on_the_path(client):
    """The path knows the two ways a form ends early (#454): a section that is
    the last by its own setting, and an option that ends the form."""
    payload = {
        "title": "Vroeg klaar",
        "status": "open",
        "is_anonymous": True,
        "sections": [
            {"title": "Deel 1", "position": 0, "next_is_end": False},
            {"title": "Deel 2", "position": 1, "next_is_end": True},
        ],
        "fields": [
            {
                "field_type": "radio",
                "label": "Kies",
                "position": 0,
                "section_index": 0,
                "options": [
                    {"label": "Verder", "position": 0},
                    {"label": "Meteen klaar", "position": 1, "skip_to_end": True},
                ],
            },
            {"field_type": "text", "label": "Naam", "position": 1, "section_index": 1},
        ],
    }
    r = forms_door.create_form(client, payload)
    assert r.status_code in (200, 201), r.text
    import html as html_lib
    import json

    html = _page(client, r.json())
    steps = re.search(r"x-data='formPath\((.*?)\)' @change", html, re.S)
    assert steps, "a form that can end early carries no path"
    path = json.loads(html_lib.unescape(steps.group(1)))
    assert path[0]["skips"][0]["end"] is True and path[1]["end"] is True


def test_a_required_question_in_a_skipped_section_blocks_nothing(client, db_session):
    """#336, #724: with "B" the middle section is never reached, so its required
    question is not judged. Without this the page would be stricter than the
    path, and a branching form could not be sent at all."""
    form = _form(client, sections=3, branch=True)
    route = next(f for f in form["fields"] if f["label"] == "Welke route?")
    option_b = next(o["id"] for o in route["options"] if o["label"] == "B")
    data = {
        **form_guard_fields(),
        **SOMEBODY,
        f"f{route['id']}": str(option_b),
        f"f{_field_id(form, 'Vraag 3')}": "slot",
    }

    r = client.post(f"/formulier/{form['share_token']}", data=data)

    assert r.status_code == 200, r.text[:400]
    assert ">Bedankt voor je reactie</h1>" in r.text
    assert _stored(db_session, form) == 1

    # With "A" the middle section IS on the path, and its question is asked for.
    option_a = next(o["id"] for o in route["options"] if o["label"] == "A")
    r = client.post(
        f"/formulier/{form['share_token']}", data={**data, f"f{route['id']}": str(option_a)}
    )
    assert r.status_code == 422
    assert re.findall(r'data-error-for="([^"]+)"', r.text) == [f"f{_field_id(form, 'Vraag 2')}"]

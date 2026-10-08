"""The form's own page and every page that asks its questions render ONE block (#1380).

Koen, after testing the Sint registration on HDEV: the registration used the form
builder's field, but built everything around it again, so the work on the form's
own page (title, description, spacing, white card) never reached it. The block is
now one partial, `forms/templates/_formulier_vragen.html` (`vragen_kop`,
`vragen_kaarten`).

Proven by what it does, not by a class name: the partial is replaced, for the length
of the test, by a copy that carries a marker in each of its two macros — and the
marker must reach the form's own page, the registration page, the answer link and
the registration detail's correction. A page that kept a block of its own would not
carry it.

Broken on purpose to check it can go red (run, then restored): the registration's
`vragen_kaarten(...)` call replaced by an empty string in `_inschrijf_velden.html`
→ the first test, on the registration page. (Against master `08a3ffbd` it cannot
run at all — the partial did not exist; the e2e measurement
`tests_e2e/test_one_question_block.py` is the red one there.)

#1589 (CR-11 pilot B, end state §2.6): what is shared everywhere is the CARDS
(`vragen_kaarten`). The head (`vragen_kop`) is for a page that shows the block
inside something of its own — the registration detail. The form's own page puts
the form's name in its name card, and the registration page asks under its own
section "Vragen bij de inschrijving".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from jinja2 import ChoiceLoader, DictLoader

from app.domains.activities import service
from app.ui import templates
from tests.conftest import register_at_the_door, seed_activity_with_product, seed_question_form

pytestmark = pytest.mark.ui_serverrendered

PARTIAL = "_formulier_vragen.html"
HEAD_MARK = "<!--probe:vragen_kop-->"
CARDS_MARK = "<!--probe:vragen_kaarten-->"


@pytest.fixture
def probed_partial():
    """The shared partial with a marker at the start of each macro."""
    env = templates.env
    source, _filename, _uptodate = env.loader.get_source(env, PARTIAL)
    head = "{% macro vragen_kop("
    cards = "{% macro vragen_kaarten("
    assert source.count(head) == 1 and source.count(cards) == 1, "the macros moved"
    # The markers go on the first line INSIDE each macro, so they render with it.
    out = []
    for line in source.split("\n"):
        out.append(line)
        if line.startswith(head):
            out.append(HEAD_MARK)
        elif line.startswith(cards):
            out.append(CARDS_MARK)
    probed = "\n".join(out)
    assert HEAD_MARK in probed and CARDS_MARK in probed, "the probe did not land"
    original = env.loader
    env.loader = ChoiceLoader([DictLoader({PARTIAL: probed}), original])
    env.cache.clear()
    yield
    env.loader = original
    env.cache.clear()


@pytest.fixture
def sint(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    service.update_component(db_session, activity.id, component.id, {"form_id": form.id})
    return SimpleNamespace(activity=activity, component=component, product=product, form=form)


def _marked(html: str) -> bool:
    return HEAD_MARK in html and CARDS_MARK in html


def test_the_form_and_the_registration_render_the_same_block(client, sint, probed_partial):
    own = client.get(f"/formulier/{sint.form.share_token}").text
    assert CARDS_MARK in own and HEAD_MARK not in own, "the form's own page"
    # #1589 (§2.6): on the registration page the questions stand under the
    # section "Vragen bij de inschrijving" — the page's own head, with the
    # form's description — so only the CARDS are the shared block there.
    page = client.get(f"/activiteiten/{sint.activity.id}/inschrijven/{sint.component.id}").text
    assert CARDS_MARK in page, "the registration page"
    assert HEAD_MARK not in page


def test_the_answer_link_and_the_correction_render_it_too(client, db_session, sint, probed_partial):
    from app.domains.activities.api import Registration
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    slot = next(f for f in sint.form.fields if f.label == "Tijdslot")
    story = next(f for f in sint.form.fields if f.label == "Verhaal")
    for name, answers in (
        ("Later Lies", None),
        (
            "Nu Noor",
            [
                {"field_id": slot.id, "option_ids": [slot.options[0].id]},
                {"field_id": story.id, "text": "Braaf"},
            ],
        ),
    ):
        body = {
            "contact_name": name,
            "contact_email": f"{name.split()[1].lower()}@example.com",
            "phone": "0470000000",
            "component_id": sint.component.id,
            "items": [{"product_id": sint.product.id, "quantity": 1}],
        }
        if answers is not None:
            body["answers"] = answers
        assert register_at_the_door(client, sint.activity.id, json=body).is_success
    regs = {
        r.contact_name: r
        for r in db_session.query(Registration).filter_by(activity_id=sint.activity.id)
    }

    link = client.get(f"/inschrijving/{regs['Later Lies'].answer_token}/vragen").text
    assert CARDS_MARK in link and HEAD_MARK not in link, "the answer link"
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    assert _marked(client.get(f"/admin/inschrijvingen/{regs['Nu Noor'].id}").text)

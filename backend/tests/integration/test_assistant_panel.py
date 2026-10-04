"""CR-11 pilot A, K8 (#1562), PR 1 — the Assistent as a panel: its context, its
one trigger, and what left with it.

Block 10 (Koen, 4 October 2026; `docs/design-system-end-state.md` §3.15):

- **the context is the screen's**: a record, a list with its filter and the
  size of the selection, otherwise the tenant — read from the screen's address,
  never from the panel;
- **a list state that cannot be carried over is refused**: the line names the
  list without a count, the panel says which filter stands in the way, and
  there is no question field until it is gone;
- **availability by rule**: a module whose objects are in the reporting universe
  offers the assistant; elsewhere the trigger is dimmed and the panel says only
  "Raakje kent deze gegevens nog niet";
- **one trigger**: the top bar's; the assistant page answers 301, and no screen
  carries an `AI ·` button of its own;
- **the tenant's switches still decide** (#1568): back office off — no trigger
  and no panel; public off — no bell and a 404 on the public endpoint.

What only a browser shows — the docked panel that moves the content aside, the
dialog, the sheet, Escape, a late answer — is in
`tests_e2e/test_assistant_panel.py`.

Proven red (each on this branch, restored after):
- the count taken from the registration groups instead of the bookings → the
  context-line test fails (2 instead of 3);
- the count taken without the filter → the context-line test fails;
- a search term carried over silently → the refusal test fails;
- every module called available → the availability tests fail;
- the trigger shown without asking the tenant's switch → the switch test fails;
- the trigger shown to a role that may not ask → the role test fails;
- the 204 for an unchanged context removed → the same-context test fails;
- `NOT_ANSWERED` left off the failed answer → the failure test fails.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.payment.api import PaymentRecord, selection_count
from app.domains.reporting.assistant_context import context_for, module_knows_the_assistant
from app.kernel.modules import MODULES, serving_module
from app.kernel.tenancy import DEFAULT_TENANT_ID
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
KNOP = "/admin/rapporten/raakje/knop"
PANEEL = "/admin/rapporten/raakje/paneel"


def _login(client, email: str = SEEDED_ADMIN_EMAIL) -> str:
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _on(screen: str) -> dict:
    """The header htmx sends with every request: the address the browser shows."""
    return {"HX-Current-URL": f"http://testserver{screen}"}


@pytest.fixture
def switched_on(db_session, monkeypatch):
    """Both switches on: the environment's and the tenant's."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()


def _booking(db, reg, amount, *, status="pending", paid=None, minutes=0, **extra):
    rec = PaymentRecord(
        payable_type="registration",
        payable_id=reg.id,
        amount=Decimal(amount),
        amount_paid=None if paid is None else Decimal(paid),
        method="transfer",
        status=status,
        created_at=T0 + timedelta(minutes=minutes),
        **extra,
    )
    db.add(rec)
    db.flush()
    return rec


@pytest.fixture
def world(db_session):
    """One activity, two registrations. Bram has TWO open bookings (so the
    groups and the bookings differ: 2 open groups would be wrong, 3 open
    bookings is right), An one open and one paid."""
    db = db_session
    activity, component, _product = seed_activity_with_product(db, price="10.00")
    activity.name = "Herfstwandeling"

    def registration(name):
        reg = Registration(
            contact_name=name,
            contact_email="deelnemer@example.org",
            phone="0470000000",
            activity_id=activity.id,
            component_id=component.id,
            registration_type="INDIVIDUAL",
        )
        db.add(reg)
        db.flush()
        return reg

    bram, an = registration("Bram Voorbeeld"), registration("An Voorbeeld")
    _booking(db, bram, "20.00", minutes=1)
    _booking(db, bram, "5.00", minutes=2)
    _booking(db, an, "10.00", minutes=3)
    _booking(db, an, "30.00", status="paid", paid="30.00", minutes=4)
    db.commit()
    return {"activity": activity}


def _context(db, screen: str):
    return context_for(db, f"http://testserver{screen}", tenant_id=DEFAULT_TENANT_ID)


# ── the context line comes from the screen ───────────────────────────────────


def test_the_context_line_of_a_list_names_the_filter_and_counts_bookings(db_session, world):
    open_ = _context(db_session, "/admin/betalingen?zicht=openstaand")
    # Three open BOOKINGS in two registrations: the unit is the booking, the
    # row a report counts — not the toolbar's registration groups — and the
    # line names it.
    assert open_.label == "over 3 openstaande betalingen (filter Openstaand)"
    assert open_.can_ask and open_.post_url == "/admin/rapporten/raakje/scherm/betalingen"
    assert len(open_.suggestions) == 3
    # Without the filter: every booking, and no filter named.
    assert _context(db_session, "/admin/betalingen").label == "over 4 betalingen"
    # The same count as the list's own filter makes.
    assert selection_count(db_session, view="openstaand") == 3
    assert selection_count(db_session, view="alle") == 4


def test_the_activity_filter_of_the_list_is_named_and_counted(db_session, world):
    other, component, _p = seed_activity_with_product(db_session, price="10.00")
    reg = Registration(
        contact_name="Cas Voorbeeld",
        contact_email="cas@example.org",
        phone="0470000000",
        activity_id=other.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
    )
    db_session.add(reg)
    db_session.flush()
    _booking(db_session, reg, "15.00")
    db_session.commit()

    ours = world["activity"].id
    scoped = _context(db_session, f"/admin/betalingen?zicht=openstaand&activiteit={ours}")
    assert scoped.label == "over 3 openstaande betalingen (filter Openstaand, Herfstwandeling)"
    assert _context(db_session, "/admin/betalingen?zicht=openstaand").label.startswith("over 4 ")
    one = _context(db_session, f"/admin/betalingen?zicht=openstaand&activiteit={other.id}")
    assert one.label.startswith("over 1 openstaande betaling (")


def test_a_list_state_that_cannot_be_carried_over_is_refused(db_session, world):
    """A search term never goes to a model, so the selection on the screen
    cannot be the conversation's: no count, the reason, and no asking."""
    blocked = _context(db_session, "/admin/betalingen?zicht=openstaand&q=bram")
    assert blocked.label == "over de betalingen op dit scherm"
    assert not re.search(r"\d", blocked.label), "a count over another selection than the screen's"
    assert "de zoekterm" in blocked.blocked and not blocked.can_ask
    # A context per year is the same kind of gap.
    assert not _context(db_session, "/admin/betalingen?context=year-2026").can_ask


def test_a_record_names_itself_on_every_tab(db_session, world):
    activity = world["activity"].id
    for tab in ("", "/inschrijvingen", "/betalingen"):
        ctx = _context(db_session, f"/admin/activiteiten/{activity}{tab}")
        assert ctx.label == "over Herfstwandeling", tab
        assert ctx.post_url == f"/admin/rapporten/raakje/activiteit/{activity}"
        assert ctx.key == f"activity:{activity}"
    # An activity that does not exist is no context of its own.
    assert _context(db_session, "/admin/activiteiten/999999").key == "tenant"


def test_without_a_record_or_a_list_the_context_is_the_tenant(db_session, world):
    from app.kernel.tenant_config import tenant_display_name

    name = tenant_display_name(db_session, tenant_id=DEFAULT_TENANT_ID)
    for screen in ("/admin", "/admin/rapporten", "/admin/leden", "/admin/activiteiten"):
        ctx = _context(db_session, screen)
        assert ctx.label == f"over {name}" and ctx.post_url == "/admin/rapporten/raakje", screen


def test_the_key_follows_the_subject_not_the_page(db_session, world):
    """A page or a sort of the list is the same conversation; another filter
    is another one."""
    first = _context(db_session, "/admin/betalingen?zicht=openstaand")
    assert (
        _context(db_session, "/admin/betalingen?zicht=openstaand&page=2&sort=-naam").key
        == first.key
    )
    assert _context(db_session, "/admin/betalingen").key != first.key


# ── availability by rule ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "screen",
    [
        "/admin",
        "/admin/leden",
        "/admin/activiteiten",
        "/admin/betalingen",
        "/admin/formulieren",
        "/admin/werkbank",
        "/admin/rapporten",
    ],
)
def test_a_module_in_the_reporting_universe_offers_the_assistant(db_session, screen):
    assert _context(db_session, screen).available


@pytest.mark.parametrize(
    "screen",
    [
        "/admin/media",
        "/admin/paginas",
        "/admin/ontwerpen",
        "/admin/vergaderingen",
        "/admin/nieuwsbrieven",
        "/admin/gebruikers",
        "/admin/instellingen",
    ],
)
def test_elsewhere_the_assistant_says_it_does_not_know_the_data(db_session, screen):
    ctx = _context(db_session, screen)
    assert not ctx.available and not ctx.can_ask
    assert ctx.blocked == "Raakje kent deze gegevens nog niet."
    assert ctx.post_url == "" and ctx.suggestions == ()


def test_availability_is_derived_from_the_module_registry():
    """Not a typed list: a module that gains a reporting folder is offered the
    assistant without a change here, and one without is not."""
    with_folder = [m for m in MODULES if m.reporting_folders]
    assert len(with_folder) >= 5, "the registry lost its reporting folders — the rule reads nothing"
    for module in MODULES:
        path = next(
            (prefix for prefix in module.route_prefixes if prefix.startswith("/admin")), None
        )
        if path is None:
            continue
        code = serving_module(path)
        expected = bool(module.reporting_folders) or module.code.value == "reporting"
        assert module_knows_the_assistant(code, path) is expected, module.code


# ── the trigger and the panel ────────────────────────────────────────────────


def test_the_shell_carries_one_trigger_and_one_panel(client, db_session, switched_on, world):
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert html.count('id="assistent-knop"') == 1 and html.count("data-raakje-panel") == 1
    assert 'hx-get="/admin/rapporten/raakje/knop"' in html
    # Nothing of the old ways in.
    assert 'href="/admin/rapporten/raakje"' not in html and "AI · " not in html


def test_the_trigger_is_active_on_a_known_module_and_dimmed_elsewhere(client, switched_on, world):
    _login(client)
    known = client.get(KNOP, headers=_on("/admin/betalingen")).text
    assert 'data-raakje-trigger data-available="true"' in known and ">Assistent<" in known
    dimmed = client.get(KNOP, headers=_on("/admin/media")).text
    assert 'data-raakje-trigger data-available="false"' in dimmed
    # Dimmed but focusable: a button, not disabled, with the reason as its title.
    assert "disabled" not in dimmed and 'title="Raakje kent deze gegevens nog niet"' in dimmed
    # It asks again when the screen changes.
    assert 'hx-trigger="raakje-screen from:body"' in known


def test_the_panel_shows_the_screens_context_and_posts_to_its_endpoint(
    client, db_session, switched_on, world
):
    _login(client)
    html = client.get(PANEEL, headers=_on("/admin/betalingen?zicht=openstaand")).text
    assert ">Assistent<" in html
    assert re.search(
        r"data-panel-context[^>]*>over 3 openstaande betalingen \(filter Openstaand\)<", html
    )
    assert 'hx-post="/admin/rapporten/raakje/scherm/betalingen"' in html
    assert html.count("data-suggestion") == 3
    # No selector in the panel: the screen owns its selection.
    assert "<select" not in html and 'type="checkbox"' not in html
    # The shared controls: the history field, the microphone, read-aloud.
    assert 'id="rp-raakje-historie"' in html and 'data-stt-target="#assistent-vraag"' in html
    assert "data-tts-toggle" in html

    activity = world["activity"].id
    record = client.get(PANEEL, headers=_on(f"/admin/activiteiten/{activity}/inschrijvingen")).text
    assert re.search(r"data-panel-context[^>]*>over Herfstwandeling<", record)
    assert f'hx-post="/admin/rapporten/raakje/activiteit/{activity}"' in record


def test_a_refused_selection_shows_its_reason_and_no_question_field(client, switched_on, world):
    _login(client)
    html = client.get(PANEEL, headers=_on("/admin/betalingen?q=bram")).text
    assert "data-panel-blocked" in html and "de zoekterm" in html
    assert "data-raakje-form" not in html and "<textarea" not in html
    assert "data-suggestion" not in html


def test_an_unknown_module_shows_only_that_sentence(client, switched_on, world):
    _login(client)
    html = client.get(PANEEL, headers=_on("/admin/media")).text
    assert "Raakje kent deze gegevens nog niet." in html
    assert "data-raakje-form" not in html and "data-panel-context" not in html


def test_the_same_context_is_not_swapped_again(client, switched_on, world):
    """The conversation stays over a page of the list or a tab of the record:
    while the context is the one shown, the answer is 204."""
    _login(client)
    screen = _on("/admin/betalingen?zicht=openstaand")
    key = re.search(r'data-context-key="([^"]+)"', client.get(PANEEL, headers=screen).text).group(1)
    assert client.get(PANEEL, params={"huidig": key}, headers=screen).status_code == 204
    paged = _on("/admin/betalingen?zicht=openstaand&page=2")
    assert client.get(PANEEL, params={"huidig": key}, headers=paged).status_code == 204
    other = client.get(PANEEL, params={"huidig": key}, headers=_on("/admin/betalingen"))
    assert other.status_code == 200 and f'data-context-key="{key}"' not in other.text


# ── the switches and the roles (#1568, #1060) ────────────────────────────────


def test_with_the_tenants_switch_off_there_is_no_trigger_and_no_panel(
    client, db_session, monkeypatch, world
):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "0")
    db_session.commit()
    _login(client)
    knop = client.get(KNOP, headers=_on("/admin/betalingen"))
    assert knop.status_code == 200 and "data-raakje-trigger" not in knop.text
    # The slot stays, so the top bar can ask again after a navigation.
    assert 'id="assistent-knop"' in knop.text
    assert client.get(PANEEL, headers=_on("/admin/betalingen")).status_code == 403
    # The public Raakje has its own switch (#1568) and is not touched by this one.
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    assert "data-raakje-trigger" in client.get(KNOP, headers=_on("/admin/betalingen")).text


def test_with_the_environments_switch_off_the_shell_carries_nothing(
    client, db_session, monkeypatch, world
):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_chat_enabled", False)
    _login(client)
    html = client.get("/admin/activiteiten").text
    assert 'id="assistent-knop"' not in html and "data-raakje-panel" not in html


def test_a_role_that_may_not_ask_gets_no_trigger(client, db_session, switched_on, world):
    """FINANCE alone sees the payments list and may not ask the assistant
    (#1060): its top bar asks too, and gets an empty slot — not a 403."""
    email = "penningmeester-k8@example.org"
    user = User(email=email, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.commit()
    _login(client, email)
    knop = client.get(KNOP, headers=_on("/admin/betalingen"))
    assert knop.status_code == 200 and "data-raakje-trigger" not in knop.text
    assert client.get(PANEEL, headers=_on("/admin/betalingen")).status_code == 403


def test_the_public_switch_off_means_no_bell_and_a_closed_endpoint(client, db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "chat_enabled", True)
    assert "data-raakje-bell" in client.get("/").text
    set_setting(db_session, "public_chat_enabled", "0")
    db_session.commit()
    home = client.get("/").text
    assert "data-raakje-bell" not in home and "data-raakje-panel" not in home
    assert "raakje-panel.js" not in home
    assert client.post("/raakje/vraag", data={"vraag": "Hallo?"}).status_code == 404


# ── what left ────────────────────────────────────────────────────────────────


def test_the_assistant_page_moved_for_good(client, switched_on):
    _login(client)
    moved = client.get("/admin/rapporten/raakje", follow_redirects=False)
    assert moved.status_code == 301 and moved.headers["location"] == "/admin/rapporten"
    listing = client.get("/admin/rapporten").text
    assert "AI · Raakje" not in listing and 'href="/admin/rapporten/raakje"' not in listing


def test_a_failed_answer_says_so_and_keeps_the_question(
    client, db_session, switched_on, monkeypatch
):
    """Decision 10: "Raakje kon geen antwoord geven — probeer het opnieuw. Je
    vraag staat er nog." The header tells the panel to leave the field as it is."""
    import app.domains.chatbot.api as chatbot_api

    def broken(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(chatbot_api, "run_chat", broken)
    csrf = _login(client)
    answer = client.post(
        "/admin/rapporten/raakje",
        data={"vraag": "Hoeveel leden zijn er?", "historie": "[]"},
        headers={"X-CSRF-Token": csrf},
    )
    assert answer.status_code == 200 and answer.headers["X-Raakje-Failed"] == "1"
    assert (
        "Raakje kon geen antwoord geven — probeer het opnieuw. Je vraag staat er nog."
        in answer.text
    )
    assert "data-raakje-answer" not in answer.text, "an answer where there was none"


# ── #1562 PR 2: the answer shows the report behind it ───────────────────────


def _scripted(monkeypatch, calls, words="Dat staat hieronder."):
    """The chat loop replaced by a script: it runs these `run_report` calls
    through the route's own dispatcher (the real engine, the real scope) and
    answers with `words` — what a model does, without a model."""
    import app.domains.chatbot.api as chatbot_api

    def run(db, messages, provider, *, dispatch, **_kwargs):
        for arguments in calls:
            result = dispatch("run_report", arguments, db)
            assert '"error"' not in result, f"the scripted report was refused: {result}"
        return words

    monkeypatch.setattr(chatbot_api, "run_chat", run)


def _ask_the_panel(client, path="/admin/rapporten/raakje"):
    csrf = _login(client)
    return client.post(
        path, data={"vraag": "Hoeveel?", "historie": "[]"}, headers={"X-CSRF-Token": csrf}
    )


def test_one_figure_stands_large_in_the_balloon_with_its_range_and_source(
    client, db_session, switched_on, world, monkeypatch
):
    """Decision 10: an amount large in the balloon, with range and source — the
    engine's own result, not the model's words. Three open bookings of 20, 5 and
    10. Proven red by leaving `seen` out of the dispatcher: the balloon holds the
    words alone."""
    _scripted(
        monkeypatch,
        [{"objects": ["payment_open_amount"]}],
        words="Er staat nog 35 euro open.",
    )
    answer = _ask_the_panel(client)
    assert answer.status_code == 200, answer.text[:300]
    html = answer.text
    assert "Er staat nog 35 euro open." in html, "the words stay"
    figure = html[html.index("data-answer-figure") :]
    value = re.search(r"data-figure-value[^>]*>(.*?)</p>", figure, re.S).group(1)
    assert "35,00" in value and "€" in value, value
    assert "text-[28px]" in figure[: figure.index("</p>")] or "text-[28px]" in figure[:600]
    assert re.search(r"data-figure-range[^>]*>Bereik: alles<", figure), "no filter: everything"
    source = re.search(r"data-figure-source[^>]*>(.*?)</p>", figure, re.S).group(1)
    assert "Rapportering · Betalingen" in source and 'href="/admin/rapporten?' in source
    assert "data-answer-table" not in html


def test_several_rows_are_a_small_table_with_the_way_to_the_whole_list(
    client, db_session, switched_on, world, monkeypatch
):
    """Four bookings: a table of at most five rows and "Bekijk alle n …", which
    opens the same selection in the reporting panel. Proven red by linking to the
    panel without the selection: the list behind the answer is every row."""
    for index in range(4):
        reg = db_session.query(Registration).first()
        _booking(db_session, reg, "7.00", minutes=10 + index)
    db_session.commit()
    _scripted(
        monkeypatch,
        [{"objects": ["payment_record", "payment_status"], "layout": "detail"}],
    )
    html = _ask_the_panel(client).text
    table = html[html.index("data-answer-table") :]
    assert table.count("<tr") == 1 + 5, "the head and five rows of the eight"
    more = re.search(r'<a data-answer-more href="([^"]+)"[^>]*>([^<]+)</a>', table)
    assert more.group(2) == "Bekijk alle 8 betalingen"
    assert more.group(1).startswith("/admin/rapporten?")
    assert "object=payment_record" in more.group(1) and "layout=detail" in more.group(1)
    assert "data-answer-figure" not in html
    # The address really opens that selection.
    panel = client.get(more.group(1).replace("&amp;", "&"))
    assert panel.status_code == 200


def test_an_answer_without_a_report_is_words_alone(client, switched_on, world, monkeypatch):
    _scripted(monkeypatch, [], words="Dat weet ik niet.")
    html = _ask_the_panel(client).text
    assert "Dat weet ik niet." in html
    assert "data-answer-figure" not in html and "data-answer-table" not in html


def test_the_figure_of_a_record_is_counted_inside_its_scope(
    client, db_session, switched_on, world, monkeypatch
):
    """Asked beside an activity, the figure is that activity's — the route's
    scope binds the report, and the range says so."""
    other, component, _p = seed_activity_with_product(db_session, price="10.00")
    reg = Registration(
        contact_name="Cas Voorbeeld",
        contact_email="cas@example.org",
        phone="0470000000",
        activity_id=other.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
    )
    db_session.add(reg)
    db_session.flush()
    _booking(db_session, reg, "500.00", minutes=20)
    db_session.commit()
    _scripted(monkeypatch, [{"objects": ["payment_amount"]}])
    activity = world["activity"].id
    html = _ask_the_panel(client, f"/admin/rapporten/raakje/activiteit/{activity}").text
    value = re.search(r"data-figure-value[^>]*>(.*?)</p>", html, re.S).group(1)
    assert "65,00" in value, f"20 + 5 + 10 + 30 of this activity, not the other's 500: {value}"
    scope = re.search(r"data-figure-range[^>]*>Bereik: ([^<]+)<", html).group(1)
    assert scope != "alles" and "Herfstwandeling" in scope, f"the range names the record: {scope}"

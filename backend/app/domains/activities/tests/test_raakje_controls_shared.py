"""Raakje carries the same controls everywhere (#1075).

Koen's rule, 20 September 2026: *Raakje and Raakje-admin are the same
everywhere; the only difference is the security on the public one.* Before
#1075 each surface carried its own copy of the input row, and the activity
overlay had quietly lost the microphone and the read-aloud toggle. A copy does
not drift on purpose; it drifts because the next change lands on the surface
someone is looking at.

Since #1562 (CR-11 K8) the rule is one component: `_raakje_panel.html` of the
chatbot domain renders the conversation for both shells — the back office's
Assistent panel and the public bell. The assistant page and the per-screen
overlay (`_raakje_overlay.html`) are gone.

Two halves, and both are needed:

- **Source: one partial, no copies.** The panel component reaches the controls
  through `_raakje_controls.html`; the two surfaces reach them through the
  panel and build nothing themselves. The attributes that make the controls
  work (`data-stt-target`, `data-tts-toggle`, the growth handler) appear in
  that one partial and nowhere else. The lists are asserted to be non-empty,
  so a moved or removed template cannot make this scan an empty set and go
  green (#678).
- **Rendered: the back office's panel equals the public bell.** Through the
  real routes, with the switches on: the microphone button of the Assistent
  panel is byte-for-byte the bell's, save for the field id, on a record as on
  a list; the read-aloud toggle carries the same attributes; and the panel
  opened on the two other tabs of an activity is that activity's.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests._reporting_seed import TENANT_A
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

DOMAINS = Path(__file__).resolve().parents[4] / "app" / "domains"
PARTIAL = DOMAINS / "chatbot" / "templates" / "_raakje_controls.html"

APP = Path(__file__).resolve().parents[4] / "app"

# The ONE place that renders the controls itself (#1562), with the variant of
# the read-aloud toggle it asks for. A new surface goes through this component —
# not through a copy (design-system §2.11).
COMPONENT = "chatbot/templates/_raakje_panel.html"
COMPONENT_TOGGLE = "on_dark=True"

# The surfaces that show Raakje through that component: the public bell and the
# back office's Assistent panel. They render no controls themselves.
VIA_PANEL = (
    "chatbot/templates/_raakje_widget.html",
    "reporting/templates/_assistant_panel.html",
)

# The screens that had an overlay of their own until #1562.
FORMER_OVERLAY_SCREENS = (
    "activities/templates/_aa_recordkop.html",
    "payment/templates/_betalingen_scherm.html",
)

# What only the partial may carry: the hooks the two scripts read, and the
# growth handler the dictation test depends on (#788).
CONTROL_MARKERS = (
    "data-stt-target",
    "data-tts-toggle",
    "$el.style.height = Math.min($el.scrollHeight, 120)",
)


# ── Source: one partial, no copies ───────────────────────────────────────────


def test_every_surface_uses_the_shared_partial():
    component = (DOMAINS / COMPONENT).read_text()
    assert '{% import "_raakje_controls.html" as controls %}' in component, (
        f"{COMPONENT} does not import the shared Raakje controls"
    )
    assert "controls.input_row(" in component, f"{COMPONENT} builds its own input row"
    assert f"controls.read_aloud_toggle({COMPONENT_TOGGLE})" in component, (
        f"{COMPONENT} lacks the read-aloud toggle"
    )

    # A floor and not an exact number, but below two there is no "everywhere"
    # left to keep the same and this gate scans nothing (#678).
    assert len(VIA_PANEL) >= 2, "the list of Raakje surfaces shrank; this gate scans nothing"
    for relative in VIA_PANEL:
        source = (DOMAINS / relative).read_text()
        assert '{% import "_raakje_panel.html" as panel %}' in source, (
            f"{relative} does not import the shared panel"
        )
        assert "panel.inner(" in source, f"{relative} does not render the shared panel"
        assert "controls." not in source and "<form" not in source, (
            f"{relative} builds its own controls beside the panel"
        )


def test_no_screen_builds_an_overlay_of_its_own():
    """#1115 made the shared overlay the one modal of the record screens; #1562
    replaced it by the shell's panel. No template imports or calls the overlay
    any more, its file is gone, and the two screens that had one build no
    conversation of their own in its place."""
    assert not (APP / "ui" / "templates" / "_raakje_overlay.html").exists()

    templates = list(APP.rglob("templates/*.html"))
    assert len(templates) > 100, f"the scan found only {len(templates)} templates"
    callers = [
        str(template.relative_to(APP))
        for template in templates
        if "_raakje_overlay.html" in template.read_text()
        or "raakje.overlay(" in template.read_text()
    ]
    assert not callers, f"these templates still reach for the removed overlay: {callers}"

    assert FORMER_OVERLAY_SCREENS, "the list of former overlay screens is empty"
    for relative in FORMER_OVERLAY_SCREENS:
        source = (DOMAINS / relative).read_text()
        for own in ("controls.", "panel.inner(", "data-raakje-form", "/admin/rapporten/raakje"):
            assert own not in source, f"{relative} builds its own assistant again: {own}"


def test_the_control_markup_lives_in_the_partial_and_nowhere_else():
    partial = PARTIAL.read_text()
    for marker in CONTROL_MARKERS:
        assert marker in partial, f"the shared partial lost {marker!r}"

    copies = []
    for template in DOMAINS.rglob("*.html"):
        if template == PARTIAL:
            continue
        source = template.read_text()
        for marker in CONTROL_MARKERS:
            if marker in source:
                copies.append(f"{template.relative_to(DOMAINS)}: {marker}")
    assert not copies, (
        "Raakje controls copied outside _raakje_controls.html — call "
        "controls.input_row / controls.read_aloud_toggle instead:\n  " + "\n  ".join(copies)
    )


# ── Rendered: the back office's panel equals the public bell ────────────────

PANEL_URL = "/admin/rapporten/raakje/paneel"


def _panel(client, path: str):
    """The Assistent panel as it is loaded on the screen at `path`."""
    return client.get(PANEL_URL, headers={"HX-Current-URL": f"http://testserver{path}"})


@pytest.fixture
def assistant_on(db_session, monkeypatch):
    """Both switches on (CR-07 §6.3): the environment's and the tenant's."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT_A)
    db_session.flush()


@pytest.fixture
def activity(db_session):
    a = Activity(name="Wandeling met microfoon", location="Miloheem")
    db_session.add(a)
    db_session.flush()
    return a


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _microphone(html: str, field_id: str) -> str:
    """The whole microphone button, as rendered, for one field."""
    found = re.findall(
        rf'<button type="button" data-stt-target="#{field_id}"[\s\S]*?</button>', html
    )
    assert len(found) == 1, f"expected one microphone for #{field_id}, found {len(found)}"
    return found[0]


def _toggles(html: str) -> list[str]:
    """Elke voorleesknop op de pagina.

    Since #1562 a page or a panel holds one: the two Raakje's on the payments
    tab of an activity (#1115) became one panel.
    """
    found = re.findall(r'<button type="button" data-tts-toggle[\s\S]*?</button>', html)
    assert found, "geen enkele voorleesknop op de pagina"
    return found


def _toggle(html: str) -> str:
    return _toggles(html)[0]


def _attributes(button: str) -> dict[str, str]:
    """The button's attributes, first occurrence wins.

    Values may be double- or single-quoted: the icon SVGs travel in single quotes
    and carry `>` and attributes of their own, so the opening tag cannot be cut
    at the first `>` — the scan runs over the whole button and keeps the first
    value per name, which is the button's own."""
    pairs = re.findall(r'([a-z-]+)=(?:"([^"]*)"|\'([^\']*)\')', button)
    attrs: dict[str, str] = {}
    for name, double, single in pairs:
        attrs.setdefault(name, double or single)
    return attrs


@pytest.fixture
def bell(client, monkeypatch) -> str:
    """A public page with the bell on it."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    answer = client.get("/")
    assert answer.status_code == 200
    return answer.text


def test_the_panel_microphone_is_the_public_bells(client, db_session, assistant_on, activity, bell):
    _login(client)
    on_record = _panel(client, f"/admin/activiteiten/{activity.id}")
    on_list = _panel(client, "/admin/rapporten")
    assert on_record.status_code == 200 and on_list.status_code == 200
    assert f"/activiteit/{activity.id}" in on_record.text, "precondition: two different contexts"

    mic_record = _microphone(on_record.text, "assistent-vraag")
    mic_list = _microphone(on_list.text, "assistent-vraag")
    mic_bell = _microphone(bell, "raakje-widget-vraag")
    assert mic_record == mic_list, "the microphone differs between two screens of the back office"
    assert mic_record.replace("assistent-vraag", "raakje-widget-vraag") == mic_bell, (
        f"the panel's microphone differs from the public bell's:\n{mic_record}\n---\n{mic_bell}"
    )
    # Same speech path, from the same configuration value.
    assert 'data-stt-mode="' in mic_record


def test_the_panel_read_aloud_toggle_reads_like_the_public_bells(
    client, db_session, assistant_on, activity, bell
):
    """Everything tts.js reads — the hook, the two icons, the accessible name —
    is the same in the back office's panel and in the bell."""
    _login(client)
    panel = _toggles(_panel(client, f"/admin/activiteiten/{activity.id}").text)
    assert len(panel) == 1, "one toggle per conversation"
    public = _toggle(bell)

    panel_attrs, public_attrs = _attributes(panel[0]), _attributes(public)
    for name in ("data-icon-aan", "data-icon-uit", "aria-label", "title"):
        assert name in panel_attrs, f"the panel's toggle lacks {name}"
        assert panel_attrs[name] == public_attrs[name], name


def test_without_the_assistant_the_panel_and_its_controls_are_absent(client, db_session, activity):
    """The negative that gives the positive tests their meaning: the controls
    come with the panel, and the panel comes with the two switches."""
    _login(client)
    path = f"/admin/activiteiten/{activity.id}"
    html = client.get(path).text
    assert 'id="assistent-paneel"' not in html and 'id="assistent-knop"' not in html
    assert "data-stt-target" not in html
    assert "data-tts-toggle" not in html
    assert _panel(client, path).status_code == 403


@pytest.mark.parametrize("tab", ["inschrijvingen", "betalingen"])
def test_the_other_tabs_open_the_activitys_panel_with_its_microphone(
    client, db_session, assistant_on, activity, tab
):
    """Three pages carry the record head (#1070). Since #1562 none of them hands
    the assistant a context key: the panel reads the record from the address,
    and a tab's address must lead to the same activity as the record's own."""
    _login(client)
    path = f"/admin/activiteiten/{activity.id}/{tab}"
    answer = client.get(path)
    assert answer.status_code == 200, answer.text[:400]
    assert 'id="assistent-paneel"' in answer.text

    panel = _panel(client, path)
    assert panel.status_code == 200
    assert f'hx-post="/admin/rapporten/raakje/activiteit/{activity.id}"' in panel.text
    assert f"over {activity.name}" in panel.text
    _microphone(panel.text, "assistent-vraag")
    _toggle(panel.text)

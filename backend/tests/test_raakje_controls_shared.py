"""Raakje carries the same controls everywhere (#1075).

Koen's rule, 20 September 2026: *Raakje and Raakje-admin are the same
everywhere; the only difference is the security on the public one.* Four
surfaces show the assistant — the public widget, `/raakje`, the reporting
Raakje and the activity overlay — and before this issue each carried its own
copy of the input row. The overlay had quietly lost the microphone and the
read-aloud toggle. A copy does not drift on purpose; it drifts because the next
change lands on the surface someone is looking at.

Two halves, and both are needed:

- **Source: one partial, no copies.** Every Raakje template reaches the controls
  through `_raakje_controls.html` — directly, or through the shared overlay
  (`_raakje_overlay.html`), which since #1115 is the ONE modal for the record
  screens. The attributes that make the controls work (`data-stt-target`,
  `data-tts-toggle`, the growth handler) appear in that one partial and nowhere
  else. Both lists are asserted to be non-empty, so a moved or removed template
  cannot make this scan an empty set and go green (#678).
- **Rendered: the overlay equals the reporting Raakje.** Through the real
  routes, with both assistant switches on: the microphone button of the
  activity overlay is byte-for-byte the reporting one, save for the field id;
  the read-aloud toggle carries the same attributes; and the two other tabs
  that include the record header still render — the header is included by four
  templates and a missing `stt_mode` fails under `StrictUndefined` rather than
  rendering blank (#1070).

Broken on purpose, each restored after:
  - the microphone button of the overlay hand-written back into
    `_aa_recordkop.html` with one class changed → the source half names the
    file, and the rendered half shows the diff between the two buttons;
  - `stt_mode` dropped from `record_kop_ctx` → the tab test fails with the
    StrictUndefined error, on Inschrijvingen and on Betalingen.
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

DOMAINS = Path(__file__).resolve().parents[1] / "app" / "domains"
PARTIAL = DOMAINS / "chatbot" / "templates" / "_raakje_controls.html"

# De plekken die de bediening ZELF renderen, met de variant van de voorleesknop.
# Een nieuwe plek erbij? Dan via het partial — niet via een kopie (design-system
# §2.11).
SURFACES = {
    "chatbot/templates/_raakje_widget.html": "on_dark=True",
    # `chatbot/templates/raakje.html` stond hier tot #1120: de publieke pagina is
    # weg (niemand kwam er), de zwevende bel erboven doet het werk.
    "reporting/templates/admin_rapporten_raakje.html": "",
}
# De gedeelde overlay staat buiten `domains/` (het is kit-schil, niet één domein).
OVERLAY = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates" / "_raakje_overlay.html"

# De schermen die hun Raakje via die overlay tonen (#1115): zij renderen de
# bediening niet zelf en horen dat ook niet te doen — één modal, één vorm.
VIA_OVERLAY = (
    "activities/templates/_aa_recordkop.html",
    "payment/templates/_betalingen_scherm.html",
)

# What only the partial may carry: the hooks the two scripts read, and the
# growth handler the dictation test depends on (#788).
CONTROL_MARKERS = ("data-stt-target", "data-tts-toggle",
                   "$el.style.height = Math.min($el.scrollHeight, 120)")


# ── Source: one partial, no copies ───────────────────────────────────────────

def test_every_surface_uses_the_shared_partial():
    # Ondergrens en geen exact getal: de lijst mag krimpen (#1120 haalde de
    # publieke pagina weg), maar bij nul of één scant deze gate niets meer en
    # slaagt ze om de verkeerde reden (#678).
    assert len(SURFACES) >= 2, "de lijst Raakje-plekken kromp; deze gate scant niets"
    bronnen = {relative: (DOMAINS / relative).read_text() for relative in SURFACES}
    bronnen["ui/templates/_raakje_overlay.html"] = OVERLAY.read_text()
    varianten = dict(SURFACES, **{"ui/templates/_raakje_overlay.html": "on_dark=True"})
    for relative, source in bronnen.items():
        variant = varianten[relative]
        assert '{% import "_raakje_controls.html" as controls %}' in source, (
            f"{relative} does not import the shared Raakje controls")
        assert "controls.input_row(" in source, f"{relative} builds its own input row"
        assert f"controls.read_aloud_toggle({variant})" in source, (
            f"{relative} lacks the read-aloud toggle ({variant or 'page variant'})")


def test_de_overlayschermen_bouwen_geen_eigen_modal():
    """#1115: de recordschermen tonen Raakje via de gedeelde overlay.

    De activiteit-recordkop droeg tot dit issue een eigen kopie van diezelfde
    modal; die liep meteen achter (ze had wél een voorleesknop, de gedeelde niet).
    Eén modal, dus één plek waar de volgende verbetering landt.
    """
    assert VIA_OVERLAY, "de lijst overlay-schermen is leeg; deze gate scant niets"
    for relative in VIA_OVERLAY:
        source = (DOMAINS / relative).read_text()
        assert '{% import "_raakje_overlay.html" as raakje %}' in source, (
            f"{relative} importeert de gedeelde overlay niet")
        assert "raakje.overlay(" in source, f"{relative} roept de overlay niet aan"
        assert "controls." not in source, (
            f"{relative} bouwt zijn eigen bediening naast de overlay")


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
        "controls.input_row / controls.read_aloud_toggle instead:\n  "
        + "\n  ".join(copies))


# ── Rendered: the overlay equals the reporting Raakje ───────────────────────

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
        rf'<button type="button" data-stt-target="#{field_id}"[\s\S]*?</button>', html)
    assert len(found) == 1, f"expected one microphone for #{field_id}, found {len(found)}"
    return found[0]


def _toggles(html: str) -> list[str]:
    """Elke voorleesknop op de pagina.

    Meer dan één is sinds #1115 normaal: de Betalingen-tab van een activiteit
    draagt twee Raakje's — één over de activiteit, één over de selectie. Ze
    tonen dezelfde stand; `tts.js` schildert ze samen bij.
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


def test_the_overlay_microphone_is_the_reporting_one(client, db_session, assistant_on,
                                                     activity):
    _login(client)
    overlay = client.get(f"/admin/activiteiten/{activity.id}")
    reporting = client.get("/admin/rapporten/raakje")
    assert overlay.status_code == 200 and reporting.status_code == 200

    mic_overlay = _microphone(overlay.text, "aa-raakje-vraag")
    mic_reporting = _microphone(reporting.text, "rp-raakje-vraag")
    assert mic_overlay.replace("aa-raakje-vraag", "rp-raakje-vraag") == mic_reporting, (
        "the overlay's microphone differs from the reporting Raakje's:\n"
        f"{mic_overlay}\n---\n{mic_reporting}")
    # Same speech path, from the same configuration value.
    assert 'data-stt-mode="' in mic_overlay


def test_the_overlay_read_aloud_toggle_reads_like_the_reporting_one(
        client, db_session, assistant_on, activity):
    """The class differs by design (white on a blue header); everything tts.js
    reads — the hook, the two icons, the accessible name — is the same."""
    _login(client)
    overlay = _toggle(client.get(f"/admin/activiteiten/{activity.id}").text)
    reporting = _toggle(client.get("/admin/rapporten/raakje").text)

    assert "data-tts-toggle" in overlay and "data-tts-toggle" in reporting
    overlay_attrs, reporting_attrs = _attributes(overlay), _attributes(reporting)
    for name in ("data-icon-aan", "data-icon-uit", "aria-label", "title"):
        assert name in overlay_attrs, f"the overlay toggle lacks {name}"
        assert overlay_attrs[name] == reporting_attrs[name], name


def test_without_the_assistant_the_overlay_and_its_controls_are_absent(
        client, db_session, activity):
    """The negative that gives the positive tests their meaning: the controls
    come with the overlay, and the overlay comes with the kernel switch."""
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "aa-raakje-vraag" not in html
    assert "data-tts-toggle" not in html


@pytest.mark.parametrize("tab", ["inschrijvingen", "betalingen"])
def test_the_other_tabs_render_the_overlay_with_its_microphone(
        client, db_session, assistant_on, activity, tab):
    """Four templates include the record header (#1070). A context key missing
    on one of them is not a blank spot but a StrictUndefined error."""
    _login(client)
    answer = client.get(f"/admin/activiteiten/{activity.id}/{tab}")
    assert answer.status_code == 200, answer.text[:400]
    _microphone(answer.text, "aa-raakje-vraag")
    _toggle(answer.text)

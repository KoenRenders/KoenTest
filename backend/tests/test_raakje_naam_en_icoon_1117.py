"""Eén naam en één icoon voor Raakje (#1117).

Asked for by Koen on 21 September 2026. There were three names for the same
assistant and none carried an icon: *AI · Betalingen*, *AI · Activiteit* and
*Vraag het Raakje*. #1117 named every entrance `AI · <Scherm>` with the
`sparkles` icon from the kit, and gave the assistant a menu item of its own in
*Inzicht*.

**#1562 (CR-11 K8) finished that thought.** One name and one icon is now one
entrance: the trigger in the top bar, called *Assistent*, with the same
`sparkles` icon. What the suffix used to say — the reach of the conversation —
is the context line of the panel it opens:

| On | The panel says |
|---|---|
| an activity | *over <the activity's name>* |
| the payments list | *over N betalingen (…)* |
| elsewhere | *over <the tenant>* |

The three `AI · …` buttons, the menu item and the assistant's own page are gone;
the page's address moves to the reports list for good.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from tests._reporting_seed import TENANT_A
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

# Een herkenbaar stuk van het Lucide-pad, niet het hele pad: een test die op de
# laatste decimaal let, breekt bij elke Lucide-update zonder dat er iets mis is.
STERRETJES = 'd="M12 3 10.1 8.8'
# The addresses the browser shows, as htmx sends them with the two fragments.
TRIGGER = "/admin/rapporten/raakje/knop"
PANEL = "/admin/rapporten/raakje/paneel"
OLD_NAMES = ("Vraag het Raakje", "AI · Activiteit", "AI · Betalingen", "AI · Raakje")


def _on(pad: str) -> dict[str, str]:
    return {"HX-Current-URL": f"http://testserver{pad}"}


def _login(client, db) -> str:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    bestaand = {r.role_code.value for r in user.roles}  # CR-12 phase 2
    for rol in ("ADMIN", "OPERATOR", "FINANCE"):
        if rol not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


@pytest.fixture
def assistent_aan(db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT_A)
    db_session.flush()


def _trigger(html: str) -> str:
    """The rendered trigger button, with its content."""
    treffers = re.findall(r"<button\b[^>]*\bdata-assistant\b[^>]*>.*?</button>", html, re.S)
    assert len(treffers) == 1, f"expected one trigger, found {len(treffers)}"
    return treffers[0]


@pytest.fixture
def screens(db_session) -> dict[str, str]:
    """The three screens that had an entrance of their own, with what their
    panel must say it is about."""
    activiteit, _o, _p = seed_activity_with_product(db_session)
    db_session.flush()
    return {
        f"/admin/activiteiten/{activiteit.id}": f"over {activiteit.name}",
        "/admin/betalingen": "betalingen",
        "/admin/rapporten": "over ",
    }


# ── 1. One entrance: sparkles + Assistent ────────────────────────────────────


def test_elke_raakje_ingang_draagt_het_sterretjesicoon(client, db_session, assistent_aan, screens):
    """Since #1562 the entrance is the same trigger on every screen."""
    _login(client, db_session)

    zonder = []
    for pad in screens:
        antwoord = client.get(TRIGGER, headers=_on(pad))
        assert antwoord.status_code == 200, f"{pad} → {antwoord.status_code}"
        knop = _trigger(antwoord.text)
        assert 'data-available="true"' in knop, f"the assistant is dimmed on {pad}"
        if STERRETJES not in knop:
            zonder.append(pad)

    assert not zonder, (
        "the Assistent trigger lacks the sparkles icon on: "
        + ", ".join(zonder)
        + ' — use ui.icon("sparkles") from the kit, no markup of its own'
    )


def test_the_entrance_is_called_assistent_everywhere(client, db_session, assistent_aan, screens):
    """#1562: the entrance has one name on every screen, *Assistent* — as its
    accessible name and as its visible word — and none of the older names is
    left on a screen."""
    _login(client, db_session)

    for pad in screens:
        html = client.get(pad).text
        for oud in OLD_NAMES:
            assert oud not in html, f"{pad} draagt de oude naam nog: {oud}"
        assert f'hx-get="{TRIGGER}"' in html, f"{pad} does not ask for the trigger"

        knop = _trigger(client.get(TRIGGER, headers=_on(pad)).text)
        assert 'aria-label="Assistent"' in knop
        assert ">Assistent</span>" in knop, "the word left the button"


def test_het_icoon_komt_uit_de_kit(client, db_session, assistent_aan):
    """Geen losse `<svg>` in een sjabloon: het pad staat één keer, in `_macros.html`."""
    from pathlib import Path

    templates = Path(__file__).resolve().parents[1] / "app"
    in_sjablonen = [
        str(p.relative_to(templates))
        for p in templates.rglob("templates/*.html")
        if STERRETJES in p.read_text()
    ]
    assert in_sjablonen == ["ui/templates/_macros.html"], in_sjablonen


# ── 2. No menu item of its own any more (#1562) ──────────────────────────────


def test_the_insight_group_has_no_assistant_item():
    """#1117 gave the assistant its own item in *Inzicht*; #1562 took it out:
    the trigger in the top bar is on every screen, a menu item beside it would
    be a second way in to the same panel."""
    from app.ui import _right_of_screen, nav_for

    groepen = {
        g["label"]: g["items"]
        for g in nav_for("/admin/rapporten", frozenset(_right_of_screen().values()))
    }
    assert "Inzicht" in groepen, sorted(groepen)
    labels = [i["label"] for i in groepen["Inzicht"]]
    assert labels == ["Dashboard", "Rapporten"], labels
    alle = [i for items in groepen.values() for i in items]
    assert len(alle) > 10, "the menu is nearly empty; this scan proves nothing"
    assert not [i for i in alle if "raakje" in i["href"] or "AI · " in i["label"]]


def test_the_old_page_moves_to_the_reports_list(client, db_session, assistent_aan):
    """The assistant's page is gone (#1562). Its address answers with a
    permanent redirect to the reports list, and that is the item that lights up
    there — one, not two."""
    from app.ui import _right_of_screen, nav_for

    _login(client, db_session)
    antwoord = client.get("/admin/rapporten/raakje", follow_redirects=False)
    assert antwoord.status_code == 301
    assert antwoord.headers["location"] == "/admin/rapporten"

    actief = [
        i["href"]
        for g in nav_for("/admin/rapporten", frozenset(_right_of_screen().values()))
        for i in g["items"]
        if i["active"]
    ]
    assert actief == ["/admin/rapporten"], actief


# ── 3. The panel itself ──────────────────────────────────────────────────────


def test_the_panel_is_called_assistent_and_says_what_it_is_about(
    client, db_session, assistent_aan, screens
):
    """Until #1562 this was the page's title and subtitle. The panel's title is
    the one name, and under it stands what the conversation is about — the
    reach the `AI · <Scherm>` suffix used to carry."""
    _login(client, db_session)

    regels = set()
    for pad, waarover in screens.items():
        antwoord = client.get(PANEL, headers=_on(pad))
        assert antwoord.status_code == 200, f"{pad} → {antwoord.status_code}"
        titel = re.search(r"<h2[^>]*data-panel-title[^>]*>(.*?)</h2>", antwoord.text, re.S)
        assert titel and titel.group(1).strip() == "Assistent", pad
        regel = re.search(r"<p data-panel-context[^>]*>(.*?)</p>", antwoord.text, re.S)
        assert regel, f"the panel on {pad} does not say what it is about"
        assert waarover in regel.group(1), (pad, regel.group(1))
        for oud in OLD_NAMES:
            assert oud not in antwoord.text, f"the panel on {pad} carries the old name {oud}"
        regels.add(regel.group(1).strip())

    assert len(regels) == len(screens), f"three screens, three contexts: {regels}"

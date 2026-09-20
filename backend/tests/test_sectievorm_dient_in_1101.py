"""De sectievorm van de formulierbouwer dient echt in (#1101).

Gevonden bij #1090, uitgeschreven door de master-CLI, op v2.5 gezet door Koen op
20 september 2026. De `<form data-sectievorm>` had geen `hx-post`, geen `action`
en geen `method`: de drie htmx-attributen stonden op een niet-afgesloten `</div`
erna. Opslaan was een gewone submit, de browser deed een GET naar het huidige
adres, en de getypte sectietitel was weg — zonder melding. De route bestond; er
ging alleen nooit iets heen.

**Waarom deze test de vorm leest en niet de route aanroept.** De bestaande tests
(`test_formulierbouwer_staart.py`, `test_formulier_sprongbestemming.py`) posten
rechtstreeks naar `/admin/formulieren/<id>/secties/<id>` en stonden al die tijd
groen: ze toetsen de route, niet haar bedrading. Deze test doet wat htmx doet —
hij haalt de bestemming uit de gerenderde vorm zelf en verstuurt de velden die
erin staan. Ontbreekt de bestemming, of wijst ze ergens anders heen, dan faalt hij
hier, en niet pas bij een bestuurder die een titel kwijt is. Het volgende geval
van dezelfde soort — een attribuut dat op de verkeerde tag belandt — vangt hij
daarmee ook, want hij kijkt naar de vorm, niet naar de regel in de template.

Kapotgemaakt om te controleren dat hij rood kan worden (gemeten): de `hx-post` van
de vorm weggehaald → rood op "de sectievorm heeft geen bestemming".
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import FormSection
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


class _Vorm(HTMLParser):
    """De eerste `<form data-sectievorm>`: haar attributen en haar velden, zoals
    een browser ze zou versturen (verborgen velden, tekstvelden, textarea's en de
    geselecteerde optie van elke select)."""

    def __init__(self):
        super().__init__()
        self.attributen: dict[str, str] | None = None
        self.velden: dict[str, str] = {}
        self._binnen = False
        self._diepte = 0
        self._select: str | None = None
        self._textarea: str | None = None
        self._tekst: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and "data-sectievorm" in a and self.attributen is None:
            self.attributen = a
            self._binnen = True
            self._diepte = 0
            return
        if not self._binnen:
            return
        self._diepte += 1 if tag not in ("input", "option", "br", "path") else 0
        if tag == "input" and a.get("name") and a.get("type", "text") not in ("checkbox", "radio"):
            self.velden[a["name"]] = a.get("value", "")
        elif tag == "select":
            self._select = a.get("name")
            self.velden.setdefault(self._select, "")
        elif tag == "option" and self._select and "selected" in a:
            self.velden[self._select] = a.get("value", "")
        elif tag == "textarea":
            self._textarea = a.get("name")
            self._tekst = []

    def handle_data(self, data):
        if self._textarea:
            self._tekst.append(data)

    def handle_endtag(self, tag):
        if not self._binnen:
            return
        if tag == "select":
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.velden[self._textarea] = "".join(self._tekst)
            self._textarea = None
        elif tag == "form" and self._diepte == 0:
            self._binnen = False
        else:
            self._diepte = max(0, self._diepte - 1)


def _login(client) -> str:
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _formulier_met_sectie(client, admin_headers, db, csrf) -> tuple[int, FormSection]:
    r = client.post("/api/v1/forms", json={"title": "Sectievorm", "status": "draft",
                                           "fields": []}, headers=admin_headers)
    assert r.status_code == 200, r.text
    form_id = r.json()["id"]
    r = client.post(f"/admin/formulieren/{form_id}/secties", data={"title": "Oude titel"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text[:300]
    db.expire_all()
    sectie = db.query(FormSection).filter(FormSection.form_id == form_id).one()
    return form_id, sectie


def test_opslaan_in_de_sectievorm_bewaart_de_titel(client, admin_headers, db_session):
    csrf = _login(client)
    form_id, sectie = _formulier_met_sectie(client, admin_headers, db_session, csrf)

    bouwer = client.get(f"/admin/formulieren/{form_id}")
    assert bouwer.status_code == 200
    vorm = _Vorm()
    vorm.feed(bouwer.text)
    assert vorm.attributen is not None, "geen <form data-sectievorm> op de bouwer"

    # Wat htmx doet: de bestemming komt uit de vorm zelf.
    bestemming = vorm.attributen.get("hx-post") or vorm.attributen.get("action")
    assert bestemming, (
        "de sectievorm heeft geen bestemming (geen hx-post en geen action): Opslaan "
        f"doet dan een kale GET en de titel gaat verloren (#1101); attributen: "
        f"{sorted(vorm.attributen)}")
    assert vorm.attributen.get("hx-target") == "#fb-detail", vorm.attributen
    assert "title" in vorm.velden and vorm.velden["title"] == "Oude titel", vorm.velden

    gegevens = dict(vorm.velden, title="Nieuwe titel")
    antwoord = client.post(bestemming, data=gegevens, headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:300]

    db_session.expire_all()
    assert db_session.get(FormSection, sectie.id).title == "Nieuwe titel"
    # En het antwoord is de bouwer opnieuw, mét de nieuwe titel in de sectiebalk.
    assert re.search(r"Sectie 1 van 1\s*·\s*Nieuwe titel", antwoord.text), antwoord.text[:400]


def test_de_sectievorm_wijst_naar_haar_eigen_sectie(client, admin_headers, db_session):
    """Twee secties, twee vormen, elk met haar eigen bestemming — een vorm die naar
    de verkeerde sectie post, bewaart de titel op de verkeerde plek."""
    csrf = _login(client)
    form_id, eerste = _formulier_met_sectie(client, admin_headers, db_session, csrf)
    client.post(f"/admin/formulieren/{form_id}/secties", data={"title": "Tweede"},
                headers={"X-CSRF-Token": csrf})

    html = client.get(f"/admin/formulieren/{form_id}").text
    bestemmingen = re.findall(r'<form[^>]*data-sectievorm[^>]*hx-post="([^"]+)"', html)
    assert len(bestemmingen) == 2, bestemmingen
    assert bestemmingen[0].endswith(f"/secties/{eerste.id}")
    assert len(set(bestemmingen)) == 2

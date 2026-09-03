"""Publieke activiteitenkaart — popup-inschrijving + compacte deelnemersregel (#601).

PROD-pariteit (v1.14): inschrijven opent als smalle gecentreerde modal (niet een
breed inline blok), en "Wie doet er mee?" is één compacte regel (niet een verticale
lijst). We toetsen de templates op die vorm zodat de regressie niet terugkeert.
"""
from pathlib import Path
from types import SimpleNamespace

from app.ui import templates

TPL = Path(__file__).resolve().parents[1] / "app" / "domains" / "activities" / "templates"


def test_inschrijf_form_is_smalle_modal_body():
    inhoud = (TPL / "_inschrijf_form.html").read_text()
    # Geen breed inline getint blok meer; gestapelde velden i.p.v. 3 kolommen.
    assert "bg-blue-50" not in inhoud
    assert "sm:grid-cols-3" not in inhoud and "grid-cols-1" in inhoud
    # Herrender/vervang-doel is de modal-kaart.
    assert "inschrijf-card" in inhoud and 'hx-target="closest .inschrijf-card"' in inhoud


def test_activiteitenkaart_opent_popup():
    inhoud = (TPL / "_activiteiten_cards.html").read_text()
    assert '@click="ins = true"' in inhoud            # knop opent de modal
    assert 'x-show="ins"' in inhoud                    # overlay
    assert "max-w-md" in inhoud                        # smal
    assert "fixed inset-0" in inhoud                   # gecentreerde popup, geen inline blok


def test_deelnemers_is_compacte_inline_regel():
    out = templates.env.get_template("_deelnemers.html").render(deelnemers=[
        SimpleNamespace(contact_name="Jan", team_name=None, quantity=1),
        SimpleNamespace(contact_name="An", team_name=None, quantity=2),
        SimpleNamespace(contact_name=None, team_name="De Toppers", quantity=1),
    ])
    assert "<li>" not in out and "<ul" not in out       # geen verticale lijst
    assert "·" in out                                    # inline gescheiden
    assert "Jan" in out and "An" in out and "De Toppers" in out
    assert "4 " in out                                   # som van de aantallen (1+2+1)


def test_deelnemers_leeg_blijft_nette_tekst():
    out = templates.env.get_template("_deelnemers.html").render(deelnemers=[])
    assert "Nog niemand ingeschreven" in out

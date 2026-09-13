"""Drillen voegt een kolom toe, en het filter wordt aangeboden (#907, #909).

Koen, na de eerste versie: *"Ik vind niet dat op 2026 klikken, 2026 instellen als
filter is. In mijn beleving komt er bij drillen een kolom bij."* En de tweede helft
die het af maakt: *"Ik zou de filter tonen maar niets wegfilteren — dat scheelt al
een klik en toont direct de mogelijkheid."*

Dit bestand toetst wat daar structureel aan is: de plaats van de filterknop (#909)
en het zichtbaar afkappen. De werking van het drillen zelf staat in
`test_reporting_drill.py`.
"""
from __future__ import annotations

import re

import pytest

from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _paneel(client, query: str = "") -> str:
    antwoord = client.get(f"/admin/rapporten/paneel{query}")
    assert antwoord.status_code == 200
    return antwoord.text


def test_the_filter_button_sits_beside_the_name_like_everywhere_else(
        client, db_session, situation):
    """#909, getoetst op de STRUCTUUR en niet op een klassenaam.

    Sinds de hiërarchie rendert een datum op twee regels, en de filterknop was
    achteraan de tweede beland — één knop die ergens anders staat dan de dertig
    eromheen. Een lijst van tientallen objecten scan je op **positie**, niet op
    tekst.

    Dus: de filterknop staat in dezelfde container als de naam, en niet in de rij
    met de niveauknopjes. Op een klasse toetsen zou de opmaak vastpinnen in plaats
    van de bedoeling.
    """
    login(client, db_session)
    tekst = _paneel(client)

    # De eerste regel van een hiërarchie: het soortsymbool, de naam, de
    # filterknop. De tweede regel draagt de niveaus.
    blok = re.search(
        r'<span class="flex-1 text-sm text-ink">Betaaldatum</span>(.*?)</div>'
        r'(.*?)</div>', tekst, re.S)
    assert blok, "de regel voor Betaaldatum staat er niet zoals verwacht"
    eerste_regel, niveaurij = blok.group(1), blok.group(2)

    assert 'name="add_filter"' in eerste_regel, (
        "de filterknop hoort naast de naam te staan, op dezelfde regel")
    assert 'name="add_filter"' not in niveaurij, (
        "en niet achteraan de rij met niveauknopjes")
    assert 'name="add"' in niveaurij or 'name="remove"' in niveaurij, (
        "de tweede regel hoort de niveaus te dragen; vindt deze test ze niet, "
        "dan meet de regel hierboven iets anders dan bedoeld")


def test_a_plain_object_has_its_filter_button_in_the_same_place(client,
                                                                db_session,
                                                                situation):
    """De vergelijking waar #909 over gaat: één positie voor alle objecten."""
    login(client, db_session)
    tekst = _paneel(client)
    blok = re.search(r'(<li class="flex items-center gap-1".*?</li>)', tekst, re.S)
    assert blok, "er staat geen gewoon object in de lijst"
    assert 'name="add_filter"' in blok.group(1)


def test_a_truncated_crosstab_says_so(client, db_session, situation):
    """Afkappen mag, stilzwijgend afkappen niet — dat is de vorm uit #877.

    Gebroken met een lage limiet: de melding hoort te verschijnen, en zonder die
    limiet weer te verdwijnen. Anders zou de test ook slagen op een tabel die
    nooit afkapt.
    """
    from app.domains.reporting.api import Selection, build_pivot

    objecten = ("payment_created_day", "payment_method", "payment_amount")
    heel = build_pivot(db_session,
                       Selection(object_keys=objecten, layout="pivot"),
                       tenant_id=TENANT_A)
    assert not heel.truncated, "met de gewone limiet valt er niets af te kappen"

    afgekapt = build_pivot(db_session,
                           Selection(object_keys=objecten, layout="pivot",
                                     limit=1),
                           tenant_id=TENANT_A)
    assert afgekapt.truncated, (
        "met een limiet van één rij hoort de draaitabel te zeggen dat ze afkapt")
    assert afgekapt.as_context()["truncated"] is True

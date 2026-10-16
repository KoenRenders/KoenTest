"""Wijzigingen-scherm: leesbare kolomvolgorde, badges en paginering (#620).

De Details-kolom stond achteraan in een tabel met `overflow-x-auto` en viel dus als
eerste weg — net de kolom waarvoor je het scherm opent. De operatie kleurde de hele
rij i.p.v. een badge te dragen, tegen §2.10 en tegen de B6-regel uit #596. En het
scherm had geen paginering, terwijl §2.5 dat voorschrijft zodra een lijst kan groeien.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from app.ui import PER_PAGE_DEFAULT as PER_PAGE
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

_TH_BLOK = re.compile(r"<th[^>]*>(.*?)</th>", re.S)


def _koppen(html: str) -> list[str]:
    """Kolomkoppen als kale tekst. Sinds golf 3 (#913) wikkelt een sorteerbare
    kop haar label in een link met chevron-svg; strip de tags zodat deze tests
    hun onderwerp (de VOLGORDE) blijven toetsen, onafhankelijk van de vorm."""
    koppen = []
    for blok in _TH_BLOK.findall(html):
        tekst = re.sub(r"<[^>]+>", " ", blok)
        tekst = " ".join(tekst.split())
        if tekst:
            koppen.append(tekst)
    return koppen


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _wijzigingen(db, aantal):
    """Zaai audit-rijen.

    Snapshots ontstaan niet vanzelf bij een insert — de routers roepen ze expliciet
    aan. Voor deze schermtest doen we hetzelfde, met dezelfde functie die de
    productiecode gebruikt.
    """
    from app.domains.mdm.api import snapshot_person

    ids = []
    for i in range(aantal):
        person = Person(first_name=f"Test{i}", last_name="Wijziging")
        db.add(person)
        db.flush()
        ids.append(person.id)
        snapshot_person(
            db,
            person,
            operation="insert",
            action="person_created",
            source="test",
            actor="tester@example.com",
        )
    db.commit()
    return ids


def test_details_staat_voor_object_actor(client, db_session):
    """De kern van #620-1: Details mag niet als eerste buiten beeld vallen."""
    _wijzigingen(db_session, 2)
    _login(client)
    koppen = _koppen(client.get("/admin/ledenwijzigingen").text)

    assert "Details" in koppen
    for later in ("Object", "Actor"):
        assert koppen.index("Details") < koppen.index(later), f"Details hoort vóór {later} te staan"


def test_persoon_staat_voor_details(client, db_session):
    """Bij het scannen van een auditlogboek wil je eerst weten over wíé het gaat."""
    _wijzigingen(db_session, 2)
    _login(client)
    koppen = _koppen(client.get("/admin/ledenwijzigingen").text)
    assert koppen.index("Persoon") < koppen.index("Details")


def test_de_rauwe_actiecode_is_geen_kolom_meer(client, db_session):
    """#620-3a: die herhaalde Wijziging + Details in ontwikkelaarstaal."""
    _wijzigingen(db_session, 2)
    _login(client)
    assert "Actie" not in _koppen(client.get("/admin/ledenwijzigingen").text)


def test_operatie_is_een_badge_zonder_rijkleur(client, db_session):
    """§2.10 noemt "Gewijzigd"/"Verwijderd" letterlijk als badges; de B6-regel uit
    #596 verbiedt een tweede statussignaal via een gekleurd vlak."""
    _wijzigingen(db_session, 2)
    _login(client)
    html = client.get("/admin/ledenwijzigingen").text

    assert "rounded-full" in html  # er staan badges
    for tint in ("bg-green-50", "bg-yellow-50", "bg-red-50"):
        assert f'<tr class="{tint}' not in html
        assert f'{tint}"' not in html.split("<tbody")[1].split("</tbody>")[0]


def _herhaalt_zijn_object(rij) -> bool:
    """Staat het object in zijn eigen vorm — "(<object> #<id>)" — in zijn samenvatting?

    Een kaal "#<id>" is geen herhaling: de samenvatting van een bestelregel noemt
    twee *andere* objecten ("product #7 ×1 (inschrijving #7)"), en hun nummers
    vallen bij toeval samen met dat van de regel zelf (#2077).
    """
    eigen = rf"\(\s*{re.escape(str(rij['entity']))}\s*#{rij['entity_id']}\s*\)"
    return re.search(eigen, rij["summary"] or "", re.I) is not None


def test_de_toets_ziet_een_herhaald_object_maar_geen_toevallig_gelijk_nummer():
    """Rood-bewijs (#2077): de samenvatting die haar eigen object herhaalt faalt,
    de bestelregel waarvan product en inschrijving hetzelfde nummer dragen als de
    regel zelf blijft groen."""
    herhaald = {"entity": "Persoon", "entity_id": 90, "summary": "Jan (Persoon #90) gewijzigd"}
    toeval = {
        "entity": "Bestelregel",
        "entity_id": 7,
        "summary": "product #7 ×1 (inschrijving #7)",
    }
    assert _herhaalt_zijn_object(herhaald)
    assert not _herhaalt_zijn_object(toeval)


def test_elke_rij_heeft_een_samenvatting_zonder_het_object_te_herhalen(client, db_session):
    """De regel die anders stilletjes terugkruipt: het object staat in zijn eigen
    kolom, dus de samenvatting hoeft "(Persoon #90)" niet te herhalen. Alleen de rijen
    van deze test: wie alle rijen van vandaag leest, leest ook wat andere tests in
    dezelfde databank achterlieten."""
    from datetime import date

    from app.domains.reporting.api import all_changes_since

    ids = _wijzigingen(db_session, 3)
    # all_changes_since levert dicts; Jinja verbergt dat verschil met r.summary,
    # Python niet.
    eigen = [
        r
        for r in all_changes_since(db_session, date.today())
        if r["entity"] == "Persoon" and r["entity_id"] in ids
    ]
    assert len(eigen) == len(ids), "niet elke aangemaakte persoon heeft een audit-rij"
    for r in eigen:
        assert (r["summary"] or "").strip(), f"lege samenvatting voor {r['entity']}"
        assert not _herhaalt_zijn_object(r), (
            "de samenvatting herhaalt het object — dat staat in de Object-kolom"
        )


def test_paginering_toont_vijftig_per_pagina_en_behoudt_de_filters(client, db_session):
    """§2.5: server-side, 50 per pagina. Op HDEV stonden er 792 in één DOM."""
    _wijzigingen(db_session, PER_PAGE + 5)
    _login(client)

    eerste = client.get("/admin/ledenwijzigingen?since=2000-01-01").text
    assert eerste.count("<tr") - 1 == PER_PAGE, "pagina 1 hoort 50 rijen te tonen"
    assert "Volgende" in eerste

    tweede = client.get("/admin/ledenwijzigingen?since=2000-01-01&page=2").text
    assert 0 < tweede.count("<tr") - 1 <= PER_PAGE
    assert "since=2000-01-01" in tweede, "de filterstand hoort mee te gaan bij het bladeren"

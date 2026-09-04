"""Wijzigingen-scherm: leesbare kolomvolgorde, badges en paginering (#620).

De Details-kolom stond achteraan in een tabel met `overflow-x-auto` en viel dus als
eerste weg — net de kolom waarvoor je het scherm opent. De operatie kleurde de hele
rij i.p.v. een badge te dragen, tegen §2.10 en tegen de B6-regel uit #596. En het
scherm had geen paginering, terwijl §2.5 dat voorschrijft zodra een lijst kan groeien.
"""
import re

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person
from app.ui.changes_ui import PER_PAGE

KOP = re.compile(r"<th[^>]*>\s*([^<]+?)\s*</th>", re.S)


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _wijzigingen(db, aantal):
    """Elke insert van een Person levert een audit-snapshot op."""
    for i in range(aantal):
        db.add(Person(first_name=f"Test{i}", last_name="Wijziging"))
    db.commit()


def test_details_staat_voor_object_actor(client, db_session):
    """De kern van #620-1: Details mag niet als eerste buiten beeld vallen."""
    _wijzigingen(db_session, 2)
    _login(client)
    koppen = KOP.findall(client.get("/admin/ledenwijzigingen").text)

    assert "Details" in koppen
    for later in ("Object", "Actor"):
        assert koppen.index("Details") < koppen.index(later), \
            f"Details hoort vóór {later} te staan"


def test_persoon_staat_voor_details(client, db_session):
    """Bij het scannen van een auditlogboek wil je eerst weten over wíé het gaat."""
    _wijzigingen(db_session, 2)
    _login(client)
    koppen = KOP.findall(client.get("/admin/ledenwijzigingen").text)
    assert koppen.index("Persoon") < koppen.index("Details")


def test_de_rauwe_actiecode_is_geen_kolom_meer(client, db_session):
    """#620-3a: die herhaalde Wijziging + Details in ontwikkelaarstaal."""
    _wijzigingen(db_session, 2)
    _login(client)
    assert "Actie" not in KOP.findall(client.get("/admin/ledenwijzigingen").text)


def test_operatie_is_een_badge_zonder_rijkleur(client, db_session):
    """§2.10 noemt "Gewijzigd"/"Verwijderd" letterlijk als badges; de B6-regel uit
    #596 verbiedt een tweede statussignaal via een gekleurd vlak."""
    _wijzigingen(db_session, 2)
    _login(client)
    html = client.get("/admin/ledenwijzigingen").text

    assert "rounded-full" in html                      # er staan badges
    for tint in ("bg-green-50", "bg-yellow-50", "bg-red-50"):
        assert f'<tr class="{tint}' not in html
        assert f"{tint}\"" not in html.split("<tbody")[1].split("</tbody>")[0]


def test_elke_rij_heeft_een_samenvatting_zonder_het_object_te_herhalen(client, db_session):
    """De regel die anders stilletjes terugkruipt: het object staat in zijn eigen
    kolom, dus de samenvatting hoeft "(person #90)" niet te herhalen."""
    from datetime import date
    from app.domains.audit.api import all_changes_since

    _wijzigingen(db_session, 3)
    rijen = all_changes_since(db_session, date.today())
    assert rijen, "geen audit-rijen om te toetsen"
    for r in rijen:
        assert (r.summary or "").strip(), f"lege samenvatting voor {r.entity}"
        assert f"#{r.entity_id}" not in (r.summary or ""), \
            "de samenvatting herhaalt het object — dat staat in de Object-kolom"


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

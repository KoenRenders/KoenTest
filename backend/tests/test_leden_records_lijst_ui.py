"""Ledenscherm volgens het records-lijst-referentiescherm C1 (#582).

Twee dingen zijn hier waardevol om te testen, en het zijn allebei dingen die er
op het oog goed uitzien terwijl ze fout staan:

* de **kantelende campagne**: het doeljaar van "nog niet vernieuwd" verschuift op
  de tenant-datum `membership_next_year_from_md`. Vóór die dag gaat de campagne
  over het lopende jaar, erna over het volgende — en het referentiejaar schuift
  mee. Een teller die het verkeerde jaar neemt, toont een plausibel getal.
* de **filters op de query**: status en lidmaatschapsjaar moeten in de SQL zitten,
  niet op de opgehaalde pagina, anders klopt de paginering niet meer.
"""
from datetime import date

from tests.conftest import (
    SEEDED_ADMIN_EMAIL, create_test_member, create_test_person,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.membership.api import Membership, not_renewed_count, renewal_years
from app.domains.mdm.api import Member


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _gezin(db, naam: str) -> Member:
    """Eén gezin met één hoofdlid dat `naam` als achternaam draagt, zodat je het
    in de gerenderde lijst kunt terugvinden."""
    from app.domains.mdm.api import MemberPerson

    member = create_test_member(db)
    persoon = create_test_person(db, last_name=naam)
    db.add(MemberPerson(member_id=member.id, person_id=persoon.id,
                        relation_type="HOOFDLID"))
    db.flush()
    return member


def _gezin_met_lidmaatschap(db, naam: str, jaren: list[int]) -> Member:
    """Gezin met voor elk jaar in `jaren` een lidmaatschap dat dat jaar dekt."""
    member = _gezin(db, naam)
    for jaar in jaren:
        db.add(Membership(member_id=member.id, year=jaar, is_active=True,
                          valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31)))
    db.commit()
    return member


# ── De kantelende campagne ────────────────────────────────────────────────────

def test_doeljaar_kantelt_op_de_tenant_datum():
    """Standaardinstelling is 17 september (membership_next_year_from_md)."""
    assert renewal_years(date(2026, 9, 16)) == (2025, 2026)
    assert renewal_years(date(2026, 9, 17)) == (2026, 2027)
    assert renewal_years(date(2026, 12, 31)) == (2026, 2027)
    assert renewal_years(date(2026, 1, 2)) == (2025, 2026)


def test_niet_vernieuwd_volgt_het_juiste_referentiejaar(db_session):
    _gezin_met_lidmaatschap(db_session, "Vorigjaar", [2025])         # enkel 2025
    _gezin_met_lidmaatschap(db_session, "Ditjaar", [2025, 2026])     # 2025 + 2026
    _gezin_met_lidmaatschap(db_session, "Vooruit", [2026, 2027])     # 2026 + 2027

    # Vóór de kanteldatum: referentie 2025, doel 2026 → enkel "Vorigjaar" mist 2026.
    assert not_renewed_count(db_session, date(2026, 9, 16)) == 1
    # Erna: referentie 2026, doel 2027 → "Ditjaar" heeft 2026 maar geen 2027.
    assert not_renewed_count(db_session, date(2026, 9, 17)) == 1


def test_niet_vernieuwd_telt_wie_al_twee_jaar_gedekt_is_niet_mee(db_session):
    """Een lidmaatschap dat na de kanteldatum betaald werd dekt twee jaren; dat is
    exact wat 'al vernieuwd' betekent."""
    member = _gezin(db_session, "Dubbeldek")
    db_session.add(Membership(member_id=member.id, year=2026, is_active=True,
                              valid_from=date(2026, 9, 20), valid_to=date(2027, 12, 31)))
    db_session.commit()
    assert not_renewed_count(db_session, date(2026, 9, 17)) == 0


def test_inactief_lidmaatschap_telt_niet_als_vernieuwd(db_session):
    member = _gezin(db_session, "Inactief")
    db_session.add_all([
        Membership(member_id=member.id, year=2025, is_active=True,
                   valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31)),
        Membership(member_id=member.id, year=2026, is_active=False,
                   valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31)),
    ])
    db_session.commit()
    assert not_renewed_count(db_session, date(2026, 9, 16)) == 1


# ── Het scherm ────────────────────────────────────────────────────────────────

def test_kpi_rij_noemt_het_doeljaar_in_het_label(client, db_session):
    _login(client)
    _, doeljaar = renewal_years()
    html = client.get("/admin/leden").text
    assert "Actieve leden" in html and "Actieve personen" in html
    assert f"Nog niet vernieuwd</div>" not in html      # zonder jaar is het dubbelzinnig
    assert f"({doeljaar})" in html


def test_lijst_heeft_nieuw_lid_import_zoek_en_filters(client, db_session):
    _login(client)
    html = client.get("/admin/leden").text
    assert "+ Nieuw lid" in html and "Leden importeren" in html
    assert 'type="search"' in html
    assert 'name="status"' in html and 'value="opgezegd"' in html


def test_jaardropdown_is_datagedreven_en_filtert(client, db_session):
    _login(client)
    _gezin_met_lidmaatschap(db_session, "Oudlid", [2024])
    _gezin_met_lidmaatschap(db_session, "Nieuwlid", [2026])

    pagina = client.get("/admin/leden").text
    assert "Lidmaatschap 2024" in pagina and "Lidmaatschap 2026" in pagina

    op_2024 = client.get("/admin/leden/lijst", params={"jaar": "2024"}).text
    assert "Oudlid" in op_2024 and "Nieuwlid" not in op_2024


def test_statusfilter_scheidt_actief_van_opgezegd(client, db_session):
    _login(client)
    dit_jaar = date.today().year
    _gezin_met_lidmaatschap(db_session, "Actiefnu", [dit_jaar])
    _gezin_met_lidmaatschap(db_session, "Gestopt", [dit_jaar - 3])

    actief = client.get("/admin/leden/lijst", params={"status": "actief"}).text
    assert "Actiefnu" in actief and "Gestopt" not in actief

    opgezegd = client.get("/admin/leden/lijst", params={"status": "opgezegd"}).text
    assert "Gestopt" in opgezegd and "Actiefnu" not in opgezegd


def test_nieuw_lid_maakt_gezin_met_hoofdlid_en_opent_de_editor(client, db_session):
    from app.domains.mdm.api import MemberPerson, Person

    csrf = _login(client)
    resp = client.post("/admin/leden",
                       data={"first_name": "Marie", "last_name": "Peeters"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    persoon = db_session.query(Person).filter(Person.last_name == "Peeters").one()
    koppeling = db_session.query(MemberPerson).filter(
        MemberPerson.person_id == persoon.id).one()
    assert koppeling.relation_type == "HOOFDLID"
    assert resp.headers["HX-Redirect"] == f"/admin/leden/gezin/{koppeling.member_id}"


def test_kaart_opent_de_paginabrede_editor(client, db_session):
    _login(client)
    member = _gezin_met_lidmaatschap(db_session, "Klikbaar", [date.today().year])

    lijst = client.get("/admin/leden").text
    assert f'href="/admin/leden/gezin/{member.id}"' in lijst

    editor = client.get(f"/admin/leden/gezin/{member.id}")
    assert editor.status_code == 200
    assert "Alle leden" in editor.text and 'id="leden-detail"' in editor.text
    # htmx krijgt nog steeds het fragment, want de mutaties swappen #leden-detail
    fragment = client.get(f"/admin/leden/gezin/{member.id}",
                          headers={"HX-Request": "true"})
    assert "<html" not in fragment.text.lower()


# ── C1-referentiescherm (#611) ────────────────────────────────────────────────

def test_acties_staan_op_de_titelregel_boven_de_kpi_rij(client, db_session):
    """Het C1-referentiescherm zet de knoppen in de kop, niet in een losse rij
    onder de KPI's (waar de prozatekst van §3.2 ze had staan). Structureel te
    toetsen: ze komen vóór de KPI-rij in de HTML."""
    _login(client)
    html = client.get("/admin/leden").text
    assert html.index("+ Nieuw lid") < html.index("Actieve leden")
    assert html.index("Leden importeren") < html.index("+ Nieuw lid")  # secundair links


def test_kpi_kaart_noemt_het_referentiejaar_niet_nog_eens_het_doeljaar(client, db_session):
    """De derde regel zegt in welk jaar iemand lid wás — anders herhaalt ze enkel
    het doeljaar dat al in het label staat. Het jaar kantelt mee met de
    tenant-datum, dus het komt uit renewal_years() en staat niet hardgecodeerd."""
    _login(client)
    referentiejaar, doeljaar = renewal_years()
    html = client.get("/admin/leden").text
    assert f"Was lid in {referentiejaar}" in html
    assert referentiejaar == doeljaar - 1
    assert "dekt" not in html          # de oude formulering is weg

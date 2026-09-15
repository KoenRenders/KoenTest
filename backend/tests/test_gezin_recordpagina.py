"""Golf 9 (#913): het gezin als recordpagina — zelfde patroon als de activiteit.

Recordkop met het gezinslabel (hoofdlid, uit één bron: family_label) en tabs
Overzicht · Inschrijvingen N · Betalingen N (#544). Beide tabs putten uit
dezelfde payable-verzameling van het gezin (inschrijvingen van zijn personen,
incl. de e-mail-terugval voor gastinschrijvingen); de Wijzigingen-tab verviel
op Koens vraag (15 sep).
"""
from decimal import Decimal

import pytest
pytestmark = pytest.mark.ui_serverrendered

from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import (SESSION_COOKIE, User, UserRole,
                                  csrf_token_for, make_session_value)


def _login(client, email=SEEDED_ADMIN_EMAIL):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _gezin(db, achternaam="Recordmans", voornaam="Rita"):
    """Gezin met hoofdlid, lidmaatschap + lidgeldbetaling, en een
    inschrijving (op person_id) met betaling — via de modellen, zoals de
    andere schermtests hun feiten zaaien."""
    from app.domains.activities.api import Registration
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    m = Member()
    db.add(m); db.flush()
    p = Person(first_name=voornaam, last_name=achternaam)
    db.add(p); db.flush()
    db.add(MemberPerson(member_id=m.id, person_id=p.id,
                        relation_type="HOOFDLID"))
    ms = Membership(member_id=m.id, year=2026, is_active=True)
    db.add(ms); db.flush()
    db.add(PaymentRecord(payable_type="membership", payable_id=ms.id,
                         amount=Decimal("35.00"), method="transfer",
                         status="pending"))
    activity, comp, _prod = seed_activity_with_product(db)
    reg = Registration(activity_id=activity.id, registration_type="INDIVIDUAL",
                       contact_name=f"{voornaam} {achternaam}",
                       contact_email=f"{achternaam.lower()}@example.com",
                       component_id=comp.id, person_id=p.id)
    db.add(reg); db.flush()
    db.add(PaymentRecord(payable_type="registration", payable_id=reg.id,
                         amount=Decimal("10.00"), method="transfer",
                         status="pending"))
    db.flush()
    return m, p, ms, reg


def test_recordkop_draagt_label_tabs_en_verwijderen(client, db_session):
    m, p, _ms, _reg = _gezin(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/leden/gezin/{m.id}").text

    assert "Recordmans Rita" in html  # gezinslabel = hoofdlid, zoals de lijst
    assert f"{_('Gezin') if False else 'Gezin'} #{m.id}" in html
    assert ">Overzicht</a>" in html
    # De Wijzigingen-tab verviel op Koens vraag (15 sep); Inschrijvingen
    # kwam ervoor in de plaats — met het aantal (één inschrijving gezaaid).
    # ("Wijzigingen" als woord staat nog in de linkernav — die blijft.)
    assert f"/admin/leden/gezin/{m.id}/wijzigingen" not in html
    assert f'href="/admin/leden/gezin/{m.id}/inschrijvingen"' in html
    assert "Inschrijvingen 1" in html
    # De oude Gezin#-kaart is weg; Verwijderen zit in de kop.
    assert ">Verwijderen<" in html
    # De gezaaide beheerder draagt FINANCE (migratie 056) → Betalingen-tab
    # met het aantal: lidgeld + inschrijvingsbetaling.
    assert f'href="/admin/leden/gezin/{m.id}/betalingen"' in html
    assert "Betalingen 2" in html


def test_admin_zonder_finance_ziet_de_tab_wel(client, db_session):
    """Betalingen BEKIJKEN mag voor ADMIN/FINANCE/OPERATOR (require_finance_ui)
    — golf 8 gate-te de tab op FINANCE alleen en verstopte hem dus voor een
    gewone ADMIN terwijl het scherm gewoon zou openen. De tab volgt nu exact
    dezelfde vraag als de poort (may_view_payments)."""
    m, *_rest = _gezin(db_session)
    db_session.commit()
    _login(client, "bestuurslid@example.com")  # ADMIN zonder FINANCE (migratie 014)
    html = client.get(f"/admin/leden/gezin/{m.id}").text
    assert f'href="/admin/leden/gezin/{m.id}/betalingen"' in html
    assert client.get(f"/admin/leden/gezin/{m.id}/betalingen").status_code == 200


def test_betalingen_tab_toont_lidgeld_en_inschrijving(client, db_session):
    m, _p, _ms, _reg = _gezin(db_session)
    ander, *_r = _gezin(db_session, achternaam="Anderman", voornaam="Bert")
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/leden/gezin/{m.id}/betalingen").text

    assert "Recordmans" in html          # de recordkop én de kaarten
    assert "Lidmaatschap" in html        # de membership-payable overleeft de scope
    assert "Anderman" not in html        # het andere gezin blijft buiten beeld
    assert "Voor gezin:" not in html     # ingebed: de kop zegt al waar je bent
    assert f'name="gezin" value="{m.id}"' in html  # scope overleeft filters


def test_gezin_deeplink_toont_zichtbare_scope(client, db_session):
    m, *_rest = _gezin(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/betalingen?gezin={m.id}").text
    assert "Voor gezin:" in html and "Recordmans Rita" in html
    assert "Alle bekijken" in html


def test_inschrijvingen_tab_groepeert_per_activiteit(client, db_session):
    """De Inschrijvingen-tab (verving Wijzigingen, 15 sep): de inschrijvingen
    van dit gezin — via zijn personen — per activiteit, met de groepskop als
    link naar de activiteitpagina en een Details-knop per rij. Een ander
    gezin lekt niet mee de scope in."""
    m, p, _ms, reg = _gezin(db_session)
    ander, *_r = _gezin(db_session, achternaam="Anderman", voornaam="Bert")
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/leden/gezin/{m.id}/inschrijvingen").text

    assert "Rita Recordmans" in html          # de rij (contact_name)
    assert "Anderman" not in html, "een ander gezin lekt de scope in"
    assert f'href="/admin/activiteiten/{reg.activity_id}"' in html  # groepskop
    assert ">Details<" in html
    assert f"/admin/inschrijvingen/{reg.id}?terug=" in html
    # De oude Wijzigingen-tab is echt weg, niet enkel verstopt.
    assert client.get(
        f"/admin/leden/gezin/{m.id}/wijzigingen").status_code == 404


def test_leesmodus_toont_ook_het_geslacht(client, db_session):
    """Alle invulbare velden zichtbaar in leesmodus (Koen, 15 sep): het
    geslacht ontbrak als enige op de persoonskaart."""
    from datetime import date as _date

    m, p, *_rest = _gezin(db_session)
    p.date_of_birth = _date(1980, 1, 1)
    p.gender_code = "M"
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/leden/gezin/{m.id}").text
    assert "° 01-01-1980 · Man" in html


def test_family_label_valt_terug_op_het_nummer(db_session):
    from app.domains.mdm.api import Member
    from app.domains.membership.api import family_label, get_family

    m = Member()
    db_session.add(m); db_session.flush()

    assert family_label(get_family(db_session, m.id)) == f"Gezin #{m.id}"


def test_accountmenu_draagt_mijn_profiel(client, db_session):
    """Golf 9-chroom: het accountmenu heeft Mijn profiel en Uitloggen;
    Werkruimte wisselen verschijnt pas bij meer dan één werkruimte (#963)."""
    _login(client)
    html = client.get("/admin").text
    assert "Mijn profiel" in html and 'href="/admin/profiel"' in html
    assert "Werkruimte wisselen" not in html  # één werkruimte vandaag


def test_mijn_profiel_toont_rollen_werkruimtebreed(client, db_session):
    _login(client)
    html = client.get("/admin/profiel").text
    assert SEEDED_ADMIN_EMAIL in html
    assert "ADMIN" in html and "FINANCE" in html  # migraties 014/056
    assert "#963" in html  # de eerlijke kanttekening tot rollen-per-werkruimte


def test_opslaan_ververst_de_kop_out_of_band(client, db_session):
    """Zelfde HDEV-melding als de activiteit: de kop (naam, adres) staat
    buiten #leden-detail en reist nu oob mee met elk mutatie-antwoord."""
    m, p, _ms, _reg = _gezin(db_session)
    db_session.commit()
    csrf = _login(client)
    r = client.post(f"/admin/leden/gezin/{m.id}/persoon/{p.id}",
                    data={"first_name": "Rita", "last_name": "Nieuwnaam",
                          "date_of_birth": "1980-01-01", "gender_code": "M",
                          "relation_type": "HOOFDLID"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert 'id="gezin-recordkop" hx-swap-oob="true"' in r.text
    assert "Nieuwnaam Rita" in r.text


def test_inschrijvingen_tab_overleeft_geschrapte_activiteit(client, db_session):
    """Een inschrijving waarvan de activiteit soft-deleted is hoort de tab
    niet te laten crashen (reg.activity is dan None door het
    soft-delete-filter); ze verdwijnt uit de deelnamelijst."""
    from datetime import datetime, timezone

    from app.domains.activities.api import Activity

    m, p, _ms, reg = _gezin(db_session)
    db_session.query(Activity).filter(Activity.id == reg.activity_id).update(
        {"deleted_at": datetime.now(timezone.utc)})
    db_session.commit()
    _login(client)
    r = client.get(f"/admin/leden/gezin/{m.id}/inschrijvingen")
    assert r.status_code == 200
    assert "Nog geen inschrijvingen" in r.text


def test_inschrijvingen_tab_sorteert_binnen_de_groep(client, db_session):
    """De gezinstab kreeg met de unificatie (15 sep) dezelfde sortering als
    de activiteitstab — zelfde whitelist, zelfde parameters."""
    import re

    from app.domains.activities.api import Registration

    m, p, _ms, reg = _gezin(db_session)
    extra = Registration(activity_id=reg.activity_id,
                         registration_type="INDIVIDUAL",
                         contact_name="Aaa Eerst",
                         contact_email="recordmans@example.com",
                         component_id=reg.component_id, person_id=p.id)
    db_session.add(extra); db_session.commit()
    _login(client)
    basis = f"/admin/leden/gezin/{m.id}/inschrijvingen"

    def namen(html):
        return re.findall(r">(Aaa Eerst|Rita Recordmans)</a>", html)

    assert namen(client.get(f"{basis}?sort=naam&richting=asc").text) == \
        ["Aaa Eerst", "Rita Recordmans"]
    assert namen(client.get(f"{basis}?sort=naam&richting=desc").text) == \
        ["Rita Recordmans", "Aaa Eerst"]
    # Vervalste parameters vallen veilig terug en lekken niet in de links.
    veilig = client.get(f"{basis}?sort=x);DROP--&richting=zijwaarts")
    assert veilig.status_code == 200 and "DROP" not in veilig.text


def test_beide_tabs_renderen_het_gedeelde_sjabloon():
    """Ratchet op de unificatie (Koens vraag, 15 sep): de groepentabel bestaat
    één keer, in _inschrijvingen_groepen.html; beide tabpagina's includen
    hem. Wie de tabel opnieuw in een pagina kopieert, maakt deze rood."""
    from pathlib import Path

    basis = Path(__file__).resolve().parents[1] / "app" / "domains"
    act = (basis / "activities" / "templates"
           / "admin_activiteit_inschrijvingen.html").read_text()
    gez = (basis / "mdm" / "templates"
           / "admin_gezin_inschrijvingen.html").read_text()
    for pagina in (act, gez):
        assert '{% include "_inschrijvingen_groepen.html" %}' in pagina
        assert "<table" not in pagina, "de tabel hoort alleen in het gedeelde sjabloon"

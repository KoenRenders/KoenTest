"""Dekkingsgaten op de kritische flows (word lid / leden beheren / inschrijven),
#600, onder de coverage-audit #529. Scope: tests toevoegen; het werkelijke gedrag
vastnagelen — geen nieuwe invarianten opleggen aan de productiecode.
"""
from decimal import Decimal

import pytest

from tests.conftest import (
    create_test_family, create_test_person,
    seed_postal_code, seed_activity_with_product,
)


def _family_payload(email="cover@example.com", **overrides):
    payload = {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {"last_name": "Peeters", "first_name": "Jan", "email": email,
             "mobile": "0470000000", "date_of_birth": "1980-01-01",
             "gender_code": "M", "relation_type": "HOOFDLID"},
            {"last_name": "Peeters", "first_name": "Kind", "relation_type": "KIND",
             "date_of_birth": "2012-03-04", "gender_code": "M"},
        ],
    }
    payload.update(overrides)
    return payload


# ── 1. POST /families — onbekende postcode + atomiciteit ──────────────────────

def test_families_onbekende_postcode_422_geen_partial_rows(client, db_session):
    """Een niet-bestaande postcode → 422, en er blijft geen half gezin achter."""
    # Bewust GEEN seed_postal_code → "2400" bestaat niet.
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 422

    from app.domains.mdm.api import Member, Person
    assert db_session.query(Member).count() == 0
    assert db_session.query(Person).count() == 0


def test_families_betaalfout_rolt_alles_terug(client, db_session, monkeypatch):
    """Faalt het aanmaken van het betaalrecord, dan rolt de registratie volledig
    terug — geen wees-Member/Person/Membership."""
    seed_postal_code(db_session)

    def _boom(*args, **kwargs):
        raise ValueError("betaalprovider onbereikbaar")

    monkeypatch.setattr(
        "app.domains.membership.register_router.create_payment_record", _boom
    )

    resp = client.post("/api/v1/families", json=_family_payload(email="boom@example.com"))
    assert resp.status_code == 422

    from app.domains.mdm.api import Member, Person
    from app.domains.membership.api import Membership
    assert db_session.query(Member).count() == 0
    assert db_session.query(Person).count() == 0
    assert db_session.query(Membership).count() == 0


# ── 2. #551 op het JSON-endpoint ──────────────────────────────────────────────

def test_families_bijkomend_lid_zonder_dob_geslacht_422(client, db_session):
    """#551, server-side in register_family: een bijkomend lid zonder geboortedatum
    én geslacht wordt geweigerd (niet enkel op het UI-pad)."""
    seed_postal_code(db_session)
    payload = _family_payload(email="dob@example.com")
    payload["members"][1].pop("date_of_birth")
    payload["members"][1].pop("gender_code")

    resp = client.post("/api/v1/families", json=payload)
    assert resp.status_code == 422

    from app.domains.mdm.api import Member
    assert db_session.query(Member).count() == 0


def test_families_hoofdlid_zonder_dob_mag_niet(client, db_session):
    """Sinds #681 gelden geboortedatum en geslacht ook voor het hoofdlid.

    Deze test heette tot #681 `..._mag_wel` en legde het tegendeel vast: #551 gold
    enkel voor de bijkomende leden. De uitzondering is bewust weggehaald — in het
    programma waarmee Raak zijn ledenbestand voert zijn het twee verplichte velden,
    en een uitzondering voor precies de persoon die élk gezin heeft, laat het gat
    even groot als voordien.
    """
    seed_postal_code(db_session)
    payload = _family_payload(email="hoofd@example.com")
    hoofdlid = {k: v for k, v in payload["members"][0].items()
                if k not in ("date_of_birth", "gender_code")}
    payload["members"] = [hoofdlid]
    assert client.post("/api/v1/families", json=payload).status_code == 422

    payload["members"] = [{**hoofdlid, "date_of_birth": "1980-01-01",
                           "gender_code": "M"}]
    resp = client.post("/api/v1/families", json=payload)
    assert resp.status_code == 201, resp.text


# ── 3. Server-side totaal-herberekening ───────────────────────────────────────

def test_totaal_negeert_client_aangeleverd_totaal(client, db_session):
    """`/…/totaal` herrekent server-side uit de aantallen en negeert een door de
    client meegestuurd totaal (§19.3 — geen drift)."""
    activity, comp, product = seed_activity_with_product(db_session, price="10.00")

    resp = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{comp.id}/totaal",
        data={f"product_{product.id}": "2", "totaal": "999.00"},
    )
    assert resp.status_code == 200
    assert "€20.00" in resp.text      # 2 × 10,00, server-side berekend
    assert "999" not in resp.text     # het client-totaal telt niet mee


def test_totaal_rekent_ledenprijs_voor_ingelogd_lid(client, db_session):
    """Een ingelogd lid met geldig lidmaatschap krijgt de ledenprijs in het
    server-side totaal."""
    from datetime import date
    from app.domains.activities.api import ActivityProduct
    from app.domains.membership.api import Membership
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    activity, comp, product = seed_activity_with_product(db_session, price="10.00")
    db_session.query(ActivityProduct).filter(ActivityProduct.id == product.id).update(
        {"member_price": Decimal("6.00")}
    )
    member, person = create_test_family(db_session, email="lid-prijs@example.com")
    y = date.today().year
    db_session.add(Membership(member_id=member.id, year=y, is_active=True,
                              valid_from=date(y, 1, 1), valid_to=date(y, 12, 31)))
    db_session.flush()

    # De totaal-route bepaalt het lid via de HttpOnly-sessiecookie, niet via Bearer.
    client.cookies.set(SESSION_COOKIE, make_session_value("lid-prijs@example.com"))
    resp = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{comp.id}/totaal",
        data={f"product_{product.id}": "2"},
    )
    assert resp.status_code == 200
    assert "€12.00" in resp.text  # 2 × ledenprijs 6,00
    assert "(ledenprijs)" in resp.text


# ── 4. HOOFDLID-integriteit op de JSON-person-endpoints ───────────────────────

def _add_person_to_family(db, member, *, relation_type="KIND", **kwargs):
    from app.domains.mdm.api import MemberPerson
    p = create_test_person(db, **kwargs)
    db.add(MemberPerson(member_id=member.id, person_id=p.id, relation_type=relation_type))
    db.flush()
    return p


def test_admin_update_person_wijzigt_relation_type_niet(client, db_session, admin_headers):
    """`PUT /persons/{id}` (admin) kan het relatietype niet degraderen: het veld
    zit op MemberPerson, niet op Person, en het schema negeert het. Een meegestuurd
    `relation_type` laat het hoofdlid hoofdlid."""
    member, person = create_test_family(db_session, email="hoofd-immut@example.com")

    resp = client.put(
        f"/api/v1/persons/{person.id}",
        json={"first_name": "Nieuw", "relation_type": "KIND"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    from app.domains.mdm.api import MemberPerson
    mp = db_session.query(MemberPerson).filter(MemberPerson.person_id == person.id).first()
    assert mp.relation_type == "HOOFDLID"


def test_admin_verwijder_bijkomend_lid_laat_hoofdlid_intact(client, db_session, admin_headers):
    """Een bijkomend lid verwijderen laat het hoofdlid (en dus het gezin) coherent
    achter — de HOOFDLID-koppeling blijft bestaan."""
    member, hoofdlid = create_test_family(db_session, email="coherent@example.com")
    kind = _add_person_to_family(db_session, member, relation_type="KIND",
                                 first_name="Kind", last_name="Persoon")

    resp = client.delete(f"/api/v1/persons/{kind.id}", headers=admin_headers)
    assert resp.status_code == 204

    db_session.expire_all()
    from app.domains.mdm.api import MemberPerson
    levend = (db_session.query(MemberPerson)
              .filter(MemberPerson.member_id == member.id,
                      MemberPerson.deleted_at.is_(None)).all())
    relaties = {mp.person_id: mp.relation_type for mp in levend}
    assert relaties.get(hoofdlid.id) == "HOOFDLID"
    assert kind.id not in relaties

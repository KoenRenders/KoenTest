"""#713 — een lege actor betekende twee dingen tegelijk.

Koen vroeg of hij ervan mag uitgaan dat een lege actor alleen bij een publieke,
niet-aangemelde handeling voorkomt. Van de tien snapshot-aanroepen zonder actor waren
er maar zes terecht.

**Niet terecht:** `create_member` (drie aanroepen) — de weg van het beheerscherm
"Nieuw lid". Dat het een vergetelheid was en geen keuze, bewijst de functie zelf: ze
had een parameter `_admin` die de JSON-route netjes doorgaf en die voor de audit
genegeerd werd. Diezelfde snapshots schreven bovendien `source="system"`, dus een
beheerdersactie stond genoteerd als systeemactie zónder actor — aan geen van beide
velden te herkennen. En `snapshot_registration_item` in de inschrijfroute, die
anonieme én aangemelde bezoekers bedient: twee regels hoger werd `current_member` wél
gebruikt om de inschrijving aan een persoon te hangen, maar niet om de auditregel te
tekenen.

**Het echte probleem was dat leeg twee dingen betekende.** Het scherm rendert een lege
actor als een lege cel, dus "we weten niet wie dit deed" en "er was niemand aangemeld"
zagen er identiek uit. Daardoor kon niemand zo'n cel lezen, en kon een volgende
vergetelheid er ongemerkt bij komen — zo zijn deze vier ontstaan.

Vanaf nu schrijven de publieke wegen `PUBLIEKE_ACTOR`, en betekent **leeg = fout**.
Bestaande rijen blijven leeg: die kunnen we niet met terugwerkende kracht duiden.
"""
import ast
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.domains.audit.api import PUBLIEKE_ACTOR
from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

APP = Path(__file__).resolve().parents[1] / "app"


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _snapshots_zonder_actor() -> list[str]:
    """Elke `snapshot_*`-aanroep in `app/` die geen `actor=` meegeeft."""
    fouten = []
    for pad in sorted(APP.rglob("*.py")):
        for knoop in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
            if not isinstance(knoop, ast.Call):
                continue
            naam = getattr(knoop.func, "id", getattr(knoop.func, "attr", ""))
            if not naam.startswith("snapshot_"):
                continue
            if not any(kw.arg == "actor" for kw in knoop.keywords):
                fouten.append(f"{pad.relative_to(APP)}:{knoop.lineno} {naam}")
    return fouten


# ── 1. De gate ─────────────────────────────────────────────────────────────

def test_elke_snapshot_tekent_zijn_actor():
    """Zonder bewaking komt de volgende ingang er weer zonder actor bij — precies
    zo zijn de vier ontstaan die dit issue rechtzet.

    **Bewijs dat deze gate werkt** (gedraaid vóór deze commit, niet beweerd): ik heb
    `actor=PUBLIEKE_ACTOR` weggehaald bij `snapshot_membership` in
    `membership/register_router.py`. De controle meldde daarop precies één regel —
    `app/domains/membership/register_router.py:435` — en na herstel weer geen enkele.
    Eén overtreding in, één treffer uit: hij kijkt dus écht, en niet naar iets anders.

    Een publieke weg geeft `PUBLIEKE_ACTOR` mee; een beheerdersweg het e-mailadres.
    Beide zijn een actor. Wat niet mag, is de vraag helemaal niet beantwoorden.
    """
    fouten = _snapshots_zonder_actor()
    assert not fouten, (
        "Elke snapshot hoort te zeggen wie de handeling deed. Is er niemand "
        "aangemeld, geef dan `actor=PUBLIEKE_ACTOR` mee — leeg betekent sinds #713 "
        "dat we het niet weten, en dat is een fout:\n  " + "\n  ".join(fouten))


# ── 2. De publieke weg markeert zichzelf ───────────────────────────────────

def test_een_publieke_gezinsaanvraag_draagt_de_publieke_markering(client, db_session):
    from app.domains.mdm.api import MemberHistory

    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json={
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": "Publiek", "first_name": "Peter",
                     "email": "peter713@example.com", "mobile": "0470000000",
                     "date_of_birth": "1980-01-01", "gender_code": "M",
                     "relation_type": "HOOFDLID"}],
    })
    assert resp.status_code == 201, resp.text

    rijen = (db_session.query(MemberHistory)
             .filter(MemberHistory.action == "family_registered").all())
    assert rijen, "geen auditregel"
    assert all(r.actor == PUBLIEKE_ACTOR for r in rijen), (
        [r.actor for r in rijen])


def test_een_anonieme_inschrijving_draagt_de_publieke_markering(client, db_session):
    """De keerzijde die het issue vroeg: zonder haar slaagt "vul overal iets in" ook,
    en dan staat er een verzonnen naam in plaats van een eerlijke markering."""
    from app.domains.activities.api import RegistrationItemHistory
    from tests.conftest import seed_activity_with_product

    activity, comp, product = seed_activity_with_product(db_session, price="10.00")
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An", "contact_email": "an713@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}]})
    assert resp.status_code in (200, 201), resp.text

    rijen = (db_session.query(RegistrationItemHistory)
             .filter(RegistrationItemHistory.action == "order_created").all())
    assert rijen and all(r.actor == PUBLIEKE_ACTOR for r in rijen), (
        [r.actor for r in rijen])


# ── 3. De beheerdersweg tekent met een naam ────────────────────────────────

def test_nieuw_lid_via_het_beheerscherm_draagt_de_beheerder(client, db_session):
    """Dit was de duidelijkste van de vier: de actor was bekend en verdween."""
    from app.domains.mdm.api import MemberHistory, PersonHistory

    csrf = _login(client)
    resp = client.post("/admin/leden",
                       data={"first_name": "Nieuw", "last_name": "Lid",
                             "date_of_birth": "1980-01-01", "gender_code": "M"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204, resp.text[:300]

    for model, actie in ((MemberHistory, "member_created"),
                         (PersonHistory, "person_created")):
        rijen = db_session.query(model).filter(model.action == actie).all()
        assert rijen, f"geen auditregel voor {actie}"
        assert all(r.actor == SEEDED_ADMIN_EMAIL for r in rijen), (
            [r.actor for r in rijen])


def test_die_handeling_heet_geen_systeemactie_meer(client, db_session):
    """`source="system"` bij een beheerdersactie maakte het aan géén van beide velden
    herkenbaar. Een systeemactie is iets wat vanzelf gebeurt; dit niet."""
    from app.domains.mdm.api import MemberHistory

    csrf = _login(client)
    client.post("/admin/leden",
                data={"first_name": "Bron", "last_name": "Test",
                      "date_of_birth": "1980-01-01", "gender_code": "M"},
                headers={"X-CSRF-Token": csrf})

    rijen = (db_session.query(MemberHistory)
             .filter(MemberHistory.action == "member_created").all())
    assert rijen and all(r.source == "admin_manual" for r in rijen), (
        [r.source for r in rijen])

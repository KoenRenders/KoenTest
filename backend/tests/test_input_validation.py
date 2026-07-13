"""Input-validatie op vorm-niveau (#130): de publieke registratie weigert
ongeldige/onvolledige invoer met een nette 422 (niet 500). Geparametriseerd zodat
nieuwe randgevallen makkelijk bij te voegen zijn.

Demonstreert ook het gebruik van de factories in conftest (create_test_family).
"""
import pytest

from tests.conftest import seed_postal_code, create_test_family

_BASE = {"street": "Milostraat", "house_number": "40", "postal_code": "2400", "payment_method": "transfer"}
_HOOFDLID = {"last_name": "Lid", "first_name": "Jan", "email": "jan@example.com",
             "mobile": "0470000000", "relation_type": "HOOFDLID"}


@pytest.mark.parametrize("payload, reason", [
    ({**_BASE, "members": []}, "geen enkel gezinslid / geen hoofdlid"),
    ({**_BASE, "members": [{**_HOOFDLID, "relation_type": "KIND"}]}, "geen HOOFDLID-type"),
    ({**_BASE, "members": [{**_HOOFDLID, "email": None}]}, "hoofdlid zonder e-mail"),
    ({**_BASE, "members": [{**_HOOFDLID, "mobile": None}]}, "hoofdlid zonder mobiel"),
    ({**_BASE, "members": [{**_HOOFDLID, "email": "geen-geldig-adres"}]}, "ongeldig e-mailadres"),
    ({"house_number": "40", "postal_code": "2400", "payment_method": "transfer",
      "members": [_HOOFDLID]}, "verplichte straat ontbreekt"),
])
def test_family_registration_rejects_invalid_input(client, db_session, payload, reason):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=payload)
    assert resp.status_code == 422, f"{reason}: kreeg {resp.status_code} — {resp.text}"


def test_factory_create_test_family(db_session):
    """De gedeelde factory levert een bruikbaar gezin + hoofdlid op."""
    from app.domains.membership.api import has_valid_membership
    member, person = create_test_family(db_session, email="factory@example.com")
    assert member.id is not None and person.id is not None
    # Vers gezin zonder lidmaatschap → geen geldig lidmaatschap.
    assert has_valid_membership(person) is False

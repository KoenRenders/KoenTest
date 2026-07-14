"""#157 — gestructureerde mededeling (OGM) + overschrijvings-betaalinstructies.

Invarianten:
- OGM heeft geldig mod-97-controlegetal en het juiste +++DDD/DDDD/DDDDD+++-formaat;
- een overschrijving krijgt een UNIEKE OGM (reconciliatie); cash/online niet;
- de betaalmail bevat voor een overschrijving IBAN + OGM + bedrag (whitelist via
  config), en niets daarvan voor online.
"""
from decimal import Decimal

from app.domains.payment.structured_communication import generate_structured_communication
from app.domains.payment.api import create_payment_record
from app.domains.mail import service as email_mod


def _mod97_ok(ogm: str) -> bool:
    digits = ogm.replace("+", "").replace("/", "")
    assert len(digits) == 12
    base10 = int(digits[:10])
    check = int(digits[10:])
    return check == (base10 % 97 or 97)


def test_ogm_format_and_checkdigits():
    ogm = generate_structured_communication(12345)
    assert ogm.startswith("+++") and ogm.endswith("+++")
    assert ogm[3:6].isdigit() and ogm[6] == "/" and ogm[11] == "/"
    assert _mod97_ok(ogm)


def test_ogm_checkdigit_is_97_when_divisible():
    # 97 % 97 == 0 → controlegetal moet 97 worden, niet 00.
    ogm = generate_structured_communication(97)
    assert ogm.replace("+", "").replace("/", "")[-2:] == "97"
    assert _mod97_ok(ogm)


def test_transfer_payment_gets_unique_ogm(db_session):
    r1 = create_payment_record(db_session, "registration", 1, Decimal("10.00"), "transfer")
    r2 = create_payment_record(db_session, "registration", 2, Decimal("10.00"), "transfer")
    assert r1.structured_communication and r2.structured_communication
    assert r1.structured_communication != r2.structured_communication
    assert _mod97_ok(r1.structured_communication)


def test_cash_payment_has_no_ogm(db_session):
    r = create_payment_record(db_session, "membership", 1, Decimal("35.00"), "cash")
    assert r.structured_communication is None


def test_transfer_instructions_contain_iban_ogm_amount(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "payment_iban", "BE48 7875 5016 1327")
    monkeypatch.setattr(settings, "payment_beneficiary", "Raak Millegem")

    class FakeRecord:
        method = "transfer"
        structured_communication = "+++123/4567/89012+++"
        amount = Decimal("35.00")

    html = email_mod._transfer_instructions_html(FakeRecord())
    assert "BE48 7875 5016 1327" in html
    assert "+++123/4567/89012+++" in html
    assert "35.00" in html


def test_online_payment_has_no_instructions():
    class FakeRecord:
        method = "online"
        structured_communication = None
        amount = Decimal("35.00")

    assert email_mod._transfer_instructions_html(FakeRecord()) == ""

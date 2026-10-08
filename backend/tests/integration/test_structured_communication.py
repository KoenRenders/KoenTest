"""#157 — gestructureerde mededeling (OGM) + overschrijvings-betaalinstructies.

Invarianten:
- OGM heeft geldig mod-97-controlegetal en het juiste +++DDD/DDDD/DDDDD+++-formaat;
- een overschrijving krijgt een UNIEKE OGM (reconciliatie); cash/online niet;
- de betaalmail bevat voor een overschrijving IBAN + OGM + bedrag (whitelist via
  config), en niets daarvan voor online.
"""

from decimal import Decimal

from app.domains.mail import service as email_mod
from app.domains.payment.api import create_payment_record, transfer_due
from app.domains.payment.structured_communication import generate_structured_communication


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


def test_transfer_instructions_contain_iban_ogm_amount(monkeypatch, db_session):
    """On a real payment record, not on a stand-in: the stand-in carried the text
    "transfer" where a record carries the enum member, and so stayed green while
    the block was empty in every mail (#1775). Broken to see it red: the method
    compared with the text "transfer" again."""
    from app.config import settings

    monkeypatch.setattr(settings, "payment_iban", "BE68 5390 0754 7034")
    monkeypatch.setattr(settings, "payment_beneficiary", "Raak Millegem")

    record = create_payment_record(db_session, "membership", 1, Decimal("35.00"), "transfer")

    due = transfer_due(db_session, record, "Betaalinstructies (overschrijving)")
    html = email_mod._transfer_instructions_html(due)
    assert "<strong>IBAN:</strong> BE68 5390 0754 7034" in html
    assert "<strong>Begunstigde:</strong> Raak Millegem" in html
    assert f"<strong>Gestructureerde mededeling:</strong> {record.structured_communication}" in html
    assert "<strong>Bedrag:</strong> € 35,00" in html
    assert "<strong>Te betalen vóór:</strong>" in html


def test_a_payment_that_is_no_transfer_has_no_instructions(db_session):
    record = create_payment_record(db_session, "membership", 1, Decimal("35.00"), "cash")

    assert transfer_due(db_session, record, "x") is None
    assert transfer_due(db_session, None, "x") is None
    assert email_mod._transfer_instructions_html(None) == ""

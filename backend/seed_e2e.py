"""Deterministische minimale dataset voor de e2e-beheerflows (#644).

Waarom dit bestaat: de drie Playwright-flows voor de beheerschermen (betaling
bevestigen, bestelregel wijzigen, gezin) skipten in CI, want na `alembic upgrade
head` + `seed_postal_codes.py` staan er geen betalingen, inschrijvingen of
gezinnen in de e2e-databank. Een skip is tussen groene runs onzichtbaar; zolang
die drie skipten bewees de e2e-job niets over precies de schermen waar de dode
knoppen van #613/#616 zaten.

Wat het maakt (alles herkenbaar aan de marker hieronder):
  - een gezin met hoofdlid en een lidmaatschap voor het lopende jaar,
  - een activiteit met één onderdeel en één betalend product (€ 10),
  - een inschrijving van 2 stuks via het **echte** registratiepad, zodat het
    openstaande betaalrecord en de OGM ontstaan zoals in productie,
  - één extra, volledig betaald record (voor de terugbetaal- en editorknoppen),
  - een formulier in draft en een CMS-pagina.

Idempotent: draait het script een tweede keer, dan herkent het zijn eigen data
aan de marker en doet het niets.

VEILIGHEID: dit script weigert te draaien tenzij APP_ENV dev of test is **en**
E2E_SEED=1 in de omgeving staat. Deze data hoort nooit op HDEV, UAT of PROD.
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

MARKER_EMAIL = "e2e-seed@example.com"
SEED_NAAM = "E2E Seed"


def _weiger_buiten_dev() -> None:
    from app.config import settings

    omgeving = (getattr(settings, "app_env", "") or "").lower()
    if omgeving not in ("dev", "test"):
        sys.exit(f"seed_e2e: geweigerd, APP_ENV={omgeving!r} is geen dev/test-omgeving")
    if os.environ.get("E2E_SEED") != "1":
        sys.exit("seed_e2e: geweigerd, zet E2E_SEED=1 om deze data te maken")


def main() -> None:
    _weiger_buiten_dev()

    from app.database import SessionLocal
    from app.domains.registry import load_all_models

    load_all_models()

    from app.domains.activities.api import (
        Activity, ActivityDate, ActivityProduct, ActivitySubRegistration, Registration,
    )
    from app.domains.cms.api import CmsPage
    from app.domains.forms.api import Form
    from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person, PostalCode
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    db = SessionLocal()
    try:
        bestaat = (db.query(ContactDetail)
                   .filter(ContactDetail.value == MARKER_EMAIL).first())
        if bestaat is not None:
            print("seed_e2e: data staat er al (marker gevonden) — niets gedaan")
            return

        if db.query(PostalCode).filter(PostalCode.postal_code == "2400").first() is None:
            db.add(PostalCode(postal_code="2400", municipality="Mol"))
            db.flush()

        # ── Gezin met hoofdlid en een lopend lidmaatschap ────────────────────
        member = Member()
        db.add(member)
        db.flush()
        person = Person(first_name="E2E", last_name="Seed")
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id,
                            relation_type="HOOFDLID"))
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                             value=MARKER_EMAIL, is_primary=True))
        jaar = date.today().year
        membership = Membership(member_id=member.id, year=jaar, is_active=True,
                                valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31))
        db.add(membership)
        db.flush()
        # Een betaald lidgeld: zonder dat levert het schrappen van het lidmaatschap
        # geen terugbetaling op en zou de ledenflow niets te toetsen hebben (#619).
        db.add(PaymentRecord(
            payable_type="membership", payable_id=membership.id, type="charge",
            amount=Decimal("20.00"), amount_paid=Decimal("20.00"),
            method="transfer", status="paid",
            structured_communication="+++000/0000/00097+++"))
        db.flush()

        # ── Activiteit met een betalend product ─────────────────────────────
        activity = Activity(name="E2E-activiteit")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id,
                            start_date=date.today() + timedelta(days=30)))
        component = ActivitySubRegistration(
            activity_id=activity.id, name="E2E-onderdeel",
            registration_type_code="INDIVIDUAL", price=Decimal("0"), is_free=True,
            max_participants=None)
        db.add(component)
        db.flush()
        product = ActivityProduct(component_id=component.id, name="E2E-product",
                                  price=Decimal("10.00"), is_free=False)
        db.add(product)
        db.commit()

        # ── Inschrijving via het echte registratiepad ────────────────────────
        # Bewust niet met de hand een Registration + PaymentRecord bouwen: dan zou
        # de seed een eigen versie van de registratielogica worden en zou de OGM
        # er anders uitzien dan in productie. Dit is precies wat de flow test.
        from fastapi import BackgroundTasks

        from app.domains.activities.router import register_for_activity
        from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

        data = RegistrationCreate(
            contact_name=SEED_NAAM, contact_email=MARKER_EMAIL, phone="0470000000",
            component_id=component.id, payment_method="TRANSFER",
            items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
        )
        resultaat = register_for_activity(activity.id, data, BackgroundTasks(),
                                          db=db, current_member=None)
        reg_id = getattr(resultaat, "id", None) or (
            resultaat.get("id") if isinstance(resultaat, dict) else None)
        if reg_id is None:
            reg = (db.query(Registration)
                   .filter(Registration.contact_email == MARKER_EMAIL).first())
            reg_id = reg.id if reg else None

        # ── Eén volledig betaald record, voor de terugbetaal-/editorknoppen ──
        db.add(PaymentRecord(
            payable_type="registration", payable_id=reg_id, type="charge",
            amount=Decimal("20.00"), amount_paid=Decimal("20.00"),
            method="transfer", status="paid"))

        formulier = Form(title="E2E-formulier", share_token="tok-e2e-seed",
                         status="draft")
        pagina = CmsPage(title="E2E-pagina", slug="e2e-pagina", content="<p>e2e</p>")
        db.add_all([formulier, pagina])
        db.commit()

        print(f"seed_e2e: gezin={member.id} lidmaatschap={membership.id} "
              f"activiteit={activity.id} "
              f"onderdeel={component.id} product={product.id} "
              f"inschrijving={reg_id} formulier={formulier.id} pagina={pagina.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

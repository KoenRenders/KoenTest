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
  - een formulier in draft, een open formulier met velden en een CMS-pagina.

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
# #1183: een extra gezin voor de LEDENFLOW-afdrukken. Het seed-gezin hierboven heeft
# een lopend lidmaatschap en toont dus geen vernieuwknop — je kan geen knop
# fotograferen die er niet staat. Dit gezin staat er NÁÁST in plaats van dat het
# seed-gezin omgezet wordt: dat gezin wordt door de bestaande e2e's gebruikt en een
# gewijzigde lidmaatschapstoestand zou die raken.
#
# Een DERDE gezin met een lopende overschrijving stond hier ook, voor het scherm met
# de betaalinstructies. Weggehaald na meting: een openstaande betaling in de gedeelde
# seed is precies de rij die `test_beheer_flows` als eerste "Bevestig" oppikt. Die
# test zette hem dan op betaald — waarmee én het scherm verdween én die test iets
# anders toetste dan bedoeld. Zie de PR van #1183.
MARKER_EMAIL_VERLOPEN = "e2e-verlopen@example.com"
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
    from app.domains.forms.api import Form, FormField
    from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person, PostalCode
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    db = SessionLocal()
    try:
        # #1075: de Raakje-overlay op het activiteitenscherm bestaat alleen als de
        # beheer-assistent aan staat — twee schakelaars in serie (CR-07 §6.3). De
        # omgevingskant zet de e2e-job (`ADMIN_CHAT_ENABLED`); de tenantkant staat
        # hier, vóór de markercontrole, want een schakelaar is geen seed-data.
        from app.kernel.tenant_config import set_setting

        set_setting(db, "admin_chat_enabled", "1")
        db.commit()

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

        # ── Gezin met een VERLOPEN lidmaatschap (#1183) ─────────────────────
        # Toont de vernieuwknop: `membership_coverage_until` kijkt alleen naar een
        # `valid_to >= vandaag`, dus een lidmaatschap van vorig jaar levert geen
        # dekking op en `renewal_available` staat dan onvoorwaardelijk op True —
        # ook buiten het hernieuwingsvenster. Daarmee is de afdruk deterministisch
        # in plaats van afhankelijk van de datum waarop iemand hem maakt.
        vorig = date.today().year - 1
        verlopen_member = Member()
        db.add(verlopen_member)
        db.flush()
        verlopen_person = Person(first_name="E2E", last_name="Verlopen")
        db.add(verlopen_person)
        db.flush()
        db.add(MemberPerson(member_id=verlopen_member.id,
                            person_id=verlopen_person.id, relation_type="HOOFDLID"))
        db.add(ContactDetail(person_id=verlopen_person.id, contact_type_code="EMAIL",
                             value=MARKER_EMAIL_VERLOPEN, is_primary=True))
        db.add(Membership(member_id=verlopen_member.id, year=vorig, is_active=True,
                          valid_from=date(vorig, 1, 1), valid_to=date(vorig, 12, 31)))
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

        # ── Twee activiteitenfoto's ─────────────────────────────────────────
        # Zonder media rendert het mediascherm zijn activiteitenkeuzelijst NIET
        # (die toont alleen activiteiten die al media hebben), en dan is de
        # drukste stand van dat scherm onmeetbaar in e2e — precies de stand waar
        # de filterrij brak (#1138 punt 1).
        from app.domains.media.api import MediaAsset

        beeld = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        # Een TWEEDE activiteit met een lange naam (#1138 punt 1). De
        # keuzelijst op het mediascherm is zo breed als haar langste optie, dus
        # de titel bepaalt of de filterrij op één regel past. Gemeten op 21
        # september 2026, beheerscherm 1024 px breed bij een venster van 1440:
        # met "E2E-activiteit (2026)" was de rij 1024 van 1024 px — exact vol,
        # dus elke echte titel duwt haar naar een tweede regel. Met Koens eigen
        # "Gezinsuitstap Irrland (2026)" paste ze nog nét; dat is geen marge.
        # Deze naam is langer, zodat de test rood staat zonder de reparatie.
        #
        # De datum ligt een jaar vooruit, zodat deze activiteit achteraan de
        # komende-lijst staat en `Activiteitdetail.open_eerste()` nog steeds de
        # bestaande E2E-activiteit opent.
        lange = Activity(name="Gezinsuitstap naar Irrland met bus en picknick")
        db.add(lange)
        db.flush()
        db.add(ActivityDate(activity_id=lange.id,
                            start_date=date.today() + timedelta(days=365)))

        for doel in (activity, lange):
            db.add(MediaAsset(kind="activity_photo", activity_id=doel.id,
                              title=f"E2E-foto {doel.name}", data=beeld,
                              content_type="image/png", thumbnail=beeld,
                              thumb_content_type="image/png", width=64, height=64,
                              byte_size=len(beeld), sort_order=0, is_active=True))

        # ── Eén pagina-afbeelding (#1173) ───────────────────────────────────
        # Zonder haar staat de afbeeldingskiezer in de pagina-editor op zijn lege
        # toestand en toetst de e2e het invoegen niet — ze zou groen blijven
        # terwijl er niets te kiezen valt.
        #
        # Een ECHTE png en niet de `beeld`-stub hierboven: de test kijkt of de
        # browser de afbeelding werkelijk laadt (`naturalWidth`), en een stuk
        # bytes met een png-kop haalt dat niet.
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (240, 150), (240, 244, 250)).save(buf, format="PNG")
        echte_png = buf.getvalue()
        db.add(MediaAsset(kind="page_image",
                          title="E2E-schermafdruk aanmelden", data=echte_png,
                          content_type="image/png", thumbnail=echte_png,
                          thumb_content_type="image/png", width=240, height=150,
                          byte_size=len(echte_png), sort_order=0, is_active=True))
        db.commit()

        # ── Inschrijving via het echte registratiepad ────────────────────────
        # Bewust niet met de hand een Registration + PaymentRecord bouwen: dan zou
        # de seed een eigen versie van de registratielogica worden en zou de OGM
        # er anders uitzien dan in productie. Dit is precies wat de flow test.
        from fastapi import BackgroundTasks

        from app.domains.activities.router import register_for_activity
        from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

        def _schrijf_in(naam: str) -> int | None:
            data = RegistrationCreate(
                contact_name=naam, contact_email=MARKER_EMAIL, phone="0470000000",
                component_id=component.id, payment_method="transfer",
                items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
            )
            resultaat = register_for_activity(activity.id, data, BackgroundTasks(),
                                              db=db, current_member=None)
            gevonden = getattr(resultaat, "id", None) or (
                resultaat.get("id") if isinstance(resultaat, dict) else None)
            if gevonden is None:
                reg = (db.query(Registration)
                       .filter(Registration.contact_name == naam).first())
                gevonden = reg.id if reg else None
            return gevonden

        # Twee inschrijvingen, dus twee openstaande vorderingen. Anders vechten de
        # flows om dezelfde: "bevestig betaald" zet de enige pending charge op
        # betaald, waarna de volgende flow er geen meer vindt.
        reg_id = _schrijf_in(SEED_NAAM)
        tweede_id = _schrijf_in(f"{SEED_NAAM} 2")

        # ── Eén volledig betaald record, voor de terugbetaal-/editorknoppen ──
        # Ook dit record krijgt een mededeling: de kaarten staan op datum
        # gesorteerd, dus zonder OGM zou de bovenste kaart er geen hebben en zoekt
        # de e2e-flow tevergeefs naar er een.
        db.add(PaymentRecord(
            payable_type="registration", payable_id=reg_id, type="charge",
            amount=Decimal("20.00"), amount_paid=Decimal("20.00"),
            method="transfer", status="paid",
            structured_communication="+++000/0000/00098+++"))

        # De beheerder uit migratie 014 heeft ADMIN; de betaalacties staan onder
        # `is_finance` en vragen FINANCE (mutaties: FINANCE/OPERATOR). Zonder deze
        # rollen rendert het scherm wel de kaarten maar geen enkele knop, en dan
        # test de e2e-flow niets. Zelfde reden als in tests/test_render_gate.py.
        from app.domains.auth.api import User, UserRole

        beheerder = db.query(User).order_by(User.id).first()
        if beheerder is not None:
            bestaande = {r.role_code for r in beheerder.roles}
            for rol in ("FINANCE", "OPERATOR"):
                if rol not in bestaande:
                    db.add(UserRole(user_id=beheerder.id, role_code=rol))
            db.flush()

        formulier = Form(title="E2E-formulier", share_token="tok-e2e-seed",
                         status="draft")
        # Een OPEN formulier mét velden, zodat de publieke formulierpagina iets
        # te tonen heeft (#785 stap 0: het screenshotscript legt hem vast; de
        # draft hierboven geeft op zijn deellink een 403).
        open_formulier = Form(title="E2E-open-formulier", share_token="tok-e2e-open",
                              status="open")
        pagina = CmsPage(title="E2E-pagina", slug="e2e-pagina", content="<p>e2e</p>")
        db.add_all([formulier, open_formulier, pagina])
        db.flush()
        db.add_all([
            FormField(form_id=open_formulier.id, field_type="text",
                      label="Naam ploeg", required=True, position=0),
            FormField(form_id=open_formulier.id, field_type="textarea",
                      label="Opmerking", position=1),
            # Mét schaal-labels (Koens vraag op het clusterpakket): zonder
            # betekenen de cijfers niets — en de afdrukken tonen dan een
            # kaler scherm dan het product kan.
            FormField(form_id=open_formulier.id, field_type="rating",
                      label="Hoe graag kom je?", position=2, rating_max=5,
                      rating_low_label="niet graag",
                      rating_high_label="zeer graag"),
        ])
        db.commit()

        print(f"seed_e2e: gezin={member.id} lidmaatschap={membership.id} "
              f"activiteit={activity.id} "
              f"onderdeel={component.id} product={product.id} "
              f"inschrijving={reg_id} tweede-inschrijving={tweede_id} "
              f"formulier={formulier.id} open-formulier={open_formulier.id} "
              f"pagina={pagina.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

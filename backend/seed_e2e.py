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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domains.payment.structured_communication import (
    generate_structured_communication,
)

# #1208: de namen in deze seed zijn leesbaar, want ze staan op de
# schermafdrukken voor de PUBLIEKE uitlegpagina (#1183). "E2E Seed" en
# "e2e-seed@example.com" lazen daar als een foutmelding.
#
# Waarom verzonnen en niet een echt gezin: HDEV draagt echte ledenrecords, dus een
# afdruk van het gezinsscherm daar zet naam, adres en e-mailadres van een echt lid
# op een publieke pagina — een lek dat geen grep vindt, want het zit in een
# afbeelding. Daarom komen de beelden uit deze seed, en daarom moet ze leesbaar zijn.
#
# De familie Jommeke draagt het gezin met een LOPEND lidmaatschap: drie van de vijf
# ledenflow-afdrukken tonen dat gezin (`leden-gezin`, `leden-gezin-bewerken` en het
# aanmeldscherm met zijn adres). `example.com` is het enige domein dat hier mag.
MARKER_EMAIL = "theofiel.jommeke@example.com"
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
#
# Een andere naam uit hetzelfde verhaal (#1208), zodat de twee gezinnen op een
# afdruk uit elkaar te houden zijn: dit is het gezin op `leden-verlengen`.
MARKER_EMAIL_VERLOPEN = "professor.gobelijn@example.com"
SEED_NAAM = "Theofiel Jommeke"
# De achternamen die deze seed maakt (#1208). `test_ledenflow_schermen` leest ze
# hier en houdt geen eigen lijst: die test bewaakt dat er geen echte ledennaam op
# een publieke afdruk staat, en een tweede kopie van deze namen zou na de
# volgende hernoeming stil groen blijven staan terwijl ze niets meer toetst.
# #1241: twee gezinnen erbij voor de verlengflow, elk voor één toestand die een
# ander gezin niet kán tonen. Eigen gezinnen en geen gedeelde toestand — zie de
# toelichting bij die blokken verderop; het is dezelfde reden waarom het gezin met
# het verlopen lidmaatschap er destijds apart bij kwam.
MARKER_EMAIL_VERNIEUWD = "filiberke.kwak@example.com"
MARKER_EMAIL_OVERSCHRIJVING = "anatool.boemel@example.com"
SEED_ACHTERNAMEN = ("Jommeke", "Gobelijn", "Kwak", "Boemel")

# #1241: het rekeningnummer op de afdruk van de overschrijving.
#
# LAAT HET CONTROLEGETAL `00` STAAN — het is geen tikfout en het hoort niet
# "gerepareerd" te worden. Een IBAN draagt na de landcode twee controlecijfers die
# per ISO 7064 mod-97-10 tussen 02 en 98 liggen; `00` is dus aantoonbaar van
# niemand. Dat is precies wat we willen op een beeld dat naar een publieke pagina
# gaat: het rendert als een echt rekeningnummer — juiste lengte, juiste groepering,
# dus een lid ziet wáár het nummer staat — zonder dat we een getal publiceren dat
# later iemands rekening blijkt te zijn.
# De twee mededelingen van de verlenggezinnen. Hier en niet in de test: een tweede
# kopie in `test_verlengflow_schermen` zou na een gewijzigd basisnummer stil groen
# blijven staan terwijl ze een rij toetst die niet meer bestaat.
VERNIEUWD_OGM = generate_structured_communication(303)
OVERSCHRIJVING_OGM = generate_structured_communication(404)
SEED_IBAN = "BE00 1234 5678 9012"
SEED_BEGUNSTIGDE = "Raak Millegem"

# #1238 punt 3: de gegevens van het voorbeeldgezin, alle vier verzonnen of uit de
# strip. Deze repo is publiek, dus een echt gsm-nummer of een echt adres hoort er
# niet in; een striphuis en een nummer van enkel nullen kunnen van niemand zijn.
#
# 30 oktober 1955 is de dag waarop Jommeke voor het eerst verscheen (Koen,
# 27 september 2026): een knipoog die niemand stoort en die het voorbeeldgezin
# consistent houdt met zijn bron.
JOMMEKE_GEBOORTE = date(1955, 10, 30)
JOMMEKE_STRAAT = "Hemelstraat"
JOMMEKE_HUISNUMMER = "12"
PARTNER_EMAIL = "marie.jommeke@example.com"
HOOFDLID_GSM = "0470 00 00 01"
PARTNER_GSM = "0470 00 00 02"

# #1238 punt 4: de voettekst van de afdrukomgeving. Zonder deze regels staat op elk
# beeld de zaai-inhoud van migratie 027 — «Naam van de vereniging» · «straat en
# nummer», «postcode en gemeente» — en dat leest op een uitlegpagina als een
# onafgewerkte site. De waarden zijn verzonnen op één na: de vereniging heet zoals ze
# heet, en Millegem is een gehucht van Mol, dus 2400 Mol klopt met het gezin
# hierboven. Het adres en het e-mailadres zijn dat NIET; een echt adres van de
# vereniging hoort niet in een publieke repo, en `example.com` is het domein dat
# daarvoor bestaat.
#
# Bewust GEEN rekeningnummer: de placeholder van 027 draagt er een, maar een
# verzonnen IBAN die er echt uitziet is precies het soort getal dat later iemands
# rekening blijkt te zijn. Wat op deze beelden niets doet, zaaien we niet.
VOETTEKST_HTML = "<p>Raak Millegem · Dorpsstraat 1, 2400 Mol</p><p>\U0001f4e7 info@example.com</p>"


def _adres(db, Address, person_id: int, postal_code_id: int) -> None:
    """Eén adres voor elk gezinslid (#1238 punt 3).

    Elk lid krijgt zijn EIGEN rij en niet één rij voor het gezin: zo modelleert
    `mdm.addresses` het (één adres per persoon, partieel uniek op `person_id`), en het
    gezinsscherm leest het per lid. Zonder rij vallen de leesweergave én het
    bewerkformulier weg — beide hangen aan dezelfde `{% if p.address %}`, en dat is
    waarom het op de afdrukken geen UI-gat was maar ontbrekende data.
    """
    db.add(
        Address(
            person_id=person_id,
            street=JOMMEKE_STRAAT,
            house_number=JOMMEKE_HUISNUMMER,
            postal_code_id=postal_code_id,
        )
    )


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
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        Registration,
    )
    from app.domains.cms.api import CmsPage
    from app.domains.forms.api import Form, FormField
    from app.domains.mdm.api import (
        Address,
        ContactDetail,
        Member,
        MemberPerson,
        Person,
        PostalCode,
    )
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
        # #1238 punt 5, gevonden door Koen: het gezinsscherm toonde op de afdrukken een
        # andere toestand dan de echte site. De vernieuwknop hangt aan
        # `renewal_available()`, en die vraagt bij een gedekt lid of het campagnevenster
        # open is — `membership_renewal_start_md`, waar leeg "dicht" betekent. Op de
        # tenant van de echte site staat er een datum, in de afdrukomgeving stond niets,
        # dus net het blok waar een uitlegpagina over verlengen om gaat ontbrak.
        #
        # `01-01` en niet de datum van de echte site: het venster opent op
        # `today >= date(today.year, maand, dag)`, dus elke andere datum laat de knop
        # een deel van het jaar weer verdwijnen — met `09-17` zou de reeks van januari
        # tot half september opnieuw het verkeerde scherm fotograferen. Een afdruk mag
        # niet van de dag afhangen waarop iemand hem maakt.
        set_setting(db, "membership_renewal_start_md", "01-01")
        # #1241: een rekening voor de organisatie van deze omgeving. Zonder haar toont
        # de afdruk van de overschrijving geen rekeningnummer en geen begunstigde: die
        # twee komen sinds migratie 119 uit de organisatie-entiteit (`bank_accounts`)
        # met de .env als vangnet, en de afdrukomgeving heeft geen van beide — de
        # sjabloon verbergt een lege waarde, dus het beeld zou juist het nummer missen
        # dat het moet aanwijzen.
        from app.domains.mdm.api import BankAccount
        from app.kernel.tenancy import DEFAULT_TENANT_ID

        if (
            db.query(BankAccount).filter(BankAccount.organization_id == DEFAULT_TENANT_ID).first()
            is None
        ):
            db.add(
                BankAccount(
                    organization_id=DEFAULT_TENANT_ID,
                    iban=SEED_IBAN,
                    beneficiary=SEED_BEGUNSTIGDE,
                    sort_order=0,
                )
            )
        # #1238 punt 4: de voettekst. Vóór de markercontrole, zodat een tweede run op
        # een bestaande databank haar ook herstelt — dit is inhoud van de OMGEVING en
        # geen rij van het voorbeeldgezin.
        from app.domains.cms.api import CmsPage as _CmsPage

        voet = db.query(_CmsPage).filter(_CmsPage.slug == "site-footer").first()
        if voet is not None:
            voet.content = VOETTEKST_HTML
        db.commit()

        vandaag = date.today()
        # CR-19 (#1478, Q1): a company tenant next to the association, so the
        # e2e flows and the screenshot set see a reduced module set. Made the
        # way an operator makes one, so it gets its modules and site blocks.
        # Before the marker check: it is idempotent itself, and an environment
        # seeded before it must get it too.
        # The CMS hears `TenantCreated` and seeds the site blocks — but only when
        # its handler is registered, which `app.main` does and a script does not.
        import app.domains.cms.handlers  # noqa: F401 — the TenantCreated subscriber
        import app.domains.forms.handlers  # noqa: F401 — and its contact form (#1509)
        import app.domains.workflow.handlers  # noqa: F401 — and the task it starts (#1509)
        from app.domains.mdm.api import TenantKind, create_tenant, tenant_codes

        if "voorbeeldbedrijf" not in tenant_codes(db):
            create_tenant(
                db, name="Voorbeeldbedrijf", code="voorbeeldbedrijf", kind=TenantKind.COMPANY
            )

        # CR-21 (#1887): a tenant of its own with the shop on, for the browser
        # test of the refused delete. The module set is cached in the server
        # process, so a row written by the test is not seen — it must be seeded.
        # The association's tenant stays untouched. Reached by its hostname
        # (`TENANT_HOSTNAMES` in `tests_e2e/e2e.env`), because back-office screens
        # are not reached by a path prefix (`path_for` never prefixes `/admin`).
        from app.domains.mdm.api import set_modules
        from app.kernel.modules import DEFAULTS
        from app.kernel.modules import M as _M
        from app.kernel.tenancy import current_tenant_id

        if "webshop" not in tenant_codes(db):
            webshop = create_tenant(db, name="Webshop", code="webshop", kind=TenantKind.ASSOCIATION)
            set_modules(db, webshop.id, DEFAULTS["VERENIGING"] | {_M.SHOP})
        webshop_id = tenant_codes(db)["webshop"]

        token = current_tenant_id.set(webshop_id)
        try:
            from app.domains.product.models import Product, ProductStatus, ProductVariant
            from app.domains.stock.api import receive

            if db.query(Product).filter(Product.name == "Webshop T-shirt").first() is None:
                artikel = Product(name="Webshop T-shirt", status=ProductStatus.ON_SALE)
                db.add(artikel)
                db.flush()
                maat = ProductVariant(
                    product_id=artikel.id, properties=[{"name": "Maat", "value": "M"}]
                )
                db.add(maat)
                db.flush()
                receive(db, maat.id, quantity=5)
        finally:
            current_tenant_id.reset(token)

        bestaat = db.query(ContactDetail).filter(ContactDetail.value == MARKER_EMAIL).first()
        if bestaat is not None:
            print("seed_e2e: data staat er al (marker gevonden) — niets gedaan")
            return

        # #1238 punt 3: het voorbeeldgezin woont op Hemelstraat 12, 2400 Mol — waar
        # Jommeke in de strip woont, en Millegem is een gehucht van Mol, dus het adres
        # past bij de vereniging zonder van iemand te zijn. De postcode moet uit DEZE
        # tabel komen: het postcodeveld in het gezinsformulier is een keuzelijst die
        # hieruit gevuld wordt, dus een adres met een postcode die er niet in staat is
        # op het scherm niet te kiezen (`docs/postal_codes_seed.csv` regel 109 draagt
        # 2400 Mol, en die lijst is de bron).
        postcode = db.query(PostalCode).filter(PostalCode.postal_code == "2400").first()
        if postcode is None:
            postcode = PostalCode(postal_code="2400", municipality="Mol")
            db.add(postcode)
            db.flush()

        # ── Gezin met hoofdlid en een lopend lidmaatschap ────────────────────
        member = Member()
        db.add(member)
        db.flush()
        person = Person(
            first_name="Theofiel",
            last_name="Jommeke",
            date_of_birth=JOMMEKE_GEBOORTE,
            gender_code="M",
        )
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
        # #1208: een gezin en niet één persoon. Het gezinsscherm is de afdruk waarop
        # een lid ziet hoe zijn gegevens erbij staan; met één rij toont hij niet wat
        # het scherm doet. Partner en kinderen erbij maken die afdruk bruikbaar.
        #
        # Waarom Annemieke en Rozemieke en niet "Jommeke Jommeke" als kind: dat
        # laatste oogt als een invoerfout, en een invoerfout is precies waar dit
        # issue vanaf wil. De tweeling is even herkenbaar en leest als twee gewone
        # namen. Jommeke zelf ontbreekt dus in de familie Jommeke; dat is de prijs
        # en ze is kleiner dan een naam die twee keer hetzelfde zegt.
        #
        # #1238 punt 3: geboortedatum en geslacht horen er BIJ. Op de afdrukken
        # stonden die velden leeg mét een sterretje, en een half ingevuld formulier is
        # precies het tegenovergestelde van wat een uitlegpagina wil tonen.
        #
        # De verdeling van de CONTACTGEGEVENS is die van Koen (27 september 2026): de
        # ouders dragen e-mail en gsm, de meerderjarige kinderen niet. Dat is geen
        # luiheid maar het geval dat een lezer herkent — en het scherm toont zo ook
        # hoe een gezinslid zónder eigen contactgegevens eruitziet, wat op die pagina
        # even nuttig is.
        kinderen_geboorte = (date(vandaag.year - 22, 6, 15), date(vandaag.year - 20, 3, 9))
        for voornaam, relatie, geboorte, geslacht in (
            ("Marie", "PARTNER", JOMMEKE_GEBOORTE, "F"),
            ("Annemieke", "KIND", kinderen_geboorte[0], "F"),
            ("Rozemieke", "KIND", kinderen_geboorte[1], "F"),
        ):
            gezinslid = Person(
                first_name=voornaam,
                last_name="Jommeke",
                date_of_birth=geboorte,
                gender_code=geslacht,
            )
            db.add(gezinslid)
            db.flush()
            db.add(MemberPerson(member_id=member.id, person_id=gezinslid.id, relation_type=relatie))
            _adres(db, Address, gezinslid.id, postcode.id)
            if relatie == "PARTNER":
                db.add(
                    ContactDetail(
                        person_id=gezinslid.id,
                        contact_type_code="EMAIL",
                        value=PARTNER_EMAIL,
                        is_primary=True,
                    )
                )
                db.add(
                    ContactDetail(
                        person_id=gezinslid.id,
                        contact_type_code="MOBILE",
                        value=PARTNER_GSM,
                        is_primary=True,
                    )
                )
        _adres(db, Address, person.id, postcode.id)
        db.add(
            ContactDetail(
                person_id=person.id, contact_type_code="EMAIL", value=MARKER_EMAIL, is_primary=True
            )
        )
        db.add(
            ContactDetail(
                person_id=person.id, contact_type_code="MOBILE", value=HOOFDLID_GSM, is_primary=True
            )
        )
        jaar = vandaag.year
        membership = Membership(
            member_id=member.id,
            year=jaar,
            is_active=True,
            valid_from=date(jaar, 1, 1),
            valid_to=date(jaar, 12, 31),
        )
        db.add(membership)
        db.flush()
        # Een betaald lidgeld: zonder dat levert het schrappen van het lidmaatschap
        # geen terugbetaling op en zou de ledenflow niets te toetsen hebben (#619).
        db.add(
            PaymentRecord(
                payable_type="membership",
                payable_id=membership.id,
                type="charge",
                amount=Decimal("20.00"),
                amount_paid=Decimal("20.00"),
                method="transfer",
                status="paid",
                structured_communication="+++000/0000/00097+++",
            )
        )
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
        # A birth date and a gender like every other household member (#681): since
        # CR-13 phase 3 the household link refuses a member without them.
        verlopen_person = Person(
            first_name="Professor",
            last_name="Gobelijn",
            date_of_birth=date(1950, 3, 14),
            gender_code="M",
        )
        db.add(verlopen_person)
        db.flush()
        db.add(
            MemberPerson(
                member_id=verlopen_member.id, person_id=verlopen_person.id, relation_type="HOOFDLID"
            )
        )
        db.add(
            ContactDetail(
                person_id=verlopen_person.id,
                contact_type_code="EMAIL",
                value=MARKER_EMAIL_VERLOPEN,
                is_primary=True,
            )
        )
        db.add(
            Membership(
                member_id=verlopen_member.id,
                year=vorig,
                is_active=True,
                valid_from=date(vorig, 1, 1),
                valid_to=date(vorig, 12, 31),
            )
        )
        db.flush()

        # ── Gezin dat ONLINE VERNIEUWD heeft (#1241, afdruk 2) ──────────────
        # Wat een lid ziet nadat de betaling gelukt is: de dekking loopt door tot eind
        # volgend jaar en het vernieuwblok is wég. Dat laatste is geen toeval maar de
        # regel uit #496 — `renewal_available()` verbergt de knop zodra de dekking het
        # volgende jaar bereikt, zodat een tweede poging niet op een 409 "al vernieuwd"
        # botst.
        #
        # Geseed en niet door Mollie gedraaid: Mollie is vanuit een lokale
        # afdrukomgeving niet bereikbaar en er is geen mock-provider. Dat is hier geen
        # tekortkoming, want wat een lid ná de betaling ziet ís gewoon zijn
        # gezinsscherm met een langere dekking — een eindtoestand, exact te seeden.
        volgend = vandaag.year + 1
        vernieuwd_member = Member()
        db.add(vernieuwd_member)
        db.flush()
        vernieuwd_person = Person(
            first_name="Filiberke",
            last_name="Kwak",
            date_of_birth=date(vandaag.year - 30, 5, 4),
            gender_code="M",
        )
        db.add(vernieuwd_person)
        db.flush()
        db.add(
            MemberPerson(
                member_id=vernieuwd_member.id,
                person_id=vernieuwd_person.id,
                relation_type="HOOFDLID",
            )
        )
        db.add(
            ContactDetail(
                person_id=vernieuwd_person.id,
                contact_type_code="EMAIL",
                value=MARKER_EMAIL_VERNIEUWD,
                is_primary=True,
            )
        )
        _adres(db, Address, vernieuwd_person.id, postcode.id)
        # Twee lidmaatschappen, zoals een echt vernieuwd gezin ze heeft: het lopende
        # jaar en het jaar dat net betaald is.
        db.add(
            Membership(
                member_id=vernieuwd_member.id,
                year=jaar,
                is_active=True,
                valid_from=date(jaar, 1, 1),
                valid_to=date(jaar, 12, 31),
            )
        )
        vernieuwing = Membership(
            member_id=vernieuwd_member.id,
            year=volgend,
            is_active=True,
            valid_from=date(volgend, 1, 1),
            valid_to=date(volgend, 12, 31),
        )
        db.add(vernieuwing)
        db.flush()
        db.add(
            PaymentRecord(
                payable_type="membership",
                payable_id=vernieuwing.id,
                type="charge",
                amount=Decimal("20.00"),
                amount_paid=Decimal("20.00"),
                method="online",
                status="paid",
                structured_communication=VERNIEUWD_OGM,
            )
        )
        db.flush()

        # ── Gezin met een LOPENDE OVERSCHRIJVING (#1241, afdruk 3) ───────────
        # De betaalinstructies (bedrag, IBAN, begunstigde, mededeling) verschijnen
        # alleen bij een vernieuwing die al loopt: `open_renewal_payment` zoekt een
        # membership-betaling van dit gezin die niet betaald, geannuleerd of mislukt
        # is, en `_lopende_vernieuwing` toont dan `renew_transfer`.
        #
        # EIGEN GEZIN, en dat is de kern van dit issue. Zo'n openstaande betaling aan
        # het gedeelde seed-gezin hangen is precies wat #1183 al gemeten heeft: het is
        # de rij die `test_beheer_flows` als eerste "Bevestig" oppikt, en die test zette
        # hem dan op betaald — waarmee én deze afdruk verdween én die test iets anders
        # toetste dan zijn naam belooft.
        #
        # `created_at` een maand terug, en de reden is preciezer dan ze lijkt. Het
        # betalingenscherm sorteert `created_at.desc()` (payment/service.py), dus de
        # JONGSTE rij komt bovenaan en wordt de eerste "Bevestig"-rij.
        #
        # Gemeten, en het verraste me: ZONDER deze regel staat die rij er ook niet
        # vooraan — de inschrijvingsbetalingen ontstaan verderop in dit bestand en zijn
        # dus jonger. De bescherming zou dan uit de VOLGORDE VAN DE BLOKKEN hier komen,
        # en die verschuift zodra iemand dit bestand herschikt, zonder dat er iets
        # zichtbaar breekt. Met een expliciete datum hangt ze er niet meer van af.
        #
        # Een openstaande overschrijving die al even loopt is bovendien het
        # realistische geval. `test_verlengflow_schermen` bewaakt de uitkomst: gezet op
        # morgen komt deze rij wél vooraan en valt die test om.
        overschrijving_member = Member()
        db.add(overschrijving_member)
        db.flush()
        overschrijving_person = Person(
            first_name="Anatool",
            last_name="Boemel",
            date_of_birth=date(vandaag.year - 45, 11, 21),
            gender_code="M",
        )
        db.add(overschrijving_person)
        db.flush()
        db.add(
            MemberPerson(
                member_id=overschrijving_member.id,
                person_id=overschrijving_person.id,
                relation_type="HOOFDLID",
            )
        )
        db.add(
            ContactDetail(
                person_id=overschrijving_person.id,
                contact_type_code="EMAIL",
                value=MARKER_EMAIL_OVERSCHRIJVING,
                is_primary=True,
            )
        )
        _adres(db, Address, overschrijving_person.id, postcode.id)
        db.add(
            Membership(
                member_id=overschrijving_member.id,
                year=jaar,
                is_active=True,
                valid_from=date(jaar, 1, 1),
                valid_to=date(jaar, 12, 31),
            )
        )
        # Het lidmaatschap van de LOPENDE vernieuwing staat nog op niet-actief; zo
        # maakt de vernieuwroute het ook aan, en pas de betaling activeert het.
        loopt = Membership(
            member_id=overschrijving_member.id,
            year=volgend,
            is_active=False,
            valid_from=date(volgend, 1, 1),
            valid_to=date(volgend, 12, 31),
        )
        db.add(loopt)
        db.flush()
        db.add(
            PaymentRecord(
                payable_type="membership",
                payable_id=loopt.id,
                type="charge",
                amount=Decimal("20.00"),
                method="transfer",
                status="pending",
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
                structured_communication=OVERSCHRIJVING_OGM,
            )
        )
        db.flush()

        # ── Activiteit met een betalend product ─────────────────────────────
        activity = Activity(name="E2E-activiteit")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=30)))
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name="E2E-onderdeel",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
            max_participants=None,
        )
        db.add(component)
        db.flush()
        product = ActivityProduct(
            component_id=component.id, name="E2E-product", price=Decimal("10.00"), is_free=False
        )
        db.add(product)

        # ── Twee activiteitenfoto's ─────────────────────────────────────────
        # Zonder media rendert het mediascherm zijn activiteitenkeuzelijst NIET
        # (die toont alleen activiteiten die al media hebben), en dan is de
        # drukste stand van dat scherm onmeetbaar in e2e — precies de stand waar
        # de filterrij brak (#1138 punt 1).
        from app.domains.media.api import MediaAsset

        beeld = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

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
        db.add(ActivityDate(activity_id=lange.id, start_date=date.today() + timedelta(days=365)))

        for doel in (activity, lange):
            db.add(
                MediaAsset(
                    kind="activity_photo",
                    activity_id=doel.id,
                    title=f"E2E-foto {doel.name}",
                    data=beeld,
                    content_type="image/png",
                    thumbnail=beeld,
                    thumb_content_type="image/png",
                    width=64,
                    height=64,
                    byte_size=len(beeld),
                    sort_order=0,
                    is_active=True,
                )
            )

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
        db.add(
            MediaAsset(
                kind="page_image",
                title="E2E-schermafdruk aanmelden",
                data=echte_png,
                content_type="image/png",
                thumbnail=echte_png,
                thumb_content_type="image/png",
                width=240,
                height=150,
                byte_size=len(echte_png),
                sort_order=0,
                is_active=True,
            )
        )
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
                contact_name=naam,
                contact_email=MARKER_EMAIL,
                phone="0470000000",
                component_id=component.id,
                payment_method="transfer",
                items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
            )
            resultaat = register_for_activity(
                activity.id, data, BackgroundTasks(), db=db, current_member=None
            )
            gevonden = getattr(resultaat, "id", None) or (
                resultaat.get("id") if isinstance(resultaat, dict) else None
            )
            if gevonden is None:
                reg = db.query(Registration).filter(Registration.contact_name == naam).first()
                gevonden = reg.id if reg else None
            return gevonden

        # Twee inschrijvingen, dus twee openstaande vorderingen. Anders vechten de
        # flows om dezelfde: "bevestig betaald" zet de enige pending charge op
        # betaald, waarna de volgende flow er geen meer vindt.
        reg_id = _schrijf_in(SEED_NAAM)
        # #1208: een tweede naam uit hetzelfde gezin en niet "<naam> 2" — die
        # telling stond op de afdrukken van het betalingenscherm.
        tweede_id = _schrijf_in("Marie Jommeke")

        # ── Eén volledig betaald record, voor de terugbetaal-/editorknoppen ──
        # Ook dit record krijgt een mededeling: de kaarten staan op datum
        # gesorteerd, dus zonder OGM zou de bovenste kaart er geen hebben en zoekt
        # de e2e-flow tevergeefs naar er een.
        db.add(
            PaymentRecord(
                payable_type="registration",
                payable_id=reg_id,
                type="charge",
                amount=Decimal("20.00"),
                amount_paid=Decimal("20.00"),
                method="transfer",
                status="paid",
                structured_communication="+++000/0000/00098+++",
            )
        )

        # De beheerder uit migratie 014 heeft ADMIN; de betaalacties staan onder
        # `is_finance` en vragen FINANCE (mutaties: FINANCE/OPERATOR). Zonder deze
        # rollen rendert het scherm wel de kaarten maar geen enkele knop, en dan
        # test de e2e-flow niets. Zelfde reden als in tests/test_render_gate.py.
        from app.domains.auth.api import User, UserRole

        beheerder = db.query(User).order_by(User.id).first()
        if beheerder is not None:
            # `.value`: since CR-12 phase 2 the column carries a `Role` member
            # and the caller passes codes. Without this step the comparison is
            # always false and the seed grants the same role twice, which the
            # unique index rightly refuses.
            bestaande = {r.role_code.value for r in beheerder.roles}
            for rol in ("FINANCE", "OPERATOR"):
                if rol not in bestaande:
                    db.add(UserRole(user_id=beheerder.id, role_code=rol))
            db.flush()

        formulier = Form(title="E2E-formulier", share_token="tok-e2e-seed", status="draft")
        # Een OPEN formulier mét velden, zodat de publieke formulierpagina iets
        # te tonen heeft (#785 stap 0: het screenshotscript legt hem vast; de
        # draft hierboven geeft op zijn deellink een 403).
        open_formulier = Form(title="E2E-open-formulier", share_token="tok-e2e-open", status="open")
        pagina = CmsPage(title="E2E-pagina", slug="e2e-pagina", content="<p>e2e</p>")
        db.add_all([formulier, open_formulier, pagina])
        db.flush()
        db.add_all(
            [
                FormField(
                    form_id=open_formulier.id,
                    field_type="text",
                    label="Naam ploeg",
                    required=True,
                    position=0,
                ),
                FormField(
                    form_id=open_formulier.id, field_type="textarea", label="Opmerking", position=1
                ),
                # Mét schaal-labels (Koens vraag op het clusterpakket): zonder
                # betekenen de cijfers niets — en de afdrukken tonen dan een
                # kaler scherm dan het product kan.
                FormField(
                    form_id=open_formulier.id,
                    field_type="rating",
                    label="Hoe graag kom je?",
                    position=2,
                    rating_max=5,
                    rating_low_label="niet graag",
                    rating_high_label="zeer graag",
                ),
            ]
        )
        db.commit()

        print(
            f"seed_e2e: gezin={member.id} lidmaatschap={membership.id} "
            f"activiteit={activity.id} "
            f"onderdeel={component.id} product={product.id} "
            f"inschrijving={reg_id} tweede-inschrijving={tweede_id} "
            f"formulier={formulier.id} open-formulier={open_formulier.id} "
            f"pagina={pagina.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

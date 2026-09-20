"""De uiterste inschrijfdatum hoort bij het ONDERDEEL (#1053, #1051, #1054).

Koens geval: bij *Brood en Spelen* sluit de inschrijving voor de BBQ een week vóór
de dag zelf, terwijl cornhole en sjoelbak tot en met die dag openblijven. Met één
datum op de activiteit kan dat niet: de vroegste datum sluit alles.

**Golf 12 (#913) landde tussendoor op master** met een publieke activiteitspagina
die dezelfde klokregel toont. Die pagina rekende haar datum en haar urgentie zelf
uit omdat de kolom toen nog op de activiteit stond; sinds #1053 leest ze dezelfde
velden van het view-model als de kaart. Eén bron, dus geen twee plekken die
beslissen wat "de laatste week" is.

**De poort is de kern, de rest is weergave.** Toets 1 hieronder is het hele issue:
twee onderdelen, verschillende datums, "vandaag" ertussenin. De schermtests
daaronder tonen de gevolgen op de publieke kaart (#1051) en leggen vast dat de
omschrijving eraf is (#1054).

Kapotgemaakt om te controleren dat deze tests rood kunnen worden. Zes ingrepen,
elk één keer gedraaid; tussen haakjes wat er werkelijk omviel:

- de poort de vroegste datum van de ACTIVITEIT laten lezen, zoals vóór #1053
  (*het ene onderdeel sluit* én *zonder datum blijft open*);
- `card_deadline` de vroegste datum laten geven in plaats van None bij verschil
  (*verschillende datums*) — dan staat er tóch één regel bovenaan, en die liegt
  over het andere onderdeel;
- de regel terug naast de inschrijfknop, per onderdeel, zoals vóór #1051
  (*één icoonregel* én *drie onderdelen, één regel*);
- `not is_full` uit `card_deadline` (*volzet telt niet mee*);
- `deadline_is_near` altijd waar (*oranje in de laatste week* — de tegenhanger in
  diezelfde test is wat dat vangt);
- de kopieerstap van de migratie leegmaken (*de migratie kopieert*);
- het omschrijvingsblok terug in de partial (*niet meer op de kaart*, beide
  paden, én *ook niet in het archief*);
- de `not a.shared_deadline`-voorwaarde uit de activiteitspagina (*de
  activiteitspagina volgt dezelfde twee takken*) — dan staat de datum er twee keer.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.activities.api import (Activity, ActivityDate, ActivityProduct,
                                        ActivitySubRegistration, Registration)

pytestmark = pytest.mark.ui_serverrendered

VANDAAG = date(2027, 5, 10)
VROEG = date(2027, 5, 3)      # voorbij op VANDAAG
LAAT = date(2027, 5, 20)      # nog open op VANDAAG


@pytest.fixture
def vandaag(monkeypatch):
    """Pin de Belgische dag; de poort leest `belgian_today()`."""
    import app.kernel.clock as clock

    monkeypatch.setattr(clock, "belgian_today", lambda: VANDAAG)
    return VANDAAG


def _activiteit(db, naam="Brood en Spelen", *, omschrijving=None):
    a = Activity(name=naam, location="Miloheem", description=omschrijving)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=VANDAAG + timedelta(days=30)))
    db.flush()
    return a


def _onderdeel(db, a, naam, *, deadline=None, max_deelnemers=None):
    comp = ActivitySubRegistration(
        activity_id=a.id, name=naam, registration_type_code="INDIVIDUAL",
        registration_closes_on=deadline, max_participants=max_deelnemers,
        price=Decimal("0"), is_free=True)
    db.add(comp)
    db.flush()
    product = ActivityProduct(component_id=comp.id, name="Plaats",
                              price=Decimal("0"), is_free=True)
    db.add(product)
    db.flush()
    return comp, product


def _inschrijven(client, a, comp, product, naam="Fee"):
    return client.post(f"/activiteiten/{a.id}/inschrijven/{comp.id}",
                       data={"contact_name": naam,
                             "contact_email": f"{naam.lower()}@example.org",
                             "phone": "0470000000", f"product_{product.id}": "1"})


def _kaart(client, a, pad="/activiteiten") -> str:
    html = client.get(pad).text
    start = html.index(a.name)
    return html[start:start + 8000]


# ── De poort ─────────────────────────────────────────────────────────────────

def test_het_ene_onderdeel_sluit_en_het_andere_niet(client, db_session, vandaag):
    """Dit is het issue in één test (#1053).

    BBQ sloot op 3 mei, cornhole sluit pas op 20 mei, en vandaag is 10 mei. De
    BBQ weigert met ZIJN datum in de melding, cornhole aanvaardt gewoon.

    Kapotgemaakt: `registration_state` het `component`-argument laten negeren (de
    vorm van vóór #1053, die de activiteit leest) → de tweede inschrijving wordt
    dan óók geweigerd en de laatste twee asserties vallen om.
    """
    a = _activiteit(db_session)
    bbq, bbq_plaats = _onderdeel(db_session, a, "Barbecue", deadline=VROEG)
    corn, corn_plaats = _onderdeel(db_session, a, "Cornhole", deadline=LAAT)

    geweigerd = _inschrijven(client, a, bbq, bbq_plaats, naam="Bea")
    assert "afgesloten sinds" in geweigerd.text
    # De melding noemt de datum van DIT onderdeel, niet die van het andere.
    assert "3 mei" in geweigerd.text and "20 mei" not in geweigerd.text

    aanvaard = _inschrijven(client, a, corn, corn_plaats, naam="Cis")
    assert "Bedankt, Cis" in aanvaard.text, aanvaard.text[:300]
    assert db_session.query(Registration).filter(
        Registration.activity_id == a.id).count() == 1


def test_een_onderdeel_zonder_datum_blijft_open(client, db_session, vandaag):
    """Ook wanneer een ander onderdeel allang gesloten is (#1053, toets 2)."""
    a = _activiteit(db_session)
    _onderdeel(db_session, a, "Barbecue", deadline=VROEG)
    vrij, plaats = _onderdeel(db_session, a, "Sjoelbak", deadline=None)

    antwoord = _inschrijven(client, a, vrij, plaats, naam="Sam")

    assert "Bedankt, Sam" in antwoord.text, antwoord.text[:300]


def test_de_activiteit_sluit_pas_als_elk_onderdeel_gesloten_is(db_session, vandaag):
    """Zonder onderdeel gevraagd, beslist de service over het geheel.

    Zolang één onderdeel nog inschrijvingen aanneemt, is de activiteit niet dicht —
    anders zou de kaart "Inschrijvingen afgesloten" zeggen boven een onderdeel dat
    wél openstaat.
    """
    from app.domains.activities.api import get_activity
    from app.domains.activities.service import RegistrationState, registration_state

    a = _activiteit(db_session)
    _onderdeel(db_session, a, "Barbecue", deadline=VROEG)
    corn, _ = _onderdeel(db_session, a, "Cornhole", deadline=LAAT)
    a = get_activity(db_session, a.id)

    assert registration_state(a) is RegistrationState.OPEN

    corn.registration_closes_on = VROEG
    db_session.flush()
    db_session.refresh(a)
    assert registration_state(a) is RegistrationState.CLOSED


# ── De publieke kaart: één regel, of bij het onderdeel (#1053 + #1051) ───────

def test_een_onderdeel_met_een_datum_geeft_een_icoonregel(client, db_session, vandaag):
    """Toets 3: één regel onder de locatie, in de vorm van de andere praktische
    regels (`ui.icon_text`)."""
    a = _activiteit(db_session)
    _onderdeel(db_session, a, "Deelname", deadline=LAAT)

    kaart = _kaart(client, a)

    assert kaart.count("Inschrijven t/m") == 1
    assert "donderdag 20 mei" in kaart, "de datum staat er niet zonder jaartal"
    assert "2027" not in kaart.split("Inschrijven t/m")[1][:60]
    # Bij datum en locatie, boven de onderdelen — niet meer in de actiekolom.
    # De naam van het enige onderdeel staat er niet (#489), dus het blok wordt
    # herkend aan de inschrijf-URL erin.
    assert (kaart.index("Miloheem") < kaart.index("Inschrijven t/m")
            < kaart.index(f"/activiteiten/{a.id}/inschrijven/"))


def test_drie_onderdelen_met_dezelfde_datum_geven_één_regel(client, db_session,
                                                            vandaag):
    """Toets 4 (#1053) en toets 2 van #1051: de oude vorm zette de regel bij élk
    onderdeel, dus drie keer.

    Kapotgemaakt: de regel terug naast de inschrijfknop zetten → de telling wordt 3.
    """
    a = _activiteit(db_session)
    for naam in ("Barbecue", "Cornhole", "Sjoelbak"):
        _onderdeel(db_session, a, naam, deadline=LAAT)

    kaart = _kaart(client, a)

    assert kaart.count("Inschrijven t/m") == 1


def test_verschillende_datums_zetten_de_datum_bij_het_onderdeel(client, db_session,
                                                                 vandaag):
    """Toets 5: geen regel bovenaan; elke datum staat bij zijn eigen onderdeel.

    Kapotgemaakt: `card_deadline` de vroegste datum laten teruggeven in plaats van
    None → er staat weer één regel bovenaan, en die zou voor het andere onderdeel
    liegen.
    """
    a = _activiteit(db_session)
    _onderdeel(db_session, a, "Barbecue", deadline=LAAT)
    _onderdeel(db_session, a, "Cornhole", deadline=LAAT + timedelta(days=5))

    kaart = _kaart(client, a)

    assert kaart.count("Inschrijven t/m") == 2
    # Beide datums staan er, elk ná de naam van zijn onderdeel.
    assert kaart.index("Barbecue") < kaart.index("donderdag 20 mei")
    assert kaart.index("Cornhole") < kaart.index("dinsdag 25 mei")
    # En als eigen klokregel ONDER de knoppenrij, niet tussen de knoppen geperst
    # (Koens plek van het golf 12-pakket; hij merkte de inline-variant meteen op).
    # Kapotgemaakt: de regel terug als <span> in de knoppen-flex → geen mt-1-blok.
    assert kaart.count('mt-1 flex items-center gap-1 text-xs') == 2
    knopblok = kaart[kaart.index("Barbecue"):kaart.index("donderdag 20 mei")]
    assert "Inschrijven</button>" in knopblok, (
        "de klokregel hoort ná de knoppenrij, niet ervoor of ertussen")


def test_een_volzet_onderdeel_telt_niet_mee_voor_de_regel(client, db_session,
                                                          vandaag):
    """Toets 3 van #1051: staat alles volzet, dan geen datumregel.

    "Inschrijven t/m 20 mei" naast een kaart die overal *Volzet* toont, spreekt
    zichzelf tegen.
    """
    a = _activiteit(db_session)
    comp, product = _onderdeel(db_session, a, "Deelname", deadline=LAAT,
                               max_deelnemers=1)
    reg = Registration(activity_id=a.id, component_id=comp.id,
                       registration_type="INDIVIDUAL",
                       contact_name="Vol", contact_email="vol@example.org")
    db_session.add(reg)
    db_session.flush()
    from app.domains.activities.api import RegistrationItem

    db_session.add(RegistrationItem(registration_id=reg.id, product_id=product.id,
                                    quantity=1))
    db_session.flush()

    kaart = _kaart(client, a)

    assert "Volzet" in kaart
    assert "Inschrijven t/m" not in kaart


def test_zonder_datum_staat_er_geen_regel_en_geen_leeg_icoon(client, db_session,
                                                             vandaag):
    """Toets 4 van #1051: geen datum, geen regel — en zeker geen kaal icoon."""
    a = _activiteit(db_session)
    _onderdeel(db_session, a, "Deelname", deadline=None)

    kaart = _kaart(client, a)

    assert "Inschrijven t/m" not in kaart


def test_in_de_laatste_week_kleurt_de_regel_oranje(client, db_session, vandaag):
    """Koen, 20 september 2026: de attentietint van *Volzet*, niet rood (§1.1).

    `text-orange-600`, dezelfde tint als de klokregel op de activiteitspagina van
    golf 12 — twee tinten voor dezelfde melding zou de eerste zijn die verschuift.

    Met de tegenhanger in dezelfde test: een datum verder weg blijft grijs. Zonder
    die helft zou "altijd oranje" ook groen staan.
    """
    a = _activiteit(db_session)
    comp, _ = _onderdeel(db_session, a, "Deelname",
                         deadline=VANDAAG + timedelta(days=3))

    assert "text-orange-600" in _kaart(client, a)

    comp.registration_closes_on = VANDAAG + timedelta(days=30)
    db_session.flush()
    kaart = _kaart(client, a)
    assert "Inschrijven t/m" in kaart and "text-orange-600" not in kaart


def test_de_activiteitspagina_volgt_dezelfde_twee_takken(client, db_session,
                                                          vandaag):
    """Golf 12's pagina toont één klokregel of één per onderdeel — zoals de kaart.

    De per-onderdeel-tak stond daar als `deadline_per: {}`: gebouwd, maar nooit
    gevuld, want met één datum op de activiteit kón ze niet bestaan. Deze test
    vult haar in en bewijst meteen dat beide takken elkaar uitsluiten — zonder de
    `not a.shared_deadline`-voorwaarde zou de datum er twee keer staan.
    """
    a = _activiteit(db_session, naam="Twee datums")
    _onderdeel(db_session, a, "Barbecue", deadline=LAAT)
    _onderdeel(db_session, a, "Cornhole", deadline=LAAT + timedelta(days=5))

    html = client.get(f"/activiteiten/{a.id}").text
    assert html.count("Inschrijven t/m") == 2
    assert html.index("Barbecue") < html.index("donderdag 20 mei")

    b = _activiteit(db_session, naam="Eén datum")
    _onderdeel(db_session, b, "Barbecue", deadline=LAAT)
    _onderdeel(db_session, b, "Cornhole", deadline=LAAT)

    assert client.get(f"/activiteiten/{b.id}").text.count("Inschrijven t/m") == 1


# ── De omschrijving verdwijnt van de kaart (#1054) ───────────────────────────

OMSCHRIJVING = "Een namiddag vol brood, spelen en te veel dessert."


@pytest.mark.parametrize("pad", ["/", "/activiteiten"])
def test_de_omschrijving_staat_niet_meer_op_de_kaart(client, db_session, vandaag,
                                                      pad):
    """Koen, 20 september 2026: "omschrijving overal weg".

    Op beide publieke schermen die de partial delen. Het archief deelt dezelfde
    partial met een andere `scope`; die staat in de test hieronder, met een
    voorbije datum — parametriseren zou daar een activiteit tonen die er niet in
    hoort.
    """
    a = _activiteit(db_session, omschrijving=OMSCHRIJVING)
    _onderdeel(db_session, a, "Deelname")

    html = client.get(pad).text

    assert a.name in html, f"de kaart staat niet op {pad}"
    assert OMSCHRIJVING not in html


def test_ook_niet_in_het_archief(client, db_session):
    """Bewust ZONDER de geprikte dag: de archieflijst filtert in SQL met de
    `belgian_today` die de router bij het importeren opnam, dus een geprikte dag
    bereikt die query niet. Een datum in het echte verleden wel."""
    a = Activity(name="Voorbije quiz", location="Miloheem",
                 description=OMSCHRIJVING)
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id,
                                start_date=date.today() - timedelta(days=30)))
    db_session.flush()

    html = client.get("/activiteiten/archief").text

    assert "Voorbije quiz" in html
    assert OMSCHRIJVING not in html


def test_de_activiteitspagina_toont_de_omschrijving_nog_wel(client, db_session):
    """De test die voorkomt dat "weg van de kaart" stil "weg uit de weergave" wordt.

    Toen #1054 geschreven werd bestond er geen publieke detailpagina —
    `/activiteiten/<sleutel>` stuurde door naar de lijst met een anker. Golf 12
    (#913) heeft die pagina er intussen wél, en dáár staat de volledige
    omschrijving. Dat is precies de bedoeling van het issue: van de KAART af, niet
    uit de weergave. Het beheerscherm staat er als tweede helft bij, want daar
    wordt ze getypt.
    """
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    a = _activiteit(db_session, omschrijving=OMSCHRIJVING)
    _onderdeel(db_session, a, "Deelname")

    assert OMSCHRIJVING in client.get(f"/activiteiten/{a.id}").text

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    assert OMSCHRIJVING in client.get(f"/admin/activiteiten/{a.id}").text


# ── De migratie ──────────────────────────────────────────────────────────────

def test_de_migratie_kopieert_de_datum_naar_elk_onderdeel(db_session):
    """Toets 6 (#1053): drie onderdelen dragen na de migratie dezelfde datum, en
    de kolom op de activiteit bestaat niet meer.

    De kopieerstap wordt hier ECHT gedraaid — het SQL komt uit de migratie zelf
    (`KOPIEER`), niet uit een kopie in deze test. De oude kolom wordt eerst
    teruggezet, want de testdatabank staat al ná de migratie; dat terugzetten is
    meteen het bewijs dat ze weg was.
    """
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "144_2026_09_20_065547_registration_deadline_per_component.py")
    spec = importlib.util.spec_from_file_location("migratie_144", pad)
    migratie = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migratie)

    bestaat = db_session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'activities' AND table_name = 'activities' "
        "AND column_name = 'registration_closes_on'")).scalar()
    assert not bestaat, "de kolom staat nog op de activiteit — is 144 wel gedraaid?"

    db_session.execute(text(
        "ALTER TABLE activities.activities ADD COLUMN registration_closes_on DATE"))
    a = _activiteit(db_session, naam="Brood en Spelen 2028")
    for naam in ("Barbecue", "Cornhole", "Sjoelbak"):
        _onderdeel(db_session, a, naam)
    db_session.execute(text(
        "UPDATE activities.activities SET registration_closes_on = :d WHERE id = :i"),
        {"d": LAAT, "i": a.id})

    db_session.execute(text(migratie.KOPIEER))

    datums = db_session.execute(text(
        "SELECT registration_closes_on FROM activities.activity_sub_registrations "
        "WHERE activity_id = :i"), {"i": a.id}).scalars().all()
    assert datums == [LAAT, LAAT, LAAT]

    db_session.execute(text(
        "ALTER TABLE activities.activities DROP COLUMN registration_closes_on"))

"""Namen op `d_person`: wat ze oplossen, en wat er níét door verandert (#1132).

Koen, 21 september 2026: *"Ik vind dat in de views de naam en voornaam etc wel moet
staan, maar Raakje mag het niet naar Mistral sturen."*

Drie dingen worden hier gemeten, en het derde is het belangrijkste omdat het een
verrassing moet voorkomen:

1. de terugvertaling van een token levert een naam voor **elke** persoon, niet
   alleen voor een bestuurslid of organisator;
2. een naam die de beheerder TYPT wordt een token, ook voor zo iemand;
3. **geen enkel bestaand rapport toont plots een naam.** De kolommen bestaan, maar
   een rapport toont alleen wat een universe-object declareert — en er komt er geen
   bij.

**Eén premisse uit het issue is gemeten en klopt niet.** Het issue schrijft dat de
naadwachter iemand die nergens in de rapportering staat "ook niet herkent". Dat
geldt voor `scrub_question`, niet voor de wachter: die leest `person_name_parts`,
dat élke persoon van de afdeling kent. De blokkerende bescherming dekte dus al
iedereen. Wat hier wint is de BRUIKBAARHEID — zie
`test_een_gewone_naam_wordt_nu_een_token_in_plaats_van_een_blokkade`, dat het
verschil meet in plaats van het te beweren.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.reporting.assistant import detokenise, scrub_question

pytestmark = pytest.mark.ui_serverrendered

TENANT = 2


def _persoon(db, first: str, last: str):
    """Een gewone persoon: geen bestuurslid, geen organisator, geen gezin.

    Bewust zonder gezin: mét een gezin zou `d_member.head_name` de naam ook
    dragen, en dan meet de test de oude bron in plaats van de nieuwe.
    """
    from app.domains.mdm.api import Person

    p = Person(tenant_id=TENANT, first_name=first, last_name=last)
    db.add(p)
    db.flush()
    return p


# ── 1. De terugvertaling ─────────────────────────────────────────────────────

def test_een_token_van_een_gewone_persoon_wordt_weer_een_naam(db_session):
    """Vóór #1132 loste alleen een bestuurslid of organisator op.

    Tegenproef (uitgevoerd): `person_name` uit `_LABEL_SQL["persoon"]` halen en
    de kolom vervangen door een lege string → deze test viel om, met het kale
    token in het antwoord.
    """
    p = _persoon(db_session, "Mira", "Vandenbulcke")
    db_session.commit()

    uit = detokenise(db_session, f"Ik zie persoon-{p.id} in de lijst.",
                     tenant_id=TENANT)

    assert "Mira Vandenbulcke" in uit, uit
    assert f"persoon-{p.id}" not in uit


def test_de_terugvertaling_verzint_niets_voor_een_onbekend_token(db_session):
    """Een token dat niemand aanwijst blijft staan — "persoon" zonder naam zou
    lezen als een gevonden persoon."""
    uit = detokenise(db_session, "En persoon-99999?", tenant_id=TENANT)
    assert "persoon-99999" in uit


def test_de_terugvertaling_blijft_binnen_de_afdeling(db_session):
    """De opzoeking is tenant-gebonden; één bron maakt dat niet minder waar."""
    p = _persoon(db_session, "Mira", "Vandenbulcke")
    db_session.commit()

    uit = detokenise(db_session, f"persoon-{p.id}", tenant_id=TENANT + 1)

    assert "Mira" not in uit, "een naam uit een andere afdeling hoort niet op te lossen"


# ── 2. Wat de beheerder typt ─────────────────────────────────────────────────

def test_een_gewone_naam_wordt_nu_een_token_in_plaats_van_een_blokkade(db_session):
    """De echte winst van punt 4, gemeten in plaats van beredeneerd.

    Vóór #1132 stond deze naam niet in de namenlijst van `scrub_question`, dus hij
    bleef in de vraag staan — waarna de naadwachter de oproep blokkeerde omdat er
    een naam uit de ledenadministratie in zat. De naam lekte niet; de vraag
    mislukte. Nu vertrekt er een token en komt er een antwoord.

    Tegenproef (uitgevoerd): de `d_person`-tak uit `_NAME_SQL` halen → de naam
    blijft in de tekst staan en deze test valt om.
    """
    p = _persoon(db_session, "Mira", "Vandenbulcke")
    db_session.commit()

    schoon = scrub_question(db_session, "Wat weten we over Vandenbulcke?",
                            tenant_id=TENANT)

    assert "Vandenbulcke" not in schoon
    assert f"persoon-{p.id}" in schoon, schoon


def test_een_gezin_wint_van_de_personen_erin(db_session):
    """Zonder deze regel valt élke achternaam terug op `[naam]`.

    Sinds de namenlijst uit `d_person` komt, betekent een achternaam minstens twee
    dingen: het gezin én de persoon erin. Gemeten toen de lijst verbreed werd:
    twee bestaande tests vielen om, allebei op een gezin dat er maar één was. De
    vraag "stopt het gezin X?" moet op `gezin-<id>` kunnen filteren.
    """
    from tests.test_assistant_masking import _household

    member, _persoon_in_gezin = _household(db_session, "Joris", "Verlinden")
    db_session.commit()

    schoon = scrub_question(db_session, "Stopt het gezin Verlinden dit jaar?",
                            tenant_id=TENANT)

    assert "Verlinden" not in schoon
    assert f"gezin-{member.id}" in schoon, schoon


# ── 3. Geen enkel rapport verandert ──────────────────────────────────────────

def test_geen_enkel_universe_object_leest_de_nieuwe_naamkolommen(db_session):
    """Test 5 uit het issue: een rapport dat Koen morgen opent, ziet er hetzelfde uit.

    De kolommen bestaan op de weergave, maar een rapport toont alleen wat een
    object declareert — en #1132 voegt geen object toe. Deze test is de reden dat
    dat waar blijft: wie er later een object bij zet, komt hier langs en moet
    bewust beslissen dat een rapport voortaan namen toont.
    """
    from app.domains.reporting.universe import OBJECTS

    nieuw = {"first_name", "last_name", "person_name"}
    lezers = sorted(o.key for o in OBJECTS
                    if o.view == "d_person"
                    and nieuw & {k for k in nieuw if f"{{view}}.{k}" in o.sql})

    assert not lezers, (
        "deze objecten lezen de naamkolommen van d_person, en dan toont een "
        f"bestaand rapport plots een naam: {lezers}. Is dat bedoeld, dan hoort "
        "die keuze in een eigen issue — met de blootstelling erbij.")


def test_de_personen_weergave_draagt_de_namen_wel(db_session):
    """De tegenhanger: zonder deze test zou de test hierboven ook groen staan als
    de migratie nooit gedraaid had."""
    kolommen = {row[0] for row in db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'reporting' AND table_name = 'd_person'"))}

    assert {"first_name", "last_name", "person_name"} <= kolommen, (
        f"d_person draagt de naamkolommen niet; gevonden: {sorted(kolommen)}")


def test_de_samengestelde_naam_overleeft_een_lege_voornaam(db_session):
    """Een persoon met alleen een achternaam draagt gewoon die achternaam.

    Gemeten onderweg: `first_name` is NOT NULL, dus het NULL-geval waar
    `TRIM(CONCAT_WS(...))` tegen beschermt kán hier niet optreden — een test
    daarop sloeg af op de constraint en bewees niets. Het bereikbare geval is de
    LEGE string, en dat is wat hier staat. `CONCAT_WS` blijft wel de vorm: het is
    dezelfde als `d_activity_organiser` (#1077), en een `||`-keten die ooit een
    nullbare kolom krijgt, verliest stil de hele naam.
    """
    from app.domains.mdm.api import Person

    p = Person(tenant_id=TENANT, first_name="", last_name="Zonderdoop")
    db_session.add(p)
    db_session.commit()

    naam = db_session.execute(text(
        "SELECT person_name FROM reporting.d_person WHERE person_id = :id"),
        {"id": p.id}).scalar()

    assert naam == "Zonderdoop", repr(naam)

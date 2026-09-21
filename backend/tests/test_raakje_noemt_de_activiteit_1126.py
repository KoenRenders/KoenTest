"""Raakje noemt de activiteit bij naam, en belooft niets over namen (#1126).

Drie bevindingen van Koen op 21 september 2026, uit een gesprek met Raakje op een
activiteit. Ze raken hetzelfde mechanisme: de tokens houden namen bij het **model**
weg, niet bij de **gebruiker** — `detokenise` zet `gezin-23` server-side terug naar
de naam vóór de beheerder het leest.

**1. De openingszin beloofde iets wat niet waar is.** *"Namen van personen geef ik
niet: ik antwoord op groepsniveau."* Waar een rij een gezin of een bestuurslid
noemt, ziet de beheerder wél de naam. Die zin stond op **drie** plaatsen (de
Betalingen-overlay, de activiteit-overlay en de pagina van de assistent); het
issue noemt er één, maar het is dezelfde zin met dezelfde fout, en één ervan
repareren laat er twee liegen.

**2. Een activiteit heette "activiteit 77".** De naam wordt nu server-side
opgezocht en gaat mee de prompt in, met het nummer ernaast — het model filtert op
dat nummer. Bewust géén token voor activiteiten: het tokenmechanisme bestaat voor
persoonsgegevens, en een activiteitsnaam is dat niet.

**Wat daarbij bewaakt moest blijven.** Deze systeemprompt is vrijgesteld van de
naam-controle van de naadwachter (`SCAN_PROMPT_NAMES=False`), en die vrijstelling
rust op één aanname: de prompt komt uit een declaratie en draagt geen opgeslagen
waarde. Een activiteitsnaam ís opgeslagen waarde, en een activiteit mag "Wandeling
met Jan Peeters" heten. De titel gaat daarom eerst door dezelfde naamschoonmaak als
de getypte vraag. Dat is de test hieronder die het meeste beschermt.

Deel 3 van het issue (de terugvertaling kent te weinig personen) zit in #1077, bij
de finetuning-CLI: `_LABEL_SQL["persoon"]` is daar een UNION van bestuursleden en
organisatoren geworden, mét een test die een organisator als naam terugkrijgt.
Afgestemd vóór de bouw, zodat we niet allebei hetzelfde blok raakten.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`_activity_label` uit `scope_for_activity` gehaald en het nummer alleen gelaten →
de naamtest valt om; de schoonmaak in `_activity_label` overgeslagen → de
ledennaam-test valt om met de naam in de prompt.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domains.reporting.assistant import (ScopeNietOverdraagbaar,
                                             build_system_prompt,
                                             scope_for_activity,
                                             scope_for_payments)
from tests._assistant_seed import TENANT, seed

pytestmark = pytest.mark.ui_serverrendered

DOMAINS = Path(__file__).resolve().parents[1] / "app" / "domains"

# De drie openingszinnen van Raakje in het beheer, met de plek waar ze staan.
OPENINGEN = (
    "payment/templates/_betalingen_scherm.html",
    "activities/templates/_aa_recordkop.html",
    "reporting/templates/admin_rapporten_raakje.html",
)


@pytest.fixture
def situatie(db_session):
    return seed(db_session)


# ── 1. Geen belofte over namen ───────────────────────────────────────────────

def test_geen_enkele_openingszin_belooft_dat_namen_wegblijven():
    """Toets de zin, niet de aanwezigheid van een overlay.

    De claim is onwaar: de terugvertaling zet `gezin-23` om naar de naam vóór de
    beheerder het leest. Beloof dus niets over namen — wat er komt, hangt af van
    wat er in de rij staat.
    """
    assert len(OPENINGEN) == 3, "de lijst openingszinnen kromp; deze test scant minder"
    fouten = []
    for relatief in OPENINGEN:
        bron = (DOMAINS / relatief).read_text()
        for zin in ("Namen van personen geef ik niet",
                    "ik antwoord op groepsniveau"):
            if zin in bron:
                fouten.append(f"{relatief}: «{zin}»")
    assert not fouten, (
        "deze openingszinnen beloven nog dat namen wegblijven, terwijl de "
        "beheerder ze wél leest (#1126):\n  " + "\n  ".join(fouten))


def test_de_rest_van_de_openingszin_blijft_staan():
    """De tegenproef: de zin is ingekort, niet leeggehaald. Zonder deze test zou
    "haal de hele begroeting weg" ook groen staan."""
    voorbeelden = {
        "payment/templates/_betalingen_scherm.html": "Ik kijk mee met de selectie",
        "activities/templates/_aa_recordkop.html": "Vraag me iets over deze activiteit",
        "reporting/templates/admin_rapporten_raakje.html": "Vraag me iets over de leden",
    }
    for relatief, stuk in voorbeelden.items():
        assert stuk in (DOMAINS / relatief).read_text(), relatief


# ── 2. De activiteit bij naam ────────────────────────────────────────────────

def test_de_activiteitscope_noemt_de_naam_en_het_nummer(db_session, situatie):
    nummer = situatie["activities"]["quiz"]
    prompt = build_system_prompt(
        scope_for_activity(db_session, nummer, tenant_id=TENANT))

    assert "«Quiz»" in prompt, "de prompt noemt de activiteit niet bij naam"
    assert f"nummer {nummer}" in prompt, "het nummer hoort erbij: het model filtert erop"


def test_de_schermselectie_noemt_de_naam_en_het_nummer(db_session, situatie):
    """Dezelfde fout stond op twee plaatsen; dit is de tweede (#1060-selectie)."""
    nummer = situatie["activities"]["wandeling"]
    prompt = build_system_prompt(
        scope_for_payments({"activiteit": str(nummer)}, db_session, tenant_id=TENANT))

    assert "Wandeling" in prompt and f"nummer {nummer}" in prompt, prompt[:400]
    assert f"activiteit {nummer}," not in prompt, "alleen het nummer is de oude vorm"


def test_een_geweigerde_selectie_zoekt_geen_naam_op(db_session, situatie):
    """De weigering staat vóór de opzoeking (#1126, opmerking van de #1060-auteur).

    Een selectie met een zoekterm is niet overdraagbaar; een naam opzoeken voor
    een scope die daarna weggegooid wordt, is een query voor niets. Gemeten op de
    databank zelf: tijdens de weigering vertrekt er geen enkele query.
    """
    from sqlalchemy import event

    queries: list[str] = []

    def _tel(conn, cursor, statement, params, context, executemany):
        queries.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", _tel)
    try:
        with pytest.raises(ScopeNietOverdraagbaar):
            scope_for_payments({"q": "janssens", "activiteit": "1"}, db_session,
                               tenant_id=TENANT)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", _tel)

    assert not queries, f"er vertrok toch een query: {queries[:2]}"


def test_een_onbekende_activiteit_blijft_een_nummer(db_session, situatie):
    """Vindt de rapporteringsview niets, dan is het nummer het eerlijke antwoord.

    Niet "activiteit (onbekend)" en zeker geen gok: de scope klopt nog steeds, en
    het model filtert op het nummer.
    """
    prompt = build_system_prompt(
        scope_for_activity(db_session, 999_999, tenant_id=TENANT))

    assert "nummer 999999" in prompt
    assert "«" not in prompt.split("nummer 999999")[0][-80:], prompt[:300]


def test_een_ledennaam_in_de_titel_gaat_niet_mee_de_prompt_in(db_session, situatie):
    """De waarborg waarop de vrijstelling van de naam-controle rust.

    Deze systeemprompt wordt NIET op namen gescand (`SCAN_PROMPT_NAMES=False`),
    omdat hij uit een declaratie komt. Sinds #1126 draagt hij ook een
    activiteitstitel, en die komt uit de databank. Een activiteit die naar een lid
    genoemd is, zou zo een ledennaam ongescand naar Mistral sturen — precies wat de
    wachter moet voorkomen. De titel gaat daarom door dezelfde schoonmaak als de
    getypte vraag: de naam wordt het token van dat gezin.
    """
    from datetime import date

    from app.domains.activities.api import Activity
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.reporting.assistant import scrub_question

    # Een eigen hoofdlid met een naam die nergens in gewoon Nederlands voorkomt.
    # De seed-namen deugen hier niet: "Bestuur" staat letterlijk in de
    # systeemprompt, en "Gezin1" draagt een cijfer — de woordsplitser laat dat
    # vallen, dus die naam is geen zuivere meting.
    achternaam = "Vliethoven"
    gezin = Member(tenant_id=TENANT)
    db_session.add(gezin)
    db_session.flush()
    hoofdlid = Person(tenant_id=TENANT, first_name="Wiebe", last_name=achternaam,
                      date_of_birth=date(1980, 6, 15), gender_code="M")
    db_session.add(hoofdlid)
    db_session.flush()
    db_session.add(MemberPerson(tenant_id=TENANT, member_id=gezin.id,
                                person_id=hoofdlid.id, relation_type="HOOFDLID"))
    db_session.flush()
    assert scrub_question(db_session, achternaam, tenant_id=TENANT) != achternaam, (
        "voorwaarde: deze naam staat in de namenlijst van de tenant")

    activiteit = Activity(tenant_id=TENANT, name=f"Wandeling met {achternaam}")
    db_session.add(activiteit)
    db_session.flush()

    prompt = build_system_prompt(
        scope_for_activity(db_session, activiteit.id, tenant_id=TENANT))

    assert achternaam.lower() not in prompt.lower(), (
        "een ledennaam uit een activiteitstitel staat in de systeemprompt, die "
        "niet op namen gescand wordt (#1126)")
    assert "Wandeling met" in prompt, "de rest van de titel hoort er wél in"

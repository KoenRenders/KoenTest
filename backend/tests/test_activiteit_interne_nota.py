"""De interne nota van een activiteit blijft binnen (#1028).

**Dit veld heet niet toevallig anders dan zijn voorganger.** De oude kolom
`notes` (#402) droeg de opmerking dat ze nergens getoond werd, en dat klopte
niet: `chatbot/tools.py` zette haar in `get_activity_detail`, de tool van de
**publieke** bot. Alles daarin gaat integraal naar het model en dus naar wie het
vraagt. Een veld dat "interne nota" heet en aan de publieke chat hangt, is een
lek dat wacht op de eerste die er iets in typt. De kolom is daarom verdwenen
(migratie 137) en deze begint leeg, onder een naam die niet met de oude te
verwarren is.

**De belangrijkste test hier is niet dat het veld werkt, maar dat het nergens
naar buiten komt** — en de chattool staat in die lijst, want dat is het kanaal
dat het echt was.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden, drie keer
gemeten:

* `notes: Optional[str]` op `ActivityResponse` gezet → rood op *het publieke
  JSON-antwoord*, en alleen daar. Daarom reist de nota apart naar het scherm
  (`_aa_detail_ctx`): dat schema is óók het publieke antwoord, dus één veld
  erbij is één lek.
* daarbovenop de kaart de nota laten tonen → rood op vijf wegen tegelijk, elk
  bij naam.
* `board_notes` in de serialiser van `get_activity_detail` gezet **zonder** hem
  in `PUBLIC_FIELD_CONTRACT` op te nemen → `test_public_tool_field_contract.py`
  wordt rood. Die poort is het eigenlijke vangnet: zij vangt precies het geval
  waar dit issue op herschreven moest worden.
"""
from datetime import date, timedelta

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# Onmiskenbaar, en niets wat toevallig in een sjabloon of script staat.
NOTA = "ZZ-interne-nota-1028 sleutel bij Mieke, kassa niet vergeten"


@pytest.fixture
def activiteit(db_session):
    a = Activity(name="Quiz met een nota", location="Miloheem", slug="quiz-met-nota",
                 description="Twee zinnen die de bezoeker leest.", board_notes=NOTA)
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id,
                                start_date=date.today() + timedelta(days=21)))
    db_session.flush()
    return a


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _publieke_wegen(activiteit) -> list[tuple[str, str]]:
    """(omschrijving, pad) — elke weg waarlangs een buitenstaander iets ziet."""
    return [
        ("de publieke activiteitenpagina", f"/activiteiten/{activiteit.id}"),
        ("de deelbare pagina op de slug", f"/activiteiten/{activiteit.slug}"),
        ("de lijst met komende activiteiten", "/activiteiten"),
        ("de homepage", "/"),
        ("het archief", "/archief"),
        ("het publieke JSON-antwoord", "/api/v1/activities"),
    ]


def test_de_nota_komt_nergens_buiten_het_beheer(client, db_session, activiteit):
    """De test die ertoe doet: elke weg naar buiten, in één keer.

    Eén test en niet zes, omdat het één invariant is — en omdat een zevende weg
    die er morgen bijkomt, hier hoort te worden toegevoegd in plaats van als
    nieuwe test te verdwalen.
    """
    gelekt = []
    for wat, pad in _publieke_wegen(activiteit):
        antwoord = client.get(pad)
        assert antwoord.status_code in (200, 301, 302, 404), (wat, pad,
                                                              antwoord.status_code)
        if NOTA.split()[0] in antwoord.text:
            gelekt.append(f"{wat} ({pad})")

    assert not gelekt, f"de interne nota staat op: {gelekt}"


def test_de_nota_zit_niet_in_het_antwoord_van_de_publieke_bot(db_session, activiteit):
    """Het kanaal dat het écht was (#1028).

    `get_activity_detail` is de tool van de publieke Raakje. Wat hier in het
    antwoord staat, gaat integraal naar het model en dus naar de bezoeker.
    """
    import json

    from app.domains.chatbot.tools import execute_tool

    antwoord = json.loads(execute_tool("get_activity_detail",
                                       {"activity_id": activiteit.id}, db_session))

    assert antwoord["name"] == "Quiz met een nota", "de tool gaat wel over deze activiteit"
    assert NOTA.split()[0] not in json.dumps(antwoord, ensure_ascii=False)
    assert "board_notes" not in antwoord and "notes" not in antwoord


def test_de_bot_leest_wel_de_publieke_omschrijving(db_session, activiteit):
    """Bewust toegevoegd in dezelfde beweging (#1028, stap 1).

    Raakje beantwoordde "waar gaat dit over?" met de affichetekst, terwijl de
    bestuurder net twee zinnen schreef voor precies die vraag. Dat is een nieuwe
    export naar een derde partij, dus ze staat in het contract én hier.
    """
    import json

    from app.domains.chatbot.tools import execute_tool

    antwoord = json.loads(execute_tool("get_activity_detail",
                                       {"activity_id": activiteit.id}, db_session))

    assert antwoord["description"] == "Twee zinnen die de bezoeker leest."


def test_de_nota_zit_niet_in_het_nieuwsbriefblok(client, db_session, activiteit):
    """Het blok dat "Activiteit invoegen" in een nieuwsbrief zet (#984).

    Een aparte test omdat deze weg achter een beheerdersessie zit: de brief is
    intern, maar wat erin staat vertrekt naar honderden lezers.
    """
    from app.domains.newsletter import service as nb

    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    db_session.flush()

    antwoord = client.get(
        f"/admin/nieuwsbrieven/{letter.id}/invoegen/activiteit/{activiteit.id}")

    assert antwoord.status_code == 200
    assert "Quiz met een nota" in antwoord.text, "het blok gaat wel over deze activiteit"
    assert NOTA.split()[0] not in antwoord.text, (
        "de interne nota komt mee in de nieuwsbrief")


def test_de_export_van_een_onderdeel_draagt_de_nota_niet(client, db_session,
                                                         activiteit):
    """De derde weg naar buiten: een deelnemerslijst gaat naar een ploegleider."""
    from app.domains.activities.api import ActivitySubRegistration

    onderdeel = ActivitySubRegistration(activity_id=activiteit.id, name="Ploegen")
    db_session.add(onderdeel)
    db_session.flush()
    _login(client)

    antwoord = client.get(
        f"/admin/activiteiten/{activiteit.id}/onderdelen/{onderdeel.id}/export")

    assert antwoord.status_code == 200
    assert NOTA.split()[0].encode() not in antwoord.content


# ── En op het beheerscherm staat ze er wél ───────────────────────────────────

def test_het_beheerscherm_toont_de_nota_met_de_vermelding_erbij(client, db_session,
                                                                activiteit):
    _login(client)

    html = client.get(f"/admin/activiteiten/{activiteit.id}").text

    assert NOTA in html
    assert "Interne nota" in html
    assert "Alleen het bestuur ziet dit" in html, (
        "de vermelding hoort BIJ het veld te staan — daar beslist iemand wat hij typt")


def test_de_nota_is_te_bewerken_en_te_wissen(client, db_session, activiteit):
    csrf = _login(client)

    def bewaar(waarde):
        return client.post(f"/admin/activiteiten/{activiteit.id}",
                           data={"name": activiteit.name, "location": "Miloheem",
                                 "description": "Twee zinnen die de bezoeker leest.",
                                 "board_notes": waarde, "slug": activiteit.slug},
                           headers={"X-CSRF-Token": csrf})

    assert bewaar("Nieuwe afspraak: sleutel bij Jan").status_code == 200
    db_session.expire_all()
    assert db_session.get(Activity, activiteit.id).board_notes == "Nieuwe afspraak: sleutel bij Jan"

    assert bewaar("   ").status_code == 200
    db_session.expire_all()
    assert db_session.get(Activity, activiteit.id).board_notes is None, (
        "een nota leegmaken moet de kolom bereiken, net als bij de omschrijving")

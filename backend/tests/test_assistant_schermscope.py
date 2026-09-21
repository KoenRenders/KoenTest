"""Admin-Raakje neemt de selectie over van het scherm waar hij staat (#1060).

Koen, 20 september 2026: *"Ik wil AI naar de bestaande ADMIN-Raakje met de context
van waar hij op dat moment wordt aangeroepen. Niet meer, niet minder."*

#975 bond het gesprek al aan één ACTIVITEIT. Dat patroon is hier veralgemeend: de
scope zit in het PAD, wordt SERVER-SIDE herleid, en wordt afgedwongen in de
`dispatcher`-closure — niet in de systeemprompt. Een prompt is geen grens: het
model kan haar vergeten, negeren of eromheen praten. Een filterlijst die bij elke
toolaanroep wordt aangeplakt, kan dat niet.

**Overdragen of weigeren, niets ertussenin.** Niet elk filter van het
betalingenscherm heeft een tegenhanger in het universum. Waar dat zo is, antwoordt
de route met de reden in plaats van met een getal over een RUIMERE verzameling dan
de lijst ernaast toont. Dat is geen striktheid om de striktheid: een assistent die
naast een gefilterde lijst een totaal over alles geeft zonder het te zeggen, liegt
onzichtbaar — en op Betalingen gaat dat over geld.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden. Zes ingrepen,
elk één keer gedraaid; tussen haakjes wat er werkelijk omviel:

- het zicht laten vallen in `scope_for_payments` (*het tabblad reist mee* en de
  twee andere tabbladen) — de filter staat dan niet in de toolaanroep;
- de scope uit het FORMULIER lezen in plaats van uit `filterparams` (*een
  vervalst formulierveld* én *de route weigert leesbaar*). Dat die twee sámen
  omvallen is het punt: wie de scope uit het formulier leest, laat een verzender
  zowel de scope kiezen als de weigering ontwijken;
- `ScopeNietOverdraagbaar` niet opwerpen bij een zoekterm (*weigert en zegt welk*
  plus *de route weigert leesbaar*) — dit is de test die het stille verbreden
  vangt;
- de aan-poort uit de route (*zonder de schakelaars geen ingang*);
- de rolvraag uit de schermvlag (*wie de assistent niet mag*) — dan staat er een
  knop voor een FINANCE-only gebruiker die op een 403 uitkomt;
- de `{% if raakje_scherm %}` altijd waar (*geen knop* én *wie de assistent niet
  mag*).
"""
from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.reporting.assistant import (Scope, ScopeNietOverdraagbaar,
                                             build_system_prompt,
                                             scope_for_payments)
from tests._assistant_seed import TENANT, seed
from tests.conftest import SEEDED_ADMIN_EMAIL

PAD = "/admin/rapporten/raakje/scherm/betalingen"


@pytest.fixture
def situatie(db_session):
    return seed(db_session)


@pytest.fixture
def aan(db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT)
    db_session.flush()


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _filters(scope: Scope) -> list[tuple[str, str]]:
    return [(f["object"], f["values"][0]) for f in scope.filters]


# ── De selectie wordt een echte filter ───────────────────────────────────────

def _scope(db, stand: dict) -> Scope:
    """#1126: de bouwer zoekt de naam van een activiteit op en heeft daarvoor de
    databank en de tenant nodig. De tests hieronder geven ze mee zoals de route
    dat doet."""
    return scope_for_payments(stand, db, tenant_id=TENANT)


def test_het_tabblad_openstaand_reist_mee_als_filter(db_session):
    """De kern: de toolaanroep draagt de scope.

    Het zicht *Openstaand* van het scherm wordt `payment_open = Ja` — exact
    dezelfde doorsnede, sinds #1078 het saldo-begrip in het universum bestaat.
    """
    scope = _scope(db_session, {"zicht": "openstaand"})

    assert ("payment_open", "Ja") in _filters(scope)
    assert scope.facts == frozenset({"f_payments"})


@pytest.mark.parametrize("zicht,verwacht", [
    ("betaald", ("payment_status", "Betaald")),
    ("terugbetaald", ("payment_type", "Terugbetaling")),
])
def test_de_andere_tabbladen_ook(db_session, zicht, verwacht):
    assert verwacht in _filters(_scope(db_session, {"zicht": zicht}))


def test_zonder_selectie_blijft_het_bij_het_feit(db_session):
    """Het kale scherm: geen filters, wel de afbakening tot betalingen.

    Zonder die afbakening zou Raakje vanaf Betalingen over lidmaatschappen of
    formulieren kunnen antwoorden — dan is het geen schermcontext meer.
    """
    scope = _scope(db_session, {})

    assert scope.filters == ()
    assert scope.facts == frozenset({"f_payments"})
    assert not scope.is_record, "dit is een selectie, geen record"


def test_de_statuskeuze_en_de_context_reizen_mee(db_session):
    scope = _scope(db_session, {"status": "pending", "context": "membership"})

    assert ("payment_status", "In afwachting") in _filters(scope)
    assert ("payment_payable_type", "Lidgeld") in _filters(scope)


def test_de_prompt_noemt_de_selectie_en_geen_opgeslagen_tekst(db_session):
    """De systeemprompt van dit pakket wordt niet op namen gescand, en die
    vrijstelling is alleen houdbaar zolang er niets uit de databank in komt.
    Alleen onze eigen labels en getallen dus."""
    prompt = build_system_prompt(
        _scope(db_session, {"zicht": "openstaand", "activiteit": "42"}))

    # Activiteit 42 bestaat hier niet, dus de naamopzoeking vindt niets en het
    # blijft bij het nummer (#1126). Dat een bestaande activiteit haar NAAM
    # meekrijgt, staat in test_raakje_noemt_de_activiteit_1126.py.
    assert "openstaand" in prompt and "activiteit 42" in prompt
    assert "BETALINGENSCHERM" in prompt


# ── Overdragen of weigeren ───────────────────────────────────────────────────

@pytest.mark.parametrize("stand,noemt", [
    ({"q": "janssens"}, "zoekterm"),
    ({"gezin": "7"}, "gezinsfilter"),
    ({"inschrijving": "9"}, "inschrijvingsfilter"),
    ({"context": "year-2026"}, "contextfilter"),
    ({"context": "comp-3"}, "contextfilter"),
])
def test_een_filter_zonder_tegenhanger_weigert_en_zegt_welk(db_session, stand, noemt):
    """En het zegt WELK filter in de weg zit — "dit kan niet" is onbruikbaar."""
    with pytest.raises(ScopeNietOverdraagbaar) as fout:
        _scope(db_session, stand)

    assert noemt in str(fout.value)


def test_de_route_weigert_leesbaar_in_plaats_van_ruimer_te_antwoorden(
        client, db_session, situatie, aan):
    """Het gedrag dat het stille verbreden tegenhoudt.

    Zonder deze weigering zou Raakje naast een op naam gefilterde lijst een totaal
    over álle betalingen geven, zonder dat iemand het ziet.
    """
    kop = _login(client)

    antwoord = client.post(
        PAD, data={"vraag": "hoeveel staat er open?", "historie": "[]"},
        headers={**kop, "HX-Current-URL":
                 "http://testserver/admin/betalingen?q=janssens"})

    assert antwoord.status_code == 200
    assert "zoekterm" in antwoord.text
    assert "niet overnemen" in antwoord.text


# ── Waar de scope vandaan komt ───────────────────────────────────────────────

def test_een_vervalst_formulierveld_verandert_de_scope_niet(client, db_session,
                                                             situatie, aan):
    """Toets 2 van het issue: de scope wordt server-side herleid.

    Het formulier draagt alleen de vraag en de geschiedenis. Zet er een `zicht`
    of een `activiteit` bij en er verandert niets — de route leest de stand van
    het scherm, niet wat de verzender erbij typt. Dit is dezelfde keuze als #975,
    waar de activiteit in het pad zit: een formulierveld kan stil wegvallen én
    stil bijgezet worden.
    """
    kop = _login(client)

    antwoord = client.post(
        PAD,
        data={"vraag": "hoeveel betalingen?", "historie": "[]",
              "zicht": "terugbetaald", "activiteit": "999", "q": "janssens"},
        headers={**kop, "HX-Current-URL": "http://testserver/admin/betalingen"})

    # De zoekterm in het formulier zou de scope onoverdraagbaar maken als ze
    # gelezen werd; ze wordt genegeerd, dus het antwoord komt er gewoon.
    assert antwoord.status_code == 200
    assert "niet overnemen" not in antwoord.text


def test_een_onbekend_scherm_bestaat_niet(client, db_session, situatie, aan):
    """Een server-side lijst en geen vrij pad: wat iemand in de URL typt, kiest
    geen code uit."""
    kop = _login(client)

    antwoord = client.post("/admin/rapporten/raakje/scherm/geheim",
                           data={"vraag": "?", "historie": "[]"}, headers=kop)

    assert antwoord.status_code == 404


# ── De ingang op het scherm ──────────────────────────────────────────────────

def test_de_ingang_staat_op_het_betalingenscherm(client, db_session, situatie, aan):
    """De knop verschijnt, en hij wijst naar de schermroute."""
    _login(client)

    html = client.get("/admin/betalingen").text

    assert "AI · Betalingen" in html
    assert 'hx-post="/admin/rapporten/raakje/scherm/betalingen"' in html


def test_zonder_de_schakelaars_geen_knop(client, db_session, situatie):
    """Bewust zonder de `aan`-fixture: uit is uit, ook op dit scherm."""
    _login(client)

    html = client.get("/admin/betalingen").text

    assert "AI · Betalingen" not in html


def test_wie_de_assistent_niet_mag_krijgt_er_geen_knop(client, db_session,
                                                        situatie, aan):
    """De rolgrens die dit scherm bijzonder maakt (Koen, 20 september 2026).

    Betalingen draait op `require_finance_ui`, de assistent op
    `require_admin_ui`. Een FINANCE-only gebruiker ziet dus wél de lijst en mag
    de assistent niet — die hoort daar geen knop te zien die op een 403 uitkomt.
    Geen nieuwe rol en geen verbreding: de ingang volgt exact wie de route
    toelaat.
    """
    from app.domains.auth.models import User, UserRole

    penningmeester = User(email="penning@example.org", is_active=True)
    db_session.add(penningmeester)
    db_session.flush()
    db_session.add(UserRole(user_id=penningmeester.id, role_code="FINANCE"))
    db_session.flush()
    client.cookies.set(SESSION_COOKIE,
                       make_session_value(penningmeester.email))

    antwoord = client.get("/admin/betalingen")

    assert antwoord.status_code == 200, "de penningmeester mag dit scherm wél zien"
    assert "AI · Betalingen" not in antwoord.text


def test_zonder_de_schakelaars_geen_ingang(client, db_session, situatie):
    """Toets 3: de dubbele aan-schakelaar geldt ook mét context.

    Deze test draait bewust ZONDER de `aan`-fixture. Een scherm dat zijn formulier
    verbergt terwijl de route blijft antwoorden, is geen kill-switch maar een
    verborgen formulier.
    """
    kop = _login(client)

    antwoord = client.post(PAD, data={"vraag": "hoeveel?", "historie": "[]"},
                           headers=kop)

    assert antwoord.status_code == 404

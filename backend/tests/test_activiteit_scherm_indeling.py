"""Het activiteitendetail: volgorde van de blokken en de sprong naar de studio.

Twee vragen van Koen op 20 september 2026, samen gebouwd omdat ze hetzelfde
scherm herschikken:

* **#1046** — Organisatoren hoort onderaan, ónder *Onderdelen & producten*.
* **#1049** (CR-10 Q23) — van een activiteit naar haar affiche springen, zonder
  langs de ontwerpenlijst te passeren.

De volgordetest staat er omdat een blok anders bij de volgende ronde stil
terugschuift: de bestaande tests van #1033 toetsen gedrag, niet plaats.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- de include terug op haar oude plek (vóór *Onderdelen & producten*) → de
  volgordetest én de lege-toestand-test vallen om;
- `ontwerpen_href` altijd de lijst-URL laten geven → de "zonder ontwerp"-test
  valt om. Een test die alleen "er staat een link" toetst, blijft groen als
  beide takken hetzelfde geven — vandaar één test per tak, plus een derde die
  de toestand omdraait.
- de include ná de buitenste `</div>` van dit bestand → **groen**, en dat is
  een meting die de aanname uit het issue bijstelt: zie de test hieronder.
"""
import re

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def activiteit(db_session):
    a = Activity(name="Quiz met een affiche", location="Miloheem")
    db_session.add(a)
    db_session.flush()
    return a


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _scherm(client, activiteit) -> str:
    antwoord = client.get(f"/admin/activiteiten/{activiteit.id}")
    assert antwoord.status_code == 200
    return antwoord.text


def _ontwerp(db, activiteit):
    from app.domains.designstudio.api import create_design

    ontwerp = create_design(db, activity_id=activiteit.id,
                            duo_code="dark_green-golden_yellow",
                            created_by=SEEDED_ADMIN_EMAIL)
    db.flush()
    return ontwerp


# ── #1046: Organisatoren onderaan ────────────────────────────────────────────

def test_organisatoren_staan_onder_onderdelen(client, db_session, activiteit):
    _login(client)
    html = _scherm(client, activiteit)

    # Op de kop zelf en niet op de losse woorden: "onderdelen" komt ook voor in
    # de lege-toestand-zin eronder.
    def kop(tekst):
        m = re.search(rf"<h3[^>]*>{tekst}</h3>", html)
        assert m, f"kop {tekst!r} niet gevonden"
        return m.start()

    onderdelen = kop("Onderdelen [^<]*producten")
    organisatoren = kop("Organisatoren")

    assert organisatoren > onderdelen, (
        "het organisatorenblok staat weer boven Onderdelen & producten (#1046)")


def test_het_blok_staat_ook_in_het_fragment_na_een_bewerking(client, db_session,
                                                             activiteit):
    """Na bewaren staat het organisatorenblok er nog — getoetst op het FRAGMENT.

    Het issue waarschuwt dat de include buiten `#aa-detail` kan belanden en dan
    stil verdwijnt bij de eerstvolgende swap. Nagemeten: vanuit dít bestand kan
    dat niet. `_aa_detail.html` ís het fragment, dus alles erin komt hoe dan ook
    binnen `#aa-detail` terecht; de include ná de buitenste `</div>` zetten laat
    deze test groen (gemeten). De echte plek waar dat mis kan gaan is
    `admin_activiteit.html`, dat het fragment in de container hangt.

    Wat deze test dus wél bewijst: een bewerking laat het blok staan. Dat is de
    zichtbare vorm van de melding, en ze zou rood worden als iemand de include
    naar de paginasjabloon verplaatst.
    """
    csrf = _login(client)

    antwoord = client.post(f"/admin/activiteiten/{activiteit.id}",
                           data={"name": activiteit.name, "location": "Miloheem",
                                 "description": "", "board_notes": "", "slug": ""},
                           headers={"X-CSRF-Token": csrf})

    assert antwoord.status_code == 200
    assert re.search(r"<h3[^>]*>Organisatoren</h3>", antwoord.text), (
        "na een bewerking is het organisatorenblok weg — de include staat buiten "
        "#aa-detail")


def test_zonder_onderdelen_blijft_de_scheiding_leesbaar(client, db_session,
                                                        activiteit):
    """#637/#650 verhuist mee: zonder onderdelen las de kaart eronder als een
    onderdeel. Die kaart is nu het organisatorenblok."""
    _login(client)
    html = _scherm(client, activiteit)

    assert "Nog geen onderdelen" in html
    assert html.index("Nog geen onderdelen") < html.index(">Organisatoren</h3>")


# ── #1049: de sprong naar de Design Studio ───────────────────────────────────

def test_met_een_ontwerp_wijst_de_sprong_naar_de_lijst(client, db_session, activiteit):
    _ontwerp(db_session, activiteit)
    _login(client)

    html = _scherm(client, activiteit)

    assert f'href="/admin/ontwerpen?activity_id={activiteit.id}"' in html
    assert "Ontwerpen: 1" in html
    assert f'href="/admin/ontwerpen/nieuw?activity_id={activiteit.id}"' not in html, (
        "beide takken geven dezelfde link; dan toetst deze test niets")


def test_zonder_ontwerp_wijst_de_sprong_naar_maken(client, db_session, activiteit):
    _login(client)

    html = _scherm(client, activiteit)

    assert f'href="/admin/ontwerpen/nieuw?activity_id={activiteit.id}"' in html
    assert "Affiche maken in de Design Studio" in html
    assert f'href="/admin/ontwerpen?activity_id={activiteit.id}"' not in html


def test_het_aantal_volgt_de_ontwerpen(client, db_session, activiteit):
    """De tegenhanger binnen één test: de toestand omdraaien verandert de link."""
    _login(client)
    assert "Affiche maken" in _scherm(client, activiteit)

    _ontwerp(db_session, activiteit)
    _ontwerp(db_session, activiteit)
    html = _scherm(client, activiteit)

    assert "Ontwerpen: 2" in html and "Affiche maken" not in html


def test_de_publieke_kant_toont_de_sprong_niet(client, db_session, activiteit):
    """Beheerderswerk. De link mag nergens in de publieke schil opduiken."""
    from datetime import date, timedelta

    from app.domains.activities.api import ActivityDate

    db_session.add(ActivityDate(activity_id=activiteit.id,
                                start_date=date.today() + timedelta(days=14)))
    db_session.flush()
    _ontwerp(db_session, activiteit)

    for pad in ("/", "/activiteiten", f"/activiteiten/{activiteit.id}"):
        html = client.get(pad).text
        assert "ontwerpen" not in html.lower(), pad
        assert "Design Studio" not in html, pad


def test_de_sprong_komt_uit_de_facade_en_niet_uit_de_interne_modules():
    """Het scherm leest de Design Studio via haar facade (#1049).

    Een grep, en dat volstaat hier: `test_import_boundaries.py` bewaakt de regel
    zelf: deze test zegt alleen dat DIT scherm haar volgt.
    """
    from pathlib import Path

    bron = (Path(__file__).resolve().parents[1]
            / "app/domains/activities/admin_ui.py").read_text()

    assert "from app.domains.designstudio.api import designs_for_activity" in bron
    assert not re.search(r"from app\.domains\.designstudio\.(?!api)", bron)

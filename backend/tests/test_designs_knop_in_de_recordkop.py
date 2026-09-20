"""De Design Studio-knop in de recordkop: één label, drie bestemmingen (#1070).

Gevraagd door Koen op 20 september 2026. De sprong naar de Design Studio (#1049)
stond in de rechterrail onder een eigen kopje *Affiche* — en dus alleen op het
tabblad Overzicht. Hij hoort naast *AI · Activiteit* in de recordkop, waar hij op
élke tab meereist.

**Eén label.** Koen vroeg, nadat er twee labels voorgesteld werden, of er niet
altijd één kan staan. Dat kan: het label is altijd *Designs* en de BESTEMMING
volgt het aantal ontwerpen. Een knop die altijd hetzelfde belooft, hoeft niets uit
te leggen en telt niets op wat niemand vroeg.

**De val die dit groter maakt dan een knop verplaatsen.** `_aa_recordkop.html`
wordt door vier sjablonen ingesloten, maar de context werd op twee plaatsen met de
hand samengesteld: in `activities.admin_ui` en in `payment.ui`. Templates renderen
onder `StrictUndefined`, dus een sleutel die op één van de twee ontbreekt geeft
geen leeg vlak maar een FOUT — op de tab Betalingen, en pas op HDEV. Er is nu één
bouwer (`record_kop_ctx`); de tabtest hieronder is de wacht daarop.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):

- `record_kop_ctx` altijd de lijst-URL laten teruggeven → **twee** van de drie
  taktesten vallen om (geen ontwerp en precies één). Dat is de tegenproef die het
  issue vraagt: valt er maar één om, dan toetsen ze niet elk hun eigen tak.
- `payment.ui` de kop weer zelf laten samenstellen zonder `designs_href` → de
  tabtest valt om met een StrictUndefined-fout, precies de val hierboven.

**#1087 (Koen, 20 september 2026, na HDEV):** de knop heet *Design Studio* — dat
belooft wat hij doet, waar *Designs* een lijst suggereerde — en de twee knoppen staan
naast elkaar. De kopregel is `justify-between`; met drie kinderen (titelblok, knop,
knop) hing de Design Studio-knop middenin. Nu vormen de knoppen één kind. De
structuurtest hieronder telt de directe kinderen van de kopregel; tegenproef: de
omhullende div weggehaald → hij valt om met drie kinderen. Met de beheer-assistent uit
is het paar één knop, en die staat nog steeds rechts (zelfde omhulling).
"""
import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def activiteit(db_session):
    a = Activity(name="Quiz met een affiche", location="Miloheem")
    db_session.add(a)
    db_session.flush()
    return a


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _ontwerp(db, activiteit):
    from app.domains.designstudio.api import create_design

    ontwerp = create_design(db, activity_id=activiteit.id,
                            duo_code="dark_green-golden_yellow",
                            created_by=SEEDED_ADMIN_EMAIL)
    db.flush()
    return ontwerp


def _kop(client, activiteit) -> str:
    antwoord = client.get(f"/admin/activiteiten/{activiteit.id}")
    assert antwoord.status_code == 200
    return antwoord.text


# ── Eén label, drie bestemmingen ─────────────────────────────────────────────

def test_zonder_ontwerp_wijst_de_knop_naar_aanmaken(client, db_session, activiteit):
    _login(client)
    html = _kop(client, activiteit)

    assert ">Design Studio</" in html
    assert f'href="/admin/ontwerpen/nieuw?activity_id={activiteit.id}"' in html


def test_met_precies_een_ontwerp_wijst_de_knop_naar_dat_ontwerp(client, db_session,
                                                                 activiteit):
    """De gewone handeling — "laat me mijn affiche zien" — is één klik korter.

    De prijs staat in het issue en is bewust aanvaard: je ziet de lijst dan niet
    meer, dus een tweede affiche maak je vanuit de Design Studio zelf.
    """
    ontwerp = _ontwerp(db_session, activiteit)
    _login(client)

    html = _kop(client, activiteit)

    assert ">Design Studio</" in html
    assert f'href="/admin/ontwerpen/{ontwerp.id}"' in html
    assert f'href="/admin/ontwerpen?activity_id={activiteit.id}"' not in html


def test_met_twee_ontwerpen_wijst_de_knop_naar_de_gefilterde_lijst(client, db_session,
                                                                    activiteit):
    _ontwerp(db_session, activiteit)
    _ontwerp(db_session, activiteit)
    _login(client)

    html = _kop(client, activiteit)

    assert ">Design Studio</" in html
    assert f'href="/admin/ontwerpen?activity_id={activiteit.id}"' in html
    assert "/admin/ontwerpen/nieuw" not in html


def test_het_label_verandert_nooit(client, db_session, activiteit):
    """De tegenhanger van de drie takken: het is één knop met één belofte.

    Zonder deze test zou "toon het aantal erbij" er stil weer in kunnen sluipen —
    en dat is precies wat #1070 wegnam.
    """
    _login(client)
    zonder = _kop(client, activiteit)
    _ontwerp(db_session, activiteit)
    met = _kop(client, activiteit)

    for html in (zonder, met):
        assert ">Design Studio</" in html
        assert "Ontwerpen:" not in html
        assert "Naar de Design Studio" not in html


# ── Naast elkaar (#1087) ─────────────────────────────────────────────────────

def _directe_kinderen_van_de_kopregel(html: str) -> list[str]:
    """De directe kind-elementen van de kopregel, als openingstags.

    Met een echte parser en niet met een regex: de vraag is structureel — hoeveel
    kinderen verdeelt `justify-between` de ruimte over — en dat zie je alleen met
    diepte."""
    from html.parser import HTMLParser

    class Teller(HTMLParser):
        def __init__(self):
            super().__init__()
            self.diepte = None
            self.kinderen: list[str] = []
            self.stapel: list[str] = []

        def handle_starttag(self, tag, attrs):
            klassen = dict(attrs).get("class", "")
            if self.diepte is None and "justify-between" in klassen and "mb-2" in klassen:
                self.diepte = len(self.stapel)
            elif self.diepte is not None and len(self.stapel) == self.diepte + 1:
                self.kinderen.append(f"<{tag} class=\"{klassen}\">")
            if tag not in ("input", "br", "img", "path", "meta", "link", "hr"):
                self.stapel.append(tag)

        def handle_endtag(self, tag):
            if self.stapel and self.stapel[-1] == tag:
                self.stapel.pop()
                if self.diepte is not None and len(self.stapel) == self.diepte:
                    self.diepte = -2  # de kopregel is dicht; niets telt nog mee

    teller = Teller()
    teller.feed(html)
    assert teller.diepte is not None, "de kopregel is niet gevonden"
    return teller.kinderen


@pytest.fixture
def assistent_aan(db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting
    from tests._reporting_seed import TENANT_A

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT_A)
    db_session.flush()


def test_met_beide_knoppen_heeft_de_kopregel_twee_kinderen(client, db_session, activiteit,
                                                           assistent_aan):
    """Titelblok links, knoppenpaar rechts. Drie kinderen is de fout van #1087."""
    _login(client)
    html = _kop(client, activiteit)
    assert "AI · Activiteit" in html, "voorwaarde: de AI-knop staat er"

    kinderen = _directe_kinderen_van_de_kopregel(html)
    assert len(kinderen) == 2, kinderen
    assert "Design Studio" not in kinderen[0] and "gap-2" in kinderen[1]


def test_zonder_assistent_staat_de_ene_knop_nog_steeds_rechts(client, db_session,
                                                              activiteit):
    """Eén knop in dezelfde omhulling: ook dan twee kinderen, en de knop in het
    tweede."""
    _login(client)
    html = _kop(client, activiteit)
    assert "AI · Activiteit" not in html, "voorwaarde: de beheer-assistent staat uit"
    assert ">Design Studio</" in html

    kinderen = _directe_kinderen_van_de_kopregel(html)
    assert len(kinderen) == 2, kinderen


# ── De StrictUndefined-val ───────────────────────────────────────────────────

@pytest.mark.parametrize("tab", ["inschrijvingen", "betalingen"])
def test_de_andere_tabs_renderen_en_dragen_dezelfde_knop(client, db_session,
                                                          activiteit, tab):
    """De kop wordt door vier sjablonen ingesloten; de context kwam van twee
    plekken. Zonder deze test valt dat pas op HDEV op — als een FOUT, want de
    templates renderen onder StrictUndefined.

    **Dit is meteen de bewaker van de één-bouwer-regel.** Stelt een aanroeper de
    kop weer zelf samen en vergeet hij een sleutel, dan faalt deze render met de
    naam van die sleutel erbij. Een bronscan die naar het ontbreken van symbolen
    zoekt, deed dat werk slechter — zie de notitie onderaan dit bestand.
    """
    ontwerp = _ontwerp(db_session, activiteit)
    _login(client)

    antwoord = client.get(f"/admin/activiteiten/{activiteit.id}/{tab}")

    assert antwoord.status_code == 200, antwoord.text[:400]
    assert ">Design Studio</" in antwoord.text
    assert f'href="/admin/ontwerpen/{ontwerp.id}"' in antwoord.text


# Hier stond een bronscan die naliep of `activities.admin_ui` en `payment.ui` de
# recordkop niet zelf samenstelden. Ze is WEGGEHAALD, en dat is een meting waard
# voor wie hem terug wil zetten: ze sloeg twee keer aan op een geldig geval en
# nul keer op een echt.
#
#   1. #1060 gaf `payment/ui.py` een eigen Raakje-ingang, met dezelfde
#      kernel-vlag die de scan verbood. Een poort die een SYMBOOL verbiedt,
#      verbiedt ook de gevallen die ze niet bedoelde.
#   2. Verfijnd naar de sleutels sloeg ze aan op `ctx["record_tabs"]` van de
#      GEZINStab — een andere recordkop, met een eigen tabbouwer. De sleutelnaam
#      is gedeeld; de regel geldt maar voor één van de koppen.
#
# Wat de duplicatie wél vangt, is de test hierboven: rendert een tab van de
# activiteit zonder fout? Stelt een aanroeper de kop weer zelf samen en vergeet
# hij een sleutel, dan faalt die render onder StrictUndefined — met de naam van
# de ontbrekende sleutel erbij. Dat is het gedrag zelf in plaats van een
# gelijkenis erop, en het heeft geen uitzonderingenlijst nodig.

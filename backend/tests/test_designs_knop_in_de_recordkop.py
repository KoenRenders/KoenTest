"""De Designs-knop in de recordkop: één label, drie bestemmingen (#1070).

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

    assert ">Designs</" in html
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

    assert ">Designs</" in html
    assert f'href="/admin/ontwerpen/{ontwerp.id}"' in html
    assert f'href="/admin/ontwerpen?activity_id={activiteit.id}"' not in html


def test_met_twee_ontwerpen_wijst_de_knop_naar_de_gefilterde_lijst(client, db_session,
                                                                    activiteit):
    _ontwerp(db_session, activiteit)
    _ontwerp(db_session, activiteit)
    _login(client)

    html = _kop(client, activiteit)

    assert ">Designs</" in html
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
        assert ">Designs</" in html
        assert "Ontwerpen:" not in html
        assert "Naar de Design Studio" not in html


# ── De StrictUndefined-val ───────────────────────────────────────────────────

@pytest.mark.parametrize("tab", ["inschrijvingen", "betalingen"])
def test_de_andere_tabs_renderen_en_dragen_dezelfde_knop(client, db_session,
                                                          activiteit, tab):
    """De kop wordt door vier sjablonen ingesloten; de context kwam van twee
    plekken. Zonder deze test valt dat pas op HDEV op — als een FOUT, want de
    templates renderen onder StrictUndefined."""
    ontwerp = _ontwerp(db_session, activiteit)
    _login(client)

    antwoord = client.get(f"/admin/activiteiten/{activiteit.id}/{tab}")

    assert antwoord.status_code == 200, antwoord.text[:400]
    assert ">Designs</" in antwoord.text
    assert f'href="/admin/ontwerpen/{ontwerp.id}"' in antwoord.text


def test_de_kop_komt_uit_een_bouwer_en_niet_uit_twee(client, db_session):
    """Eén bron voor de context van de recordkop (#1070).

    Een grep, en die volstaat hier: de twee aanroepers staan met naam in deze
    test, dus een derde plek die het weer zelf samenstelt valt hierop niet — maar
    een terugval van deze twee wel. Dat is precies de fout die dit issue blootlegde.
    """
    from pathlib import Path

    wortel = Path(__file__).resolve().parents[1] / "app" / "domains"
    for pad in ("activities/admin_ui.py", "payment/ui.py"):
        bron = (wortel / pad).read_text()
        assert "record_kop_ctx" in bron, pad
        assert "tenant_admin_chat_enabled" not in bron, (
            f"{pad} stelt de recordkop weer zelf samen")

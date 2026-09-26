"""Het vinkje bij een product zegt wat het doet (#1201).

Koen bij het valideren van #1191 op HDEV: *"Is 'Publiek boekbaar' het alternatief
voor actief? Ik vind dat geen goede vertaling."* Twee dingen klopten er niet aan.

**"Boeken" bestaat niet in deze applicatie** — overal heet het inschrijven. En
**"Actief" is hier niet het alternatief**, ook al heet de kolom `is_active`: op
Media betekent Actief "nergens", terwijl deze vlag betekent "weg van het publieke
formulier, maar het bestuur kan er nog bij". Dat onderscheid is de hele reden dat
#1191 bestaat, en een label "Actief" zou het uitwissen.

**Waarom hier één test staat en geen twee.** Het issue vroeg een test die bewaakt
dat de twee plaatsen — de bewerkrij en de aanmaakrij van hetzelfde product — niet
uiteen groeien. Dat is opgelost door ze niet te laten bestaan: label en hint staan
als `{% set %}` bovenaan het sjabloon, zoals `INTERNE_NOTA_BELOFTE` daar al stond
om precies dezelfde reden. Een poort die twee kopieën vergelijkt houdt de tweede
kopie in stand; dit telt dat beide plaatsen uit één bron renderen.

**De hint belooft niet meer dan v2.6.0 kan.** Hij zegt *toevoegen aan een
bestaande inschrijving* en niet *iemand inschrijven*: een `Registration` ontstaat
in deze release alleen langs de publieke weg, aanmaken vanuit het beheer komt met
#1192 op v2.7.0. Een hint die een handeling belooft die het scherm niet aanbiedt,
is erger dan het jargon dat we ermee vervangen — daarom staat de volledige zin
hieronder letterlijk in de assertie en niet als losse steekwoorden.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden. Twee proeven,
met wat er werkelijk omviel:
- **één van de twee plaatsen terug op `_("Publiek boekbaar")`**: 2 failed — de
  teltest met "het label staat 1 van de 2 keer", en de oude-woorden-test met
  "'Publiek boekbaar' staat nog op het activiteitscherm".
- **`PRODUCT_ZICHTBAAR_HINT` teruggezet op "…kan er nog iemand op inschrijven"**:
  ook 2 failed. Behalve de hint-test viel de teltest mee om, want die telt óók de
  hint — dat is geen ruis maar dezelfde bevinding langs twee wegen.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.activities.api import (Activity, ActivityDate, ActivityProduct,
                                        ActivitySubRegistration)
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

LABEL = "Op het inschrijfformulier"
HINT = ("Uit: het product verdwijnt van het publieke formulier, maar het bestuur "
        "kan het nog toevoegen aan een bestaande inschrijving.")
# Twee plaatsen: de bewerkrij van het bestaande product en de aanmaakrij eronder.
PLAATSEN = 2


@pytest.fixture
def activiteit_met_product(db_session):
    a = Activity(name="Bowlen met een product", location="Miloheem",
                 slug="bowlen-met-product")
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id,
                                start_date=date.today() + timedelta(days=21)))
    onderdeel = ActivitySubRegistration(activity_id=a.id, name="Deelname",
                                        price=Decimal("0"), is_free=True)
    db_session.add(onderdeel)
    db_session.flush()
    db_session.add(ActivityProduct(component_id=onderdeel.id, name="aantal deelnemers",
                                   price=Decimal("0"), is_free=False,
                                   pay_on_site=True))
    db_session.flush()
    return a


def _scherm(client, activiteit) -> str:
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    antwoord = client.get(f"/admin/activiteiten/{activiteit.id}")
    assert antwoord.status_code == 200, antwoord.status_code
    return antwoord.text


def test_beide_plaatsen_dragen_het_label_en_de_hint(client, db_session,
                                                    activiteit_met_product):
    """Eerst dát ze er staan, dan pas hoeveel.

    Nul treffers zou anders als geslaagd lezen — dan zou deze test groen blijven
    wanneer het vinkje helemaal verdwijnt.
    """
    html = _scherm(client, activiteit_met_product)

    assert LABEL in html, f"het label {LABEL!r} staat nergens op het scherm"
    assert HINT in html, f"de hint staat nergens op het scherm: {HINT!r}"
    assert html.count(LABEL) == PLAATSEN, (
        f"het label staat {html.count(LABEL)} van de {PLAATSEN} keer — de bewerkrij "
        "en de aanmaakrij van hetzelfde product horen het allebei te dragen")
    assert html.count(HINT) == PLAATSEN, (
        f"de hint staat {html.count(HINT)} van de {PLAATSEN} keer")


def test_de_hint_belooft_niet_meer_dan_deze_release_kan(client, db_session,
                                                        activiteit_met_product):
    """De volledige zin, letterlijk.

    Op steekwoorden toetsen zou "kan er nog iemand op inschrijven" laten passeren,
    en dat is precies de belofte die v2.6.0 niet waarmaakt: een inschrijving
    aanmaken vanuit het beheer kan pas met #1192.
    """
    html = _scherm(client, activiteit_met_product)

    assert HINT in html, (
        "de hint wijkt af van de afgesproken zin; hij hoort te zeggen dat het "
        f"bestuur het nog kan TOEVOEGEN aan een bestaande inschrijving:\n{HINT}")


def test_de_oude_woorden_zijn_weg(client, db_session, activiteit_met_product):
    """`boeken` bestaat nergens anders in deze UI, en `Actief` zou het verschil
    met "nergens" uitwissen — zie #1191."""
    html = _scherm(client, activiteit_met_product)

    for woord in ("Publiek boekbaar", "boekbaar"):
        assert woord not in html, (
            f"{woord!r} staat nog op het activiteitscherm")

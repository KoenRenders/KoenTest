"""Query-budget per lijstscherm (#645 D) — een N+1 komt niet stil terug.

Met htmx is de snelheid van de UI gelijk aan de snelheid van de server. Een
lijstscherm dat per rij een extra query doet, valt bij tien rijen niet op en bij
tweehonderd wel — en dan is het al maanden zo. Deze gate telt de queries van een
scherm bij een gevulde databank en begrenst ze.

**Twee gates met een verschillende rol** (#1058, 20 september 2026):

* het **plafond** per scherm is een grove bovengrens. Het mag meegeven als er werk
  bijkomt, mét een reden in de commit — het plafond van het activiteitendetail ging
  in vier dagen drie keer omhoog en alle drie terecht. Het vangt wat de andere niet
  vangt: een scherm dat zestig VASTE vragen stelt is traag zonder mee te schalen.
* de **verschiltest** meet hetzelfde scherm bij twee databankgroottes en eist dat
  het aantal gelijk is. Die mag nooit bewegen: "schaalt niet mee met de data" is
  de eigenschap die ertoe doet, en die verandert niet als er een functie bijkomt.

Zonder die tweede meet het plafond op den duur "hoeveel functies staan er op dit
scherm", en is een verhoging die wél meeschaalt niet te onderscheiden van een die
dat niet doet.

Faalt een gate, dan toont ze het aantal en de vijf meest herhaalde statements,
zodat je meteen ziet wélke query zich herhaalt.

Kapotgemaakt om te controleren dat de verschiltest het onderscheid werkelijk maakt
(gemeten op 20 september 2026, allebei op het activiteitendetail):

* een echte **N+1** erin — `db.query(Activity).all()` en per rij `poster_asset_url`
  aanraken — gaf *"26 vragen bij 5 rijen per soort, 66 bij 45 — dit scherm schaalt
  mee met de data"*, met de herhaalde media-query bovenaan het rapport;
* één **vaste** extra vraag (`db.query(Activity).count()`) liet de verschiltest
  **groen** en deed alleen het plafond aanslaan (20 tegen 19). Dat is de toets die
  bewijst dat de nieuwe gate iets anders meet dan de oude.
"""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.database import engine
from app.domains.auth.api import SESSION_COOKIE, make_session_value

from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_activity_with_product, seed_postal_code)

pytestmark = pytest.mark.ui_serverrendered

# Plafond per scherm. Verlaag na een fix; verhogen mag alleen met een reden in de
# commit — dat is precies het gesprek dat deze gate wil afdwingen.
BUDGET = {
    "/admin/leden": 30,
    "/admin/activiteiten": 40,
    "/admin/betalingen": 40,
    "/admin/ledenwijzigingen": 40,
    "/admin/werkbank": 25,
    # Gemeten: 4 (rolcheck, keuzelijst, media-activiteit-ids, medialijst). Bewust
    # krap: een terugval naar `list_activities` voegt de selectinloads voor datums,
    # onderdelen en producten toe plus de bezettingsberekening — samen ruim boven
    # dit plafond, en dát is precies de regressie die deze regel moet vangen (#645).
    "/admin/media": 6,
    "/activiteiten": 40,
}

AANTAL_GEZINNEN = 40
AANTAL_INSCHRIJVINGEN = 40
# Genoeg activiteiten dat het verschil tussen een lichte keuzelijst-query en de
# volledige lijstbewerking zichtbaar wordt (#645). Let op wat deze gate wél en
# niet vangt: ze telt query's, niet rijen. De bevinding op /admin/media was
# rij-volume — `list_activities` doet met selectinload een vást aantal query's,
# hoeveel activiteiten er ook zijn. Wat de gate hier bewaakt, is dat de
# eager-loading-query's (datums, onderdelen, producten) en de subquery's voor de
# datumsortering niet terugkeren op dit scherm.
AANTAL_ACTIVITEITEN = 15


class Queryteller:
    """Telt SQL-statements op de engine zolang de contextmanager loopt."""

    def __init__(self):
        self.statements: list[str] = []

    def __enter__(self):
        @event.listens_for(engine, "before_cursor_execute")
        def _tel(conn, cursor, statement, params, context, executemany):
            self.statements.append(statement)

        self._handler = _tel
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._handler)
        return False

    def __len__(self):
        return len(self.statements)

    def rapport(self) -> str:
        vaakst = Counter(s.split("\n")[0][:100] for s in self.statements).most_common(5)
        regels = [f"{n}x  {s}" for s, n in vaakst]
        return "\n    ".join(regels)


def _vul(db_session, *, activiteiten: int, gezinnen: int, inschrijvingen: int,
         vanaf: int = 0, doel=None):
    """Voeg rijen TOE aan de databank; geef het drietal terug om op te bouwen.

    #1058 maakte hier een fabriek van. Ze is bewust **aanvullend** en niet
    "zet de databank op N": de verschiltest meet hetzelfde scherm twee keer in
    dezelfde transactie, en dan is groeien de enige manier om een tweede grootte te
    krijgen. `vanaf` houdt de e-mailadressen en namen uniek tussen twee rondes.
    """
    from datetime import timedelta

    from app.domains.activities.api import (Activity, ActivityDate, Registration,
                                            RegistrationItem)
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    if doel is None:
        seed_postal_code(db_session)
        doel = seed_activity_with_product(db_session, is_free=False)
    activity, component, product = doel

    for i in range(vanaf, vanaf + activiteiten):
        extra = Activity(name=f"Budgetactiviteit {i}")
        db_session.add(extra)
        db_session.flush()
        db_session.add(ActivityDate(activity_id=extra.id,
                                    start_date=date.today() - timedelta(days=30 * i)))

    jaar = date.today().year
    for i in range(vanaf, vanaf + gezinnen):
        member, _person = create_test_family(db_session, email=f"budget{i}@example.com")
        db_session.add(Membership(member_id=member.id, year=jaar, is_active=True,
                                  valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31)))
        db_session.add(PaymentRecord(
            payable_type="membership", payable_id=member.id, type="charge",
            amount=Decimal("20.00"), method="transfer", status="pending"))

    for i in range(vanaf, vanaf + inschrijvingen):
        registratie = Registration(activity_id=activity.id, component_id=component.id,
                                   registration_type="INDIVIDUAL",
                                   contact_name=f"Budget {i}",
                                   contact_email=f"reg{i}@example.com")
        db_session.add(registratie)
        db_session.flush()
        db_session.add(RegistrationItem(registration_id=registratie.id,
                                        product_id=product.id, quantity=2))
        db_session.add(PaymentRecord(
            payable_type="registration", payable_id=registratie.id, type="charge",
            amount=Decimal("20.00"), method="transfer", status="pending"))
    db_session.commit()
    return doel


@pytest.fixture
def gevulde_databank(client, db_session):
    """Genoeg rijen dat een N+1 niet meer binnen een plafond past."""
    _vul(db_session, activiteiten=AANTAL_ACTIVITEITEN, gezinnen=AANTAL_GEZINNEN,
         inschrijvingen=AANTAL_INSCHRIJVINGEN)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    return client


# Het activiteitdetail staat niet in BUDGET: zijn pad heeft een id nodig, en dat
# komt pas uit de fixture. En het heeft een ándere gate nodig — zie hieronder.
# Beide plafonds zijn gemeten, niet geschat, en tegen de oude weg gehouden:
#
#                        ná de fix      de oude weg (list_activities scope=all)
#   query's                    12                                           44
#   opgehaalde rijen           10                                           40
#
# Twee grenzen, want ze vangen niet hetzelfde. Het rijenplafond vangt het
# volume: de lijstbewerking laadde datums, onderdelen en producten van álle
# activiteiten om er daarna één uit te vissen. Het querybudget vangt de N+1 die
# daarin verstopt zat — `ActivityResponse` leest `poster_asset_url` én
# `poster_asset_is_pdf`, en elk van die twee properties doet een eigen query per
# activiteit (models.py:59-68). Vandaar 44 bij zestien activiteiten.
#
# Allebei schalen ze mee met AANTAL_ACTIVITEITEN, dus een terugval wordt met de
# fixture alleen maar duidelijker zichtbaar.
# 16 → 17 op 15 september 2026 (golf 8, #913): de recordpagina kreeg tabs en
# een rechterrail — dat kost precies één extra COUNT (inschrijvingen) naast de
# bestaande zonder-onderdeel-telling; bezetting en betalingen-tel zijn elk één
# query. Een verdere stijging is weer een bevinding.
# 17 → 18 op 18 september 2026 (#1004): de organisatoren van de activiteit. Eén
# query zolang er geen zijn; met organisatoren komen er twee bij (personen en
# contactgegevens), en dat schaalt niet mee met het aantal activiteiten. Gemeten
# met een warme cache — zie de opmerking in de test zelf.
# 18 → 19 op 20 september 2026 (#1049): de sprong naar de Design Studio leest de
# ontwerpen van déze activiteit. Eén query, die niet meeschaalt met het aantal
# activiteiten — het scherm toont het aantal en kiest de bestemming, dus het moet
# ze tellen. Gemeten met een warme cache, zoals de opmerking in de test zegt.
BUDGET_ACTIVITEITDETAIL = 19
RIJEN_ACTIVITEITDETAIL = 20


class Rijenteller(Queryteller):
    """Telt óók de opgehaalde rijen, niet enkel de statements.

    psycopg2 zet `rowcount` bij een SELECT meteen na execute; -1 betekent
    "niet van toepassing" (DDL, sommige DML) en telt niet mee.
    """

    def __init__(self):
        super().__init__()
        self.rijen = 0

    def __enter__(self):
        super().__enter__()

        @event.listens_for(engine, "after_cursor_execute")
        def _tel_rijen(conn, cursor, statement, params, context, executemany):
            aantal = getattr(cursor, "rowcount", -1)
            if aantal and aantal > 0:
                self.rijen += aantal

        self._rij_handler = _tel_rijen
        return self

    def __exit__(self, *exc):
        event.remove(engine, "after_cursor_execute", self._rij_handler)
        return super().__exit__(*exc)


def test_het_activiteitdetail_haalt_niet_de_hele_lijst_op(gevulde_databank, db_session):
    """#651: het detail van één activiteit hergebruikte de volledige lijst.

    Op HDEV kostte het detail van ÉÉN activiteit meer dan de lijst van alle 167
    (483 ms tegen 89 ms), en omdat het de gedeelde render-helper is, betaalde élke
    mutatie op dat scherm die prijs opnieuw.

    Een tijdmeting is te wisselvallig voor CI, dus meten we wat de traagheid
    veroorzaakte: opgehaalde rijen én query's. Zie de plafonds hierboven voor de
    gemeten getallen van beide implementaties.
    """
    from app.domains.activities.api import Activity

    activiteit = db_session.query(Activity).filter(
        Activity.name == "Testactiviteit").first()
    assert activiteit is not None, "de fixture levert geen activiteit om te openen"
    pad = f"/admin/activiteiten/{activiteit.id}"

    # Eén keer opvragen vóór de meting (#1004). De tenant-caches (code→id,
    # platform-tenant) zijn procesbreed en koud bij de eerste aanroep in een
    # proces: dan telt de gate drie cachemissers mee die niets met dit scherm te
    # maken hebben. Gemeten: koud 20, warm 17 op dezelfde code — dus stond het
    # plafond te halen of niet naargelang de volgorde van de testbestanden.
    gevulde_databank.get(pad)

    with Rijenteller() as teller:
        antwoord = gevulde_databank.get(pad)

    assert antwoord.status_code == 200, pad
    assert teller.rijen <= RIJEN_ACTIVITEITDETAIL, (
        f"{pad}: {teller.rijen} rijen opgehaald (plafond {RIJEN_ACTIVITEITDETAIL}) "
        f"naast {AANTAL_ACTIVITEITEN} andere activiteiten. Haalt dit scherm de "
        f"volledige lijst op?\n    Meest herhaalde statements:\n    {teller.rapport()}"
    )
    assert len(teller) <= BUDGET_ACTIVITEITDETAIL, (
        f"{pad}: {len(teller)} queries (budget {BUDGET_ACTIVITEITDETAIL}).\n"
        f"    Meest herhaalde statements:\n    {teller.rapport()}"
    )


# ── De gate die niet mag bewegen: schaalt het scherm mee? (#1058) ────────────
#
# Het plafond hierboven ging in vier dagen drie keer omhoog, en elke keer terecht:
# vaste vragen die niet meeschalen. Maar een plafond dat bij elke nieuwe functie
# meegeeft, meet op den duur "hoeveel functies staan er op dit scherm" — en dan is
# de dag dat iemand een verhoging doorvoert die WEL meeschaalt, niet te
# onderscheiden van de drie die dat niet deden.
#
# Daarom twee gates met een verschillende rol, en dat verschil hoort hier te staan
# zodat de volgende de verhogingen hierboven niet als slordigheid leest:
#
#   * het PLAFOND is een grove bovengrens. Het mag meegeven als er werk bijkomt —
#     mét een reden in de commit. Het vangt wat de verschiltest niet vangt: een
#     scherm dat zestig VASTE vragen stelt, is traag zonder mee te schalen.
#   * de VERSCHILTEST hieronder mag nooit bewegen. Ze meet hetzelfde scherm bij
#     twee databankgroottes en eist dat het aantal gelijk is. Die eigenschap
#     verandert niet als er een functie bijkomt.
#
# De groottes liggen ver genoeg uiteen dat één N+1 tientallen vragen scheelt, en de
# grote is ongeveer het volume van `gevulde_databank` — zwaarder maakt de suite
# trager zonder iets extra te bewijzen.
SCHAAL_KLEIN = 5
SCHAAL_GROOT = 45


def _meet(client, pad) -> Queryteller:
    """Eén meting, met een opwarmronde erbij.

    De tenant-caches zijn procesbreed en koud bij de eerste aanroep in een proces;
    die drie cachemissers horen niet bij het scherm. #1004 warmde één keer op, vóór
    één meting. Hier moet het bij ÉLKE meting, anders zou het verschil tussen de
    twee groottes de cache kunnen zijn in plaats van de data.
    """
    client.get(pad)
    with Queryteller() as teller:
        antwoord = client.get(pad)
    assert antwoord.status_code == 200, f"{pad}: {antwoord.status_code}"
    return teller


def _verschiltest(client, db_session, pad_van):
    """Meet `pad_van(doel)` klein, laat de databank groeien, meet opnieuw."""
    doel = _vul(db_session, activiteiten=SCHAAL_KLEIN, gezinnen=SCHAAL_KLEIN,
                inschrijvingen=SCHAAL_KLEIN)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    pad = pad_van(doel)

    klein = _meet(client, pad)

    groei = SCHAAL_GROOT - SCHAAL_KLEIN
    _vul(db_session, activiteiten=groei, gezinnen=groei, inschrijvingen=groei,
         vanaf=SCHAAL_KLEIN, doel=doel)

    groot = _meet(client, pad)

    assert len(klein) == len(groot), (
        f"{pad}: {len(klein)} vragen bij {SCHAAL_KLEIN} rijen per soort, "
        f"{len(groot)} bij {SCHAAL_GROOT} — dit scherm schaalt mee met de data.\n"
        f"    Meest herhaalde statements bij {SCHAAL_GROOT}:\n    {groot.rapport()}"
    )


def test_het_activiteitdetail_schaalt_niet_mee(client, db_session):
    """Waar de drift zat (#1058). De plafondtest hierboven staat erboven, niet
    ervoor: die twee vangen niet hetzelfde."""
    _verschiltest(client, db_session,
                  lambda doel: f"/admin/activiteiten/{doel[0].id}")


# Gemeten, scherm per scherm, op 20 september 2026 (#1058): alle zeven zijn vlak —
# hetzelfde aantal vragen bij 5 en bij 45 rijen per soort. Geen enkel scherm is hier
# opgenomen zonder die meting; een lijst die je niet gemeten hebt, hoort niet stil in
# een gate te belanden alsof ze bewezen is.
@pytest.mark.parametrize("pad", sorted(BUDGET))
def test_een_lijstscherm_schaalt_niet_mee(client, db_session, pad):
    _verschiltest(client, db_session, lambda _doel: pad)


@pytest.mark.parametrize("pad", sorted(BUDGET))
def test_een_lijstscherm_blijft_binnen_zijn_querybudget(gevulde_databank, pad):
    with Queryteller() as teller:
        antwoord = gevulde_databank.get(pad)

    assert antwoord.status_code == 200, pad
    assert len(teller) <= BUDGET[pad], (
        f"{pad}: {len(teller)} queries (budget {BUDGET[pad]}) bij "
        f"{AANTAL_GEZINNEN} gezinnen en {AANTAL_INSCHRIJVINGEN} inschrijvingen.\n"
        f"    Meest herhaalde statements:\n    {teller.rapport()}"
    )

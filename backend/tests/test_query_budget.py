"""Query-budget per lijstscherm (#645 D) — een N+1 komt niet stil terug.

Met htmx is de snelheid van de UI gelijk aan de snelheid van de server. Een
lijstscherm dat per rij een extra query doet, valt bij tien rijen niet op en bij
tweehonderd wel — en dan is het al maanden zo. Deze gate telt de queries van een
scherm bij een gevulde databank en begrenst ze.

De budgetten zijn **ruim** en vast: ze staan op wat het scherm vandaag nodig heeft,
afgerond naar boven. Ze zijn geen doel maar een plafond — verlaag ze wanneer een
fix het aantal omlaag brengt, zodat de winst niet stilletjes weer weglekt. Faalt
de gate, dan toont ze het aantal en de eerste vijf statements, zodat je meteen
ziet wélke query zich herhaalt.

Belangrijk: het budget mag **niet** met de hoeveelheid data meeschalen. Daarom
vult de fixture veertig gezinnen en veertig inschrijvingen — bij een N+1 loopt het
aantal queries dan zo ver op dat geen enkel redelijk plafond nog past.
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


@pytest.fixture
def gevulde_databank(client, db_session):
    """Genoeg rijen dat een N+1 niet meer binnen een plafond past."""
    from app.domains.activities.api import Registration, RegistrationItem
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    seed_postal_code(db_session)
    activity, component, product = seed_activity_with_product(db_session, is_free=False)

    from datetime import timedelta

    from app.domains.activities.api import Activity, ActivityDate

    for i in range(AANTAL_ACTIVITEITEN):
        extra = Activity(name=f"Budgetactiviteit {i}")
        db_session.add(extra)
        db_session.flush()
        db_session.add(ActivityDate(activity_id=extra.id,
                                    start_date=date.today() - timedelta(days=30 * i)))

    jaar = date.today().year
    for i in range(AANTAL_GEZINNEN):
        member, _person = create_test_family(db_session, email=f"budget{i}@example.com")
        db_session.add(Membership(member_id=member.id, year=jaar, is_active=True,
                                  valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31)))
        db_session.add(PaymentRecord(
            payable_type="membership", payable_id=member.id, type="charge",
            amount=Decimal("20.00"), method="transfer", status="pending"))

    for i in range(AANTAL_INSCHRIJVINGEN):
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

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    return client


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

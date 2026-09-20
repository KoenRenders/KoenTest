"""Een gelijkstand op `sort_order` mag de volgorde niet laten wisselen (#1068).

Voortgekomen uit PR #1063: een test viel op CI om omdat de onderdelen van een
activiteit in een andere volgorde stonden dan lokaal — dezelfde code, dezelfde
data. `sort_order` staat standaard op 0, en bij een gelijkstand mag Postgres de
rijen teruggeven in de volgorde die hem uitkomt. Daar is toen de id als tweede
sleutel bijgekomen.

**Het issue noemde twee achterblijvers; het is er één.** Nagemeten bij het
bouwen: `activity_organisers` draagt sinds migratie 133 een unieke sleutel op
(activity_id, sort_order) én een CHECK op 0/1/2 — daar kan geen gelijkstand
bestaan. Alleen `ActivityProduct` mist dat patroon. De organisatoren krijgen
daarom geen tiebreak maar een test op die sleutel: valt ze weg, dan klopt de
redenering niet meer.

**Twee metingen bepalen de vorm van deze tests**, en ze staan er allebei bij
omdat de volgende ze anders opnieuw moet doen. Met zestig producten waarvan de
eerste dertig bijgewerkt: rauwe SQL met `ORDER BY sort_order` geeft
`[31..60, 1..30]` — de gelijkstand klapt dus echt om — maar dezelfde lading via de
ORM-relatie geeft `[1..60]`, óók zonder tiebreak, want de soft-delete-voorwaarde
zet de planner op een ander pad. Een gedragstest zou hier dus groen blijven bij
een kapotte sortering. Daarom toetst de producttest de CLAUSULE, met de meting in
haar docstring.

`DesignHighlight` en `DesignLogo` staan hier bewust NIET bij: die dragen een
unieke sleutel op `(design_id, sort_order)`, dus een gelijkstand kan er niet
bestaan. Dat is het patroon dat deze twee missen.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
`id` uit de `order_by` van `products` halen → de clausuletest valt om, en de
"eigen volgorde wint"-test blijft groen (die toetst iets anders). De unieke
sleutel van de organisatoren laten vallen zou de sleuteltest laten omvallen; die
staat in de databank en niet in de code, dus daar is de test zelf het bewijs.
"""
from decimal import Decimal

import pytest
from app.domains.activities.api import (Activity, ActivityProduct,
                                        ActivitySubRegistration)
# `ActivityOrganiser` staat niet op de facade — die exporteert de VIEW
# (`OrganiserView`) en de bewerkingen, niet de tabel. Voor een sorteertest op de
# relatie zelf is het model nodig; de laaggate geldt voor productiecode.
from app.domains.activities.models import ActivityOrganiser

pytestmark = pytest.mark.ui_agnostisch

def _activiteit(db):
    a = Activity(name="Sorteerproef")
    db.add(a)
    db.flush()
    return a


def _onderdeel(db, a):
    c = ActivitySubRegistration(activity_id=a.id, name="Onderdeel",
                                registration_type_code="INDIVIDUAL",
                                price=Decimal("0"), is_free=True)
    db.add(c)
    db.flush()
    return c


# ── Organisatoren: geen tiebreak nodig, en waarom ───────────────────────────

def test_organisatoren_kunnen_geen_gelijkstand_hebben(db_session):
    """De databank verbiedt het, dus er valt niets te ordenen (#1068).

    Het issue noemde deze relatie als tweede geval. Nagemeten bij het bouwen:
    migratie 133 legt `uq_activity_organiser_order` op (activity_id, sort_order),
    plus een CHECK die `sort_order` tot 0, 1 of 2 beperkt. Precies het patroon dat
    `DesignHighlight` en `DesignLogo` ook hebben — en dat de producten missen.

    Daarom staat hier een test op de SLEUTEL en niet op de sortering: verdwijnt
    die unieke sleutel ooit, dan klopt de redenering in `models.py` niet meer en
    hoort de id-tiebreak er alsnog bij te komen. Deze test is de wacht daarop.
    """
    from sqlalchemy.exc import IntegrityError

    a = _activiteit(db_session)
    db_session.add(ActivityOrganiser(activity_id=a.id, person_id=1, sort_order=0))
    db_session.flush()
    db_session.add(ActivityOrganiser(activity_id=a.id, person_id=2, sort_order=0))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ── Producten van een onderdeel ──────────────────────────────────────────────

def test_de_productvolgorde_belooft_de_id_als_tweede_sleutel():
    """De relatie sorteert op `sort_order` én `id` (#1068).

    Dit toetst de BELOFTE en niet één uitkomst, en dat is een keuze met een
    meting eronder. Nagemeten op deze codebase, met zestig producten waarvan de
    eerste dertig bijgewerkt:

    * `SELECT ... WHERE component_id = :c ORDER BY sort_order` geeft
      `[31..60, 1..30]` — de gelijkstand klapt dus echt om;
    * dezelfde lading via de ORM-relatie geeft `[1..60]`, óók zonder de
      tiebreak. De globale soft-delete-voorwaarde (`deleted_at IS NULL`) zet de
      planner op een ander pad, en dat pad gaf hier toevallig de id-volgorde.

    Een gedragstest zou dus groen blijven bij een kapotte sortering — precies de
    val waar dit issue uit voortkomt. Wat wél vastligt is de clausule; haal de
    `id` eruit en deze test valt om (gemeten). Dat "toevallig" is de reden dat de
    tiebreak er hoort te staan: een ander queryplan — een andere filter, een
    join, een `selectinload` over meerdere onderdelen — hoeft die volgorde niet
    te geven. Zo is het bij de onderdelen op CI misgegaan (#1063).
    """
    namen = [getattr(k, "name", str(k))
             for k in ActivitySubRegistration.products.property.order_by]

    assert namen == ["sort_order", "id"], namen


def test_een_eigen_productvolgorde_wint_van_de_id(db_session):
    a = _activiteit(db_session)
    comp = _onderdeel(db_session, a)
    for naam, order in (("Laatste", 2), ("Midden", 1), ("Eerste", 0)):
        db_session.add(ActivityProduct(component_id=comp.id, name=naam,
                                       price=Decimal("1.00"), is_free=False,
                                       sort_order=order))
    db_session.flush()
    db_session.expire_all()

    vers = db_session.get(ActivitySubRegistration, comp.id)

    assert [p.name for p in vers.products] == ["Eerste", "Midden", "Laatste"]

"""Een dimensie met meerdere rijen mag geen som opblazen (#1114).

Een dimensie die méér dan één rij per koppelsleutel heeft, vermenigvuldigt de
rijen van het feit waaraan ze hangt. Elke maat die niet op `DISTINCT` steunt telt
dan dubbel — en niemand ziet het, want het rapport klopt met zichzelf.

Gevonden bij #1077, waar `d_activity_organiser` de eerste dimensie werd die dit
per ontwerp doet: een activiteit heeft tot drie organisatoren. Die hangt daarom
alleen aan `f_activities`, dat precies één maat draagt en die is
`COUNT(DISTINCT activity_id)`. Dezelfde join op `f_payments` zou een
`SUM(amount)` verdubbeld hebben — stil, en in geld.

**Dat was een afhankelijkheid en geen voorziening**, en dat is de reden dat deze
poort bestaat. `additive` in het universum beschrijft precies deze eigenschap,
maar staat er expliciet in als *gedeclareerd en niet afgedwongen*. Hier wordt ze
afgedwongen.

De poort kijkt **vooruit** en niet naar de huidige toestand. De twee manieren
waarop dit morgen stukgaat, staan hieronder allebei als tegenproef:

1. iemand voegt een som-maat toe aan een feit dat al aan zo'n dimensie hangt;
2. iemand hangt de dimensie aan een tweede feit, omdat "per organisator" daar ook
   een nuttige vraag lijkt.

Kapotgemaakt om te controleren dat deze poort rood kan worden (gemeten, en beide
ingrepen apart gedraaid):

- een `SUM`-maat op `f_activities` → rood, met `f_activities`,
  `d_activity_organiser` en de naam van die maat in de melding;
- `Join("f_payments", "d_activity_organiser", …)` erbij → rood, met alle drie de
  geldmaten van dat feit opgesomd;
- `multi_row=True` weghalen bij de organisatoren → de laatste test hieronder valt
  om, die eist dat de poort überhaupt iets te controleren had. Zonder die test
  slaagt deze poort stil zodra er geen enkele meerrijige dimensie meer is — en
  dan bewaakt ze niets meer terwijl ze groen staat.
"""
from __future__ import annotations

import re

from app.domains.reporting.universe import DIMENSIONS, JOINS, OBJECTS

#: Een maat is bestand tegen vermenigvuldiging als ze telt wat ze telt op een
#: SLEUTEL en niet op een rij. `COUNT(DISTINCT x)` levert hetzelfde getal of je
#: elke rij nu één of drie keer ziet; `SUM(x)` en `COUNT(x)` niet.
_VEILIG = re.compile(r"\bDISTINCT\b", re.I)

#: Dimensies die per ontwerp meer dan één rij per koppelsleutel hebben.
MEERRIJIG = {d.key for d in DIMENSIONS if d.multi_row}


def _bereikbaar(feit: str) -> set[str]:
    """Elke dimensie die aan dit feit hangt, ook via een snowflake.

    De keten telt mee: hangt `d_address` aan `d_person` en `d_person` aan een
    feit, dan vermenigvuldigt een meerrijige `d_address` de rijen van dát feit.
    """
    uit: set[str] = set()
    te_doen = [feit]
    while te_doen:
        links = te_doen.pop()
        for join in JOINS:
            if join.left == links and join.dimension not in uit:
                uit.add(join.dimension)
                te_doen.append(join.dimension)
    return uit


def _maten_van(feit: str) -> list:
    return [o for o in OBJECTS if o.is_measure and o.fact == feit]


def _feiten_met_maten() -> set[str]:
    return {o.fact for o in OBJECTS if o.is_measure and o.fact}


def test_geen_maat_kan_opblazen_door_een_meerrijige_dimensie():
    """De poort zelf.

    De melding noemt het feit, de dimensie én de maat — alle drie, want de lezer
    moet kunnen kiezen welke van de drie hij aanpast: de maat op `DISTINCT`
    zetten, de join weghalen, of de dimensie op één rij per sleutel knijpen.
    """
    klachten: list[str] = []
    for feit in sorted(_feiten_met_maten()):
        boosdoeners = sorted(_bereikbaar(feit) & MEERRIJIG)
        if not boosdoeners:
            continue
        for maat in _maten_van(feit):
            if _VEILIG.search(maat.sql):
                continue
            klachten.append(
                f"{feit} hangt aan {', '.join(boosdoeners)} (meerdere rijen per "
                f"sleutel) en draagt '{maat.name}' ({maat.key}) met "
                f"{maat.sql.replace('{view}', feit)} — die telt dubbel zodra de "
                f"dimensie meer dan één rij levert. Kies: de maat op COUNT(DISTINCT), "
                f"de join weg, of de dimensie op één rij per sleutel."
            )

    assert not klachten, "\n".join(klachten)


def test_de_poort_had_werkelijk_iets_te_controleren():
    """Een poort die over niets loopt, slaagt stil.

    Deze test is de tegenhanger van de vorige: die kan groen staan omdat alles
    klopt, óf omdat er geen enkele meerrijige dimensie meer is en de lus dus nooit
    draaide. Dat onderscheid moet zichtbaar zijn — het is dezelfde val als een
    grep die nul treffers heeft en daarmee "geen overtredingen" lijkt te zeggen.
    """
    assert MEERRIJIG, (
        "geen enkele dimensie staat op multi_row — is de vlag verdwenen, of "
        "hangt `d_activity_organiser` er niet meer? Dan bewaakt de poort niets.")

    gecontroleerd = [f for f in _feiten_met_maten() if _bereikbaar(f) & MEERRIJIG]
    assert gecontroleerd, (
        f"{MEERRIJIG} hangt aan geen enkel feit met maten, dus de poort hierboven "
        "heeft geen enkele maat bekeken.")
    assert any(_maten_van(f) for f in gecontroleerd)


def test_de_keten_telt_mee_en_niet_alleen_de_directe_join():
    """Een snowflake vermenigvuldigt net zo goed.

    `d_address` hangt aan `d_person` en niet aan een feit; zou ze meerrijig
    worden, dan moet de poort dat zien via de keten. Deze test toetst de
    doorloop zelf, zodat een latere vereenvoudiging naar 'alleen directe joins'
    opvalt.
    """
    via_persoon = _bereikbaar("f_registrations")

    assert "d_person" in via_persoon, "de directe join ontbreekt"
    assert "d_address" in via_persoon, (
        "d_address hangt aan d_person en hoort via de keten bereikbaar te zijn")

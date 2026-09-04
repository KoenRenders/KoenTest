"""Broers en zussen herordenen (#635 E).

Dezelfde handeling stond twee keer, met twee algoritmen: activiteiten
normaliseerden `sort_order` naar 0..n en wisselden dan met de buur, formulieren
wisselden alleen twee `position`-waarden. Dat tweede werkt niet als alle waarden
nog op hun default staan — dan is er niets te wisselen en gebeurt er niets, zonder
foutmelding.

Eén helper, met het strengere van de twee: eerst normaliseren (zodat er altijd
distincte waarden zijn), dan wisselen. Kernel-code, dus zonder domeinkennis: welke
attribuutnaam de volgorde draagt, zegt de aanroeper.
"""
from typing import Any, Literal, Sequence

Richting = Literal["up", "down"]

# De woorden die de twee schermen in hun formulier gebruiken. Ze staan hier zodat
# de helper niet per aanroeper opnieuw vertaald hoeft te worden.
_OMHOOG = {"up", "op", "omhoog"}


def move_sibling(items: Sequence[Any], item_id: int, direction: str, *,
                 attr: str = "sort_order") -> bool:
    """Verplaats één item één plaats binnen zijn broers/zussen.

    Normaliseert `attr` eerst naar 0..n — ook als alles nog op de default staat —
    en wisselt daarna met de buur. Commit niet: de aanroeper bepaalt de
    transactiegrens (#635 regel 2).

    Geeft terug of er iets verplaatst is; buiten bereik (bovenste omhoog, onderste
    omlaag) is een no-op, geen fout.
    """
    geordend = sorted(items, key=lambda item: (getattr(item, attr) or 0, item.id))
    for index, item in enumerate(geordend):
        setattr(item, attr, index)

    positie = next((i for i, item in enumerate(geordend) if item.id == item_id), None)
    if positie is None:
        return False

    buur = positie - 1 if direction in _OMHOOG else positie + 1
    if not (0 <= buur < len(geordend)):
        return False

    huidig, ander = geordend[positie], geordend[buur]
    huidige_waarde = getattr(huidig, attr)
    setattr(huidig, attr, getattr(ander, attr))
    setattr(ander, attr, huidige_waarde)
    return True

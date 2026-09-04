"""Herordenen van broers en zussen (#635 E).

Activiteiten en formulieren deden dit met twee verschillende algoritmen. Het
formulier-algoritme wisselde alleen twee waarden — en dat werkt niet zolang alle
posities nog op hun default staan: dan valt er niets te wisselen en gebeurt er
stil niets. De gedeelde helper normaliseert eerst, en dat gedrag wordt hier
vastgelegd zonder scherm en zonder databank.
"""
from types import SimpleNamespace

import pytest

from app.kernel.ordering import move_sibling

pytestmark = pytest.mark.ui_agnostisch


def items(*posities, attr="sort_order"):
    return [SimpleNamespace(id=i + 1, **{attr: p}) for i, p in enumerate(posities)]


def volgorde(lijst, attr="sort_order"):
    return [item.id for item in sorted(lijst, key=lambda x: getattr(x, attr))]


def test_omhoog_wisselt_met_de_bovenbuur():
    lijst = items(0, 1, 2)
    assert move_sibling(lijst, item_id=3, direction="up") is True
    assert volgorde(lijst) == [1, 3, 2]


def test_omlaag_wisselt_met_de_onderbuur():
    lijst = items(0, 1, 2)
    assert move_sibling(lijst, item_id=1, direction="down") is True
    assert volgorde(lijst) == [2, 1, 3]


def test_alles_op_dezelfde_defaultwaarde_werkt_toch():
    """De fout in het oude formulier-algoritme: drie keer positie 0 betekende dat
    wisselen niets deed, zonder foutmelding."""
    lijst = items(0, 0, 0)
    assert move_sibling(lijst, item_id=3, direction="up") is True
    assert volgorde(lijst) == [1, 3, 2]


def test_een_none_waarde_telt_als_nul():
    lijst = items(None, None, 5)
    assert move_sibling(lijst, item_id=2, direction="up") is True
    assert volgorde(lijst) == [2, 1, 3]


def test_bovenste_omhoog_is_een_no_op():
    lijst = items(0, 1, 2)
    assert move_sibling(lijst, item_id=1, direction="up") is False
    assert volgorde(lijst) == [1, 2, 3]


def test_onderste_omlaag_is_een_no_op():
    lijst = items(0, 1, 2)
    assert move_sibling(lijst, item_id=3, direction="down") is False
    assert volgorde(lijst) == [1, 2, 3]


def test_onbekend_item_verandert_niets():
    lijst = items(0, 1, 2)
    assert move_sibling(lijst, item_id=99, direction="up") is False
    assert volgorde(lijst) == [1, 2, 3]


@pytest.mark.parametrize("woord", ["up", "op", "omhoog"])
def test_de_twee_schermen_spreken_hun_eigen_woord(woord):
    """Activiteiten sturen "omhoog", formulieren "op" — de helper kent beide, zodat
    geen van beide schermen zijn formulier hoefde te wijzigen."""
    lijst = items(0, 1)
    assert move_sibling(lijst, item_id=2, direction=woord) is True
    assert volgorde(lijst) == [2, 1]


def test_een_andere_attribuutnaam_werkt_net_zo():
    """Formulieren gebruiken `position` i.p.v. `sort_order`."""
    lijst = items(0, 1, 2, attr="position")
    assert move_sibling(lijst, item_id=3, direction="up", attr="position") is True
    assert volgorde(lijst, attr="position") == [1, 3, 2]

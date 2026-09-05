"""#678 — een gate mag niet groen staan omdat hij nergens kijkt.

Veertien bestandsscannende gate-functies melden wat ze fout vinden. Vinden ze
niets, dan zijn ze groen — maar "niets gevonden" en "nergens gekeken" zien er
identiek uit. Verandert er een pad, een glob of een mapnaam, dan scant zo'n gate
nul bestanden en kleurt hij voor altijd groen zonder ooit nog iets te bewaken.

Dat weegt zwaar omdat acht van de veertien een layout- of huisstijlregel bewaken
en samen vrijwel elke visuele bevinding van de v2.0.0-validatie dekken. De gate
die #656 bewaakt kan dus zelf stilvallen zonder dat iemand het merkt — tot het
defect opnieuw op het scherm staat.

`tests/_bestanden.bestanden()` is de ene plek die dat uitsluit. Deze tests bewijzen
dat de helper doet wat hij belooft, én dat élke gate hem gebruikt: een nieuwe gate
die zelf een glob schrijft, valt hier op.

## Bewijs dat elk gate-bestand rood kán worden

Een niet-leeg-controle is zelf een bewering, dus ze is gecontroleerd met de
werkwijze van de css-poort (#652): overtreding maken, kijken of hij aanslaat,
herstellen. Per bestand één representatieve regel, op 5 september 2026:

| Gate-bestand | Overtreding | Sloeg aan |
|---|---|---|
| `test_ui_conventions_gate.py` | `text-blue-800` in een template | ja |
| `test_style_guardrails.py` | rauwe hex `#abcdef` in een template | ja |
| `test_i18n_gate.py` | `detail="Zomaar een tekst"` zonder `_()` | ja |
| `test_import_boundaries.py` | import van `payment.service` buiten payment | ja |
| `test_layer_gate.py` | `db.query(...)` in een `ui.py` | ja |
| `test_payable_delete_gate.py` | `db.delete(x)` in `domains/membership/` | ja |

De regels die ik in deze reeks zelf toevoegde zijn elk apart zo gemeten en dat
staat in hun eigen docstring: 4 treffers vóór en 0 ná #646, 3/0 bij #647, 1/0 bij
#653, 1/0 bij #656, en bij #659 het volledige restant.
"""
import ast
from pathlib import Path

import pytest

from tests._bestanden import bestanden

TESTS = Path(__file__).resolve().parent

# De bestanden met bestandsscannende gates. Komt er een gate bij die zelf een glob
# schrijft, dan faalt test_elke_gate_gebruikt_de_helper hieronder.
GATE_BESTANDEN = [
    "test_i18n_gate.py",
    "test_layer_gate.py",
    "test_payable_delete_gate.py",
    "test_ui_conventions_gate.py",
    "test_style_guardrails.py",
    "test_import_boundaries.py",
]


def test_een_lege_verzameling_faalt():
    """De kern: nul bestanden is een fout, geen stilte."""
    with pytest.raises(AssertionError) as fout:
        bestanden(Path("/bestaat/niet").rglob("*.py"), wat="een pad dat niet bestaat")
    melding = str(fout.value)
    assert "0 bestanden" in melding, "de melding zegt niet dat er niets gescand is"
    assert "een pad dat niet bestaat" in melding, (
        "de melding zegt niet WELKE verzameling leeg was — dan helpt ze niemand")


def test_te_weinig_bestanden_faalt_ook():
    """Een glob die nog wél iets vindt maar het grootste deel mist, is even stil."""
    with pytest.raises(AssertionError):
        bestanden(TESTS.glob("_bestanden.py"), wat="één bestand", minstens=10)


def test_een_gevulde_verzameling_komt_gesorteerd_en_ontdubbeld_terug():
    twee_keer = bestanden(TESTS.glob("test_gate_niet_leeg.py"),
                          TESTS.glob("test_gate_niet_leeg.py"),
                          wat="dit testbestand")
    assert len(twee_keer) == 1
    veel = bestanden(TESTS.glob("test_*.py"), wat="de tests", minstens=5)
    assert veel == sorted(veel)


@pytest.mark.parametrize("naam", GATE_BESTANDEN)
def test_elke_gate_gebruikt_de_helper(naam):
    """Eén helper in plaats van veertien losse controles — anders KAN de volgende
    gate hem vergeten, en dat is precies de fout die dit issue wegneemt."""
    bron = (TESTS / naam).read_text(encoding="utf-8")
    assert "from tests._bestanden import bestanden" in bron, (
        f"{naam} haalt zijn bestanden buiten de helper om")


@pytest.mark.parametrize("naam", GATE_BESTANDEN)
def test_geen_gate_scant_nog_rechtstreeks(naam):
    """`rglob`/`glob` mag alleen nog als argument van de helper voorkomen.

    Anders staat er naast de bewaakte verzameling stilletjes een tweede die het
    wél kan laten afweten.
    """
    boom = ast.parse((TESTS / naam).read_text(encoding="utf-8"))
    los = []
    binnen_helper = set()
    for node in ast.walk(boom):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "bestanden"):
            for arg in node.args:
                for kind in ast.walk(arg):
                    binnen_helper.add(id(kind))
    for node in ast.walk(boom):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("rglob", "glob")
                and id(node) not in binnen_helper):
            los.append(node.lineno)
    assert not los, (
        f"{naam} scant rechtstreeks op regel {los} — die verzameling valt buiten "
        "de niet-leeg-controle (#678)")

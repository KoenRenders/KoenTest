"""Bestandsverzamelingen voor de gates — die nooit stil leeg mogen zijn (#678).

Veertien gates scannen bestanden en melden wat ze fout vinden. Vinden ze niets,
dan zijn ze groen. Maar "niets gevonden" en "nergens gekeken" zien er identiek
uit: verandert er een pad, een glob of een mapnaam, dan scant zo'n gate nul
bestanden en kleurt hij voor altijd groen zonder ooit nog iets te bewaken.

Dat is geen theoretisch risico. Bij het bouwen van de regel voor #653 gaf mijn
eigen droogloop 0 treffers terwijl de glob nog niet klopte, en dat las als
bevestiging dat de code in orde was. Het viel toen alleen op omdat ik de regel
daarna tegen de kapotte toestand hield en hij nog steeds 0 gaf. Dat was toeval,
geen methode.

Het weegt zwaarder dan het klinkt: acht van de veertien bewaken een layout- of
huisstijlregel, en samen dekken ze vrijwel elke visuele bevinding van de
v2.0.0-validatie. De gate die #656 bewaakt kan dus zelf stilvallen zonder dat
iemand het merkt — tot het defect opnieuw op het scherm staat.

Eén helper in plaats van veertien losse controles, om dezelfde reden als de
hoogte in #677 naar één plek ging: veertien plaatsen repareren lost dít geval op,
een helper sluit de fout uit. Een nieuwe gate die deze functie gebruikt, KAN de
controle niet vergeten.
"""

from pathlib import Path
from typing import Iterable

from check_imports import is_test_code

APP = Path(__file__).resolve().parents[1] / "app"


def is_app_test(path: Path) -> bool:
    """A file in a domain's `tests/` package (CR-13 R15): test code inside `app/`.

    The same rule as the import smoke test's, applied to a path, so the two cannot
    disagree about what counts as a test.
    """
    try:
        relative = path.resolve().relative_to(APP.parent)
    except ValueError:
        return False
    return relative.parts[0] == "app" and is_test_code(".".join(relative.with_suffix("").parts))


def bestanden(
    *groepen: Iterable[Path], wat: str, minstens: int = 1, met_tests: bool = False
) -> list[Path]:
    """De bestanden uit één of meer globs, gesorteerd, en nooit (te) leeg.

    `wat` beschrijft wat er gescand had moeten worden; die tekst komt in de
    foutmelding, want "0 bestanden" zonder te zeggen wélke helpt niemand verder.

    `minstens` staat standaard op 1. Een gate die weet dat er tientallen bestanden
    horen te zijn, mag hoger gaan — dan valt ook een glob op die nog wél iets
    vindt maar het grootste deel mist.
    """
    gevonden = sorted({p for groep in groepen for p in groep})
    if not met_tests:
        # Since CR-13 phase 0b a domain's tests live under app/domains/<x>/tests/. A
        # gate over the application must not judge them as application code; a gate
        # that is about the tests asks for them with met_tests=True.
        gevonden = [p for p in gevonden if not is_app_test(p)]
    assert len(gevonden) >= minstens, (
        f"deze gate scande {len(gevonden)} bestanden ({wat}), verwacht minstens "
        f"{minstens}. Een gate die nergens kijkt staat groen zonder iets te "
        f"bewaken — controleer het pad of de glob (#678)."
    )
    return gevonden

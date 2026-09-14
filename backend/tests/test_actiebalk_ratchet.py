"""Golf 6 (#913, A2): ratchet op handgerolde [Opslaan]-knopparen.

Sinds golf 6 is `ui.action_bar` dé afsluiting van een bewerkvlak. Deze gate
bevriest de plekken die vandaag nog een eigen `btn_primary(_("Opslaan"))`
bouwen — de 6b-schermen met een edit-toggle, die bij hun eigen ombouw uit de
baseline verdwijnen. Zelfde vorm als de taal-ratchet (#780): de lijst mag
alleen krimpen. Een nieuwe handgerolde Opslaan buiten de baseline faalt, en
een omgebouwd scherm dat in de baseline blijft staan faalt óók — een regel
met een groeiende uitzonderingslijst is dood.

De kitpagina staat er bewust in: die demonstreert het rauwe knoppenpaar naast
de actiebalk, en dat is documentatie, geen scherm.
"""
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# template → aantal handgerolde Opslaan-knoppen. Alleen omlaag bijwerken.
# Na golf 6b resten twee bewuste uitzonderingen: de gebruikersrij is een
# horizontale rij (een balk eronder zou elke rij verdubbelen — herbekijken als
# dat scherm ooit panelen krijgt), en de kitpagina demonstreert het rauwe
# knoppenpaar naast de actiebalk.
BASELINE = {
    "domains/auth/templates/_gu_lijst.html": 1,
    "ui/templates/design_system.html": 2,
}


def _huidig() -> dict[str, int]:
    telling: Counter[str] = Counter()
    for pad in APP.rglob("templates/*.html"):
        if pad.name == "_macros.html":
            continue
        n = pad.read_text(encoding="utf-8").count('btn_primary(_("Opslaan"))')
        if n:
            telling[str(pad.relative_to(APP))] = n
    return dict(telling)


def test_geen_nieuwe_handgerolde_opslaanknoppen():
    huidig = _huidig()
    te_veel = {t: n for t, n in huidig.items() if n > BASELINE.get(t, 0)}
    assert not te_veel, (
        "Nieuwe handgerolde [Opslaan] buiten de baseline — gebruik "
        f"ui.action_bar (golf 6, #913): {te_veel}")


def test_de_baseline_krimpt_mee():
    huidig = _huidig()
    verouderd = {t: n for t, n in BASELINE.items() if huidig.get(t, 0) < n}
    assert not verouderd, (
        "Deze schermen zijn (deels) omgebouwd; verlaag hun tel in de "
        f"BASELINE zodat de ratchet niet terug kan: {verouderd}")

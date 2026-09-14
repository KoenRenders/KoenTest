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


def test_het_cluster_zit_nooit_in_een_verborgen_leeswrapper():
    """Koens bevinding op golfpakket-6 v2: de persoonskaart opende in
    bewerkmodus ZONDER Opslaan — het cluster stond in de kopregel die met
    x-show="!edit" verdwijnt (#639-patroon te breed toegepast). De leesinfo
    mag wijken; de knoppen niet.

    Statische scan: een ui.action_bar-aanroep mag nergens binnen een
    <div x-show="!…">-wrapper staan. Rood bewezen door de fix in
    _leden_detail.html één keer terug te draaien.
    """
    import re

    fouten = []
    for pad in APP.rglob("templates/*.html"):
        if pad.name in ("_macros.html", "design_system.html"):
            continue
        tekst = pad.read_text(encoding="utf-8")
        # dieptes van open divs; onthoud per open div of hij negatief verbergt.
        stapel: list[bool] = []
        for token in re.finditer(r"<div\b[^>]*>|</div>|ui\.action_bar\(", tekst):
            t = token.group(0)
            if t == "</div>":
                if stapel:
                    stapel.pop()
            elif t.startswith("<div"):
                stapel.append('x-show="!' in t)
            elif any(stapel):
                regel = tekst[:token.start()].count("\n") + 1
                fouten.append(f"{pad.relative_to(APP)}:{regel}")
    assert not fouten, (
        "action_bar binnen een x-show=\"!…\"-wrapper — de knoppen verdwijnen "
        f"in bewerkmodus: {fouten}")

"""Golf 6 (#913, A2): het actiecluster staat nooit in een verborgen leeswrapper.

Tot #1091 stond hier ook de ratchet op handgerolde [Opslaan]-knopparen. Die
telde de letterlijke tekst `btn_primary(_("Opslaan"))` en miste daardoor drie
van de vier schermen uit #1090 (`size="sm"` erbij, of "Bewaren"): ze bewaakte
de spelling van het label, niet de regel. Ze is vervangen door regel 3 in
`test_ui_conventions_gate.py` (`HANDGEROLDE_CLUSTERS`), die naar de aanroepen
zelf kijkt en een uitzonderingslijst draagt die alleen mag krimpen. Wat hier
overblijft is de plaatsregel: het cluster mag niet in een `x-show="!…"`-wrapper
staan.
"""
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


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

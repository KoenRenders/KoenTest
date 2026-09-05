"""Elk label in de AI-contextlijst wijst naar een veld dat in díe tak bestaat.

Het scherm heeft twee elkaar uitsluitende takken: een notitie (die alleen een
tekst heeft) en een bron-item (met een vervangende én een aanvullende tekst).
Beide gebruiken het veld `text_addition` — dat is geen botsing, want ze worden
nooit samen gerenderd.

Wat wél misging: bij de kit-omzetting van #663 kreeg de textarea in de bron-tak
een eigen id (`edit-add2-`, want `edit-add-` was al van de notitie-tak) terwijl
haar label naar het oude id bleef wijzen. In die tak wees het label dus naar iets
wat er niet is: klikken zette de cursor nergens, en een schermlezer koppelt het
veld aan geen enkel label.
"""
import re

import pytest

APP = "app/domains/chatbot/templates/_ai_context_lijst.html"

pytestmark = pytest.mark.ui_serverrendered

LABEL = re.compile(r'ui\.label\([^)]*?"([a-z0-9-]+-)"\s*~\s*info\.id')
CONTROL = re.compile(r'id="([a-z0-9-]+-)"\s*~\s*info\.id')


def test_elk_label_wijst_naar_een_veld_in_dezelfde_tak():
    bron = open(APP, encoding="utf-8").read()
    # Per regelpaar: het label staat vlak boven zijn control.
    regels = bron.splitlines()
    for nr, regel in enumerate(regels):
        m = LABEL.search(regel)
        if not m:
            continue
        volgende = "\n".join(regels[nr + 1:nr + 4])
        ids = CONTROL.findall(volgende)
        if not ids:
            continue  # label zonder control eronder — niet dit soort veld
        assert m.group(1) == ids[0], (
            f"regel {nr + 1}: het label wijst naar '{m.group(1)}…' terwijl het veld "
            f"eronder '{ids[0]}…' heet — in deze tak bestaat dat id niet")

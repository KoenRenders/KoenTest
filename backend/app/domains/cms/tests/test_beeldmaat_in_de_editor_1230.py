"""De editor toont dezelfde maten als de pagina — uit dezelfde bron (#1230).

De maat van een pagina-afbeelding wordt pas bij het tonen op de `<img>` gezet
(`image_attributes_from_attachment`, #1207). In de editor stond elke afbeelding
daardoor op volle breedte: je koos *klein* en zag *groot*.

De editor leest die maat nu rechtstreeks uit de bijlage-gegevens, met een
attribuutselector op precies de opgeslagen waarde. **Deze poort bewaakt dat die
twee niet uit elkaar lopen.**

**Waarom een poort en niet alleen een e2e.** De e2e meet dat *klein* smaller
rendert dan *vol*; die blijft groen wanneer er een vierde maat bijkomt waarvoor
in de editor geen regel staat. Dan kiest een beheerder een maat, ziet geen
verschil, en niemand merkt het tot iemand het meldt. Dit is dezelfde vorm als een
poort die haar eigen lijst bijhoudt naast de bron — alleen staat de lijst hier in
CSS in plaats van in Python.

Kapotgemaakt om te controleren dat deze test rood kan worden (gemeten):
- de regel voor `half` uit `admin_pagina.html` gehaald → "de editor mist een
  regel voor maat 'half' (klasse cms-beeld-half)";
- een regel voor een verzonnen maat `reus` toegevoegd → "de editor heeft een
  regel voor 'reus', maar die maat staat niet in IMAGE_SIZES".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.cms.render import IMAGE_SIZES

pytestmark = pytest.mark.ui_serverrendered

SJABLOON = Path(__file__).resolve().parents[4] / "app/domains/cms/templates/admin_pagina.html"
# De selector zoals hij in het sjabloon staat: `[data-trix-attachment*='"size":"<maat>"']`
REGEL = re.compile(r"""data-trix-attachment\*='"size":"([a-z_]+)"'""")


def _maten_in_de_editor() -> set[str]:
    return set(REGEL.findall(SJABLOON.read_text(encoding="utf-8")))


def test_elke_maat_met_een_klasse_heeft_ook_een_regel_in_de_editor():
    """`vol` hoort er juist NIET bij: die draagt geen klasse en is de
    standaardweergave, in de editor net zo goed als op de pagina."""
    met_klasse = {maat for maat, klasse in IMAGE_SIZES.items() if klasse}
    in_de_editor = _maten_in_de_editor()

    assert in_de_editor, (
        "geen enkele maatregel gevonden in admin_pagina.html — staat de "
        "attribuutselector er nog, of is de schrijfwijze veranderd?"
    )
    ontbreekt = met_klasse - in_de_editor
    assert not ontbreekt, (
        "de editor mist een regel voor maat "
        + ", ".join(f"{m!r} (klasse {IMAGE_SIZES[m]})" for m in sorted(ontbreekt))
        + " — een beheerder kiest die maat dan en ziet geen verschil"
    )


def test_de_editor_kent_geen_maten_die_de_pagina_niet_kent():
    """De andere kant, en ze is de reden dat dit een poort is.

    Een regel voor een maat die `IMAGE_SIZES` niet kent, zou in de editor iets
    tonen wat op de gepubliceerde pagina niet gebeurt — en dat is precies de
    soepelere tweede vertaling die #1207 wilde uitsluiten.
    """
    te_veel = _maten_in_de_editor() - set(IMAGE_SIZES)

    assert not te_veel, (
        "de editor heeft een regel voor "
        + ", ".join(repr(m) for m in sorted(te_veel))
        + ", maar die maat staat niet in IMAGE_SIZES"
    )


def test_vol_draagt_ook_in_de_editor_geen_eigen_regel():
    """Anders zou "volle breedte" iets anders zijn dan de gewone weergave, en dan
    rendert een pagina van vóór #1207 opeens anders."""
    assert "vol" not in _maten_in_de_editor(), (
        "volle breedte hoort de standaardweergave te blijven, zonder eigen regel"
    )

"""View-models: wat een scherm van zijn route krijgt (#643).

Een UI-route bouwt een view-model en kiest een template (#635). Dit is de vorm van
dat view-model: een bevroren dataclass per scherm, met getypeerde velden. Wat de
route belooft, staat daarmee op één plek — en mypy controleert het.

Waarom niet gewoon een dict? Omdat een dict geen belofte is. `{"totaal": ...}`
doorgeven aan een template die `total` leest, is een typefout die niemand ziet:
Jinja rendert stil leeg (StrictUndefined vangt dat nu, maar pas bij het renderen)
en mypy heeft niets om op te controleren. Met een dataclass is een verkeerde
veldnaam een fout in de route zelf, en kan een gate per (template, view-model)
bewijzen dat de template niets vraagt wat het view-model niet heeft.

Conventie:
  - één `<Scherm>View(ViewModel)` per template, in `<domein>/viewmodels.py`;
  - velden getypeerd (`list[PaymentRecord]`, `Decimal`, `dict[str, str]`), geen
    `Any` tenzij toegelicht;
  - de route eindigt op
    `templates.TemplateResponse(request, "x.html", vm.context())`.

Ook een fragment krijgt een view-model. Dat voelt zwaar voor twee variabelen, maar
juist de fragmenten worden vanuit meerdere routes gerenderd — daar loopt het
gemakkelijkst iets mis.
"""
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ViewModel:
    """Basis voor elk scherm-view-model.

    `frozen=True` omdat een view-model beschrijft wat er getoond wordt en niet
    onderweg nog verandert; `kw_only=True` omdat een aanroep met tien positionele
    argumenten onleesbaar is en bij een veldwijziging stil verschuift.
    """

    def context(self) -> dict[str, Any]:
        """De template-context.

        Bewust **ondiep** en niet `dataclasses.asdict()`: die maakt een diepe kopie
        en zou elk ORM-object in het view-model recursief uitpakken — traag, en het
        breekt lazy relaties waar de template op rekent.
        """
        return {veld.name: getattr(self, veld.name) for veld in fields(self)}

    def met(self, **wijzigingen: Any) -> "ViewModel":
        """Een kopie met enkele velden anders — voor de route die hetzelfde scherm
        met een foutmelding opnieuw rendert."""
        from dataclasses import replace

        return replace(self, **wijzigingen)

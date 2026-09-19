"""Template-variabelen-gate (#643 E): het `tsc --noEmit` van deze stack.

Jinja controleert niets vooraf. Een template die `totaal` leest terwijl de route
`total` doorgeeft, faalt pas bij het renderen — en alleen als er een test langs dat
scherm komt. Deze gate bewijst statisch, per (template, view-model), dat de
template niets vraagt wat het view-model niet belooft.

`jinja2.meta.find_undeclared_variables` werkt per bronbestand: variabelen uit een
`{% extends %}`-schil of een `{% include %}` zitten er niet bij. Fragmenten staan
daarom **apart** in het register — wat sowieso beter is, want juist een fragment
wordt vanuit meerdere routes gerenderd.

Het register groeit met elk scherm dat op een view-model overgaat (#635 raakt die
routes toch). Een scherm dat er nog niet in staat, wordt hier niet gecontroleerd;
dat is zichtbaar aan de lengte van dit register.
"""
import pytest
from jinja2 import meta

from app.domains.activities.viewmodels import AdminActiviteitenView
from app.domains.designstudio.viewmodels import (
    DesignEditorView, DesignListView, DesignNewView)
from app.domains.mdm.viewmodels import LedenView
from app.domains.payment.viewmodels import BetalingenView
from app.domains.meetings.viewmodels import (
    MeetingCircleView, MeetingDocumentView, MeetingItemView, MeetingListView,
    MeetingNewView, MeetingSendView)
from app.domains.newsletter.viewmodels import (
    NewsletterArchiveView, NewsletterComposeView, NewsletterListView,
    NewsletterPickerView, NewsletterSendView, NewsletterSettingsView,
    SubscriberImportView, SubscriberListView)
from app.domains.reporting.viewmodels import ReportListView, ReportPanelView
from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered

# (template, view-model). Eén regel per omgezet scherm.
VIEWMODELS = {
    "betalingen.html": BetalingenView,
    "_betalingen_lijst.html": BetalingenView,
    "leden.html": LedenView,
    "_leden_lijst.html": LedenView,
    "admin_activiteiten.html": AdminActiviteitenView,
    "_aa_kaarten.html": AdminActiviteitenView,
    "admin_rapporten.html": ReportListView,
    "_rp_kaarten.html": ReportListView,
    "admin_rapport_paneel.html": ReportPanelView,
    "_rp_paneel.html": ReportPanelView,
    "admin_vergaderingen.html": MeetingListView,
    "admin_vergadering_nieuw.html": MeetingNewView,
    "_vg_lijst.html": MeetingListView,
    "admin_vergadering.html": MeetingDocumentView,
    "_vg_document.html": MeetingDocumentView,
    "_vg_punt.html": MeetingItemView,
    "admin_vergadering_verstuur.html": MeetingSendView,
    "_vg_verstuur.html": MeetingSendView,
    "admin_vergaderkring.html": MeetingCircleView,
    "_vg_kring.html": MeetingCircleView,
    "admin_nieuwsbrieven.html": NewsletterListView,
    "_nb_lijst.html": NewsletterListView,
    "admin_nieuwsbrief.html": NewsletterComposeView,
    "_nb_bewaard.html": NewsletterComposeView,
    "_nb_raakje.html": NewsletterComposeView,
    "_nb_kiezer.html": NewsletterPickerView,
    "admin_nieuwsbrief_archief.html": NewsletterArchiveView,
    "_nb_afleveringen.html": NewsletterArchiveView,
    "admin_nieuwsbrief_versturen.html": NewsletterSendView,
    "_nb_versturen.html": NewsletterSendView,
    "admin_abonnees.html": SubscriberListView,
    "_nb_abonnees.html": SubscriberListView,
    "admin_abonnees_import.html": SubscriberImportView,
    "_nb_import.html": SubscriberImportView,
    "admin_ontwerpen.html": DesignListView,
    "_ds_lijst.html": DesignListView,
    "admin_ontwerp_nieuw.html": DesignNewView,
    "admin_ontwerp.html": DesignEditorView,
    "_ds_voorbeeld.html": DesignEditorView,
    "admin_nieuwsbrief_instellingen.html": NewsletterSettingsView,
    "_nb_instellingen.html": NewsletterSettingsView,
}

# Namen die niet uit het view-model komen maar altijd bestaan:
#  - de env-globals (`_`, `omgeving`, `confirm_attrs`, `css_version`, …),
#  - `request`, dat Starlette zelf in elke context zet,
#  - `ui`, de macro-import bovenaan elke template,
#  - `caller`, dat Jinja binnen een {% call %} zelf levert.
ALTIJD_BESCHIKBAAR = set(templates.env.globals) | {"request", "ui", "caller"}


def _toegewezen_namen(boom) -> set[str]:
    """Namen die de template zichzelf geeft met `{% set %}`.

    `find_undeclared_variables` telt die mee zodra de toewijzing binnen een `{% if %}`
    of `{% for %}` staat: Jinja kan dan niet bewijzen dat de naam op elk pad bestaat.
    Voor deze gate zijn het geen ontbrekende velden — de template maakt ze zelf.
    """
    from jinja2 import nodes

    namen: set[str] = set()
    for soort in (nodes.Assign, nodes.AssignBlock):
        for knoop in boom.find_all(soort):
            doel = knoop.target
            if isinstance(doel, nodes.Name):
                namen.add(doel.name)
            elif isinstance(doel, nodes.Tuple):
                namen.update(item.name for item in doel.items
                             if isinstance(item, nodes.Name))
    return namen


def _gevraagde_namen(bestandsnaam: str) -> set[str]:
    bron = templates.env.loader.get_source(templates.env, bestandsnaam)[0]
    boom = templates.env.parse(bron)
    return meta.find_undeclared_variables(boom) - _toegewezen_namen(boom)


@pytest.mark.parametrize("bestandsnaam,model", sorted(
    VIEWMODELS.items(), key=lambda kv: kv[0]))
def test_de_template_vraagt_niets_wat_het_view_model_niet_belooft(bestandsnaam, model):
    from dataclasses import fields

    beloofd = {veld.name for veld in fields(model)} | ALTIJD_BESCHIKBAAR
    gevraagd = _gevraagde_namen(bestandsnaam)

    ontbreekt = gevraagd - beloofd
    assert not ontbreekt, (
        f"{bestandsnaam} gebruikt {sorted(ontbreekt)}, maar {model.__name__} heeft "
        f"dat niet. Zet het veld in het view-model, of gebruik |default(...) met "
        f"een reden als het echt optioneel is."
    )


def test_het_register_dekt_beide_kanten_van_het_betalingenscherm():
    """De pagina én haar fragment: het fragment wordt los gerenderd bij zoeken en
    filteren, en juist dáár ontbrak vroeger een variabele (#617)."""
    assert "betalingen.html" in VIEWMODELS
    assert "_betalingen_lijst.html" in VIEWMODELS

"""Publieke activiteitenkaart — popup-inschrijving + compacte deelnemersregel (#601).

PROD-pariteit (v1.14): inschrijven opent als smalle gecentreerde modal (niet een
breed inline blok), en "Wie doet er mee?" is één compacte regel (niet een verticale
lijst). We toetsen de templates op die vorm zodat de regressie niet terugkeert.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered

TPL = Path(__file__).resolve().parents[4] / "app" / "domains" / "activities" / "templates"


def test_the_registration_fields_are_stacked():
    """Stacked fields, no wide tinted block (#601) — on the page as in the modal it
    replaced (CR-14 phase 1); a submit swaps the page, not a card."""
    inhoud = (
        (TPL / "inschrijven.html").read_text()
        # #1284: the fields moved into their own template, shared with the board.
        + (TPL / "_inschrijf_velden.html").read_text()
    )
    assert "bg-blue-50" not in inhoud
    assert "sm:grid-cols-3" not in inhoud and "grid-cols-1" in inhoud
    assert 'hx-target="#inschrijf-pagina"' in inhoud


def test_the_card_links_to_the_registration_page():
    """CR-14 phase 1 (B4.1): the popup of #601 became a page. The card and the
    activity page share one block of component actions, and it links there."""
    kaart = (TPL / "_activiteiten_cards.html").read_text()
    pagina = (TPL / "activiteit.html").read_text()
    blok = (TPL / "_onderdeel_acties.html").read_text()
    assert '{% include "_onderdeel_acties.html" %}' in kaart
    assert '{% include "_onderdeel_acties.html" %}' in pagina
    assert 'href="/activiteiten/{{ a.id }}/inschrijven/{{ c.id }}"' in blok
    assert 'x-show="ins"' not in kaart + pagina + blok, "the popup is back"


def test_deelnemers_is_compacte_inline_regel():
    out = templates.env.get_template("_deelnemers.html").render(
        deelnemers=[
            SimpleNamespace(contact_name="Jan", team_name=None, quantity=1),
            SimpleNamespace(contact_name="An", team_name=None, quantity=2),
            SimpleNamespace(contact_name=None, team_name="De Toppers", quantity=1),
        ]
    )
    assert "<li>" not in out and "<ul" not in out  # geen verticale lijst
    assert "·" in out  # inline gescheiden
    assert "Jan" in out and "An" in out and "De Toppers" in out
    assert "4 " in out  # som van de aantallen (1+2+1)


def test_deelnemers_leeg_blijft_nette_tekst():
    out = templates.env.get_template("_deelnemers.html").render(deelnemers=[])
    assert "Nog niemand ingeschreven" in out


# ── Totaal altijd zichtbaar bij een betalend onderdeel (#607) ─────────────────
# Het blok verscheen vroeger pas bij het eerste aantal, waardoor het formulier
# versprong. De invariant die telt: zichtbaar-vanaf-het-begin dán en enkel dán
# als er via de portaal iets af te rekenen valt.


def _totaal_html(**ctx):
    return templates.env.get_template("_inschrijf_totaal.html").render(**ctx)


def test_totaal_staat_er_meteen_bij_een_betalend_onderdeel():
    """Op €0,00 al zichtbaar (gedempt) — anders verspringt het formulier."""
    out = _totaal_html(heeft_prijs=True, totaal=Decimal("0"), is_member=False)
    assert "Totaal:" in out and "0,00" in out
    assert "text-gray-500" in out and "text-blue-700" not in out


def test_totaal_wordt_merkblauw_zodra_er_een_bedrag_staat():
    out = _totaal_html(heeft_prijs=True, totaal=Decimal("27.50"), is_member=False)
    assert "27,50" in out and "text-blue-700" in out
    assert "text-gray-500" not in out


def test_geen_totaalblok_als_er_niets_af_te_rekenen_valt():
    """Gratis of ter-plaatse: "Totaal: €0,00" zou misleidende ruis zijn."""
    assert _totaal_html(heeft_prijs=False, totaal=Decimal("0"), is_member=False).strip() == ""


def test_heeft_prijs_volgt_de_prijsberekening():
    """De weergave leidt af uit dezelfde stukprijs als het totaal.

    De helper woont sinds #635 in `activities/totals.py` (als
    `has_payable_products`) i.p.v. in `ui.py`: het is een domeinregel, en het
    scherm hoort er geen tweede versie van te hebben.
    """
    from app.domains.activities.totals import has_payable_products as _heeft_prijs

    def product(**kw):
        velden = dict(is_free=False, pay_on_site=False, price=Decimal("10"), member_price=None)
        velden.update(kw)
        return SimpleNamespace(**velden)

    betalend = SimpleNamespace(products=[product()])
    gratis = SimpleNamespace(products=[product(is_free=True)])
    ter_plaatse = SimpleNamespace(products=[product(pay_on_site=True)])
    assert _heeft_prijs(betalend, is_member=False) is True
    assert _heeft_prijs(gratis, is_member=False) is False
    assert _heeft_prijs(ter_plaatse, is_member=False) is False
    assert _heeft_prijs(SimpleNamespace(products=[]), is_member=False) is False
    # Ledenprijs 0 = voor een lid niets te betalen, voor een niet-lid wél.
    gratis_voor_leden = SimpleNamespace(products=[product(member_price=Decimal("0"))])
    assert _heeft_prijs(gratis_voor_leden, is_member=True) is False
    assert _heeft_prijs(gratis_voor_leden, is_member=False) is True


def test_betaalwijze_volgt_dezelfde_voorwaarde_als_het_totaal():
    """Bijvangst (#607): geen betaalkeuze bij een onderdeel zonder betalend deel."""
    inhoud = (
        (TPL / "inschrijven.html").read_text()
        # #1284: the fields moved into their own template, shared with the board.
        + (TPL / "_inschrijf_velden.html").read_text()
    )
    assert "{% if heeft_prijs %}" in inhoud
    assert "Betaalwijze (bij betalend deel)" not in inhoud


def test_volzet_is_oranje_geen_rood():
    """#609: volzet is 'attention', geen fout — rood blijft voor Mislukt/Geannuleerd.

    design-system §1.1 houdt de tinten uit elkaar (#f16532 attention · outstanding
    versus #ee3a37 error · delete); ui-conventies §2.10 is daarop rechtgezet.
    """
    # CR-14 phase 1: the component actions live in one partial for card and page.
    inhoud = (TPL / "_onderdeel_acties.html").read_text()
    assert 'ui.badge(_("Volzet"), "orange")' in inhoud
    # CR-12 phase 4: the state badge takes its tone from the code, no longer
    # from a dictionary keyed on the Dutch label inside the template. Its
    # `"Vol"` key was dead — no state ever read "Vol" — so the orange that
    # matters is the Volzet badge above. Red stays where it belongs:
    import app.domains.activities.ui  # noqa: F401  (registers the tones)
    from app.domains.activities.api import REGISTRATION_STATE, RegistrationState
    from app.kernel.codes import tone

    assert tone(REGISTRATION_STATE.name, RegistrationState.CANCELLED) == "red"

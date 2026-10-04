"""#660 — de tonen van de betaalbadges, als invariant en niet per losse badge.

Koen koos twee wijzigingen die elkaar nodig hebben: de type-badge
"Terugbetaling" wordt oranje (pariteit met v1.14.0), en de status
"Terug te betalen" wordt geel, gelijk aan "Openstaand".

Die tweede is geen cosmetiek maar de reden dat de eerste kan: zonder haar staan er
twee oranje badges naast elkaar op één kaart, en precies daarvoor was in #617 een
zevende toon (teal) ingevoerd die in §2.10 niet bestaat.

De redenering: "Openstaand" en "Terug te betalen" zijn hetzelfde soort toestand —
er moet nog geld bewegen, alleen de richting verschilt. Die richting lees je af
aan de type-badge.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# De verwachte toon per afgeleide status (payment/ui.py: kaart_status).
VERWACHT = {
    "paid": "green",
    "refund_due": "yellow",
    "partial": "orange",
    "pending": "yellow",
    "failed": "red",
    "cancelled": "gray",
}


def _kaart_status(client):
    """The tones as the screens get them: from the one function the payments list
    and the booking page both read (`_status_badges`, #1574). Until then this
    test parsed the source text of the view for a `kaart_status={` literal."""
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    from app.domains.payment import ui as betalingen_ui

    return {status: tone for status, (_label, tone) in betalingen_ui._status_badges().items()}


def test_elke_afgeleide_status_heeft_de_afgesproken_toon(client):
    assert _kaart_status(client) == VERWACHT


def test_terug_te_betalen_draagt_dezelfde_toon_als_openstaand(client):
    """De invariant achter #660, los van welke kleur het precies is.

    Beide zijn "er moet nog geld bewegen". Wijzigt de ene ooit, dan hoort de
    andere mee te gaan — en die koppeling is wat deze test bewaakt.
    """
    tonen = _kaart_status(client)
    assert tonen["refund_due"] == tonen["pending"], (
        "Terug te betalen en Openstaand horen dezelfde toon te dragen (#660)"
    )


def test_deels_betaald_blijft_apart(client):
    """Geen kudde-effect: partial is een andere situatie en blijft oranje."""
    tonen = _kaart_status(client)
    assert tonen["partial"] == "orange"
    assert tonen["partial"] != tonen["pending"]


def test_het_soort_terugbetaling_staat_in_de_subregel():
    """Sinds de Betalingen-verfijning (#996) is de aparte soortbadge weg: het
    soort staat als tekst in de contextsubregel ("Terugbetaling · Online"),
    zodat een rij één badge draagt en niet dubbel zo hoog wordt. De oranje
    v1.14-badge (#660) is daarmee bewust vervallen."""
    lijst = open("app/domains/payment/templates/_betalingen_lijst.html", encoding="utf-8").read()
    assert '{{ _("Terugbetaling") }} · ' in lijst
    regels = [r for r in lijst.splitlines() if "Terugbetaling" in r and "ui.badge" in r]
    assert not regels, f"soortbadge is terug: {regels[0].strip() if regels else ''}"

"""De activiteitspagina zet tekst en affiche als één blok in het midden (#1143).

Koen meldde op 21 september 2026 een leeg vlak van ruwweg een derde van de
breedte tussen zijn tekst en de affiche op de Bowlen-pagina.

**De oorzaak was de kolom, niet de tekst.** De inhoudskolom was `flex-1` en nam
dus álle overblijvende ruimte, terwijl de tekst erin stopt bij de leesbreedte.
De affiche stond niet te ver naar rechts — ze werd erheen geduwd door ruimte die
niemand gebruikte.

Koens keuze: het geheel centreren. Tekst en affiche vormen samen één blok in het
midden; de overgebleven ruimte wordt gelijk verdeeld. Het alternatief — de
affiche naar de tekst toe halen en al het wit rechts laten — is bewust niet
gekozen.

**Wat deze tests vastleggen is de afleiding**, want dat is wat morgen stuk gaat.
De breedte van het blok is de som van drie maten die elk ook ergens anders
gebruikt worden: de leesbreedte (de omschrijving), de tussenruimte (`gap-8`) en
de affichekolom. Staat er een vierde getal naast, dan loopt dat uit de pas zodra
iemand er één aanpast. Dat de pixels dan ook echt gelijk verdeeld zijn, meet de
browser: `tests_e2e/test_activiteitspagina_blok.py`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
`md:max-w-[calc(...)]` van de rij weggehaald (de linkerkolom neemt weer alle
ruimte) → de eerste twee vallen om; `max-w-[var(--leesbreedte)]` op de
omschrijving terug naar `max-w-2xl` → de afleidingstest valt om, want dan staat
de leesbreedte weer op twee plaatsen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.media.api import MediaAsset

pytestmark = pytest.mark.ui_serverrendered

SJABLOON = (Path(__file__).resolve().parents[1] / "app" / "domains" / "activities"
            / "templates" / "activiteit.html")
# De som die het blok breed maakt. Eén uitdrukking, drie variabelen.
BLOKBREEDTE = "calc(var(--leesbreedte)_+_var(--tussenruimte)_+_var(--affiche))"


def _activiteit(db, naam: str, *, met_affiche: bool, omschrijving: str = "Tekst."):
    from datetime import date, timedelta
    from decimal import Decimal

    from app.domains.activities.api import (Activity, ActivityDate,
                                            ActivitySubRegistration)

    a = Activity(name=naam, description=omschrijving)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=14)))
    db.add(ActivitySubRegistration(activity_id=a.id, name="Deelname",
                                   registration_type_code="INDIVIDUAL",
                                   price=Decimal("0"), is_free=True))
    if met_affiche:
        db.add(MediaAsset(kind="activity_poster", activity_id=a.id, title="Affiche",
                          content_type="image/png", data=b"png"))
    db.commit()
    return a


def _rij(html: str) -> str:
    """De openingstag van de rij met de twee kolommen."""
    treffer = re.search(r'<div class="mt-4 md:flex[^"]*"', html)
    assert treffer, "de rij met de twee kolommen is niet gevonden"
    return treffer.group(0)


# ── 1. Het blok staat gecentreerd, en zijn breedte is afgeleid ───────────────

def test_met_affiche_staat_het_blok_gecentreerd(client, db_session):
    a = _activiteit(db_session, "Bowlen", met_affiche=True)

    rij = _rij(client.get(f"/activiteiten/{a.id}").text)

    assert "md:mx-auto" in rij, "het blok wordt niet gecentreerd"
    assert BLOKBREEDTE in rij, (
        "de rij heeft geen afgeleide breedte; dan neemt de linkerkolom weer alle "
        f"ruimte en staat de affiche los van de tekst: {rij}")


def test_de_breedte_is_de_som_van_maten_die_elders_gebruikt_worden(client, db_session):
    """Geen vierde getal: elke maat in die som staat maar op één plaats.

    De leesbreedte hoort bij de omschrijving, de affichebreedte bij de
    rechterkolom, en de tussenruimte is de `gap` van de rij zelf. Schrijft iemand
    de som als een los getal (`md:max-w-[62rem]`), dan klopt ze de dag erna niet
    meer.
    """
    # Zonder het commentaar: dat noemt de oude maten met opzet (het legt uit
    # waar `--leesbreedte` vandaan komt), en die uitleg hoort niet als
    # overtreding te tellen — dezelfde reden als `_zonder_commentaar` in de
    # UI-conventiepoort.
    bron = re.sub(r"\{#.*?#\}", "", SJABLOON.read_text(), flags=re.S)

    # De drie maten worden één keer gezet…
    for variabele, waarde in (("--leesbreedte", "42rem"), ("--tussenruimte", "2rem"),
                              ("--affiche", "18rem")):
        assert bron.count(f"[{variabele}:{waarde}]") == 1, variabele
    assert bron.count("lg:[--affiche:20rem]") == 1, "de brede variant van de affiche"

    # …en elders alleen nog gelézen.
    assert "max-w-[var(--leesbreedte)]" in bron, "de omschrijving leest de leesbreedte niet"
    assert "md:w-[var(--affiche)]" in bron, "de affichekolom leest haar breedte niet"
    assert "md:gap-8" in bron, "de tussenruimte van de rij hoort gelijk te blijven aan --tussenruimte"

    # En de oude, losse maten staan er niet meer naast.
    for oud in ("max-w-2xl", "md:w-72", "lg:w-80"):
        assert oud not in bron, f"{oud} staat er nog naast de variabele"


def test_de_leesbreedte_van_de_omschrijving_is_ongewijzigd(client, db_session):
    """De begrenzing die moest blijven: 42rem, precies wat `max-w-2xl` was.

    Het probleem was de kolom, niet de tekst — een regel over de volle
    schermbreedte leest slecht.
    """
    a = _activiteit(db_session, "Leesbreedte", met_affiche=True,
                    omschrijving="Een avond voor het hele dorp.")
    html = client.get(f"/activiteiten/{a.id}").text

    omschrijving = re.search(r'<div class="mt-5 [^"]*">Een avond', html)
    assert omschrijving, "de omschrijving is niet gevonden"
    assert "max-w-[var(--leesbreedte)]" in omschrijving.group(0)
    assert "[--leesbreedte:42rem]" in _rij(html), "42rem = de oude max-w-2xl"


# ── 2. Zonder affiche blijft de pagina zoals ze was ──────────────────────────

def test_zonder_affiche_geen_gecentreerd_blok_en_geen_lege_kolom(client, db_session):
    """Bewuste keuze (#1143): geen rechterkolom, dus niets om naast te staan.

    Een gecentreerd blok zou daar een tweede kolom suggereren die niet komt, en
    het zou de inschrijfkaarten versmallen op pagina's waarover niemand iets
    gemeld heeft. Die pagina's blijven dus precies zoals ze waren.
    """
    a = _activiteit(db_session, "Kaalproef", met_affiche=False)
    html = client.get(f"/activiteiten/{a.id}").text

    rij = _rij(html)
    assert "md:mx-auto" not in rij, "zonder affiche hoort het blok niet gecentreerd"
    assert BLOKBREEDTE not in rij, "zonder affiche is er geen affichekolom om bij op te tellen"
    assert "<aside" not in html, "er staat een lege rechterkolom"


# ── 3. Mobiel raakt dit niets ────────────────────────────────────────────────

def test_op_mobiel_blijft_de_affiche_boven_de_omschrijving(client, db_session):
    """80% van het bezoek is mobiel; daar is er één kolom en staat de affiche al
    boven de tekst. Elke nieuwe klasse hangt daarom aan `md:`."""
    a = _activiteit(db_session, "Mobiel", met_affiche=True)
    html = client.get(f"/activiteiten/{a.id}").text

    # Het mobiele beeld staat vóór de omschrijving in de bron, en is op een breed
    # scherm verborgen (`md:hidden`); de rechterkolom is het omgekeerde.
    mobiel = html.index("md:hidden")
    omschrijving = html.index("mt-5 text-base md:text-sm text-ink")
    assert mobiel < omschrijving, "de affiche staat niet meer boven de omschrijving"
    assert "hidden md:block" in html, "de rechterkolom is niet meer md-only"

    rij = _rij(html)
    for klasse in ("md:mx-auto", "md:max-w-[calc(", "md:flex", "md:gap-8"):
        assert klasse in rij, klasse
    # Elke nieuwe klasse draagt het `md:`-voorvoegsel: op een telefoon geldt er
    # dus niets van. Op de klasse zelf getoetst en niet met een "niet gevonden",
    # want `md:mx-auto` bevat `mx-auto` en een losse zoekopdracht ziet het
    # verschil niet.
    for klasse in re.findall(r"\S*mx-auto|\S*max-w-\[calc\(", rij):
        assert klasse.startswith("md:"), (
            f"{klasse} geldt ook op een telefoon; daar is er maar één kolom")


def test_een_korte_omschrijving_verandert_de_blokbreedte_niet(client, db_session):
    """Twee zinnen naast een affiche van volle hoogte trekken niets scheef: de
    breedte komt uit de drie maten en niet uit de inhoud."""
    kort = _activiteit(db_session, "Kort", met_affiche=True, omschrijving="Twee zinnen. Meer niet.")
    lang = _activiteit(db_session, "Lang", met_affiche=True,
                       omschrijving="Een lange omschrijving. " * 60)

    assert _rij(client.get(f"/activiteiten/{kort.id}").text) == \
        _rij(client.get(f"/activiteiten/{lang.id}").text)

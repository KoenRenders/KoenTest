"""Wijzigingen en E-maillog in de Betalingen-vorm (#1083).

Since #1925 the e-mail log stands on the kit's list (`list_page`, the toolbar,
the table and the pager), which the kit's own tests hold; this file keeps
Wijzigingen's width, page size and period. Since #2109 Wijzigingen stands on the list
page too: the tests of its hand-built form (the scroll container, the meta line, the
inline label, the one-row filter bar) went with it — the kit's own tests hold those.

Vier dingen gaan hier naar de referentie van §2.3: volle breedte, een dichte
tabel, een meta-regel boven die tabel (hoeveel regels, in welke volgorde) en de
keuze hoeveel rijen er op een pagina staan.

**Wat deze tests NIET doen: een 200 toetsen.** Beide schermen antwoordden vóór dit
issue ook netjes; wat veranderde is hoe breed, hoe dicht en met hoeveel rijen. De
tests kijken dus naar de gerenderde opmaak en naar gedrag dat kan wegvallen —
vooral of de paginagrootte een filterwissel en een kop-klik OVERLEEFT, want dat is
het stukje dat stil kapotgaat.

**Rood gemaakt om te bewijzen dat ze meten** (met de hand, tijdens het bouwen):

* `max-w-none` terug naar `max-w-7xl` in `admin_ledenwijzigingen.html` →
  `test_beide_schermen_gebruiken_de_volle_breedte` viel om op Wijzigingen;
* `ui.inline_label` terug naar `ui.label` (het blok-label) in diezelfde
  filterbalk → `test_het_vanaf_label_staat_naast_het_veld_niet_erboven` viel om
  met "draagt `block`"; de rij-test van #1079 bleef terecht groen, want een
  blok-label verandert de STRUCTUUR niet — alleen de uitlijning. Daarom toetst
  die test de labelvorm en niet het aantal kinderen;
* `params["per_page"] = per_page` weggehaald uit `_sorteer_url` (mail/ui.py) →
  `test_de_paginagrootte_overleeft_een_kop_klik` viel om op het e-maillog.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.kernel.clock import belgian_today
from app.ui import PER_PAGE_DEFAULT, PER_PAGE_OPTIONS
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

WIJZIGINGEN = "/admin/ledenwijzigingen"


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _wijzigingen(db, aantal):
    """Audit-rijen via dezelfde functie als de productiecode (zie #620-tests)."""
    from app.domains.mdm.api import Person, snapshot_person

    for i in range(aantal):
        person = Person(first_name=f"Vorm{i}", last_name="Test")
        db.add(person)
        db.flush()
        snapshot_person(
            db,
            person,
            operation="insert",
            action="person_created",
            source="test",
            actor=f"tester{i:03d}@example.com",
        )
    db.commit()


def _emails(db, aantal):
    from app.domains.mail.models import EmailLog

    moment = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    for i in range(aantal):
        db.add(
            EmailLog(
                recipient=f"vormtest{i:03d}@example.com",
                subject=f"Onderwerp {i}",
                email_type="other",
                status="sent",
                created_at=moment + timedelta(minutes=i),
            )
        )
    db.commit()


# ── 1. Volle breedte ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("pad", [WIJZIGINGEN])
def test_beide_schermen_gebruiken_de_volle_breedte(client, db_session, pad):
    """De schil geeft standaard `max-w-5xl` — de leesbreedte van een formulier.

    Op de contentwikkel van de schil getoetst en niet op "staat de string ergens
    in de pagina": `max-w-5xl` komt ook in een modal voor, en dan zou de test
    groen blijven bij een scherm dat zijn overschrijving verloor.
    """
    _login(client, db_session)
    html = client.get(pad).text

    # The shell's content wrapper carries `admin-content` since #1482.
    assert '<div class="admin-content max-w-none mx-auto">' in html, (
        f"{pad}: de contentkolom staat niet op max-w-none"
    )
    for grens in ("max-w-5xl mx-auto", "max-w-7xl mx-auto"):
        assert grens not in html, f"{pad}: draagt nog de begrensde kolom {grens}"


# ── 2. De meta-regel boven de tabel ──────────────────────────────────────────


# ── 3. Hoeveel rijen op een pagina ───────────────────────────────────────────


@pytest.mark.parametrize("pad,form_id", [(WIJZIGINGEN, "lw-filters")])
def test_de_keuze_biedt_precies_de_toegestane_maten(client, db_session, pad, form_id):
    """De keuzelijst wordt uit dezelfde reeks gevuld als de whitelist in de route.

    En ze draagt `form=`: het veld staat BUITEN de filterbalk, dus zonder die
    koppeling serialiseert een filterwissel het niet mee en wist ze de keuze uit
    de URL die ze zelf duwt.
    """
    _wijzigingen(db_session, 2)
    _emails(db_session, 2)
    _login(client, db_session)
    html = client.get(pad).text

    for n in PER_PAGE_OPTIONS:
        assert f'<option value="{n}"' in html, f"{pad}: maat {n} ontbreekt"
    # Since #2109 the size is a field of the toolbar's own form (`data-page-size`).
    assert "data-page-size" in html, f"{pad}: de keuzelijst staat niet in de werkbalk"


def test_een_kleinere_pagina_toont_ook_echt_minder_rijen(client, db_session):
    """De keuze moet de SNEDE sturen, niet alleen de keuzelijst kleuren."""
    _wijzigingen(db_session, PER_PAGE_DEFAULT + 5)
    _login(client, db_session)

    def rijen(**params):
        html = client.get(WIJZIGINGEN, params={"since": "2000-01-01", **params}).text
        return html.count("data-change")

    assert rijen() == PER_PAGE_DEFAULT
    assert rijen(per_page=25) == 25
    # Een verzonnen maat is invoer uit een URL en valt terug op de standaard —
    # niet op "toon alles".
    assert rijen(per_page=100000) == PER_PAGE_DEFAULT


@pytest.mark.parametrize("pad,sleutel", [(WIJZIGINGEN, "actor")])
def test_de_paginagrootte_overleeft_een_kop_klik(client, db_session, pad, sleutel):
    """Een kop-klik gaat langs de LINK en niet langs de filterbalk.

    Draagt die link de paginagrootte niet, dan valt ze bij het sorteren terug op
    50 — en dat is precies de stille terugval waar dit issue om vraagt.
    """
    _wijzigingen(db_session, 3)
    _emails(db_session, 3)
    _login(client, db_session)

    html = client.get(pad, params={"since": "2000-01-01", "per_page": 25}).text
    koplinks = [r for r in html.splitlines() if f"sort={sleutel}" in r]
    assert koplinks, f"{pad}: geen sorteerlink voor {sleutel} gevonden"
    assert any("per_page=25" in r for r in koplinks), (
        f"{pad}: de sorteerlink van {sleutel} laat de paginagrootte vallen"
    )


def test_de_paginagrootte_reist_mee_bij_het_bladeren(client, db_session):
    """Zonder dit springt pagina 2 terug naar 50 rijen."""
    _wijzigingen(db_session, 60)
    _login(client, db_session)
    html = client.get(WIJZIGINGEN, params={"since": "2000-01-01", "per_page": 25}).text
    assert "per_page=25" in html and "Volgende" in html


# ── 4. Het veld *Vanaf* blijft, met een zichtbaar label ERNAAST ──────────────


def test_het_vanaf_veld_draagt_geen_dubbel_label(client, db_session):
    """Een `aria-label` NAAST een echt `<label for=…>` laat een schermlezer het
    veld twee keer voorlezen. Het `aria_label` uit #1079 hoort dus te vervallen."""
    import re

    _login(client, db_session)
    html = client.get(WIJZIGINGEN).text

    veld = re.search(r'<input[^>]*id="lw-since"[^>]*>', html).group(0)
    assert "aria-label" not in veld, veld


def test_het_vanaf_veld_staat_standaard_op_dertig_dagen_geleden(client, db_session):
    """Het venster van de query, niet zomaar een filter: `all_changes_since`
    verenigt ~10 history-tabellen in Python en de paginering snijdt pas daarna.
    De datum is dus de enige echte rem — en een leeg verzoek hoort er een te
    hebben."""
    import re

    _login(client, db_session)
    veld = re.search(r'<input[^>]*id="lw-since"[^>]*>', client.get(WIJZIGINGEN).text).group(0)

    verwacht = (belgian_today() - timedelta(days=30)).isoformat()
    assert f'value="{verwacht}"' in veld, veld


# ── De filterregel van #1079 blijft staan ────────────────────────────────────

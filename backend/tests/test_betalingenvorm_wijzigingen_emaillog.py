"""Wijzigingen en E-maillog in de Betalingen-vorm (#1083).

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
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole,
                                  make_session_value)
from app.ui import PER_PAGE_DEFAULT, PER_PAGE_OPTIONS
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.test_filterbalk_op_een_regel import meet

pytestmark = pytest.mark.ui_serverrendered

WIJZIGINGEN = "/admin/ledenwijzigingen"
EMAILLOG = "/admin/e-maillog"


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _wijzigingen(db, aantal):
    """Audit-rijen via dezelfde functie als de productiecode (zie #620-tests)."""
    from app.domains.audit.api import snapshot_person
    from app.domains.mdm.api import Person

    for i in range(aantal):
        person = Person(first_name=f"Vorm{i}", last_name="Test")
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action="person_created",
                        source="test", actor=f"tester{i:03d}@example.com")
    db.commit()


def _emails(db, aantal):
    from app.domains.mail.models import EmailLog

    moment = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    for i in range(aantal):
        db.add(EmailLog(recipient=f"vormtest{i:03d}@example.com",
                        subject=f"Onderwerp {i}", email_type="other",
                        status="sent", created_at=moment + timedelta(minutes=i)))
    db.commit()


# ── 1. Volle breedte ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("pad", [WIJZIGINGEN, EMAILLOG])
def test_beide_schermen_gebruiken_de_volle_breedte(client, db_session, pad):
    """De schil geeft standaard `max-w-5xl` — de leesbreedte van een formulier.

    Op de contentwikkel van de schil getoetst en niet op "staat de string ergens
    in de pagina": `max-w-5xl` komt ook in een modal voor, en dan zou de test
    groen blijven bij een scherm dat zijn overschrijving verloor.
    """
    _login(client, db_session)
    html = client.get(pad).text

    assert '<div class="max-w-none mx-auto">' in html, \
        f"{pad}: de contentkolom staat niet op max-w-none"
    for grens in ("max-w-5xl mx-auto", "max-w-7xl mx-auto"):
        assert grens not in html, f"{pad}: draagt nog de begrensde kolom {grens}"


@pytest.mark.parametrize("pad", [WIJZIGINGEN, EMAILLOG])
def test_de_tabel_zit_in_haar_eigen_schuifcontainer(client, db_session, pad):
    """Volle breedte mag de PAGINA niet breed maken (§2.3).

    Een dichte tabel is op een telefoon breder dan het scherm; die breedte hoort
    in de container rond de tabel te blijven, niet in de pagina te lekken. Op de
    volgorde getoetst — de `overflow-x-auto` moet vóór de `<table>` komen en in
    hetzelfde blok — want "de klasse staat ergens in de pagina" zou ook groen
    blijven bij een wrapper die ergens anders hangt.
    """
    _wijzigingen(db_session, 2)
    _emails(db_session, 2)
    _login(client, db_session)
    html = client.get(pad).text

    opening = html.find("<table")
    assert opening != -1, f"{pad}: geen tabel gevonden"
    blok = html[:opening]
    wrapper = blok.rfind("overflow-x-auto")
    assert wrapper != -1 and blok.rfind("<div", wrapper - 200, wrapper) != -1, \
        f"{pad}: de tabel staat niet in een overflow-x-auto-container"


# ── 2. De meta-regel boven de tabel ──────────────────────────────────────────

def test_de_meta_regel_van_wijzigingen_telt_en_benoemt_de_volgorde(client, db_session):
    """§2.3: hoeveel regels en waarom deze bovenaan staat, zonder de koppen af te gaan."""
    _wijzigingen(db_session, 3)
    _login(client, db_session)

    standaard = client.get(WIJZIGINGEN, params={"since": "2000-01-01"}).text
    assert "wijzigingen · nieuwste eerst" in standaard

    # Een andere sortering hoort een ANDERE zin te geven — anders is de regel
    # opsmuk die altijd hetzelfde zegt.
    op_actor = client.get(WIJZIGINGEN, params={"since": "2000-01-01",
                                               "sort": "actor",
                                               "richting": "asc"}).text
    assert "op Actor, oplopend" in op_actor
    assert "nieuwste eerst" not in op_actor


def test_de_meta_regel_van_het_emaillog_belooft_geen_totaal(client, db_session):
    """Dit scherm doet bewust GEEN `COUNT` (§2.3) — het haalt één rij extra op.

    "N e-mails" zou dus een totaal suggereren dat nooit gemeten is; de regel zegt
    daarom wat ze wél weet: wat er op deze pagina staat.
    """
    _emails(db_session, 4)
    _login(client, db_session)
    html = client.get(EMAILLOG).text

    assert "e-mails op deze pagina · nieuwste eerst" in html


# ── 3. Hoeveel rijen op een pagina ───────────────────────────────────────────

@pytest.mark.parametrize("pad,form_id", [(WIJZIGINGEN, "lw-filters"),
                                         (EMAILLOG, "el-filters")])
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
    assert f'form="{form_id}"' in html, \
        f"{pad}: de keuzelijst hangt niet aan de filterbalk"


def test_een_kleinere_pagina_toont_ook_echt_minder_rijen(client, db_session):
    """De keuze moet de SNEDE sturen, niet alleen de keuzelijst kleuren."""
    _wijzigingen(db_session, PER_PAGE_DEFAULT + 5)
    _login(client, db_session)

    def rijen(**params):
        html = client.get(WIJZIGINGEN, params={"since": "2000-01-01", **params}).text
        return html.count('<tr class="border-t border-gray-100 align-middle')

    assert rijen() == PER_PAGE_DEFAULT
    assert rijen(per_page=25) == 25
    # Een verzonnen maat is invoer uit een URL en valt terug op de standaard —
    # niet op "toon alles".
    assert rijen(per_page=100000) == PER_PAGE_DEFAULT


@pytest.mark.parametrize("pad,sleutel", [(WIJZIGINGEN, "actor"),
                                         (EMAILLOG, "ontvanger")])
def test_de_paginagrootte_overleeft_een_kop_klik(client, db_session, pad, sleutel):
    """Een kop-klik gaat langs de LINK en niet langs de filterbalk.

    Draagt die link de paginagrootte niet, dan valt ze bij het sorteren terug op
    50 — en dat is precies de stille terugval waar dit issue om vraagt.
    """
    _wijzigingen(db_session, 3)
    _emails(db_session, 3)
    _login(client, db_session)

    html = client.get(pad, params={"since": "2000-01-01", "per_page": 25}).text
    koplinks = [r for r in html.splitlines() if f'sort={sleutel}' in r]
    assert koplinks, f"{pad}: geen sorteerlink voor {sleutel} gevonden"
    assert any("per_page=25" in r for r in koplinks), \
        f"{pad}: de sorteerlink van {sleutel} laat de paginagrootte vallen"


def test_de_paginagrootte_reist_mee_bij_het_bladeren(client, db_session):
    """Zonder dit springt pagina 2 terug naar 50 rijen."""
    _wijzigingen(db_session, 60)
    _login(client, db_session)
    html = client.get(WIJZIGINGEN, params={"since": "2000-01-01",
                                           "per_page": 25}).text
    assert "per_page=25" in html and "Volgende" in html


# ── 4. Het veld *Vanaf* blijft, met een zichtbaar label ERNAAST ──────────────

def test_het_vanaf_label_staat_naast_het_veld_niet_erboven(client, db_session):
    """Het label keert terug (Koen, 20 sep) — maar niet als blok-label.

    `ui.label` rendert `block … mb-1` bóven het veld; die kolom is dan hoger dan
    een kaal invoerveld en dwingt de rij terug naar `items-end`. Dat is precies
    waarom het label in #1079 wegviel. Een blok-label verandert de STRUCTUUR van
    de filterbalk niet — de rij-test van #1079 zou er groen bij blijven — dus
    toetst deze test de vorm van het label zelf.
    """
    import re

    _login(client, db_session)
    html = client.get(WIJZIGINGEN).text

    labels = re.findall(r'<label[^>]*for="lw-since"[^>]*>(.*?)</label>', html, re.S)
    assert len(labels) == 1, f"verwacht één label voor lw-since, gevonden {len(labels)}"
    assert "Vanaf" in labels[0]

    tag = re.search(r'<label[^>]*for="lw-since"[^>]*>', html).group(0)
    assert "block" not in tag, f"het label draagt `block` en staat dus bóven het veld: {tag}"

    # De rij blijft één regel: dezelfde uitlijning als de tien andere filterbalken.
    assert "items-center" in html


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
    veld = re.search(r'<input[^>]*id="lw-since"[^>]*>',
                     client.get(WIJZIGINGEN).text).group(0)

    verwacht = (date.today() - timedelta(days=30)).isoformat()
    assert f'value="{verwacht}"' in veld, veld


# ── De filterregel van #1079 blijft staan ────────────────────────────────────

@pytest.mark.parametrize("pad,verwacht", [
    (WIJZIGINGEN, {"actor", "since", "group"}),
    (EMAILLOG, {"recipient", "email_type", "status"}),
])
def test_de_filterregel_blijft_een_rij(client, db_session, pad, verwacht):
    """#1079 mag hier niet sneuvelen: de keuzelijst voor de paginagrootte hangt
    via `form=` aan de balk, maar staat er BUITEN — ze hoort dus geen tweede
    regel in de filterbalk te worden."""
    _login(client, db_session)
    controls = meet(client.get(pad).text)

    assert {naam for _k, naam, _s in controls} == verwacht
    assert len({kind for kind, _n, _s in controls}) == 1, \
        f"{pad}: de filterbalk heeft meer dan één directe kind: {sorted(controls)}"

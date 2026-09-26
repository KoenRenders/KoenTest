"""Vier bewerkvlakken halen hun knoppenrij uit `ui.action_bar` (#1090).

Gevonden op 20 september 2026, na Koens waarneming dat schermen er anders uitzien.
De norm (design-system §2.4, `ui.action_bar`): één cluster per bewerkvlak,
bovenaan, **[Verwijderen]** apart links, dan **[Annuleren] [Opslaan]** met Opslaan
uiterst rechts, alles `sm`. Vier schermen bouwden het cluster met de hand en
kregen het elk anders: de gebruikersrij precies omgekeerd en zonder maat, het
rapportpaneel met Opslaan links en Verwijderen tussen Kopiëren en Exporteren, de
organisatoren met "Bewaren" en Verwijderen rechts, de optierij met een
verwijderknop zonder maat (de #616-fout opnieuw).

Twee dingen zijn bewust géén afwijking en staan hier dus niet: de zichtbaarheid
van Verwijderen op het rapportpaneel (alleen de eigenaar, nooit een meegeleverd
rapport — Koen, 20 september 2026), en `_betalingen_lijst.html`, dat het patroon
correct met de hand nabouwt omdat die rij ook "Status verversen" en een invoerveld
draagt; die staat in de ratchet (#1091).

Per scherm twee toetsen. **Bron:** het cluster komt uit `ui.action_bar` en er
staat geen handgerolde Opslaan/Bewaren meer; bij de organisatoren staat het
cluster in de kopregel naast de opener, vóór de vorm. **Gerenderd:** door de
echte route, met de knoppen in de voorgeschreven volgorde en alle drie op de
kitmaat `sm` — de maat wordt uit de kit zelf gerenderd, niet overgetypt.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
gebruikersrij teruggezet naar haar oude handgerolde rij (Opslaan → Annuleren →
Verwijderen, zonder maat) → de brontest valt om op de ontbrekende `action_bar` en
de rendertest op de volgorde én de maat.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.activities.api import Activity, add_organiser
from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.mdm.api import Member, MemberPerson, Person
from app.ui import templates
from tests._reporting_seed import seed
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

DOMAINS = Path(__file__).resolve().parents[1] / "app" / "domains"

# Scherm → (template, het blok waarin het cluster hoort, handgerolde vormen die
# er niet meer mogen staan).
SCHERMEN = {
    "gebruikers": "auth/templates/_gu_lijst.html",
    "rapportpaneel": "reporting/templates/_rp_paneel.html",
    "organisatoren": "activities/templates/_aa_organisatoren.html",
    "optierij": "forms/templates/_fb_builder.html",
}
HANDGEROLD = ('btn_primary(_("Opslaan")', 'btn_primary(_("Bewaren")',
              'btn_secondary(_("Annuleren")')

CLUSTER = re.compile(
    r'<div class="flex flex-wrap items-center justify-end gap-2[^"]*">[\s\S]*?</div>')


# ── Bron ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scherm", sorted(SCHERMEN))
def test_het_cluster_komt_uit_de_macro(scherm):
    bron = (DOMAINS / SCHERMEN[scherm]).read_text()
    assert "ui.action_bar(" in bron, f"{scherm}: geen ui.action_bar"
    for vorm in HANDGEROLD:
        assert vorm not in bron, f"{scherm}: bouwt nog een eigen {vorm}"


def test_bij_de_organisatoren_staat_het_cluster_in_de_kopregel_naast_de_opener():
    """§2.4: het cluster vervangt de opener op dezelfde regel — niet in de vorm
    eronder, waar het tot #1090 stond."""
    bron = (DOMAINS / SCHERMEN["organisatoren"]).read_text()
    opener = bron.index('ui.edit_toggle("edit")')
    cluster = bron.index('ui.action_bar(form="org-"')
    vorm = bron.index('<form id="org-{{ o.id }}"')
    assert opener < cluster < vorm, (
        "het cluster hoort in de kopregel, na de opener en vóór de bewerkvorm")


# ── Gerenderd ────────────────────────────────────────────────────────────────

def _login(client, db, roles=("ADMIN", "OPERATOR")) -> str:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    bestaand = {r.role_code.value for r in user.roles}  # CR-12 fase 2
    for role in roles:
        if role not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _kitmaat_sm() -> set[str]:
    """De klassen die de kit aan een `sm`-knop geeft — gerenderd, niet overgetypt."""
    sjabloon = templates.env.from_string(
        '{% import "_macros.html" as ui %}{{ ui.btn_class("secondary", "sm") }}')
    secondary = set(sjabloon.render().split())
    sjabloon = templates.env.from_string(
        '{% import "_macros.html" as ui %}{{ ui.btn_class("secondary", "md") }}')
    md = set(sjabloon.render().split())
    maat = secondary - md
    assert maat, "sm en md verschillen niet in klassen; deze meting is leeg"
    return maat


def _clusters(html: str) -> list[str]:
    gevonden = CLUSTER.findall(html)
    assert gevonden, "geen action_bar-cluster in de pagina"
    return gevonden


def _controleer_cluster(cluster: str, *, met_verwijderen: bool) -> None:
    annuleren = cluster.index(">Annuleren<")
    opslaan = cluster.index(">Opslaan<")
    assert annuleren < opslaan, "Opslaan hoort uiterst rechts, na Annuleren"
    if met_verwijderen:
        verwijderen = cluster.index(">Verwijderen<")
        assert verwijderen < annuleren, "Verwijderen hoort apart links"
    else:
        assert ">Verwijderen<" not in cluster
    maat = _kitmaat_sm()
    for knop in re.findall(r"<(?:button|a)\b[^>]*>", cluster):
        klassen = set(re.search(r'class="([^"]*)"', knop).group(1).split())
        assert maat <= klassen, f"knop zonder kitmaat sm: {knop[:120]}"


def test_de_gebruikersrij_rendert_het_cluster_in_volgorde(client, db_session):
    _login(client, db_session)
    html = client.get("/admin/gebruikers").text
    clusters = _clusters(html)
    for cluster in clusters:
        _controleer_cluster(cluster, met_verwijderen=True)


def test_het_rapportpaneel_rendert_het_cluster_in_volgorde(client, db_session):
    seed(db_session)
    _login(client, db_session, roles=("ADMIN",))
    html = client.get("/admin/rapporten/nieuw").text
    (cluster,) = _clusters(html)
    # Een nieuw rapport heeft niets te verwijderen; Opslaan staat wel rechts.
    _controleer_cluster(cluster, met_verwijderen=False)


def test_de_organisatorrij_rendert_het_cluster_in_volgorde(client, db_session):
    activiteit = Activity(name="Quiz met organisator")
    db_session.add(activiteit)
    db_session.flush()
    persoon = Person(first_name="Els", last_name="Trekker")
    db_session.add(persoon)
    db_session.flush()
    gezin = Member()
    db_session.add(gezin)
    db_session.flush()
    db_session.add(MemberPerson(member_id=gezin.id, person_id=persoon.id,
                                relation_type="HOOFDLID"))
    db_session.flush()
    rij = add_organiser(db_session, activiteit.id, persoon.id)
    _login(client, db_session)

    html = client.get(f"/admin/activiteiten/{activiteit.id}").text
    clusters = [c for c in _clusters(html) if f"/organisatoren/{rij.id}/verwijderen" in c]
    assert len(clusters) == 1, "geen cluster voor de organisator"
    _controleer_cluster(clusters[0], met_verwijderen=True)
    assert f'form="org-{rij.id}"' in clusters[0], "Opslaan is niet aan de vorm gebonden"


def test_de_optierij_rendert_het_cluster_in_volgorde(client, db_session, admin_headers):
    antwoord = client.post("/api/v1/forms", json={
        "title": "Knoppenrij", "status": "draft",
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "options": [{"label": "Een", "position": 0}]}],
    }, headers=admin_headers)
    assert antwoord.status_code == 200, antwoord.text
    _login(client, db_session)

    html = client.get(f"/admin/formulieren/{antwoord.json()['id']}").text
    bestaand = [c for c in _clusters(html) if "/opties/" in c and "/verwijderen" in c]
    assert len(bestaand) == 1, "geen cluster voor de bestaande optie"
    _controleer_cluster(bestaand[0], met_verwijderen=True)

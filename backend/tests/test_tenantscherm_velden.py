"""#954: elk veld op het tenantscherm kan ingevuld worden — en blijft staan.

Koens vraag na #945: *"Kan het zijn dat de naam 'Raak Millegem' van de organisatie
niet meer editeerbaar is via tenant config?"* Ja. #945 haalde de
`display_name`-instelling weg omdat de naam uit de organisatie hoort te komen,
maar `name` kwam niet in `ORGANISATIEVELDEN` terecht. Eén bron, nul invoervelden.

**De vorm van deze test is de helft van de waarde.** Ze leest de veldenlijsten
**uit de code** en loopt ze af. Een test die de velden zou nátikken, zou vandaag
groen staan mét deze bug erin — want niemand had `name` in die opsomming gezet.
Dat is dan geen test maar een tweede kopie van de fout. Met de lijst als bron valt
elk veld dat er later bij komt er automatisch onder.

En ze gaat door het **scherm**, niet door de service. Dat is waar deze regressie
zat: de service kon de naam al schrijven, er was alleen geen invoerveld. Een test
die `update_organization_details` rechtstreeks aanroept, staat groen terwijl het
scherm het veld niet toont.

## Wat de lijstgestuurde vorm NIET kan, en wat er daarom bij staat

Op 15 september 2026 is `("name", …)` één keer uit `ORGANISATIEVELDEN` gehaald om
te meten wat er dan gebeurt. Uitkomst: `test_elk_organisatieveld_is_invulbaar`
bleef **groen**. Het veld verdween uit de lijst, dus de parametrisatie maakte er
geen geval meer voor — de test verdween samen met het veld.

Dat is de blinde vlek van elke lijstgestuurde test, en ze is precies de vorm van
de bug die dit issue behandelt: hij vangt *"een veld in de lijst dat stuk is"*,
niet *"een veld dat in de lijst hoort en er niet in staat"*. Alleen de
foutmeldingstest viel om, en dat was toeval.

Er staan daarom twee dingen naast:

- `test_elk_schrijfbaar_organisatieveld_staat_op_het_scherm` vergelijkt de
  schermlijst met wat de **service** kan schrijven (`ALLE_ORGANISATIEVELDEN`).
  Die twee lijsten zijn vandaag twee plaatsen voor één feit; deze test is wat de
  duplicatie draaglijk maakt tot ze ooit één bron wordt.
- `test_de_naam_staat_op_het_scherm` noemt `name` met zoveel woorden. Bewust
  hardgecodeerd: een regressietest die vastpint wát er stuk was, is iets anders
  dan een opsomming die de hele lijst natikt.

Het weghalen van `name` maakt die tweede rood met de naam erin. Gemeten, niet
aangenomen.
"""
from __future__ import annotations

import pytest

from app.domains.mdm.api import secrets_gezet
from app.kernel.tenant_config import get_setting
from app.ui.tenants_ui import (BEKENDE_SLEUTELS, GEHEIME_SLEUTELS,
                               ORGANISATIEVELDEN)
from app.kernel.tenancy import TENANT_VOORBEELD_ID

TENANT = TENANT_VOORBEELD_ID

# Velden met een eigen vorm. De rest krijgt een gewone tekst; staat een sleutel
# hier niet én weigert hij de gewone waarde, dan faalt de test — en dat is de
# bedoeling. Een nieuw veld met eigen validatie hoort op te vallen in plaats van
# stil overgeslagen te worden.
BIJZONDERE_WAARDEN = {
    "legal_form": "VZW",
    "mail_mode": "log_only",
    "noindex": "1",
    "language": "nl_BE",
    "membership_price_full": "35.00",
    "membership_price_half": "17.50",
    "membership_half_price_start_md": "04-16",
    "membership_half_price_end_md": "09-16",
    "membership_next_year_from_md": "09-17",
    "membership_renewal_start_md": "10-01",
    "payment_term_days": "7",
    "max_item_quantity": "50",
    "max_registrations_per_email": "3",
    "admin_chat_enabled": "1",
    "base_url": "https://voorbeeld.example",
    "privacy_url": "https://voorbeeld.example/privacy",
    "umami_src": "https://stats.example/script.js",
    "gmail_user": "afzender@example.com",
    "gmail_from": "Raak Voorbeeld <afzender@example.com>",
}


def _waarde(key: str) -> str:
    return BIJZONDERE_WAARDEN.get(key, f"proef-{key}")


def _operator(client, db_session) -> str:
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from tests.test_reporting_panel_ui import login

    return login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))


def _volledig_formulier() -> dict[str, str]:
    """Alle velden tegelijk, zoals het scherm ze ook verstuurt.

    Eén veld per keer posten zou een andere situatie toetsen: het formulier stuurt
    álles mee, en een handler die maar één sleutel tegelijk aankan zou hier
    doorheen glippen.
    """
    velden = {key: _waarde(key) for key, _label, _hulp in ORGANISATIEVELDEN}
    velden.update({key: _waarde(key) for key, _label, _hulp in BEKENDE_SLEUTELS})
    return velden


@pytest.fixture
def opgeslagen(client, db_session):
    csrf = _operator(client, db_session)
    antwoord = client.post(f"/admin/tenants/{TENANT}", data=_volledig_formulier(),
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:400]
    return client.get(f"/admin/tenants/{TENANT}").text


@pytest.mark.parametrize("key,label", [(k, l) for k, l, _h in ORGANISATIEVELDEN])
def test_elk_organisatieveld_is_invulbaar(key, label, opgeslagen):
    """Invullen, opslaan, terugleezen — en identiek terugkrijgen.

    De lijst komt uit `tenants_ui`; `name` hoorde er tussen #945 en #954 niet in
    te staan en daarom kon niemand de naam van de vereniging nog wijzigen.
    """
    assert f'name="{key}"' in opgeslagen, (
        f"het veld `{key}` ({label}) staat niet op het scherm — dan is het "
        "nergens te bewerken, ook al kan de service het schrijven (#954)")
    assert f'value="{_waarde(key)}"' in opgeslagen, (
        f"`{key}` kwam niet terug met de opgeslagen waarde; het scherm toont "
        "iets anders dan wat er bewaard is")


@pytest.mark.parametrize("key,label", [(k, l) for k, l, _h in BEKENDE_SLEUTELS])
def test_elke_bekende_instelling_is_invulbaar(key, label, opgeslagen, db_session):
    assert f'name="{key}"' in opgeslagen, (
        f"de instelling `{key}` ({label}) staat niet op het scherm")
    bewaard = get_setting(db_session, key, tenant_id=TENANT)
    assert bewaard == _waarde(key), (
        f"`{key}` werd opgeslagen als {bewaard!r} in plaats van "
        f"{_waarde(key)!r}")


def test_elke_geheime_sleutel_wordt_bewaard(client, db_session):
    """Geheimen doen niet mee aan de terugleesstap — ze worden bewust nooit
    teruggetoond. Dát ze aankomen is wel te toetsen."""
    csrf = _operator(client, db_session)
    formulier = _volledig_formulier()
    formulier.update({key: f"geheim-{key}" for key, _l, _h in GEHEIME_SLEUTELS})
    antwoord = client.post(f"/admin/tenants/{TENANT}", data=formulier,
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:400]

    gezet = secrets_gezet(db_session, TENANT,
                          [key for key, _l, _h in GEHEIME_SLEUTELS])
    assert all(gezet.values()), f"niet elke geheime sleutel kwam aan: {gezet}"
    for key, _l, _h in GEHEIME_SLEUTELS:
        assert f"geheim-{key}" not in antwoord.text, (
            f"`{key}` wordt teruggetoond op het scherm — een geheim hoort dat nooit")


def test_elk_schrijfbaar_organisatieveld_staat_op_het_scherm():
    """De schermlijst en de servicelijst mogen niet uit elkaar lopen.

    `tenants_ui.ORGANISATIEVELDEN` draagt de labels, `mdm`'s
    `ALLE_ORGANISATIEVELDEN` zegt wat er geschreven kan worden. Twee plaatsen voor
    één feit — en het gevolg van een verschil is precies de bug van #954: een veld
    dat de service kan bewaren en dat nergens te bewerken is, of een invoerveld
    waarvan de waarde nergens aankomt.

    Zolang de lijsten niet samengevoegd zijn, is dit de goedkope vangrail.
    """
    from app.domains.mdm.api import ALLE_ORGANISATIEVELDEN

    op_scherm = {key for key, _l, _h in ORGANISATIEVELDEN}
    schrijfbaar = set(ALLE_ORGANISATIEVELDEN)
    assert op_scherm == schrijfbaar, (
        "de schermlijst en wat de service schrijft lopen uiteen — "
        f"alleen op het scherm: {sorted(op_scherm - schrijfbaar)}; "
        f"alleen in de service: {sorted(schrijfbaar - op_scherm)}")


def test_de_naam_staat_op_het_scherm():
    """De regressie van #954, met zoveel woorden vastgepind.

    Bewust hardgecodeerd, en dat is geen slordigheid: een lijstgestuurde test kan
    niet zien dat er iets uit zijn eigen lijst ontbreekt — haal `name` weg en er
    verdwijnt gewoon een testgeval. Gemeten op 15 september 2026: de parametrische
    test bleef groen, deze wordt rood.
    """
    assert "name" in {key for key, _l, _h in ORGANISATIEVELDEN}, (
        "de naam van de organisatie staat niet op het tenantscherm. Sinds #945 is "
        "`organizations.name` de enige bron voor de paginatitel, de afzender en de "
        "footer — zonder invoerveld is hij alleen bij het aanmaken te zetten (#954)")


def test_de_lijsten_overlappen_niet(db_session):
    """Een sleutel in beide lijsten zou twee bewerkbare bronnen zijn.

    Precies wat #924 en #945 hebben weggehaald: de instelling won dan van de
    organisatie, of andersom, afhankelijk van de volgorde van opslaan.
    """
    organisatie = {key for key, _l, _h in ORGANISATIEVELDEN}
    instellingen = {key for key, _l, _h in BEKENDE_SLEUTELS}
    geheimen = {key for key, _l, _h in GEHEIME_SLEUTELS}
    assert not (organisatie & instellingen), organisatie & instellingen
    assert not (organisatie & geheimen), organisatie & geheimen
    assert not (instellingen & geheimen), instellingen & geheimen


# ── De naam mag niet leeg ──────────────────────────────────────────────────

def test_een_lege_naam_wordt_geweigerd_met_een_zichtbare_melding(client, db_session):
    """`organizations.name` voedt de paginatitel, de afzender en de footer.

    Sinds #945 heeft `tenant_display_name` geen terugval meer achter de
    organisatie, dus een lege naam laat overal een gat vallen. Hij hoort dus niet
    op te slaan te zijn — en de gebruiker hoort te lezen waaróm.
    """
    csrf = _operator(client, db_session)
    formulier = _volledig_formulier()
    formulier["name"] = "   "

    antwoord = client.post(f"/admin/tenants/{TENANT}", data=formulier,
                           headers={"X-CSRF-Token": csrf})

    assert antwoord.status_code == 422
    assert "Naam van de organisatie" in antwoord.text, (
        "de melding noemt het veld niet bij zijn label")
    assert "paginatitel" in antwoord.text, (
        "de melding zegt niet waaróm een lege naam niet kan")


def test_een_geweigerde_naam_laat_de_rest_ongemoeid(client, db_session):
    """Eerst weigeren, dan pas schrijven.

    Zou de rechtsvorm al bewaard zijn wanneer de naam afketst, dan is de opslag
    half doorgevoerd en klopt het scherm daarna niet meer met de databank.
    """
    from app.domains.mdm.api import Organization

    csrf = _operator(client, db_session)
    client.post(f"/admin/tenants/{TENANT}",
                data={**_volledig_formulier(), "legal_form": "VZW"},
                headers={"X-CSRF-Token": csrf})
    organisatie = (db_session.query(Organization).filter(Organization.id == TENANT)
                   .execution_options(include_all_tenants=True).one())
    db_session.refresh(organisatie)
    naam_vooraf = organisatie.name

    client.post(f"/admin/tenants/{TENANT}",
                data={**_volledig_formulier(), "name": "",
                      "legal_form": "FEITELIJKE_VERENIGING"},
                headers={"X-CSRF-Token": csrf})

    db_session.refresh(organisatie)
    assert organisatie.name == naam_vooraf
    assert organisatie.legal_form == "VZW", (
        "de rechtsvorm is bewaard terwijl de naam geweigerd werd — dan is de "
        "opslag half doorgevoerd")


def test_de_naam_wijzigen_verandert_de_paginatitel(client, db_session):
    """Waarom het veld ertoe doet, in plaats van dat het er alleen staat.

    De naam voedt sinds #945 de schil. Deze test valt om zodra iemand de
    organisatienaam loskoppelt van `tenant_display_name` — en dan is er weer een
    tweede bron.
    """
    csrf = _operator(client, db_session)
    client.post(f"/admin/tenants/{TENANT}",
                data={**_volledig_formulier(), "name": "Raak Andersgem"},
                headers={"X-CSRF-Token": csrf})

    from app.kernel.tenant_config import tenant_display_name

    assert tenant_display_name(db_session, TENANT) == "Raak Andersgem"

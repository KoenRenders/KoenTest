"""#1218 — de bevestiging van een inschrijving gaat naar het INGEVULDE adres.

Koen na de bouw van #1174: *"Zijn er testen geschreven om al die mail-to te
testen?"* Grotendeels wel — de nieuwsbrief naar alle adressen, het voorvullen van
het inschrijfveld en de import zijn afgedekt — maar niets legde vast waar de
bevestiging van een inschrijving hééngaat.

**Dat het veld goed voorgevuld wordt, is iets anders.**
`test_inschrijfadres_volgt_aanmelding.py` bewijst dat de bezoeker het juiste
adres te zíén krijgt; het zegt niets over de ontvanger van de mail. De regel is:
*een bevestiging gaat naar het adres dat je zelf invulde.* Niets belet iemand om
dat over een half jaar te "verbeteren" naar het hoofdadres van de persoon — dat
leest als een opruiming en klinkt zelfs redelijk. Er viel tot nu toe geen enkele
test om.

**De val, en ze is de hele test.** Het aangemelde lid vult hier een ADRES IN DAT
NIET ZIJN HOOFDADRES IS. Vulde de test hetzelfde adres in, dan slaagde hij ook
wanneer de code stilletjes het hoofdadres pakt, en dan bewijst hij niets.
Dezelfde reden waarom de voorvultest zijn tegenhanger heeft.

**Punt 3 van het issue kan niet zoals het er staat, en dat is een bevinding.**
Het vroeg vast te leggen dat er zónder ingevuld adres geen bevestiging vertrekt
(`if data.contact_email:` in de registratieroute). Die tak is onbereikbaar:
`RegistrationCreate.contact_email` is een **verplichte** `EmailStr`, dus een
inschrijving zonder adres komt nooit tot bij die `if`. Pydantic weigert eerder,
en het publieke formulier weigert nog eerder. Hem toch toetsen zou betekenen dat
ik de routerfunctie rechtstreeks aanroep met een met de hand gebouwd object dat
de validatie omzeilt — een test die groen blijft als niemand die functie nog
aanroept. Wat hier in de plaats staat, is wat er wél waar is en wat een bezoeker
werkelijk kan doen: zonder adres is er geen inschrijving en dus geen mail.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten). De
proef is de "verbetering" waar dit issue bang voor is, op de plek waar iemand ze
zou schrijven: in `activities/ui.py` het `contact_email` van het formulier
vervangen door het primaire adres van de aangemelde persoon.

Uitkomst: **1 failed, 2 passed**. De eerste test valt om met *"werk@example.com
verwacht, ['hoofd@example.com'] gekregen"*; de tweede blijft groen omdát daar
niemand aangemeld is, en de derde ook. Dat de tweede blijft staan is geen
zwakte maar de reden dat de eerste een ánder adres invult dan het hoofdadres —
zonder dat verschil zou geen van beide iets zien.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail
from tests.conftest import create_test_family, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

HOOFD = "hoofd@example.com"
WERK = "werk@example.com"
GAST = "gast@example.com"


@pytest.fixture
def verstuurde_mail(monkeypatch):
    """Vangt elke uitgaande mail op de laatste stap vóór SMTP.

    Op `_send` en niet op `send_activity_registration_confirmation`: die tweede
    is precies de functie waarvan dit issue zegt dat ze in geen enkele test
    voorkwam, en hem vervangen zou de weg ernaartoe niet meer toetsen. Via de
    TestClient draaien de achtergrondtaken ná de respons, dus het adres staat er
    tegen de tijd dat de assertie kijkt.
    """
    verstuurd: list[dict] = []

    from app.domains.mail import service as mail_service

    def _vang(to_email, subject, body_html, *args, **kwargs):
        verstuurd.append({"aan": to_email, "onderwerp": subject})

    monkeypatch.setattr(mail_service, "_send", _vang)
    return verstuurd


@pytest.fixture
def lid_met_twee_adressen(db_session):
    _member, person = create_test_family(db_session, email=HOOFD)
    db_session.add(
        ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=WERK, is_primary=False)
    )
    db_session.commit()
    return person


def _schrijf_in(client, activity, component, product, *, email, aangemeld_met=None):
    client.cookies.clear()
    if aangemeld_met:
        client.cookies.set(SESSION_COOKIE, make_session_value(aangemeld_met))
    return client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Deelnemer",
            "contact_email": email,
            "phone": "0470000000",
            f"product_{product.id}": "1",
            "payment_method": "transfer",
        },
    )


def _bevestigingen(verstuurd: list[dict]) -> list[str]:
    return [m["aan"] for m in verstuurd if "Inschrijving bevestigd" in m["onderwerp"]]


def test_een_aangemeld_lid_krijgt_de_bevestiging_op_het_ingevulde_adres(
    client, db_session, lid_met_twee_adressen, verstuurde_mail
):
    """Het geval waarvoor dit issue bestaat.

    Het lid is aangemeld met zijn hoofdadres en vult zijn WERKadres in. Gaat de
    bevestiging naar het hoofdadres, dan landt ze in een mailbox die hij voor
    deze inschrijving niet gebruikt.
    """
    activity, component, product = seed_activity_with_product(db_session)

    respons = _schrijf_in(client, activity, component, product, email=WERK, aangemeld_met=HOOFD)

    assert respons.status_code == 200, respons.status_code
    aan = _bevestigingen(verstuurde_mail)
    assert aan, (
        "er vertrok geen bevestiging; alle opgevangen mail: "
        f"{[m['onderwerp'] for m in verstuurde_mail]}"
    )
    assert aan == [WERK], (
        f"{WERK} verwacht, {aan} gekregen — de bevestiging volgt het hoofdadres "
        "van de persoon in plaats van wat er op het formulier stond (#1218)"
    )
    assert HOOFD not in aan


def test_een_bezoeker_zonder_aanmelding_krijgt_ze_op_het_getypte_adres(
    client, db_session, verstuurde_mail
):
    """Zonder sessie is er geen hoofdadres om per ongeluk te kiezen; deze test
    bewaakt dat het gewone geval blijft werken."""
    activity, component, product = seed_activity_with_product(db_session)

    respons = _schrijf_in(client, activity, component, product, email=GAST)

    assert respons.status_code == 200, respons.status_code
    assert _bevestigingen(verstuurde_mail) == [GAST]


def test_zonder_adres_is_er_geen_inschrijving_en_dus_geen_mail(client, db_session, verstuurde_mail):
    """Wat er in de plaats komt van punt 3 — zie de kop van dit bestand.

    Het formulier weigert de inschrijving vóór er iets bewaard of verstuurd
    wordt. Dat is het echte gedrag en het is langs de weg van een bezoeker
    bereikbaar, anders dan de `if data.contact_email:` die erachter ligt.
    """
    activity, component, product = seed_activity_with_product(db_session)

    respons = _schrijf_in(client, activity, component, product, email="")

    assert respons.status_code == 200
    assert "Vul naam, e-mailadres en mobiel nummer in" in respons.text, (
        "het formulier aanvaardde een inschrijving zonder adres"
    )
    assert not verstuurde_mail, f"er vertrok toch een mail zonder ingevuld adres: {verstuurde_mail}"

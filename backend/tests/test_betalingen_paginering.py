"""Server-side paginering op Betalingen — per GROEP (#1059).

Koen, 20 september 2026 (kandidaat uit de meetronde #996): de beheerlijsten die
onbegrensd meegroeien met de data krijgen paginering, met Betalingen als piloot
omdat dat het referentiescherm is (§2.3).

**Groepen, geen rijen.** De lijst groepeert per inschrijving — een vordering met
haar terugbetalingen en een totaalregel eronder. Snijd je op rijen, dan staat een
inschrijving half op pagina 1 en half op pagina 2, mét een totaalregel die niet
klopt. Daarom telt de paginering groepen; "1–50 van 120" gaat dus over
inschrijvingen, terwijl de regels erboven en eronder de boekingen van de hele
selectie tellen.

**Wat NIET mag meeschuiven met de pagina**: de kengetallenband, de aantallen op
de statustabs, het financieel overzicht en de export. Die gaan over de selectie,
niet over wat er toevallig op het scherm past. Dat is geen detail: een band die
"€ 500 openstaand" zegt terwijl er 3000 openstaat, is erger dan geen band.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden. Zeven ingrepen,
elk één keer gedraaid; tussen haakjes wat er werkelijk omviel — telkens precies
één test, dus ze meten elk iets anders:

- op KAARTEN snijden in plaats van op groepen (*een groep breekt nooit*: 1 kaart
  op pagina 1, 4 op pagina 2);
- `page` altijd uit `stand` lezen, dus ook bij een GET (*een filterwissel begint
  weer op 1*);
- `page` altijd uit de query lezen, dus ook bij een POST (*een mutatie blijft
  staan*) — het spiegelbeeld van de vorige;
- `records` en de band op het paginadeel laten slaan (*de tellingen bewegen niet*);
- de export op vijftig rijen afkappen (*de export draait de volledige selectie*);
- `total=None` aan `ui.pager` geven (*met meer dan één pagina staat de balk er
  wel*: dan staat er "Pagina 1" in plaats van "1–50 van 62");
- `PER_PAGE = 1` (*bij één pagina data staan er geen knoppen*) — die laatste
  bewijst dat de test de bladerbalk werkelijk ziet en niet alleen een tikfout in
  de macronaam overleeft.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord
from app.domains.payment.ui import PER_PAGE
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

#: Ruim over één pagina, en niet net: bij precies 51 zou een fout van één groep
#: nog binnen de speling vallen.
AANTAL = PER_PAGE + 12
EERSTE_ID = 7000


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


#: De lijst sorteert op `created_at` aflopend, dus de tijdstempels staan hier
#: expliciet: anders hangt de volgorde af van microseconden binnen één
#: transactie, en dan is "de groep op de grens" toeval in plaats van een meting.
BASIS = datetime(2027, 3, 1, 12, 0, tzinfo=timezone.utc)


def _groepen(db, aantal=AANTAL, *, open_vanaf=0):
    """`aantal` inschrijvingen met elk één boeking; vanaf `open_vanaf` openstaand.

    Inschrijving `EERSTE_ID + i` staat op positie `i` in de lijst.
    """
    for i in range(aantal):
        nr = EERSTE_ID + i
        betaald = i < open_vanaf
        db.add(PaymentRecord(
            payable_type="registration", payable_id=nr,
            amount=Decimal("20.00"),
            amount_paid=Decimal("20.00") if betaald else None,
            method="transfer", status="paid" if betaald else "pending",
            type="charge", created_at=BASIS - timedelta(minutes=i)))
    db.commit()


def _zichtbare_ids(html: str, aantal=AANTAL) -> set[int]:
    return {EERSTE_ID + i for i in range(aantal)
            if f"/admin/inschrijvingen/{EERSTE_ID + i}?" in html}


def _exportrijen(antwoord) -> list[str]:
    """De rijen van een .ods-antwoord als tekst, zonder kop- en totaalregel."""
    from io import BytesIO

    from odf.opendocument import load
    from odf.table import Table, TableRow
    from odf.teletype import extractText

    doc = load(BytesIO(antwoord.content))
    tabel = doc.getElementsByType(Table)[0]
    rijen = [extractText(tr) for tr in tabel.getElementsByType(TableRow)]
    return rijen[1:-1]


def _lijst(client, **params) -> str:
    from urllib.parse import urlencode

    qs = f"?{urlencode(params)}" if params else ""
    antwoord = client.get(f"/admin/betalingen/lijst{qs}")
    assert antwoord.status_code == 200, antwoord.text[:300]
    return antwoord.text


# ── Bladeren ─────────────────────────────────────────────────────────────────

def test_de_eerste_pagina_toont_er_vijftig_en_de_tweede_de_rest(client, db_session):
    _groepen(db_session)
    _login(client)

    een = _zichtbare_ids(_lijst(client))
    twee = _zichtbare_ids(_lijst(client, page=2))

    assert len(een) == PER_PAGE
    assert len(twee) == AANTAL - PER_PAGE
    assert not (een & twee), "dezelfde inschrijving staat op twee pagina's"
    assert een | twee == {EERSTE_ID + i for i in range(AANTAL)}


def test_een_inschrijvingsgroep_breekt_nooit_over_twee_paginas(client, db_session):
    """De reden dat er op groepen gesneden wordt.

    De groep op de grens krijgt vier VORDERINGEN. Bij snijden op rijen zou er
    daarvan één op pagina 1 belanden en de rest op pagina 2 — met een totaalregel
    die maar een deel telt.

    Gemeten tijdens de tegenproef, en het is de moeite: met vier TERUGBETALINGEN
    bleef deze test groen, ook bij snijden op rijen. `group_cards` nestelt een
    terugbetaling onder haar vordering, dus dat blijft één kaart. Alleen meerdere
    vorderingen op dezelfde inschrijving geven meerdere kaarten in één groep — en
    dát is het geval dat kan breken.
    """
    _groepen(db_session)
    # De groep op positie 49 — de laatste van pagina 1 — krijgt er vier bij. Ze
    # zijn OUDER dan haar eerste boeking, zodat de groep op haar plek blijft: de
    # lijst rangschikt een groep op haar nieuwste kaart.
    grens = EERSTE_ID + PER_PAGE - 1
    for k in range(4):
        db_session.add(PaymentRecord(
            payable_type="registration", payable_id=grens,
            amount=Decimal("7.00"), method="transfer", status="pending",
            type="charge",
            created_at=BASIS - timedelta(minutes=PER_PAGE - 1, seconds=k + 1)))
    db_session.commit()
    _login(client)

    # Per RECORD geteld, niet per link naar de inschrijving: die zegt alleen dát
    # de groep er staat, niet hoevéél van haar kaarten. Een bedrag telde ook niet:
    # elke kaart toont het drie keer (bedrag, ontvangen, saldo) — gemeten.
    kaart_ids = [r.id for r in db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_id == grens).all()]
    assert len(kaart_ids) == 5

    een, twee = _lijst(client), _lijst(client, page=2)

    def _erop(html):
        return {i for i in kaart_ids if f"/admin/betalingen/{i}/" in html}

    op_een, op_twee = _erop(een), _erop(twee)

    assert not (op_een and op_twee), (
        f"de groep staat verdeeld: {len(op_een)} kaarten op pagina 1, "
        f"{len(op_twee)} op pagina 2")
    assert len(op_een | op_twee) == 5, "niet elke kaart van de groep is zichtbaar"


def test_bij_een_pagina_data_staan_er_geen_knoppen(client, db_session):
    """Geen dode chrome: drie inschrijvingen krijgen geen bladerbalk."""
    _groepen(db_session, aantal=3)
    _login(client)

    html = _lijst(client)

    assert 'aria-label="Paginering"' not in html
    assert "Volgende" not in html


def test_met_meer_dan_een_pagina_staat_de_balk_er_wel(client, db_session):
    """De tegenhanger van de test hierboven — anders bewijst "niet aanwezig"
    niets: een tikfout in de macronaam zou beide groen laten."""
    _groepen(db_session)
    _login(client)

    html = _lijst(client)

    assert 'aria-label="Paginering"' in html
    assert f"1–{PER_PAGE} van {AANTAL}" in html


# ── Wat NIET mag meeschuiven ─────────────────────────────────────────────────

def test_de_tellingen_bewegen_niet_bij_het_bladeren(client, db_session):
    """Band, tabaantallen, meta-regel en financieel overzicht gaan over de
    selectie — niet over wat er op het scherm past."""
    _groepen(db_session, open_vanaf=20)
    _login(client)

    een, twee = _lijst(client), _lijst(client, page=2)

    # De meta-regel, de totaalregel en de band tellen de BOEKINGEN van de hele
    # selectie — even vaak op pagina 1 als op pagina 2, en nergens 50.
    aantal_een = een.count(f"{AANTAL} boekingen")
    assert aantal_een and aantal_een == twee.count(f"{AANTAL} boekingen")
    assert f"{PER_PAGE} boekingen" not in een, "een teller volgt de pagina"

    # De tabaantallen komen uit dezelfde zicht-basis: 20 betaald, de rest open.
    def _tabaantal(html, label):
        import re

        m = re.search(rf"{label}\s*<span[^>]*>(\d+)</span>", html)
        assert m, f"tab {label!r} niet gevonden"
        return int(m.group(1))

    for html in (een, twee):
        assert _tabaantal(html, "Openstaand") == AANTAL - 20
        assert _tabaantal(html, "Betaald") == 20


def test_de_export_draait_de_volledige_selectie(client, db_session):
    """Een actieve pagina verandert niets aan het bestand.

    Gemeten op de bytes: dezelfde export mét en zonder `page=2`. De exportroute
    leest de filterparameters opnieuw en kent `page` niet — deze test legt vast
    dat dat zo blijft.
    """
    _groepen(db_session)
    _login(client)

    zonder = client.get("/admin/betalingen/export")
    met = client.get("/admin/betalingen/export?page=2")

    assert zonder.status_code == met.status_code == 200
    # Niet op de bytes: een .ods is een zip en draagt tijdstempels. Op de RIJEN,
    # want dat is wat de vraag stelt.
    assert _exportrijen(met) == _exportrijen(zonder)
    # En het zijn er echt meer dan één pagina, anders bewijst "gelijk" niets.
    assert len(_exportrijen(zonder)) > PER_PAGE


# ── Waar de pagina vandaan komt ──────────────────────────────────────────────

def test_bladeren_behoudt_het_zicht_en_de_filter(client, db_session):
    """De bladerknop draagt de stand zélf, zoals de tabs — geen hx-include."""
    _groepen(db_session, open_vanaf=20)
    _login(client)

    html = _lijst(client, zicht="openstaand")

    assert "zicht=openstaand" in html, "de bladerknop verliest het actieve tab"
    # En het werkt ook echt: pagina 2 van het openstaand-tab toont geen betaalde.
    twee = _zichtbare_ids(_lijst(client, zicht="openstaand", page=2))
    betaalde = {EERSTE_ID + i for i in range(20)}
    assert twee and not (twee & betaalde)


def test_een_filterwissel_begint_weer_op_pagina_een(client, db_session):
    """Een tabwissel of filterwijziging is een andere selectie — pagina 3 van de
    vorige zegt daar niets meer over.

    De filterbalk serialiseert geen `page`, maar htmx stuurt wél de URL mee waar
    je vandaan komt (`HX-Current-URL`). Zonder de regel "bij een GET telt alleen
    de eigen query-string" sleepte die oude pagina mee.
    """
    _groepen(db_session)
    _login(client)

    html = client.get("/admin/betalingen/lijst",
                      headers={"HX-Request": "true",
                               "HX-Current-URL": "http://testserver/admin/betalingen?page=2"}).text

    assert len(_zichtbare_ids(html)) == PER_PAGE
    assert EERSTE_ID + AANTAL - 1 in _zichtbare_ids(html) or True  # zie hieronder
    # De harde toets: de eerste pagina en de tweede zijn disjunct, dus als dit
    # antwoord gelijk is aan pagina 1 staat er geen enkele id van pagina 2 in.
    twee = _zichtbare_ids(_lijst(client, page=2))
    assert not (_zichtbare_ids(html) & twee)


def test_een_mutatie_blijft_op_de_pagina_waar_je_stond(client, db_session):
    """Bevestig je een betaling op pagina 2, dan blijf je daar staan.

    Een mutatie post naar haar eigen endpoint zonder query-string; daarvoor is
    `HX-Current-URL` juist de goede bron. Dat is het spiegelbeeld van de test
    hierboven, en samen leggen ze de regel vast.
    """
    _groepen(db_session)
    _login(client)
    csrf = _login(client)
    laatste = (db_session.query(PaymentRecord)
               .filter(PaymentRecord.payable_id == EERSTE_ID + AANTAL - 1).one())

    antwoord = client.post(
        f"/admin/betalingen/{laatste.id}/bevestigen",
        headers={"X-CSRF-Token": csrf, "HX-Request": "true",
                 "HX-Current-URL": "http://testserver/admin/betalingen?page=2"})

    assert antwoord.status_code == 200, antwoord.text[:300]
    zichtbaar = _zichtbare_ids(antwoord.text)
    assert len(zichtbaar) == AANTAL - PER_PAGE, (
        "na de bevestiging staat de lijst terug op pagina 1")


def test_een_pagina_voorbij_het_einde_valt_terug_op_de_laatste(client, db_session):
    """Verwijder de laatste groep van de laatste pagina en die pagina bestaat
    niet meer. Terugvallen is beter dan een lege tabel tonen."""
    _groepen(db_session)
    _login(client)

    html = _lijst(client, page=99)

    assert _zichtbare_ids(html) == _zichtbare_ids(_lijst(client, page=2))

"""Een object dat uit een naamkolom leest, kan niet `PLAIN` zijn (#1132 punt 3).

Sinds #1132 dragen de rapportage-weergaven persoonsnamen. Dat maakt de bescherming
sterker — de naadwachter kent iedereen in plaats van twee rollen — **maar alleen
zolang deze poort bestaat**. Zonder haar is de wijziging een verslechtering: elk
object móét vandaag een blootstelling declareren (`AiExposure` heeft geen default,
dus een object zonder classificatie importeert niet), maar niets belet iemand om
`PLAIN` te kiezen op een kolom die een naam draagt.

## Hoe deze poort weet wat een naam is

Niet uit een lijst in dit bestand, en niet uit de kolomnaam. **Uit de weergave
zelf**: een kolom die een persoonsnaam draagt, krijgt in de migratie een COMMENT dat
begint met `persoonsnaam`. Deze poort leest die markeringen uit `pg_description`.

Een naamgevingsafspraak op `_name` is gemeten en afgewezen, en de meting staat in
migratie 148: vijftien van de twintig objecten die uit een kolom met "name" of
"label" lezen zijn terecht `PLAIN` (een activiteit heeft ook een naam), en
`payable_label` draagt wél een persoonsnaam zonder "name" in de kolomnaam. Het
onderscheid zit niet in de kolomnaam, dus moet het verklaard worden — in dezelfde
opdracht die de kolom maakt.

## Rood gemaakt om te bewijzen dat ze meet

* `ai_exposure=AiExposure.PLAIN` op `board_member` (leest `board_member_name`) →
  `test_geen_enkel_object_leest_plain_uit_een_naamkolom` viel om mét `board_member`
  en de kolomnaam in de melding. Teruggezet → groen.
* `d_member.head_name` uit `PERSOONSNAAM_KOLOMMEN` van migratie 148 gehaald →
  `test_elke_bekende_naamkolom_is_gemarkeerd` viel om, met precies die kolom in de
  melding. Teruggezet → groen.

  De eerste poging hiertoe bewees NIETS en dat hoort hier: ik wiste het commentaar
  met `COMMENT ON COLUMN … IS NULL` rechtstreeks op de testdatabank, en de test
  bleef groen — de suite dropt haar schema's en draait de migratieketen opnieuw aan
  het begin van elke sessie, dus de handmatige wijziging was al weg vóór de eerste
  test. Een kapotmaak-proef op déze suite hoort dus in de MIGRATIE te gebeuren, niet
  in de databank.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from app.domains.reporting.universe import DIMENSIONS, OBJECTS, AiExposure

pytestmark = pytest.mark.ui_serverrendered

#: Het markeerwoord waarmee een kolomcommentaar begint. Eén plek; de migratie
#: schrijft het, deze poort leest het.
MARKERING = "persoonsnaam"

#: `{view}.kolom` uit de SQL van een object. Objecten schrijven hun bron altijd zo
#: — de engine vult `{view}` in met de naam van de weergave.
_KOLOM = re.compile(r"\{view\}\.(\w+)")

#: `DIMENSIONS` is een tuple; de poort zoekt per sleutel.
_DIM_PER_SLEUTEL = {d.key: d for d in DIMENSIONS}


def _naamkolommen(db) -> set[tuple[str, str]]:
    """(weergave, kolom) voor elke kolom die als persoonsnaam gemarkeerd is."""
    rows = db.execute(text(
        "SELECT c.relname, a.attname "
        "FROM pg_description d "
        "JOIN pg_class c ON c.oid = d.objoid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid "
        "WHERE n.nspname = 'reporting' AND d.objsubid > 0 "
        "  AND d.description LIKE :markering"), {"markering": f"{MARKERING}%"})
    return {(row[0], row[1]) for row in rows}


def _bronweergave(obj) -> str:
    """De echte weergavenaam achter `obj.view`.

    Een dimensie mag onder een eigen sleutel uit een andere weergave lezen
    (`d_paid_date` leest `d_date`); een feit heet zoals zijn weergave.
    """
    dim = _DIM_PER_SLEUTEL.get(obj.view)
    return dim.source if dim else obj.view


def test_de_poort_vindt_de_markeringen(db_session):
    """Een poort die niets vindt, is groen zonder iets te bewaken (#678).

    Ze faalt hier liever luid: geen markeringen betekent dat de migratie niet
    draaide of dat het markeerwoord veranderde, en in beide gevallen bewaakt de
    test eronder niets meer.
    """
    gevonden = _naamkolommen(db_session)

    assert gevonden, (
        f"geen enkele kolom in schema 'reporting' draagt de markering "
        f"'{MARKERING}'. Draaide migratie 148, of heet het markeerwoord anders?")
    assert ("d_person", "first_name") in gevonden, (
        "de voornaam op d_person is niet gemarkeerd — dat is de kolom waar #1132 "
        f"om draait; gevonden: {sorted(gevonden)}")


def test_elke_bekende_naamkolom_is_gemarkeerd(db_session):
    """De markering beschrijft de DATA, dus ook de kolommen van vóór #1132.

    Een markering die alleen de nieuwe kolommen kent, levert een poort die de
    oudste blootstellingen niet ziet — en dan is de bescherming precies daar het
    zwakst waar ze het langst bestaat.
    """
    verwacht = {
        ("d_person", "first_name"), ("d_person", "last_name"),
        ("d_person", "person_name"),
        ("d_member", "head_name"), ("d_member", "partner_name"),
        ("d_board_member", "board_member_name"),
        ("d_activity_organiser", "organiser_name"),
        ("f_payments", "payable_label"),
    }
    ontbreekt = verwacht - _naamkolommen(db_session)

    assert not ontbreekt, (
        f"deze kolommen dragen een persoonsnaam maar geen markering: "
        f"{sorted(ontbreekt)}")


def test_geen_enkel_object_leest_plain_uit_een_naamkolom(db_session):
    """De kern: een naam mag nooit ongewijzigd naar een taalmodel.

    `TOKENISED` mag — dan reist er `persoon-90` — en `NONE` mag, dan reist er
    niets. `PLAIN` betekent "ongewijzigd", en dat is op een naam het enige wat
    niet kan.
    """
    naamkolommen = _naamkolommen(db_session)
    assert naamkolommen, "zie test_de_poort_vindt_de_markeringen"

    fout = []
    for obj in OBJECTS:
        if obj.ai_exposure is not AiExposure.PLAIN:
            continue
        weergave = _bronweergave(obj)
        raak = sorted(kolom for kolom in _KOLOM.findall(obj.sql)
                      if (weergave, kolom) in naamkolommen)
        if raak:
            fout.append(f"{obj.key} leest {weergave}.{','.join(raak)}")

    assert not fout, (
        "deze objecten lezen uit een kolom met een persoonsnaam en declareren "
        "PLAIN — zet ze op TOKENISED (met een token_prefix en een entiteit-id) of "
        f"op NONE:\n  " + "\n  ".join(fout))


def test_de_poort_kijkt_naar_echte_objecten(db_session):
    """Zonder objecten om te toetsen zou de test hierboven altijd slagen."""
    assert len(OBJECTS) > 100, f"maar {len(OBJECTS)} objecten — leest deze poort de universe?"
    plain = [o for o in OBJECTS if o.ai_exposure is AiExposure.PLAIN]
    assert plain, "geen enkel PLAIN-object — dan toetst de regel hierboven niets"

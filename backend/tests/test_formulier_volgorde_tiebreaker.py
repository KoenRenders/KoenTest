"""#725 — een bewerkt veld sprong naar onderen.

Drie lagen samen, en geen ervan is op zichzelf de fout:

1. **De gegevens zijn niet eenduidig.** Veel rijen dragen dezelfde `position` —
   op HDEV 22 groepen dubbele velden en 66 groepen dubbele opties, allemaal op 0.
   Herkomst: `FieldIn.position` heeft default 0 en de import nam die letterlijk over.
2. **Er werd gesorteerd zonder tiebreaker.** `sorted` is stabiel, dus bij gelijkspel
   bleef staan wat de databank teruggaf — en dat is heap-volgorde, geen volgorde.
3. **Een UPDATE verplaatst de rij in de heap.** PostgreSQL schrijft een nieuwe
   tupelversie achteraan, dus het bewerkte veld schoof naar het einde van zijn
   gelijkspel-groep.

**Daarom werkt deze test met een échte UPDATE.** Een test die na het opzetten
gewoon opnieuw bevraagt, reproduceert stap 3 niet en staat groen mét de bug erin.
`db_session.flush()` volstaat niet: de rij moet daadwerkelijk herschreven zijn.

De tweede test is de tegenhanger: hij bewijst dat de volgorde nog altijd door
`position` bepaald wordt en niet stilletjes door `id`. Zonder haar zou "sorteer
altijd op id" ook groen staan — en dan is elke handmatige ordening weg.

Kapotgemaakt om te controleren dat elke test rood kan worden (lokaal, met
scripts/test-local.sh):
  * de tiebreaker uit `order_by` op de relatie → de eerste test valt om; de bouwer
    blijft groen, want die sorteert zelf;
  * daarbovenop de tiebreaker uit de drie sorteringen in `admin_ui._builder_ctx` →
    ook de bouwertest valt om;
  * `field.position = fi.position` terug in `apply_definition` → alleen de
    importtest valt om;
  * de `ORDER BY position, id` in migratie 093 teruggebracht tot `ORDER BY id` →
    alleen de migratietest valt om, op de zichtbare volgorde. Dat is precies het
    verschil tussen de volgorde vastzetten en de volgorde veranderen.

Bij die tweede mutatie kwam een gat in deze test zelf aan het licht: met alleen
`flush()` bediende de route de velden uit de identity map, in de volgorde van vóór
de UPDATE — de test stond dan groen zonder de heap-volgorde ooit aan te raken.
Vandaar de `expire_all()` daar, met dezelfde reden in een commentaar.
"""
import pytest
from sqlalchemy import text

from app.domains.forms.models import Form, FormField

pytestmark = pytest.mark.ui_agnostisch


def _formulier_met_gelijkspel(db, aantal=4) -> Form:
    """Een formulier met `aantal` velden die ALLE dezelfde position dragen.

    Precies de toestand die een JSON-import zonder posities achterliet.
    """
    form = Form(title="Volgordetest", share_token="tok-volgorde-1", status="open")
    db.add(form)
    db.flush()
    for nr in range(aantal):
        db.add(FormField(form_id=form.id, field_type="text",
                         label=f"Vraag {nr + 1}", position=0))
    db.flush()
    return form


def _labels(db, form: Form) -> list[str]:
    """De velden zoals de bouwer ze toont: via de relatie, dus met haar order_by."""
    db.expire_all()
    return [f.label for f in db.get(Form, form.id).fields]


def test_een_bewerkt_veld_blijft_op_zijn_plaats(db_session):
    """Het gemelde geval: "verplicht" aanvinken bij een vraag.

    De UPDATE gaat rechtstreeks naar de databank, want het gaat om wat PostgreSQL
    met de rij doet — niet om wat de ORM in haar identity map bewaart.
    """
    form = _formulier_met_gelijkspel(db_session)
    voor = _labels(db_session, form)
    tweede = db_session.get(Form, form.id).fields[1]

    db_session.execute(
        text("UPDATE form.form_fields SET required = true WHERE id = :id"),
        {"id": tweede.id})

    assert _labels(db_session, form) == voor, (
        "het bewerkte veld is verschoven — de sortering heeft geen tiebreaker")


def test_de_positie_blijft_de_eerste_sleutel(db_session):
    """De tegenhanger, en zonder haar bewijst de vorige test niets.

    "Sorteer op id" zou de test hierboven ook groen zetten, en dan is elke
    handmatige ordening weg. Hier staan de posities juist ómgekeerd aan de id's.
    """
    form = Form(title="Omgekeerd", share_token="tok-volgorde-2", status="open")
    db_session.add(form)
    db_session.flush()
    for nr, positie in enumerate([2, 1, 0]):
        db_session.add(FormField(form_id=form.id, field_type="text",
                                 label=f"Vraag {nr + 1}", position=positie))
    db_session.flush()

    assert _labels(db_session, form) == ["Vraag 3", "Vraag 2", "Vraag 1"]


def test_de_bouwer_toont_dezelfde_volgorde_als_de_relatie(client, db_session,
                                                          admin_headers):
    """De bouwer sorteert zelf (per sectie), dus die weg moet apart afgedekt.

    Zonder deze test kan de relatie kloppen terwijl het scherm iets anders toont —
    en het scherm is waar de melding vandaan komt.
    """
    from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                      make_session_value)
    from tests.conftest import SEEDED_ADMIN_EMAIL

    form = _formulier_met_gelijkspel(db_session)
    tweede = db_session.get(Form, form.id).fields[1]
    db_session.execute(
        text("UPDATE form.form_fields SET required = true WHERE id = :id"),
        {"id": tweede.id})
    # expire_all() is hier geen opsmuk: zonder haar bedient de route de velden uit
    # de identity map, in de volgorde van vóór de UPDATE. De test stond dan groen
    # zonder de heap-volgorde ooit aan te raken — precies het soort test dat niets
    # bewijst. Gemeten: mét flush() alleen bleef hij groen onder de mutatie.
    db_session.expire_all()

    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    csrf_token_for(waarde)
    html = client.get(f"/admin/formulieren/{form.id}").text

    posities = [html.index(f"Vraag {nr}") for nr in (1, 2, 3, 4)]
    assert posities == sorted(posities), (
        "de bouwer toont de vragen in een andere volgorde dan de relatie")


def test_een_import_zonder_posities_levert_geen_dubbels_op(db_session):
    """De herkomst afsluiten: anders komen de dubbels bij de volgende import terug.

    `position` heeft default 0 in het invoerschema, dus een bestand zonder expliciete
    posities zette élk veld op nul. De lijstvolgorde is nu de bron.
    """
    from app.domains.forms.api import apply_definition
    from app.domains.forms.schemas import FormCreate

    form = Form(title="Import zonder posities", share_token="tok-volgorde-3",
                status="open")
    db_session.add(form)
    db_session.flush()

    apply_definition(form, FormCreate(
        title="Import zonder posities",
        fields=[{"field_type": "text", "label": "Eerst"},
                {"field_type": "text", "label": "Dan"},
                {"field_type": "text", "label": "Laatst"}]))
    db_session.flush()

    assert [f.position for f in form.fields] == [0, 1, 2]
    assert _labels(db_session, form) == ["Eerst", "Dan", "Laatst"]


# ── De datastap: migratie 093 ────────────────────────────────────────────────

def _migratie_093():
    """De migratiemodule inladen op pad — `alembic/versions` is geen package."""
    import importlib.util
    from pathlib import Path

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "093_formulier_posities_uniek_per_ouder.py")
    spec = importlib.util.spec_from_file_location("migratie_093", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_de_migratie_hernummert_de_dubbels_zonder_de_volgorde_te_wijzigen(db_session):
    """Twee dingen tegelijk, en het tweede is het gevoelige.

    Hernummeren mag de volgorde die vandaag op het scherm staat niet omgooien: er
    wordt op `(position, id)` gesorteerd, dezelfde sleutel als de code gebruikt.
    Was er op `id` alleen hernummerd, dan zou een formulier met écht gezette
    posities stilletjes van volgorde veranderen — bij honderden rijen op PROD merkt
    niemand dat tot iemand zijn formulier opent.

    De suite draait de migratie vóór er data is, dus dit voert de SQL zelf uit op
    rijen die hier gemaakt zijn.
    """
    migratie = _migratie_093()
    form = _formulier_met_gelijkspel(db_session, aantal=3)
    # Eén veld met een écht gezette positie ertussen, om te tonen dat die telt.
    db_session.add(FormField(form_id=form.id, field_type="text",
                             label="Handmatig eerst", position=-1))
    db_session.flush()
    verwacht = _labels(db_session, form)

    for tabel, partitie in migratie.HERNUMMERINGEN:
        db_session.execute(text(migratie.hernummer_sql(tabel, partitie)))

    db_session.expire_all()
    velden = db_session.get(Form, form.id).fields
    assert [f.position for f in velden] == [0, 1, 2, 3], "de dubbels staan er nog"
    assert [f.label for f in velden] == verwacht, (
        "de hernummering heeft de zichtbare volgorde veranderd")

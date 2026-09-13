"""Elke datum bij haar onderwerp (#901).

Koen, na de hiërarchie van #899: de gewone *Datum* betekende per feit iets anders.
Ze stond op de eigen sleuteldatum van het feit dat je bevraagt — bij inschrijvingen
de inschrijfdatum, bij betalingen de aanmaakdatum. De omschrijving van het
buurobject gaf het zelf toe: *"kalenderjaar van de gebeurtenis (inschrijfdatum of
aanmaakdatum van de betaling)"*.

**Eén object met twee betekenissen is erger dan #894.** Daar stond de fout
zichtbaar in de lijst — twee objecten met bijna dezelfde naam. Hier klopt het
rapport, en weet alleen wie het feit eronder kent wat er geteld is.

De eerste test hieronder is de kerntest die het issue noemt, en ze is met opzet
**mechanisch**: zoek in de omschrijvingen naar een "of" die twee bronnen naast
elkaar zet. Die mag er niet meer staan, en een nieuwe mag er niet bij komen.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import Selection, run_validated
from app.domains.reporting.universe import (BY_KEY, CLASSES, DIMENSION_BY_KEY,
                                            HIERARCHIES, OBJECTS, joins_for)
from tests._reporting_seed import TENANT_A, seed


@pytest.fixture
def situation(db_session):
    return seed(db_session)


# De woorden waarmee een omschrijving een BRON aanwijst. Staan er twee van naast
# een "of", dan geeft het object toe dat het twee dingen kan betekenen — precies
# de vorm die dit issue opruimt.
BRONWOORDEN = ("aanmaak", "inschrijf", "betaal", "inzend", "afhandel",
               "gebeurtenis", "start", "eind")


def _noemt_twee_bronnen(omschrijving: str) -> bool:
    tekst = (omschrijving or "").lower()
    if " of " not in tekst:
        return False
    return len({woord for woord in BRONWOORDEN if woord in tekst}) >= 2


def test_no_description_names_two_sources():
    """De kerntest van dit issue.

    Niet "de omschrijvingen zijn netjes", maar: geen enkele zegt nog dat ze twee
    dingen kan betekenen. Zo'n zin is het spoor van een object dat per feit iets
    anders is, en het is het enige spoor dat er was.
    """
    fouten = [f"{o.name} (`{o.key}`): {o.description}"
              for o in OBJECTS if _noemt_twee_bronnen(o.description)]
    assert not fouten, (
        "omschrijvingen die twee bronnen noemen:\n" + "\n".join(fouten))


def test_the_pattern_would_catch_the_old_description():
    """Anders bewijst de test hierboven niets.

    Dit is de letterlijke zin die in de universe stond vóór dit issue. Vangt het
    patroon die niet meer, dan is de poort een formaliteit geworden.
    """
    oud = ("Kalenderjaar van de gebeurtenis (inschrijfdatum of aanmaakdatum van "
           "de betaling).")
    assert _noemt_twee_bronnen(oud), (
        "het patroon hoort de oude omschrijving te herkennen")
    assert not _noemt_twee_bronnen(
        "Wanneer er betaald is. Opgerold tot maand."), (
        "en een omschrijving met één bron hoort er níét in te vallen")


def test_the_time_class_is_gone():
    """Ingedeeld naar onderwerp, niet naar soort ding — zoals #871 bij betalingen.

    *Tijd* was de laatste klasse die naar een SOORT genoemd was. Zodra elke datum
    bij haar onderwerp staat, blijft er niets over om erin te zetten.
    """
    assert "Tijd" not in CLASSES
    assert not [o.key for o in OBJECTS if o.klass == "Tijd"]


def test_every_date_sits_with_its_subject():
    """De datums van een feit staan in de klasse van dat feit."""
    verwacht = {
        "registration_date": "Activiteiten", "start_date": "Activiteiten",
        "end_date": "Activiteiten", "payment_created": "Betalingen",
        "paid_date": "Betalingen", "member_created": "Leden",
        "form_created": "Formulieren", "submission_date": "Formulieren",
        "task_created": "Taken", "done_date": "Taken",
    }
    werkelijk = {h.key: h.klass for h in HIERARCHIES}
    assert werkelijk == verwacht, werkelijk
    assert BY_KEY["membership_year"].klass == "Leden"


def test_the_same_grain_means_something_different_per_subject(db_session,
                                                              situation):
    """Het punt van dit issue, als meting.

    Betalingen per aanmaakmaand en inschrijvingen per inschrijfmaand zijn twee
    vragen. Tot dit issue heetten ze allebei *Maand* en stond nergens welke van
    de twee je stelde.
    """
    betalingen = run_validated(
        db_session,
        Selection(object_keys=("payment_created_month", "payment_amount")),
        tenant_id=TENANT_A).rows
    inschrijvingen = run_validated(
        db_session,
        Selection(object_keys=("registration_date_month", "registration_count")),
        tenant_id=TENANT_A).rows
    assert betalingen and inschrijvingen
    assert BY_KEY["payment_created_month"].name != \
        BY_KEY["registration_date_month"].name


def test_a_date_of_another_subject_is_refused(db_session, situation):
    """En de vergissing is nu een weigering in plaats van een verkeerd getal.

    Vóór dit issue leverde "lidmaatschappen per maand" gewoon een tabel op — de
    gedeelde datum hing aan élk feit. Nu hoort een betaaldatum niet bij een
    lidmaatschapsrapport, en dat zegt het scherm.
    """
    from app.domains.reporting.engine import SelectionError

    with pytest.raises(SelectionError):
        run_validated(
            db_session,
            Selection(object_keys=("paid_date_month", "membership_households")),
            tenant_id=TENANT_A)


def test_the_activity_end_date_is_not_joined_twice():
    """`f_activities.date_key` IS de einddatum, en die had al een eigen rol.

    Twee namen voor dezelfde kolom is precies wat dit issue opruimt, en het stond
    er sinds #895 zonder dat iemand het zag.
    """
    kalender = {v for v in joins_for("f_activities")
                if DIMENSION_BY_KEY.get(v) is not None
                and DIMENSION_BY_KEY[v].source == "d_date"}
    assert kalender == {"d_activity_start", "d_activity_end"}, kalender


def test_every_shipped_report_still_names_an_existing_object(db_session,
                                                             situation):
    """De sleutels wijzigden hier wél, anders dan bij #899.

    Een object veranderde van klasse én van betekenis, dus de bewaarde selecties
    moesten mee in dezelfde migratie. Dit is dezelfde controle als de gate van
    #880, hier herhaald omdat dit issue precies de wijziging is die haar op de
    proef stelt.
    """
    from app.domains.reporting.api import list_saved_reports, selection_from_dict

    for rapport in list_saved_reports(db_session, tenant_id=TENANT_A, viewer=""):
        if not rapport.builtin_key:
            continue
        selectie = selection_from_dict(rapport.selection)
        onbekend = [k for k in selectie.object_keys if k not in BY_KEY]
        assert not onbekend, f"{rapport.builtin_key}: {onbekend}"
        for filter_ in selectie.filters:
            assert filter_.object_key in BY_KEY, (
                f"{rapport.builtin_key}: filter op {filter_.object_key}")

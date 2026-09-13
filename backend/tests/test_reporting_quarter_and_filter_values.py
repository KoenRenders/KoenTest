"""Drie dingen die een plausibel scherm opleverden (#912).

Koen vond ze bij gebruik en niet met de suite, en dat is geen toeval: alle drie
falen ze **zichtbaar nergens**. Een kwartaal zonder jaartal telt netjes op, een
jaarfilter werkt, en een te lange lijst oogt volledig.

Daarom staan de tests hieronder op de **uitkomst** en niet op de aanwezigheid: dat
twee jaargangen niet samenvallen, dat het filter het huidige niveau draagt, en dat
de lijst geen waarde bevat die in het feit niet voorkomt.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (BY_KEY, Selection, dimension_values,
                                       run_validated)
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    """De seed plus één betaling in een ANDER jaar.

    De gedeelde seed zet elke betaling binnen tweehonderd dagen van vandaag, dus
    alles valt in één jaargang — en dan is niet te zien dat twee jaargangen
    samenvallen in één kwartaalrij. Hier en niet in de seed: die draagt met de
    hand uitgerekende verwachtingen voor elk bedrag.
    """
    gegevens = seed(db_session)
    # Twee betalingen in DEZELFDE maand, twee jaar uit elkaar. Niet "schuif er
    # eentje twee jaar terug": dan verhuist die rij en houdt haar oude kwartaal
    # misschien geen enkele andere betaling over — of wel, afhankelijk van de dag
    # waarop de suite draait. Deze test viel daar al een keer over om, alleen in
    # de volledige run, en een test die met de kalender meebeweegt is erger dan
    # geen test.
    db_session.execute(text(
        "UPDATE payment.payment_records b "
        "SET created_at = a.created_at - interval '2 years' "
        "FROM (SELECT created_at FROM payment.payment_records "
        "      WHERE tenant_id = :t ORDER BY id LIMIT 1) a "
        "WHERE b.tenant_id = :t "
        "  AND b.id = (SELECT MAX(id) FROM payment.payment_records "
        "              WHERE tenant_id = :t)"), {"t": TENANT_A})
    db_session.commit()
    return gegevens


def _paneel(client, query: str = "") -> str:
    antwoord = client.get(f"/admin/rapporten/paneel?{query}")
    assert antwoord.status_code == 200
    return antwoord.text


# ── 1. Het kwartaal draagt zijn jaartal ─────────────────────────────────────

def test_two_years_do_not_collapse_into_one_quarter(db_session, situation):
    """De schade, en dus de test.

    De seed heeft betalingen in meer dan één jaar. Groepeer op kwartaal en elk
    jaar hoort zijn eigen rij te houden; zonder jaartal vielen ze samen in een
    getal dat optelt en een andere vraag beantwoordt.
    """
    per_jaar = run_validated(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount")),
        tenant_id=TENANT_A).rows
    assert len({r["payment_created_year"] for r in per_jaar}) > 1, (
        "de seed hoort betalingen in meer dan één jaar te hebben, anders meet "
        "deze test niets")

    per_kwartaal = run_validated(
        db_session,
        Selection(object_keys=("payment_created_quarter", "payment_amount")),
        tenant_id=TENANT_A).rows
    kwartalen = [r["payment_created_quarter"] for r in per_kwartaal]
    jaren = {k.split("-")[0] for k in kwartalen}
    assert len(jaren) > 1, (
        f"alle kwartalen vallen in één jaar: {kwartalen} — het jaartal ontbreekt "
        "in het label en twee jaargangen zijn samengevallen")
    assert len(kwartalen) == len(set(kwartalen)), f"dubbele rijen: {kwartalen}"


def test_the_breakage_is_what_collapsing_looks_like(db_session, situation):
    """Het tegenbewijs: zonder jaartal vallen de rijen wél samen.

    Gebroken door de uitdrukking terug te zetten op het kale kwartaalnummer —
    precies zoals ze stond. Het aantal rijen zakt, het totaal blijft gelijk, en
    niets faalt: dát is waarom dit pas bij gebruik gevonden werd.
    """
    heel = run_validated(
        db_session,
        Selection(object_keys=("payment_created_quarter", "payment_amount")),
        tenant_id=TENANT_A).rows

    # De fixture schoof één betaling exact twee jaar terug: zelfde maand, dus
    # hetzelfde kwartaalNUMMER in een ander jaar. Kaal vallen die twee samen.
    kaal = {rij[0] for rij in db_session.execute(text(
        "SELECT DISTINCT d_payment_created.quarter "
        "FROM reporting.f_payments AS f_payments "
        "LEFT JOIN reporting.d_date AS d_payment_created "
        "  ON d_payment_created.tenant_id = f_payments.tenant_id "
        " AND d_payment_created.date_key = f_payments.date_key "
        "WHERE f_payments.tenant_id = :t"), {"t": TENANT_A})}
    gelabeld = {r["payment_created_quarter"] for r in heel}
    assert len(kaal) < len(gelabeld), (
        f"kaal {sorted(kaal)} tegenover gelabeld {sorted(gelabeld)} — vallen ze "
        "niet samen, dan toont deze test de schade niet")


def test_the_quarter_sorts_chronologically(db_session, situation):
    """Chronologisch en niet alfabetisch — de les van het huisnummer in #850.

    `2026-K1` sorteert toevallig goed als tekst, maar de sorteersleutel staat op
    (jaar, kwartaal) omdat "toevallig goed" geen ontwerp is.
    """
    from app.domains.reporting.api import build_query
    from app.domains.reporting.engine import Sort

    plan = build_query(
        Selection(object_keys=("payment_created_quarter", "payment_amount"),
                  sort=(Sort("payment_created_quarter"),)),
        tenant_id=TENANT_A)
    assert "quarter" in plan.sql and "year" in plan.sql
    assert BY_KEY["payment_created_quarter"].sort_sql, (
        "zonder eigen sorteersleutel sorteert het kwartaal op zijn etiket")


# ── 2. Het filter volgt het niveau waarop je staat ──────────────────────────

def test_the_filter_button_follows_the_level_you_are_on(client, db_session,
                                                        situation):
    """De knop gebruikte altijd het bovenste niveau.

    Wie tot de dag gedrild had, kreeg nog steeds een jaarfilter: het aanbod ging
    over waar je begon in plaats van over waar je bent.
    """
    login(client, db_session)
    ondiep = _paneel(client, "object=payment_created_year&object=payment_amount")
    assert 'name="add_filter" value="payment_created_year"' in ondiep

    diep = _paneel(client, "object=payment_created_year"
                           "&object=payment_created_quarter"
                           "&object=payment_created_day&object=payment_amount")
    assert 'name="add_filter" value="payment_created_day"' in diep, (
        "tot de dag gedrild hoort de filterknop de dag te bieden")
    assert 'name="add_filter" value="payment_created_year"' not in diep


def test_an_unused_hierarchy_still_offers_its_top_level(client, db_session,
                                                        situation):
    """Anders heeft een datum die je nog niet koos géén filterknop meer."""
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_year&object=payment_amount")
    assert 'name="add_filter" value="paid_date_year"' in tekst


# ── 3. De waarden komen uit de data, niet uit de kalender ───────────────────

def test_the_filter_only_offers_values_that_occur(db_session, situation):
    """De kalender loopt van 2015 tot twee jaar vooruit.

    Rechtstreeks lezen bood dus elk jaar aan, ook jaren zonder één betaling —
    letterlijk de eis uit #907 die niet mee gebouwd was.
    """
    uit_de_data = dimension_values(db_session, "payment_created_year",
                                   tenant_id=TENANT_A, fact="f_payments")
    werkelijk = {str(r["payment_created_year"]) for r in run_validated(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount")),
        tenant_id=TENANT_A).rows}
    assert uit_de_data, "er hoort iets aangeboden te worden"
    assert set(uit_de_data) == werkelijk, (
        f"aangeboden {sorted(uit_de_data)}, terwijl het feit alleen "
        f"{sorted(werkelijk)} kent")


def test_reading_the_calendar_straight_offers_far_too_much(db_session,
                                                           situation):
    """Het tegenbewijs, en het toont meteen de omvang.

    Zonder feit leest dezelfde functie de dimensie rechtstreeks — het gedrag van
    vóór dit issue. Dat biedt jaren aan waarin geen enkele betaling valt, en het
    is geen randgeval: de kalender omspant meer dan tien jaargangen.
    """
    uit_de_kalender = dimension_values(db_session, "payment_created_year",
                                       tenant_id=TENANT_A)
    uit_de_data = dimension_values(db_session, "payment_created_year",
                                   tenant_id=TENANT_A, fact="f_payments")
    # Boven de aanbodgrens geeft de functie een lege lijst terug; ook dát is het
    # bewijs dat de kalender te veel jaren draagt om aan te bieden.
    assert not uit_de_kalender or len(uit_de_kalender) > len(uit_de_data), (
        f"kalender {uit_de_kalender} tegenover data {uit_de_data}")


def test_the_values_are_offered_in_the_report_order(db_session, situation):
    """Een andere volgorde dan het rapport leest als een tweede lijst."""
    waarden = dimension_values(db_session, "payment_created_quarter",
                               tenant_id=TENANT_A, fact="f_payments")
    assert waarden == sorted(waarden), waarden


def test_a_dimension_that_does_not_belong_to_the_fact_offers_nothing(
        db_session, situation):
    """Geen uitzondering, maar een lege lijst: het paneel toont dan een tekstveld
    in plaats van een keuzelijst, en dat is precies goed voor iets wat hier niet
    hoort."""
    assert dimension_values(db_session, "payment_created_year",
                            tenant_id=TENANT_A, fact="f_memberships") == []


def test_a_month_filter_is_a_dropdown_and_not_a_search_box(client, db_session,
                                                           situation):
    """Koens eis, en ze wordt op de UITKOMST getoetst.

    Boven `OFFER_LIMIT` wordt een filter bewust een zoekveld, en die regel is
    juist: *"a municipality list of four hundred is a search box, not a
    dropdown."* De maandlijst was alleen zo lang omdat ze uit de KALENDER kwam —
    bijna veertien jaargangen, 165 maanden. Uit de data blijven er een handvol
    over en verschijnt de keuzelijst vanzelf.

    Dus niet "de opgehaalde waarden kloppen" — dat kan waar zijn terwijl het
    element een tekstveld blijft — maar: er staat een `<select>` met die maanden
    erin. `OFFER_LIMIT` blijft waar hij staat; de bron was de klem, niet de grens.
    """
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_month&object=payment_amount"
                            "&filter=payment_created_month")

    maanden = dimension_values(db_session, "payment_created_month",
                               tenant_id=TENANT_A, fact="f_payments")
    assert 0 < len(maanden) <= 12, (
        f"{len(maanden)} maanden in de data — komt de lijst nog uit de kalender?")

    blok = tekst[tekst.index('name="v_payment_created_month"'):]
    blok = blok[:blok.index("</select>")] if "</select>" in blok else ""
    assert blok, "het maandfilter hoort een keuzelijst te zijn, geen tekstveld"
    for maand in maanden:
        assert f'value="{maand}"' in blok, f"{maand} ontbreekt in de keuzelijst"


def test_the_offer_limit_still_protects_a_long_list(db_session, situation):
    """De grens blijft staan, en dat is geen detail.

    Ze beschermt de gemeentelijst — vierhonderd gemeenten horen een zoekveld te
    zijn. De bron was de klem, niet de grens, dus de grens is niet aangeraakt.
    """
    from app.domains.reporting.service import OFFER_LIMIT

    assert OFFER_LIMIT == 60
    # En een dimensie met méér waarden dan dat geeft nog steeds een lege lijst,
    # dus een tekstveld.
    veel = dimension_values(db_session, "payment_created_day",
                            tenant_id=TENANT_A)
    assert veel == [], "een datumlijst uit de kalender hoort een zoekveld te zijn"

"""Reporting per responsible board member (#849).

Koen: *"Het bestuurslid dat toegewezen is aan een gezin. Een bestuurslid neemt de
leden in zijn omgeving tot zijn verantwoordelijkheid."* The term is
**"Verantwoordelijk bestuurslid"**, the one the family portal already uses; the
word that goes round in conversation is not in the product and is not introduced
here.

Two things are worth a test and one of them is easy to get wrong. The dimension
**snowflakes**: it hangs off the household and not off a fact, which is the first
chained join in this universe — so the first test is that the chain resolves and
does not multiply anything. The second is that a household **without** a board
member stays visible: `board_member_id` is nullable, an INNER JOIN would swallow
those rows, and "not assigned" is one of the most useful answers this report gives.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (
    Selection, list_saved_reports, run_validated, selection_of,
)
from tests._reporting_seed import TENANT_A, TENANT_B, seed
from tests.test_reporting_panel_ui import ADMIN_EMAIL, login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _assign(db, situation, *, first: str, last: str, households: list[str]):
    """Make a board member and put some households in their care."""
    from app.domains.mdm.api import Member, Person

    bestuurslid = Person(tenant_id=TENANT_A, first_name=first, last_name=last,
                         date_of_birth=date(1980, 1, 1), gender_code="M")
    db.add(bestuurslid)
    db.flush()
    for sleutel in households:
        gezin = db.query(Member).filter(
            Member.id == situation["households"][sleutel]).first()
        gezin.board_member_id = bestuurslid.id
    db.commit()
    return bestuurslid


def _per_board_member(db, extra=()):
    result = run_validated(
        db,
        Selection(object_keys=("board_member", "membership_households", *extra)),
        tenant_id=TENANT_A)
    return {row["board_member"]: row for row in result.rows}


# ── The chained join ─────────────────────────────────────────────────────────

def test_the_board_member_hangs_off_the_household_and_multiplies_nothing(
        db_session, situation):
    """The first snowflake in this universe: fact → d_member → d_board_member.

    Same grain as the household it hangs off, so the counts underneath are
    untouched. A chain that multiplied would show it here first, as a total that
    is suddenly larger than the report without the dimension.
    """
    _assign(db_session, situation, first="Anna", last="Bestuur",
            households=["h1", "h3"])

    zonder = run_validated(
        db_session, Selection(object_keys=("membership_households",)),
        tenant_id=TENANT_A).rows[0]["membership_households"]
    met = sum(r["membership_households"] for r in _per_board_member(db_session).values())
    assert met == zonder, (
        "de dimensie erbij mag het totaal niet veranderen — dat is wat een "
        "vermenigvuldigende join wél doet")


def test_a_household_without_a_board_member_stays_visible(db_session, situation):
    """`board_member_id` is nullable, and "niet toegewezen" is a useful answer.

    An INNER JOIN would swallow these rows and the report would quietly describe
    only the assigned part of the association.
    """
    _assign(db_session, situation, first="Anna", last="Bestuur", households=["h1"])
    per_lid = _per_board_member(db_session)

    assert "Anna Bestuur" in per_lid
    assert "Niet toegewezen" in per_lid, (
        "gezinnen zonder bestuurslid horen als eigen rij te verschijnen")
    assert per_lid["Niet toegewezen"]["membership_households"] > 0


def test_the_distribution_is_what_the_report_is_for(db_session, situation):
    """"Heeft er iemand dertig terwijl een ander er acht heeft?" """
    _assign(db_session, situation, first="Anna", last="Bestuur",
            households=["h1", "h2"])
    _assign(db_session, situation, first="Bram", last="Bestuur",
            households=["h3"])

    _y0, _y1, y2, _y3 = situation["years"]
    result = run_validated(
        db_session,
        Selection(object_keys=("board_member", "membership_households"),
                  filters=()),
        tenant_id=TENANT_A)
    per_lid = {row["board_member"]: row["membership_households"]
               for row in result.rows}
    assert per_lid["Anna Bestuur"] >= per_lid["Bram Bestuur"], (
        "Anna draagt er twee, Bram één — over alle jaren samen"
    )
    assert y2


def test_the_dimension_stays_inside_its_tenant(db_session, situation):
    _assign(db_session, situation, first="Anna", last="Bestuur", households=["h1"])
    b = run_validated(
        db_session, Selection(object_keys=("board_member", "membership_households")),
        tenant_id=TENANT_B)
    assert "Anna Bestuur" not in {row["board_member"] for row in b.rows}


def test_only_board_members_who_carry_a_household_are_in_the_dimension(db_session,
                                                                       situation):
    """A person is not a board member until a household is put in their care."""
    from app.domains.mdm.api import Person

    db_session.add(Person(tenant_id=TENANT_A, first_name="Niemand",
                          last_name="Bestuur", date_of_birth=date(1980, 1, 1),
                          gender_code="M"))
    db_session.commit()
    namen = {row[0] for row in db_session.execute(text(
        "SELECT board_member_name FROM reporting.d_board_member "
        "WHERE tenant_id = :t"), {"t": TENANT_A})}
    assert "Niemand Bestuur" not in namen


# ── The shipped report ───────────────────────────────────────────────────────

def test_the_shipped_report_is_a_work_list(db_session, situation):
    """Not a number: households per board member WITH their membership status."""
    _assign(db_session, situation, first="Anna", last="Bestuur",
            households=["h1", "h3"])

    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == "households_per_board_member")
    selectie = selection_of(rapport)
    assert "membership_status" in selectie.object_keys, (
        "de status maakt het een werklijst in plaats van een telling")
    assert selectie.filters[0].symbolic == "dit_jaar", (
        "het jaar is relatief, anders is de werklijst volgend jaar verouderd")

    _y0, _y1, y2, _y3 = situation["years"]
    resultaat = run_validated(db_session, selectie, tenant_id=TENANT_A,
                              today=date(y2, 6, 1))
    assert resultaat.rows, "het rapport draait"
    assert {"board_member", "membership_status"} <= set(resultaat.rows[0])


def test_the_report_opens_in_the_panel(client, db_session, situation):
    _assign(db_session, situation, first="Anna", last="Bestuur", households=["h1"])
    login(client, db_session)
    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == "households_per_board_member")
    pagina = client.get(f"/admin/rapporten/{rapport.id}")
    assert pagina.status_code == 200
    assert "Verantwoordelijk bestuurslid" in pagina.text
    assert "wijkmeester" not in pagina.text.lower(), (
        "één woord voor één ding — de spreektaal hoort niet in het product")

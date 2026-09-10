"""The query panel: the list, the panel, saving and exporting (#833).

CR-06 §5. What is asserted here is what a board member actually does — open the
list, put three objects in a table, filter it, sort it, save it, take it home —
and the fences around that: the tenant, the door, and the validation of a
selection before any query runs.

Would these tests be green if the subject were broken? The numbers come from the
known seed of #832, so a wrong join or a lost tenant condition shows up as a
number that is not the one written down. The refusals assert the *reason* and not
the status (#680): a 403 is also what a missing CSRF token produces, and a 422 is
also what a typo produces.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value,
)
from tests._reporting_seed import EXPECTED, TENANT_A, TENANT_B, seed

ADMIN_EMAIL = "rapport-beheer@example.com"
OTHER_EMAIL = "rapport-collega@example.com"


def login(client, db, email=ADMIN_EMAIL, roles=("ADMIN",)) -> str:
    """Sign in as a back-office user; returns the CSRF token for mutations."""
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
    bestaand = {r.role_code for r in user.roles}
    for role in roles:
        if role not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


@pytest.fixture
def situation(db_session):
    return seed(db_session)


# ── The door (#833 test 2) ───────────────────────────────────────────────────

def test_reporting_needs_a_session(client):
    assert client.get("/admin/rapporten").status_code == 401
    assert client.get("/admin/rapporten/nieuw").status_code == 401


def test_a_finance_only_user_is_refused_with_the_reason(client, db_session):
    """No new security surface: FINANCE alone is not a back-office role here.

    The reason and not just the status — a 403 is also what an expired session or
    a missing CSRF token produces, and those need a different fix.
    """
    login(client, db_session, "alleen-penning@example.com", ("FINANCE",))
    for url in ("/admin/rapporten", "/admin/rapporten/nieuw",
                "/admin/rapporten/paneel"):
        antwoord = client.get(url)
        assert antwoord.status_code == 403, url
        assert antwoord.json()["detail"] == "Geen toegang", url


def test_a_finance_only_user_does_not_see_the_menu_item(db_session):
    from app.ui import admin_nav

    labels = [item["href"] for item in admin_nav("/admin/betalingen",
                                                 roles=["FINANCE"])]
    assert labels == ["/admin/betalingen"]


def test_an_admin_and_an_operator_both_get_in(client, db_session, situation):
    for email, roles in (("beheer-a@example.com", ("ADMIN",)),
                         ("beheer-o@example.com", ("OPERATOR",))):
        login(client, db_session, email, roles)
        pagina = client.get("/admin/rapporten/nieuw")
        assert pagina.status_code == 200, email
        # All four classes are offered: the role fence is declared, not enforced.
        for klasse in ("Leden", "Activiteiten", "Betalingen", "Tijd"):
            assert klasse in pagina.text, f"{email} mist de klasse {klasse}"


# ── The list (#833 point 2) ──────────────────────────────────────────────────

def test_the_shipped_reports_are_on_the_list(client, db_session, situation):
    login(client, db_session)
    pagina = client.get("/admin/rapporten")
    assert pagina.status_code == 200
    for naam in ("Leden per jaar", "Nieuw, vernieuwd en vervallen per jaar",
                 "Inschrijvingen per activiteit", "Opbrengst per activiteit",
                 "Omzet per maand", "Openstaand en hoe lang al",
                 "Betaalwijze en betaaltermijn"):
        assert naam in pagina.text, naam


def test_the_list_searches_and_filters(client, db_session, situation):
    login(client, db_session)
    gevonden = client.get("/admin/rapporten/lijst?q=Omzet")
    assert "Omzet per maand" in gevonden.text
    assert "Leden per jaar" not in gevonden.text

    eigen = client.get("/admin/rapporten/lijst?owner=mine")
    assert "Leden per jaar" not in eigen.text, (
        "de meegeleverde rapporten zijn van de afdeling, niet van mij")


# ── The seven shipped reports on the known seed (#833 test 5) ────────────────

def test_the_shipped_reports_return_the_numbers_of_the_seed(db_session, situation):
    """Each of the seven, run through the engine exactly as its card would.

    This is the test that makes the seed worth having: a shipped report that
    returns a plausible but wrong number would look right on day one and be
    believed for a year.
    """
    from app.domains.reporting.api import (
        list_saved_reports, run_validated, selection_of,
    )

    reports = {r.builtin_key: r for r in
               list_saved_reports(db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
               if r.builtin_key}
    # Seven since #833, ten since #841 (the questions of CR-06 §3), plus the
    # payments listing of #841 point 4.
    assert len(reports) == 11, "de elf meegeleverde rapporten staan er"

    def run(key):
        selection = selection_of(reports[key])
        return run_validated(db_session, selection, tenant_id=TENANT_A)

    _y0, _y1, y2, _y3 = situation["years"]

    leden = {row["membership_year"]: row for row in run("members_per_year").rows}
    assert leden[y2]["membership_households"] == EXPECTED["memberships"]["households"][2]
    assert leden[y2]["membership_persons"] == EXPECTED["memberships"]["persons"][2]

    verloop = {row["membership_year"]: row
               for row in run("membership_flow_per_year").rows}
    assert verloop[y2]["membership_new"] == EXPECTED["memberships"]["new"][2]
    assert verloop[y2]["membership_lapsed"] == EXPECTED["memberships"]["lapsed"][2]

    inschrijvingen = run("registrations_per_activity").rows
    assert inschrijvingen[0]["activity"] == "Quiz"
    assert inschrijvingen[0]["registration_count"] == \
        EXPECTED["registrations"]["count"]

    opbrengst = {row["activity"]: row for row in run("revenue_per_activity").rows}
    assert Decimal(opbrengst["Quiz"]["payment_amount"]) == \
        EXPECTED["payments"]["per_activity"]["Quiz"]["amount"]

    omzet = run("revenue_per_month")
    assert Decimal(omzet.totals["payment_amount"]) == EXPECTED["payments"]["amount"]

    openstaand = {row["payment_age_bucket"]: row
                  for row in run("outstanding_by_age").rows}
    assert Decimal(openstaand["meer dan 90 dagen"]["payment_open_amount"]) == \
        Decimal("10.00")

    betaalwijze = {row["payment_method"]: row
                   for row in run("payment_method_per_month").rows}
    assert set(betaalwijze) == {"Online", "Overschrijving", "Cash"}


# ── Building a report in the panel (#833 points 3 and 4) ─────────────────────

def test_the_empty_panel_says_what_to_do(client, db_session, situation):
    login(client, db_session)
    paneel = client.get("/admin/rapporten/nieuw")
    assert "Kies objecten links, filters rechts." in paneel.text


def test_adding_objects_puts_them_in_the_order_they_were_added(client, db_session,
                                                               situation):
    """A newly added object lands at the end, and the columns follow that order."""
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=activity&add=registration_count")
    assert fragment.status_code == 200
    # The hidden state IS the column order, so that is what is asserted — the
    # objects pane also contains both names and would make a text search lie.
    import re

    volgorde = re.findall(r'name="object" value="([a-z_]+)"', fragment.text)
    assert volgorde == ["activity", "registration_count"]


def test_the_table_totals_the_measures(client, db_session, situation):
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount")
    assert fragment.status_code == 200
    assert "Totaal" in fragment.text
    # 120,00 is the seed's net total; the row amounts are 45, 45 and 30.
    assert "120,00" in fragment.text


def test_a_filter_narrows_the_table(client, db_session, situation):
    login(client, db_session)
    alles = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount")
    assert "Cash" in alles.text

    gefilterd = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&filter=payment_method&op_payment_method=eq&v_payment_method=Online")
    # Not a text search: "Cash" is also an option in the filter dropdown. Its
    # amount is what may not be in the table any more.
    assert "45,00" in gefilterd.text
    assert "30,00" not in gefilterd.text, "de cash-rij hoort weggefilterd te zijn"


def test_a_filter_value_the_dimension_does_not_have_is_refused(client, db_session,
                                                               situation):
    """#833 test 6: refused before a query runs, with the reason.

    An unknown value would otherwise return an empty table, and an empty table
    reads as "no data" instead of "you filtered on something that is not there".
    """
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&filter=payment_method&op_payment_method=eq&v_payment_method=Bancontact")
    assert "Bancontact" in fragment.text
    assert "geen waarde van" in fragment.text


def test_two_facts_in_one_report_are_refused_in_the_panel(client, db_session,
                                                          situation):
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=registration_count&object=payment_amount")
    assert "twee feiten" in fragment.text
    assert "Inschrijvingen" in fragment.text and "Betalingen" in fragment.text


def test_an_unknown_object_key_is_simply_not_part_of_the_report(client, db_session,
                                                                situation):
    """A key the universe does not know never reaches the engine.

    Dropped while reading the state rather than refused: a stale link with one
    unknown object should still open, and the engine only ever sees keys that
    exist.
    """
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_amount&object=verzonnen_object")
    assert fragment.status_code == 200
    assert "verzonnen_object" not in fragment.text


def test_sorting_turns_around_when_you_click_the_same_column(client, db_session,
                                                             situation):
    login(client, db_session)
    eerst = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&sort_by=payment_method")
    assert 'name="dir" value="asc"' in eerst.text
    opnieuw = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&sort=payment_method&dir=asc&sort_by=payment_method")
    assert 'name="dir" value="desc"' in opnieuw.text


def test_a_row_links_through_to_the_record_behind_it(client, db_session, situation):
    """Design-system P8: a report is a way in, not a dead end."""
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=activity&object=registration_count")
    assert f'/admin/activiteiten/{situation["activity_id"]}' in fragment.text

    betaling = client.get(
        "/admin/rapporten/paneel?object=payment_record&object=payment_amount")
    assert "/admin/betalingen?record=" in betaling.text


# ── Saving (#833 point 6, design-system P1) ──────────────────────────────────

def _save(client, csrf, *, name, objects, report_id=None, extra=""):
    """Save through the real form post: the state travels in the body, as htmx sends it."""
    velden = "&".join(f"object={k}" for k in objects)
    url = f"/admin/rapporten/{report_id}" if report_id else "/admin/rapporten"
    return client.post(
        url,
        headers={"X-CSRF-Token": csrf,
                 "Content-Type": "application/x-www-form-urlencoded"},
        content=f"name={name}&is_shared=1&{velden}{extra}")


def test_saving_stays_on_the_screen_and_shows_a_toast(client, db_session, situation):
    csrf = login(client, db_session)
    antwoord = _save(client, csrf, name="Mijn+rapport",
                     objects=["payment_method", "payment_amount"])
    assert antwoord.status_code == 200
    assert "HX-Redirect" not in antwoord.headers, "P1: je blijft staan"
    assert "Opgeslagen" in antwoord.text
    assert "rp-paneel" in antwoord.text


def test_a_failed_save_shows_the_banner_and_no_toast(client, db_session, situation):
    """P1, the half that is easy to forget: no toast on a failure."""
    csrf = login(client, db_session)
    antwoord = _save(client, csrf, name="",
                     objects=["payment_method", "payment_amount"])
    assert antwoord.status_code == 200
    assert "Geef het rapport een naam" in antwoord.text
    assert "Opgeslagen" not in antwoord.text


def test_a_name_that_is_already_taken_is_refused_with_the_reason(client, db_session,
                                                                situation):
    csrf = login(client, db_session)
    antwoord = _save(client, csrf, name="Omzet+per+maand",
                     objects=["payment_method", "payment_amount"])
    assert "Er bestaat al een rapport" in antwoord.text


def test_a_saved_report_opens_on_its_own_selection(client, db_session, situation):
    from app.domains.reporting.api import list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Betaalwijzen", objects=["payment_method",
                                                      "payment_amount"])
    bewaard = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Betaalwijzen"]
    assert bewaard, "het rapport is bewaard"
    pagina = client.get(f"/admin/rapporten/{bewaard[0].id}")
    assert pagina.status_code == 200
    assert "Betaalwijze" in pagina.text
    assert "120,00" in pagina.text


def test_copying_makes_your_own_and_leaves_the_original_alone(client, db_session,
                                                              situation):
    from app.domains.reporting.api import get_saved_report, list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Gedeeld+rapport", objects=["payment_method",
                                                         "payment_amount"])
    origineel = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                               viewer=ADMIN_EMAIL)
                 if r.name == "Gedeeld rapport"][0]

    csrf2 = login(client, db_session, OTHER_EMAIL, ("ADMIN",))
    antwoord = client.post(f"/admin/rapporten/{origineel.id}/kopieren",
                           headers={"X-CSRF-Token": csrf2})
    assert antwoord.status_code == 204
    assert antwoord.headers["HX-Redirect"].startswith("/admin/rapporten/")

    db_session.expire_all()
    onaangeroerd = get_saved_report(db_session, origineel.id, tenant_id=TENANT_A,
                                    viewer=OTHER_EMAIL)
    assert onaangeroerd.owner_email == ADMIN_EMAIL, "het origineel blijft van mij"

    kopie = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                           viewer=OTHER_EMAIL)
             if r.owner_email == OTHER_EMAIL]
    assert len(kopie) == 1
    assert kopie[0].name == "Gedeeld rapport (kopie)"
    assert kopie[0].is_shared is False, "een kopie om iets te proberen is privé"


def test_a_private_report_of_someone_else_is_a_404(client, db_session, situation):
    from app.domains.reporting.api import list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Mijn+klad", objects=["payment_amount"])
    # `_save` always shares; the private flag is set here so the test is about
    # what a private report does, not about how it got that way.
    mijn = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                          viewer=ADMIN_EMAIL)
            if r.name == "Mijn klad"][0]
    mijn.is_shared = False
    db_session.commit()

    login(client, db_session, OTHER_EMAIL, ("ADMIN",))
    assert client.get(f"/admin/rapporten/{mijn.id}").status_code == 404
    lijst = client.get("/admin/rapporten/lijst")
    assert "Mijn klad" not in lijst.text


# ── Tenant isolation (#833 test 1) ───────────────────────────────────────────

def test_a_report_of_another_tenant_is_invisible_and_a_404(client, db_session,
                                                           situation):
    from app.domains.reporting.api import Selection, save_report

    ander = save_report(db_session, tenant_id=TENANT_B, owner="b@example.com",
                        name="Rapport van B",
                        selection=Selection(object_keys=("payment_amount",)))
    login(client, db_session)
    lijst = client.get("/admin/rapporten/lijst")
    assert "Rapport van B" not in lijst.text
    assert client.get(f"/admin/rapporten/{ander.id}").status_code == 404


# ── The export (#833 point 5 and test 3) ─────────────────────────────────────

def _sheets(content: bytes):
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    document = load(BytesIO(content))
    bladen = {}
    for tabel in document.getElementsByType(Table):
        rijen = []
        for rij in tabel.getElementsByType(TableRow):
            cellen = []
            for cel in rij.getElementsByType(TableCell):
                tekst = "".join(str(p) for p in cel.getElementsByType(P))
                cellen.append(tekst)
            rijen.append(cellen)
        bladen[tabel.getAttribute("name")] = rijen
    return bladen


def test_the_export_holds_the_table_with_its_filters_and_the_detail_rows(
        client, db_session, situation):
    """Sheet 1 is what is on the screen; sheet 2 is what is behind it."""
    login(client, db_session)
    antwoord = client.get(
        "/admin/rapporten/export.ods?object=payment_method&object=payment_amount"
        "&filter=payment_method&op_payment_method=eq&v_payment_method=Online")
    assert antwoord.status_code == 200
    bladen = _sheets(antwoord.content)

    blad1 = bladen["Rapport"]
    assert blad1[0][:2] == ["Rapport", "Rapport"]
    assert any(rij[:1] == ["Filter"] and "Betaalwijze is Online" in rij[1]
               for rij in blad1), "de actieve filters staan in de kop"
    kop = next(rij for rij in blad1 if rij[:1] == ["Betaalwijze"])
    assert kop == ["Betaalwijze", "Te betalen"]
    inhoud = blad1[blad1.index(kop) + 1:]
    assert inhoud[0] == ["Online", "45.0"]
    assert inhoud[-1][0] == "Totaal"

    assert "Detail" in bladen
    assert "payment_id" in bladen["Detail"][0]


def test_sheet_one_holds_exactly_what_the_screen_holds(client, db_session,
                                                       situation):
    """#833 test 3: the export is not a second story.

    The same selection through the screen and through the export must produce the
    same rows and the same total, or a board member is comparing two numbers that
    were never the same.
    """
    from app.domains.reporting.api import Selection, run_validated

    login(client, db_session)
    query = "object=payment_method&object=payment_amount"
    scherm = run_validated(
        db_session, Selection(object_keys=("payment_method", "payment_amount")),
        tenant_id=TENANT_A)

    bladen = _sheets(client.get(f"/admin/rapporten/export.ods?{query}").content)
    blad1 = bladen["Rapport"]
    kop = next(rij for rij in blad1 if rij[:1] == ["Betaalwijze"])
    rijen = blad1[blad1.index(kop) + 1:]

    assert len(rijen) == len(scherm.rows) + 1, "de rijen plus één totaalrij"
    for uit_blad, uit_scherm in zip(rijen, scherm.rows):
        assert uit_blad[0] == uit_scherm["payment_method"]
        assert Decimal(uit_blad[1]) == Decimal(uit_scherm["payment_amount"])
    assert Decimal(rijen[-1][1]) == Decimal(scherm.totals["payment_amount"])


def test_every_export_leaves_one_row_in_the_trail(client, db_session, situation):
    """CR-06 §7.6: an export is data leaving the system."""
    from sqlalchemy import text

    login(client, db_session)
    voor = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.export_log WHERE tenant_id = :t"),
        {"t": TENANT_A}).scalar()

    client.get("/admin/rapporten/export.ods?object=payment_method&object=payment_amount")
    client.get("/admin/rapporten/dataset/f_payments.ods")

    rijen = db_session.execute(text(
        "SELECT kind, subject, row_count, actor FROM reporting.export_log "
        "WHERE tenant_id = :t ORDER BY id DESC LIMIT 2"), {"t": TENANT_A}).all()
    na = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.export_log WHERE tenant_id = :t"),
        {"t": TENANT_A}).scalar()

    assert na == voor + 2
    soorten = {rij[0] for rij in rijen}
    assert soorten == {"ad-hoc", "dataset"}
    assert all(rij[3] == ADMIN_EMAIL for rij in rijen), "wie exporteerde staat erbij"
    dataset = next(rij for rij in rijen if rij[0] == "dataset")
    assert dataset[2] == EXPECTED["payments"]["count"]


def test_an_export_of_another_tenant_holds_only_its_own_rows(client, db_session,
                                                             situation):
    """The tenant fence reaches the file, not only the screen."""
    login(client, db_session)
    bladen = _sheets(client.get(
        "/admin/rapporten/export.ods?object=payment_amount").content)
    kop = next(rij for rij in bladen["Rapport"] if rij[:1] == ["Te betalen"])
    waarde = bladen["Rapport"][bladen["Rapport"].index(kop) + 1][0]
    assert Decimal(waarde) == EXPECTED["payments"]["amount"]
    assert Decimal(waarde) != EXPECTED["tenant_b"]["payments_amount"]


def test_editing_a_report_keeps_you_on_the_screen(client, db_session, situation):
    """P1 again, now on the update path: the name changes, you stay, toast."""
    from app.domains.reporting.api import get_saved_report, list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Eerste+naam", objects=["payment_method",
                                                     "payment_amount"])
    rapport = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Eerste naam"][0]

    antwoord = _save(client, csrf, name="Tweede+naam", report_id=rapport.id,
                     objects=["payment_status", "payment_amount"])
    assert antwoord.status_code == 200
    assert "HX-Redirect" not in antwoord.headers
    assert "Opgeslagen" in antwoord.text

    db_session.expire_all()
    opnieuw = get_saved_report(db_session, rapport.id, tenant_id=TENANT_A,
                               viewer=ADMIN_EMAIL)
    assert opnieuw.name == "Tweede naam"
    assert opnieuw.selection["objects"] == ["payment_status", "payment_amount"]


def test_someone_else_cannot_edit_your_report(client, db_session, situation):
    from app.domains.reporting.api import list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Van+mij", objects=["payment_amount"])
    rapport = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Van mij"][0]

    csrf2 = login(client, db_session, OTHER_EMAIL, ("ADMIN",))
    antwoord = _save(client, csrf2, name="Gekaapt", report_id=rapport.id,
                     objects=["payment_amount"])
    assert antwoord.status_code == 200
    assert "van iemand anders" in antwoord.text
    assert "Kopiëren" in antwoord.text, "de melding wijst de weg"
    assert "Opgeslagen" not in antwoord.text


def test_deleting_a_report_sends_you_back_to_the_list(client, db_session, situation):
    from app.domains.reporting.api import get_saved_report, list_saved_reports

    csrf = login(client, db_session)
    _save(client, csrf, name="Weg+ermee", objects=["payment_amount"])
    rapport = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Weg ermee"][0]

    antwoord = client.post(f"/admin/rapporten/{rapport.id}/verwijderen",
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 204
    assert antwoord.headers["HX-Redirect"] == "/admin/rapporten"

    db_session.expire_all()
    assert get_saved_report(db_session, rapport.id, tenant_id=TENANT_A,
                            viewer=ADMIN_EMAIL) is None


def test_a_shipped_report_cannot_be_deleted_from_the_panel(client, db_session,
                                                           situation):
    """It would come back on the next deploy, so the button is not offered."""
    from app.domains.reporting.api import list_saved_reports

    login(client, db_session)
    meegeleverd = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == "revenue_per_month"][0]
    paneel = client.get(f"/admin/rapporten/{meegeleverd.id}")
    assert paneel.status_code == 200
    assert f"/admin/rapporten/{meegeleverd.id}/verwijderen" not in paneel.text


def test_a_report_that_points_at_a_vanished_object_says_so(client, db_session,
                                                           situation):
    """The universe changes; a saved report may not answer with half a table.

    Silently dropping the unknown column would give a table that looks fine and is
    missing a number — the failure this whole design refuses to make quiet.
    """
    from app.domains.reporting.api import list_saved_reports

    login(client, db_session)
    rapport = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.builtin_key == "revenue_per_month"][0]
    rapport.selection = {"objects": ["date_month", "verdwenen_maat"],
                         "filters": [], "sort": [], "layout": "table"}
    db_session.commit()

    paneel = client.get(f"/admin/rapporten/{rapport.id}")
    assert paneel.status_code == 200
    assert "Onbekend object" in paneel.text
    assert "verdwenen_maat" in paneel.text

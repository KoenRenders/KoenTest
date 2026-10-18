"""Ledenscherm volgens het records-lijst-referentiescherm C1 (#582).

Twee dingen zijn hier waardevol om te testen, en het zijn allebei dingen die er
op het oog goed uitzien terwijl ze fout staan:

* de **kantelende campagne**: het doeljaar van "nog niet vernieuwd" verschuift op
  de tenant-datum `membership_next_year_from_md`. Vóór die dag gaat de campagne
  over het lopende jaar, erna over het volgende — en het referentiejaar schuift
  mee. Een teller die het verkeerde jaar neemt, toont een plausibel getal.
* de **filters op de query**: status en lidmaatschapsjaar moeten in de SQL zitten,
  niet op de opgehaalde pagina, anders klopt de paginering niet meer.
"""

import re
from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, RelationType
from app.domains.membership.api import Membership, not_renewed_count, renewal_years
from app.kernel.clock import belgian_today
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_member,
    create_test_person,
)

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _gezin(db, naam: str) -> Member:
    """Eén gezin met één hoofdlid dat `naam` als achternaam draagt, zodat je het
    in de gerenderde lijst kunt terugvinden."""
    from app.domains.mdm.api import MemberPerson

    member = create_test_member(db)
    persoon = create_test_person(db, last_name=naam)
    db.add(MemberPerson(member_id=member.id, person_id=persoon.id, relation_type="HOOFDLID"))
    db.flush()
    return member


def _gezin_met_lidmaatschap(db, naam: str, jaren: list[int]) -> Member:
    """Gezin met voor elk jaar in `jaren` een lidmaatschap dat dat jaar dekt."""
    member = _gezin(db, naam)
    for jaar in jaren:
        db.add(
            Membership(
                member_id=member.id,
                year=jaar,
                is_active=True,
                valid_from=date(jaar, 1, 1),
                valid_to=date(jaar, 12, 31),
            )
        )
    db.commit()
    return member


# ── De kantelende campagne ────────────────────────────────────────────────────


def test_doeljaar_kantelt_op_de_tenant_datum():
    """Standaardinstelling is 17 september (membership_next_year_from_md)."""
    assert renewal_years(date(2026, 9, 16)) == (2025, 2026)
    assert renewal_years(date(2026, 9, 17)) == (2026, 2027)
    assert renewal_years(date(2026, 12, 31)) == (2026, 2027)
    assert renewal_years(date(2026, 1, 2)) == (2025, 2026)


def test_niet_vernieuwd_volgt_het_juiste_referentiejaar(db_session):
    _gezin_met_lidmaatschap(db_session, "Vorigjaar", [2025])  # enkel 2025
    _gezin_met_lidmaatschap(db_session, "Ditjaar", [2025, 2026])  # 2025 + 2026
    _gezin_met_lidmaatschap(db_session, "Vooruit", [2026, 2027])  # 2026 + 2027

    # Vóór de kanteldatum: referentie 2025, doel 2026 → enkel "Vorigjaar" mist 2026.
    assert not_renewed_count(db_session, date(2026, 9, 16)) == 1
    # Erna: referentie 2026, doel 2027 → "Ditjaar" heeft 2026 maar geen 2027.
    assert not_renewed_count(db_session, date(2026, 9, 17)) == 1


def test_niet_vernieuwd_telt_wie_al_twee_jaar_gedekt_is_niet_mee(db_session):
    """Een lidmaatschap dat na de kanteldatum betaald werd dekt twee jaren; dat is
    exact wat 'al vernieuwd' betekent."""
    member = _gezin(db_session, "Dubbeldek")
    db_session.add(
        Membership(
            member_id=member.id,
            year=2026,
            is_active=True,
            valid_from=date(2026, 9, 20),
            valid_to=date(2027, 12, 31),
        )
    )
    db_session.commit()
    assert not_renewed_count(db_session, date(2026, 9, 17)) == 0


def test_inactief_lidmaatschap_telt_niet_als_vernieuwd(db_session):
    member = _gezin(db_session, "Inactief")
    db_session.add_all(
        [
            Membership(
                member_id=member.id,
                year=2025,
                is_active=True,
                valid_from=date(2025, 1, 1),
                valid_to=date(2025, 12, 31),
            ),
            Membership(
                member_id=member.id,
                year=2026,
                is_active=False,
                valid_from=date(2026, 1, 1),
                valid_to=date(2026, 12, 31),
            ),
        ]
    )
    db_session.commit()
    assert not_renewed_count(db_session, date(2026, 9, 16)) == 1


# ── Het scherm ────────────────────────────────────────────────────────────────


def test_kpi_rij_noemt_het_doeljaar_in_het_label(client, db_session):
    """#1899: the three figures stand in the title row (`ui.figures`); the third
    carries its target year, which tilts on the tenant's date."""
    _login(client)
    _, doeljaar = renewal_years()
    html = client.get("/admin/leden").text
    labels = re.findall(r"<dt data-figure-label[^>]*>([^<]*)</dt>", html)
    assert labels == ["Actieve gezinnen", "Actieve personen", f"Te vernieuwen {doeljaar}"]


def test_lijst_heeft_nieuw_lid_import_zoek_en_filters(client, db_session):
    _login(client)
    html = client.get("/admin/leden").text
    assert "Nieuw lid" in html and "Leden importeren" in html
    assert 'type="search"' in html
    # #1899: three segments and no "Alle" — a list opens on a status.
    assert re.findall(r'<input type="radio" name="status" value="([^"]*)"', html) == [
        "actief",
        "vernieuwen",
        "opgezegd",
    ]
    assert (
        'name="status" value="actief" class="peer absolute inset-0 h-full w-full m-0 opacity-0 cursor-pointer" checked'
        in html
    )


def test_jaardropdown_is_datagedreven_en_filtert(client, db_session):
    """The year select is data-driven and filters WITHIN the segment (#1899: there
    is no "Alle" any more, so a household of 2024 alone is found under Opgezegd)."""
    _login(client)
    _gezin_met_lidmaatschap(db_session, "Oudlid", [2024])
    _gezin_met_lidmaatschap(db_session, "Nieuwlid", [belgian_today().year])

    pagina = client.get("/admin/leden").text
    assert "Lid in 2024" in pagina and f"Lid in {belgian_today().year}" in pagina

    op_2024 = client.get("/admin/leden/lijst", params={"status": "opgezegd", "jaar": "2024"}).text
    assert "Oudlid" in op_2024 and "Nieuwlid" not in op_2024
    actief_2024 = client.get("/admin/leden/lijst", params={"status": "actief", "jaar": "2024"}).text
    assert "Oudlid" not in actief_2024 and "Nieuwlid" not in actief_2024


def test_statusfilter_scheidt_actief_van_opgezegd(client, db_session):
    _login(client)
    dit_jaar = belgian_today().year
    _gezin_met_lidmaatschap(db_session, "Actiefnu", [dit_jaar])
    _gezin_met_lidmaatschap(db_session, "Gestopt", [dit_jaar - 3])

    actief = client.get("/admin/leden/lijst", params={"status": "actief"}).text
    assert "Actiefnu" in actief and "Gestopt" not in actief

    opgezegd = client.get("/admin/leden/lijst", params={"status": "opgezegd"}).text
    assert "Gestopt" in opgezegd and "Actiefnu" not in opgezegd


def test_nieuw_lid_maakt_gezin_met_hoofdlid_en_opent_de_editor(client, db_session):
    from app.domains.mdm.api import MemberPerson, Person
    from tests.conftest import nieuw_lid_velden

    csrf = _login(client)
    resp = client.post(
        "/admin/leden",
        # #681: geboortedatum en geslacht zijn verplicht; sinds
        # #1110 verstuurt het scherm één formulier met m0_-velden,
        # het adres en de contactgegevens van het hoofdlid.
        data=nieuw_lid_velden(
            db_session, m0_first_name="Marie", m0_last_name="Peeters", m0_gender_code="F"
        ),
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204
    persoon = db_session.query(Person).filter(Person.last_name == "Peeters").one()
    koppeling = db_session.query(MemberPerson).filter(MemberPerson.person_id == persoon.id).one()
    assert koppeling.relation_type == RelationType.PRIMARY_MEMBER
    assert resp.headers["HX-Redirect"] == f"/admin/leden/gezin/{koppeling.member_id}"


def test_a_row_opens_the_households_record(client, db_session):
    _login(client)
    member = _gezin_met_lidmaatschap(db_session, "Klikbaar", [belgian_today().year])

    lijst = client.get("/admin/leden").text
    # #1940: the row names the list as it stands in the one key `terug`.
    assert f'href="/admin/leden/gezin/{member.id}?terug=/admin/leden"' in lijst

    record = client.get(f"/admin/leden/gezin/{member.id}")
    assert record.status_code == 200
    # #1899: the record layout — its head with the way back, read first.
    assert 'id="gezin-record"' in record.text and "data-record-head" in record.text
    assert 'data-mode="read"' in record.text and 'id="leden-detail"' not in record.text


# ── C1-referentiescherm (#611) ────────────────────────────────────────────────


def test_acties_staan_op_de_titelregel_boven_de_kpi_rij(client, db_session):
    """#1899: the title row carries ONE primary button, "Nieuw lid"; the import
    is a secondary action and lives under the toolbar's `⋯`, not in the title row."""
    _login(client)
    html = client.get("/admin/leden").text
    head = html[html.index("data-list-head") : html.index("data-toolbar")]
    assert "Nieuw lid" in head and "Leden importeren" not in head
    menu = html[html.index("data-more-menu") :]
    assert 'href="/admin/leden-import"' in menu[: menu.index("</form>")]


def test_kpi_kaart_noemt_het_referentiejaar_niet_nog_eens_het_doeljaar(client, db_session):
    """The third figure says in its title in which year a household WAS a member —
    otherwise it only repeats the target year of its label. The years tilt with
    the tenant's date, so they come from renewal_years()."""
    _login(client)
    referentiejaar, doeljaar = renewal_years()
    html = client.get("/admin/leden").text
    assert f'title="Lid in {referentiejaar}, nog niet vernieuwd voor {doeljaar}."' in html
    assert referentiejaar == doeljaar - 1


# ── #1899: the list-page layout — segments, counts, sort, the row ───────────────


def _rows(html: str) -> list[str]:
    """The household names of the list, in the order they stand."""
    return re.findall(r"<a [^>]*data-row-link[^>]*>([^<]*)</a>", html)


def _segment_count(html: str, segment: str) -> int:
    found = re.search(rf'id="leden-filter-n-{segment}"[^>]*>\((\d+)\)<', html)
    assert found, f"the segment {segment} carries no count"
    return int(found.group(1))


def test_a_household_of_the_reference_year_alone_stands_under_te_vernieuwen(client, db_session):
    """Koen, 11 October 2026: the campaign's rule decides "te vernieuwen", for the
    figure and for the segment — a member in the reference year who does not
    cover the target year. Goes red on a segment that reads another rule than
    `members_to_renew`."""
    _login(client)
    referentiejaar, doeljaar = renewal_years()
    _gezin_met_lidmaatschap(db_session, "Moetnog", [referentiejaar])
    _gezin_met_lidmaatschap(db_session, "Isalklaar", [referentiejaar, doeljaar])
    _gezin_met_lidmaatschap(db_session, "Langweg", [referentiejaar - 3])

    html = client.get("/admin/leden/lijst", params={"status": "vernieuwen"}).text
    assert _rows(html) == ["Moetnog Test"]
    # The figure above the list counts the same households.
    page = client.get("/admin/leden", params={"status": "vernieuwen"}).text
    figure = re.search(
        r"<dd data-figure[^>]*>(\d+)</dd>\s*<dt data-figure-label[^>]*>Te vernieuwen", page
    )
    assert figure and int(figure.group(1)) == not_renewed_count(db_session) == 1


def test_the_segments_count_what_the_click_yields(client, db_session):
    """#1899: the number on a segment is the number of rows its click gives —
    within the search. Goes red on a count taken outside the search."""
    _login(client)
    referentiejaar, _doeljaar = renewal_years()
    dit_jaar = belgian_today().year
    for name in ("Telmee", "Telook"):
        _gezin_met_lidmaatschap(db_session, name, [dit_jaar])
    _gezin_met_lidmaatschap(db_session, "Anders", [dit_jaar])
    _gezin_met_lidmaatschap(
        db_session, "Telnog", [referentiejaar] if referentiejaar != dit_jaar else [dit_jaar]
    )

    for q in ("", "Tel"):
        for segment in ("actief", "vernieuwen"):
            html = client.get(
                "/admin/leden/lijst", params={"status": segment, "q": q, "per_page": "100"}
            ).text
            assert _segment_count(html, segment) == len(_rows(html)), (q, segment)
    searched = client.get("/admin/leden/lijst", params={"status": "actief", "q": "Tel"}).text
    assert "Anders" not in searched and _segment_count(searched, "actief") < _segment_count(
        client.get("/admin/leden/lijst", params={"status": "actief"}).text, "actief"
    )


def test_opgezegd_is_the_rest_and_carries_no_count(client, db_session):
    """Opgezegd is neither Actief nor Te vernieuwen. "Moetnog" was a member in the
    reference year and is none today — whatever the day this runs on: its period
    ended yesterday at the latest — so it is to renew and NOT under Opgezegd.
    Goes red on an Opgezegd that only leaves the members of today out."""
    from datetime import timedelta

    _login(client)
    referentiejaar, _doeljaar = renewal_years()
    _gezin_met_lidmaatschap(db_session, "Langweg", [referentiejaar - 3])
    moetnog = _gezin(db_session, "Moetnog")
    db_session.add(
        Membership(
            member_id=moetnog.id,
            year=referentiejaar,
            is_active=True,
            valid_from=date(referentiejaar, 1, 1),
            valid_to=min(date(referentiejaar, 12, 31), belgian_today() - timedelta(days=1)),
        )
    )
    db_session.commit()
    assert "Moetnog Test" not in _rows(
        client.get("/admin/leden/lijst", params={"status": "actief"}).text
    )
    html = client.get("/admin/leden/lijst", params={"status": "opgezegd"}).text
    names = _rows(html)
    assert "Langweg Test" in names and "Moetnog Test" not in names
    assert 'id="leden-filter-n-opgezegd"' not in html


def test_the_list_sorts_on_the_household_name_both_ways(client, db_session):
    """The Gezin column sorts; the list opens A–Z. Goes red on a sort that the
    query does not apply."""
    _login(client)
    dit_jaar = belgian_today().year
    for name in ("Zwaan", "Adelaar", "Merel"):
        _gezin_met_lidmaatschap(db_session, name, [dit_jaar])
    ours = {"Zwaan Test", "Adelaar Test", "Merel Test"}

    def order(**params) -> list[str]:
        html = client.get("/admin/leden/lijst", params={"per_page": "100", **params}).text
        return [name for name in _rows(html) if name in ours]

    assert order() == ["Adelaar Test", "Merel Test", "Zwaan Test"]
    assert order(sort="-naam") == ["Zwaan Test", "Merel Test", "Adelaar Test"]
    # The head's link turns the sort and keeps the segment.
    html = client.get("/admin/leden/lijst", params={"status": "actief"}).text
    assert "/admin/leden/lijst?status=actief&amp;per_page=50&amp;sort=-naam" in html


def test_a_row_is_the_household_its_address_its_persons_and_its_badge(client, db_session):
    """No Gemeente column and no actions column (#1899): the address stands under
    the name, and a household is deleted on its record."""
    _login(client)
    dit_jaar = belgian_today().year
    member = _gezin_met_lidmaatschap(db_session, "Rijtje", [dit_jaar])
    html = client.get("/admin/leden/lijst", params={"q": "Rijtje"}).text
    row = re.search(rf'<tr data-row data-household="{member.id}".*?</tr>', html, re.S)
    assert row, "the household has no row"
    cells = re.findall(r'<td data-cell="([a-z]+)"', row.group(0))
    assert cells == ["name", "extra", "status"]
    # The search is part of the list as it stands: it is in the way back (#1940).
    assert f'href="/admin/leden/gezin/{member.id}?terug=/admin/leden%3Fq%3DRijtje"' in row.group(0)
    assert f"Lid in {dit_jaar}" in row.group(0)
    assert "hx-post" not in row.group(0) and "Verwijderen" not in html
    heads = re.findall(r"<th[^>]*>.*?</th>", html, re.S)
    assert len(heads) == 3 and not any("Gemeente" in h or "Acties" in h for h in heads)

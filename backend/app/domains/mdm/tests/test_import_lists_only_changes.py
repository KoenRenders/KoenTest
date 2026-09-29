"""#1308 — the member import lists the households that change, and counts the rest.

Koen, after uploading a member report: *"Waarom staan er zoveel updates?"* Every
existing household got an `UPDATE gezin` line, changed or not, so a report of a
hundred households gave a hundred lines and the eight real changes drowned in
them. `updated_families` counted every existing household too.

Now a household gets its header only when something in it changes, and the
decision is the one each step already makes: every change writes its own line (a
field, a move, a removal, an attached member number, a revival, a new
membership — and since #1308 also the address and the contacts, which changed in
silence before), and the header goes in front of those lines. A household without
one is counted in `unchanged_families`. The `admin:` lines follow the same rule:
an existing account is counted, not listed — in the preview too, which listed
every board member with an address and so disagreed with the run.

Proven red against master `43ac7e05` (29 September 2026), on the lines and not
only on the new counters:
- one changed household: two `UPDATE gezin` lines for one change;
- the identical report: two `UPDATE gezin` lines for no change;
- the address alone: two lines, and no `~ adres` — the change was silent;
- the existing admin account: `admin: Bo Boons <…>` in the preview.
The preview-versus-run test failed there only on the missing counter: its lines
agreed on master too. It guards that they keep agreeing now that the preview also
compares address, contacts and admin accounts.
"""

import pytest

from app.domains.auth.api import User
from app.domains.mdm.import_service import upsert_families
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch


def _row(lidnr, voornaam, naam, *, geboortedatum="1980-05-01", huisnummer="1", email=None):
    from datetime import date

    return {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": "milostraat",
        "huisnummer": huisnummer,
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": email,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": date.fromisoformat(geboortedatum),
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": "HOOFDLID",
    }


def _report(**changes):
    """Two households, A and B; `changes` overrides B's row."""
    return [
        [_row("901", "An", "Aerts", huisnummer="1")],
        [_row("902", "Bo", "Boons", **{"huisnummer": "2", **changes})],
    ]


def _updates(report) -> list[str]:
    return [line for line in report.lines if line.startswith("UPDATE gezin")]


@pytest.fixture
def imported(db_session):
    seed_postal_code(db_session)
    first = upsert_families(db_session, _report(), {}, [], apply=True)
    assert first.new_families == 2, first.lines
    db_session.flush()


def test_one_changed_household_gets_one_update_line(db_session, imported):
    report = upsert_families(db_session, _report(geboortedatum="1981-05-01"), {}, [], apply=False)

    assert len(_updates(report)) == 1, report.lines
    header = report.lines.index(_updates(report)[0])
    assert "Boons" not in report.lines[header] and "2, 2400" in report.lines[header]
    assert report.lines[header + 1].startswith("  ~ update #902"), report.lines
    assert (report.updated_families, report.unchanged_families) == (1, 1)


def test_an_identical_report_gives_no_update_line(db_session, imported):
    report = upsert_families(db_session, _report(), {}, [], apply=False)

    assert _updates(report) == [], report.lines
    assert report.lines == [], report.lines
    assert (report.updated_families, report.unchanged_families) == (0, 2)


def test_an_address_change_alone_is_a_change(db_session, imported):
    """It changed in silence before: no line, and so no reason for the header."""
    report = upsert_families(db_session, _report(huisnummer="2A"), {}, [], apply=False)

    assert len(_updates(report)) == 1, report.lines
    assert any(line.startswith("  ~ adres #902") for line in report.lines), report.lines


def test_preview_and_run_list_the_same_lines(db_session, imported):
    changed = _report(geboortedatum="1981-05-01", email="bo@example.com")
    preview = upsert_families(db_session, changed, {}, [], apply=False)
    run = upsert_families(
        db_session, _report(geboortedatum="1981-05-01", email="bo@example.com"), {}, [], apply=True
    )

    assert preview.lines == run.lines
    assert (preview.updated_families, preview.unchanged_families) == (
        run.updated_families,
        run.unchanged_families,
    )


def test_an_existing_admin_account_is_counted_not_listed(db_session, imported):
    db_session.add(User(email="bo@example.com", is_active=True))
    db_session.flush()
    families = _report(email="bo@example.com")
    bl_index = {"bo boons": [families[1][0]]}

    report = upsert_families(db_session, families, bl_index, ["bo boons"], apply=False)

    assert not [line for line in report.lines if "admin:" in line], report.lines
    assert (report.admins_created, report.admins_existing) == (0, 1)

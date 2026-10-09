"""CR-13 phase 4c, C7-3 (#1251): the member import says what the report says, and the
owners write their own rows — what is reported and written stays.

The member report of Raak Nationaal names the households that are members for
its year and the board member responsible for each. Until C7-3 the import
(`mdm/import_service.py`) wrote two things that are not mdm's: a login with the
role ADMIN for a board member who has none (`auth.User`, `auth.UserRole`), and
the year's membership of a household that has none (`membership.Membership`).
They are facts now: the import publishes `BoardMemberReported` and
`MembershipReported` (`kernel/contracts/mdm.py`); auth and membership subscribe
and write their own rows, in the import's transaction. What the preview counts
is read through the owners' facades.

No behaviour changes, so the proof is **the same report and the same rows on the
same input**: a preview, a run and a second run of one report were recorded on
the code BEFORE the events — every number and line of the report, then every
login, role, membership and membership history row — and the code with the
events must give them again, character for character (`tests/_snapshot.py`).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.domains.auth.api import User, UserRole
from app.domains.mdm.api import Address, ContactDetail, Member, MemberPerson, Person
from app.domains.mdm.import_service import _norm, upsert_families
from app.domains.membership.api import Membership
from app.domains.membership.models import MembershipHistory
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import seed_postal_code

SNAPSHOTS = Path(__file__).parent / "snapshots" / "import_events_1251"
BEFORE = "the import published what the report says (CR-13 phase 4c, C7-3)"
MODELS = (Member, Person, MemberPerson, Address, ContactDetail, Membership, MembershipHistory)
MODELS += (User, UserRole)
ACTOR = "invoerder-1251@example.com"


def _row(lidnr: str, first: str, last: str, email: str | None, board: str | None) -> dict:
    return {
        "lidnr": lidnr,
        "voornaam": first,
        "naam": last,
        "straat": "Milostraat",
        "huisnummer": lidnr[-1],
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": email,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": date(1980, 5, 1),
        "geslacht": "M",
        "bestuurslid": board,
        "_relatie": "HOOFDLID",
    }


def _report() -> tuple[list, dict, list]:
    """Three households. Mon and Bo are board members with an e-mail address —
    Bo has a login already; Fien's household has no board member with an address."""
    mon = _row("101", "Mon", "Proefmans", "mon-1251@example.com", "Mon Proefmans")
    bo = _row("102", "Bo", "Proefboons", "bo-1251@example.com", "Bo Proefboons")
    fien = _row("103", "Fien", "Proefs", None, "Mon Proefmans")
    names = [_norm("Mon Proefmans"), _norm("Bo Proefboons")]
    return [[mon], [bo], [fien]], {names[0]: [mon], names[1]: [bo]}, names


def _rows(db) -> str:
    db.expire_all()
    lines = []
    for user in db.query(User).filter(User.email.like("%-1251@example.com")).order_by(User.email):
        roles = sorted(
            role.role_code for role in db.query(UserRole).filter(UserRole.user_id == user.id)
        )
        lines.append(f"login {user.email}: active={user.is_active} roles={roles}")
    for membership in db.query(Membership).order_by(Membership.id):
        lines.append(
            f"membership {membership.id}: household={membership.member_id} "
            f"year={membership.year} active={membership.is_active} "
            f"valid={membership.valid_from}..{membership.valid_to}"
        )
    for row in db.query(MembershipHistory).order_by(MembershipHistory.id):
        lines.append(
            f"membership history: {row.operation} {row.action} source={row.source} "
            f"actor={row.actor} membership={row.membership_id}"
        )
    return "\n".join(lines) or "(no rows)"


def _recorded(report, db) -> str:
    said = json.dumps(report.to_dict(), indent=1, ensure_ascii=False, default=str)
    return f"--- report ---\n{said}\n--- rows ---\n{_rows(db)}"


def test_a_preview_a_run_and_a_second_run_are_what_they_were(db_session):
    with fixed_ids(db_session, MODELS):
        seed_postal_code(db_session)
        db_session.add(User(email="bo-1251@example.com", is_active=True))
        db_session.commit()

        families, board, names = _report()
        preview = upsert_families(db_session, families, board, names, apply=False, actor=ACTOR)
        compare(SNAPSHOTS, "preview", normalise(_recorded(preview, db_session), {}, {}), BEFORE)

        families, board, names = _report()
        run = upsert_families(db_session, families, board, names, apply=True, actor=ACTOR)
        db_session.commit()
        compare(SNAPSHOTS, "run", normalise(_recorded(run, db_session), {}, {}), BEFORE)

        # The preview promises what the run does: the same numbers, the same lines.
        assert preview.to_dict() == run.to_dict()

        families, board, names = _report()
        again = upsert_families(db_session, families, board, names, apply=True, actor=ACTOR)
        db_session.commit()
        compare(SNAPSHOTS, "second_run", normalise(_recorded(again, db_session), {}, {}), BEFORE)
        assert (again.memberships_created, again.admins_created) == (0, 0)


@pytest.mark.parametrize("silent", ["MembershipReported", "BoardMemberReported"])
def test_an_import_into_silence_is_refused(db_session, monkeypatch, silent):
    """Neither consequence is optional: with nothing subscribed (the owner's
    handlers not imported) a run fails loudly instead of counting a membership or
    a login it never made. A preview publishes nothing and still works."""
    from app.kernel import contracts, events

    seed_postal_code(db_session)
    db_session.flush()
    monkeypatch.delitem(events._subscribers, getattr(contracts.mdm, silent))

    families, board, names = _report()
    preview = upsert_families(db_session, families, board, names, apply=False, actor=ACTOR)
    assert (preview.memberships_created, preview.admins_created) == (3, 2)

    families, board, names = _report()
    with pytest.raises(RuntimeError, match=silent):
        upsert_families(db_session, families, board, names, apply=True, actor=ACTOR)
    db_session.rollback()

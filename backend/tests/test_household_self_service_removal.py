"""#870 (half of D from #529) — the gezinsportaal: the refusal was tested, the writing was not.

`remove_person` measured 5 covered lines against 9 missing on this tree. The covered part is
the 403 from #599 — a member of household A cannot touch household B. Missing is the other
side: that a successful removal hits the **right** record, and the rule *"you cannot remove
yourself from the household"* (`household_router.py:421-422`), which no test touched at all.

**Half on purpose.** `update_person` stays uncovered; covering the whole gezinsportaal is a
day, and the half that would be a leak is already tested. If it comes later it is a new
issue, not an extension of this one — that boundary is written down in #870 so nobody reads
this file as an oversight.

Broken on purpose to check that these tests can go red: the self-removal guard removed →
the second test falls over, and the member removes themselves from their own household,
which leaves a household nobody can administer; and `soft_delete(mp)` skipped → the first
falls over with the person still in the household.
"""
import pytest

from app.domains.auth.api import create_access_token
from app.domains.mdm.api import MemberPerson, Person
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_agnostisch


def _member_headers(email: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def _extra_person(db, member, first_name="Kind"):
    from app.domains.mdm.api import Person as P

    person = P(first_name=first_name, last_name="Testgezin")
    db.add(person)
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=person.id,
                        relation_type="KIND"))
    db.flush()
    return person


def _in_household(db, member_id, person_id) -> bool:
    return db.query(MemberPerson).filter(
        MemberPerson.member_id == member_id,
        MemberPerson.person_id == person_id,
        MemberPerson.deleted_at.is_(None)).first() is not None


def test_removing_someone_from_your_own_household_works(client, db_session):
    """Het succespad: de weigering is getest (#599), dit is de andere kant.

    Zonder deze test bewijst "een vreemd gezin geeft 403" niet dat het eigen gezin het
    wél doet — dan zou een route die alles weigert evengoed groen staan.
    """
    member, hoofdlid = create_test_family(db_session, email="gezin-a@example.com")
    kind = _extra_person(db_session, member)
    assert _in_household(db_session, member.id, kind.id), "opzet klopt niet (#678)"

    resp = client.delete(f"/api/v1/member/household/persons/{kind.id}",
                         headers=_member_headers("gezin-a@example.com"))

    assert resp.status_code == 204, resp.text[:200]
    db_session.expire_all()
    assert not _in_household(db_session, member.id, kind.id), (
        "de persoon zit nog in het gezin — het verwijderen raakte het verkeerde record "
        "of helemaal niets")
    assert _in_household(db_session, member.id, hoofdlid.id), (
        "het hoofdlid is mee verdwenen — er is te veel verwijderd")


def test_you_cannot_remove_yourself(client, db_session):
    """De regel die vandaag door geen enkele test aangeraakt wordt.

    Zonder haar haalt een lid zichzelf uit zijn eigen gezin, en blijft er een gezin over
    dat niemand meer kan beheren — een deur die alleen van binnenuit op slot kan.
    """
    member, hoofdlid = create_test_family(db_session, email="gezin-b@example.com")
    _extra_person(db_session, member)

    resp = client.delete(f"/api/v1/member/household/persons/{hoofdlid.id}",
                         headers=_member_headers("gezin-b@example.com"))

    assert resp.status_code == 400, f"{resp.status_code} — {resp.text[:200]}"
    assert "jezelf" in resp.text, (
        f"geweigerd om een andere reden dan de zelfverwijderregel: {resp.text[:200]}")
    db_session.expire_all()
    assert _in_household(db_session, member.id, hoofdlid.id), (
        "het lid is toch uit zijn eigen gezin verdwenen")


def test_a_stranger_is_still_refused(client, db_session):
    """De grens uit #599, hier als vangrail: het succespad hierboven mag die niet
    ongemerkt hebben opengezet."""
    member_a, _ = create_test_family(db_session, email="gezin-c@example.com")
    member_b, _ = create_test_family(db_session, email="gezin-d@example.com")
    vreemde = _extra_person(db_session, member_b, first_name="Vreemde")

    resp = client.delete(f"/api/v1/member/household/persons/{vreemde.id}",
                         headers=_member_headers("gezin-c@example.com"))

    assert resp.status_code == 403
    db_session.expire_all()
    assert _in_household(db_session, member_b.id, vreemde.id)

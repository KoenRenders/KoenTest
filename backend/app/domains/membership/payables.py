"""A membership as a payable: how `payment` learns what a membership's payment is for
(CR-21 Q48, #1748). Registered for `PayableType.MEMBERSHIP` in `app/main.py`.

Moved here from `payment` — `enriched_records`, the export's `_enrich` and
`family_payables` each knew a membership's tables — not rewritten: the same reads, the
same words, soft-deleted rows included (#190). The payable id is the `Membership.id`,
not the household's: the year comes from the membership, the name from the head of
that household (#141).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from sqlalchemy.orm import Session

from app.domains.membership.models import Membership

if TYPE_CHECKING:
    from app.domains.payment.api import Describer, PayableDescription


def _q(db: Session, model: Any) -> Any:
    return db.query(model).execution_options(include_deleted=True)


def describe_memberships(db: Session, ids: Iterable[int]) -> dict[int, "PayableDescription"]:
    """`{membership_id: PayableDescription}`. A membership that is gone is still
    described — "Lidmaatschap", without a year — as the screen and the export did."""
    from app.domains.mdm.api import Member, MemberPerson, Person, RelationType
    from app.domains.payment.api import PayableDescription

    wanted = set(ids)
    if not wanted:
        return {}
    memberships = {m.id: m for m in _q(db, Membership).filter(Membership.id.in_(wanted)).all()}
    household_ids = {m.member_id for m in memberships.values()}
    head_name: dict[int, str] = {}
    if household_ids:
        living = {m.id for m in _q(db, Member).filter(Member.id.in_(household_ids)).all()}
        links = (
            _q(db, MemberPerson)
            .filter(
                MemberPerson.member_id.in_(living),
                MemberPerson.relation_type == RelationType.PRIMARY_MEMBER,
            )
            .all()
        )
        persons = (
            {
                p.id: p
                for p in _q(db, Person).filter(Person.id.in_({k.person_id for k in links})).all()
            }
            if links
            else {}
        )
        for link in links:
            person = persons.get(link.person_id)
            if person is not None:
                head_name[link.member_id] = f"{person.first_name} {person.last_name}"

    described = {}
    for membership_id in wanted:
        membership = memberships.get(membership_id)
        if membership is None:
            described[membership_id] = PayableDescription(
                description="Lidmaatschap", export_label="Lidmaatschap"
            )
            continue
        name = head_name.get(membership.member_id)
        period = f"Lidmaatschap {membership.year}"
        described[membership_id] = PayableDescription(
            contact_name=name,
            description=period,
            context_href=f"/admin/leden/gezin/{membership.member_id}",
            filter_context=f"year-{membership.year}",
            export_label=" — ".join(x for x in (name, period) if x),
            household_id=membership.member_id,
            record_fields={"membership_year": membership.year},
        )
    return described


def memberships_of_household(db: Session, household_id: int) -> list[int]:
    return [
        row[0] for row in _q(db, Membership.id).filter(Membership.member_id == household_id).all()
    ]


def membership_describer() -> "Describer":
    """The describer `app/main.py` registers for `PayableType.MEMBERSHIP`."""
    from app.domains.payment.api import Describer

    return Describer(
        describe=describe_memberships,
        of_household=memberships_of_household,
        export_kind="Lidgeld",
        filter_group="membership",
        filter_prefix="year-",
    )

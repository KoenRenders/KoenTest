"""A small world for the tests of the newsletter's audiences (CR-36, #2026): past
activities with registrations, households with a membership, subscribers, and the
mailbox that records what would leave. Made-up people on the reserved example domain."""

from __future__ import annotations

from datetime import date, timedelta

from app.domains.activities.models import Activity, ActivityDate, Registration
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from app.domains.membership.api import Membership
from app.domains.newsletter.models import Subscriber, SubscriberStatus
from app.kernel.clock import belgian_today

YEAR = belgian_today().year


class Mailbox:
    """What would have left: one entry per mail, in order."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def __call__(
        self,
        to_email,
        subject,
        body_html,
        *,
        email_type,
        reply_to=None,
        unsubscribe_url=None,
        body_text=None,
    ):
        self.sent.append(
            {
                "to": to_email,
                "body": body_html,
                "unsubscribe_url": unsubscribe_url,
                "body_text": body_text,
            }
        )
        return "sent"

    @property
    def addresses(self) -> list[str]:
        return [m["to"] for m in self.sent]


def past_activity(
    db, name: str, *, days_ago: int = 200, cancelled: bool = False, tenant_id: int | None = None
) -> Activity:
    extra = {"tenant_id": tenant_id} if tenant_id is not None else {}
    activity = Activity(name=name, location="Dorpsplein", is_cancelled=cancelled, **extra)
    db.add(activity)
    db.flush()
    day = belgian_today() - timedelta(days=days_ago)
    db.add(ActivityDate(activity_id=activity.id, start_date=day, **extra))
    db.flush()
    return activity


def register(db, activity: Activity, email: str, *, name: str = "Gast", tenant_id=None):
    extra = {"tenant_id": tenant_id} if tenant_id is not None else {}
    registration = Registration(
        activity_id=activity.id,
        registration_type="INDIVIDUAL",
        contact_name=name,
        contact_email=email,
        phone="0470000000",
        **extra,
    )
    db.add(registration)
    db.flush()
    return registration


def household(db, email: str, year: int = YEAR) -> Member:
    """A household with a membership for `year` and one person with this address."""
    member = Member()
    db.add(member)
    db.flush()
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name="Lid", last_name="Voorbeeld"
    )
    db.add(person)
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
    db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    db.add(
        Membership(
            member_id=member.id,
            year=year,
            is_active=True,
            valid_from=date(year, 1, 1),
            valid_to=date(year, 12, 31),
        )
    )
    db.flush()
    return member


def subscriber(db, email: str, status=SubscriberStatus.CONFIRMED, source="admin") -> Subscriber:
    row = Subscriber(email=email, status=status, source=source, unsubscribe_token=f"tok-{email}")
    db.add(row)
    db.flush()
    return row

"""What the measurement run adds to the e2e seed (#1605; CR-11 B7 test 11).

The e2e seed has two activities, both ahead, without a poster: the public photo
overview is empty on it and no card shows more than one date. The measurement
database is its OWN database (`scripts/measure-local.sh`, the CI step), so what
the pilot screens need is added here and the e2e's keep their seed:

- an activity that is over, with two photos: an album on `/fotos`, a card in the
  archive, an album page with two tiles;
- an activity ahead with three dates, a place, two components, an uploaded
  poster and a description of two paragraphs: the date tile, the facts, the
  actions of more than one component and the poster's column;
- one of the seed's own registrations, with its transfer still to make, linked
  to the seeded member: a card on Mijn inschrijvingen and the latest
  registration on the landing page, each with the transfer block (CR-22 S5,
  #1709). Linked, not added: a new one would move the back office's lists.

Invented names only. Every date is counted from `measures.MEASURE_NOW`, never
from today: the run lives in that moment.

    E2E_SEED=1 python -m tests_e2e.measure_seed
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from tests_e2e.measures import AHEAD, MEASURE_NOW

#: The activity that is over; the one ahead is named in `measures.AHEAD`,
#: where the screens look for it.
PAST = "Meetbasis voorbije wandeling"


def _png(size: tuple[int, int], colour: tuple[int, int, int]) -> bytes:
    from PIL import Image

    out = BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def _registration_with_a_transfer(db, today) -> None:
    """One of the e2e seed's two registrations becomes the seeded member's own.

    The seed makes them as a guest would (no person), each with a transfer of
    € 20 still to make. Linked to the member, one stands on Mijn inschrijvingen
    and as the latest registration on the landing page — and nothing is added:
    a new registration with its booking would be one more row on Betalingen and
    on the activity's tabs, and move the back office's baselines for no reason."""
    from app.domains.activities.api import Registration
    from app.domains.auth.api import login_person_for_email
    from seed_e2e import MARKER_EMAIL

    person = login_person_for_email(db, MARKER_EMAIL)
    registration = db.query(Registration).filter(Registration.contact_name == "Marie Jommeke").one()
    registration.person_id = person.id


def _person_without_household(db) -> None:
    """One person in no household (CR-22 S7, #1712): what Personen shows on its
    default view. In no household, so no list of households moves."""
    from app.domains.mdm.api import ContactDetail, Person

    person = Person(first_name="Pekkie", last_name="Meetbasis")
    db.add(person)
    db.flush()
    for code, value in (("EMAIL", "pekkie.meetbasis@example.com"), ("MOBILE", "0470 00 00 09")):
        db.add(
            ContactDetail(
                person_id=person.id,
                contact_type_code=code,
                value=value,
                is_primary=True,
                confirmed_at=datetime.fromisoformat(MEASURE_NOW),
            )
        )


def main() -> None:
    if os.environ.get("E2E_SEED") != "1":
        sys.exit("measure_seed: refused, set E2E_SEED=1 to make this data")
    import app.models  # noqa: F401  load every table
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration
    from app.domains.media.api import MediaAsset

    today = datetime.fromisoformat(MEASURE_NOW).date()
    db = SessionLocal()
    try:
        if db.query(Activity).filter(Activity.name == PAST).count():
            sys.exit("measure_seed: this database has the measurement data already")

        past = Activity(name=PAST, location="Voorbeeldplein 1, Miloheem")
        db.add(past)
        db.flush()
        db.add(ActivityDate(activity_id=past.id, start_date=today - timedelta(days=94)))
        photo = _png((640, 480), (37, 78, 115))
        thumb = _png((320, 240), (37, 78, 115))
        for order in (0, 1):
            db.add(
                MediaAsset(
                    kind="activity_photo",
                    activity_id=past.id,
                    title=f"Meetbasis foto {order + 1}",
                    data=photo,
                    content_type="image/png",
                    thumbnail=thumb,
                    thumb_content_type="image/png",
                    width=640,
                    height=480,
                    byte_size=len(photo),
                    sort_order=order,
                    is_active=True,
                )
            )

        ahead = Activity(
            name=AHEAD,
            location="Voorbeeldzaal, Dorpsstraat 1, Miloheem",
            description=(
                "Eerste alinea van de omschrijving, lang genoeg om op een telefoon "
                "over meer dan één regel te lopen.\n\nTweede alinea."
            ),
        )
        db.add(ahead)
        db.flush()
        for days, start in ((10, time(14, 0)), (11, time(10, 30)), (17, None)):
            db.add(
                ActivityDate(
                    activity_id=ahead.id, start_date=today + timedelta(days=days), start_time=start
                )
            )
        for order, name in enumerate(("Meetbasis volwassenen", "Meetbasis kinderen")):
            db.add(
                ActivitySubRegistration(
                    activity_id=ahead.id,
                    name=name,
                    registration_type_code="INDIVIDUAL",
                    price=Decimal("0"),
                    is_free=True,
                    max_participants=None,
                    sort_order=order,
                )
            )
        db.add(
            MediaAsset(
                kind="activity_poster",
                activity_id=ahead.id,
                title="Meetbasis affiche",
                content_type="image/png",
                data=_png((600, 848), (238, 193, 94)),
            )
        )
        _registration_with_a_transfer(db, today)
        _person_without_household(db)
        db.commit()
        print(f"measure_seed: voorbij={past.id} komend={ahead.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

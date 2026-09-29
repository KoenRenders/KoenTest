"""Lidmaatschap-status: heeft een persoon een geldig lidmaatschap op een datum?

Dit is de bron van waarheid voor de vraag "mag deze persoon de ledenprijs?"
(#111). Een lidmaatschap telt als **geldig** wanneer:

  - het actief is (``is_active``), én
  - de referentiedatum binnen ``[valid_from, valid_to]`` valt.

We vereisen **géén** betaald ``PaymentRecord``: de bestaande leden zijn via een
data-import aangemaakt zónder betaalrecord (``is_active=True`` met een
geldigheidsperiode). Vernieuwingen (vanaf #113) schrijven óók een actief
lidmaatschap met geldigheidsperiode weg, zodat dezelfde regel blijft gelden.

De functie navigeert via de ORM-relaties (persoon → gezin(nen) → lidmaatschappen)
en doet zelf geen DB-query; binnen een sessie zijn die relaties beschikbaar.
"""

from datetime import date
from typing import Optional, Sequence

from sqlalchemy.orm import Session


def has_valid_membership(person, ref_date: Optional[date] = None) -> bool:
    """True als ``person`` op ``ref_date`` een actief, geldig lidmaatschap heeft.

    ``ref_date`` standaard vandaag. Bij ``person is None`` (niet ingelogd) altijd
    False.
    """
    if person is None:
        return False
    if ref_date is None:
        ref_date = date.today()
    return valid_membership_until(person, ref_date) is not None


def valid_membership_until(person, ref_date: Optional[date] = None):
    """Geeft de ``valid_to``-datum van een actief, geldig lidmaatschap op
    ``ref_date``, of None als er geen geldig lidmaatschap is. Bij meerdere
    geldige lidmaatschappen de verst reikende ``valid_to`` (gunstigst voor het
    lid). Wordt gebruikt door het gezinscherm om de status + vernieuwknop te
    tonen (#113)."""
    if person is None:
        return None
    if ref_date is None:
        ref_date = date.today()
    best = None
    for mp in getattr(person, "member_persons", None) or []:
        member = getattr(mp, "member", None)
        if member is None:
            continue
        for ms in getattr(member, "memberships", None) or []:
            # The rule is the membership's (CR-13 phase 3): active, and the day
            # within its period.
            if ms.valid_on(ref_date):
                if best is None or ms.valid_to > best:
                    best = ms.valid_to
    return best


def membership_coverage_until(person, ref_date: Optional[date] = None):
    """Verst reikende ``valid_to`` van een actief lidmaatschap dat vandaag OF in de
    toekomst geldig is (``valid_to >= ref_date``) — dus **inclusief een al betaald
    volgend jaar** (#496). Voor de status + vernieuwknop in het gezinscherm.
    NIET voor 'is nu lid' (dat blijft ``valid_membership_until`` — ledenprijzen
    op activiteiten ongemoeid)."""
    if person is None:
        return None
    if ref_date is None:
        ref_date = date.today()
    best = None
    for mp in getattr(person, "member_persons", None) or []:
        member = getattr(mp, "member", None)
        if member is None:
            continue
        for ms in getattr(member, "memberships", None) or []:
            if ms.is_active and ms.valid_to is not None and ms.valid_to >= ref_date:
                if best is None or ms.valid_to > best:
                    best = ms.valid_to
    return best


# ── Hernieuwingsvenster (§19.3: één plek) ──────────────────────────────────────


def renewal_open(today: Optional[date] = None) -> bool:
    """True zodra de jaarlijkse vernieuwingscampagne open is
    (MEMBERSHIP_RENEWAL_START_MD, "MM-DD"). Zonder instelling: dicht."""

    if today is None:
        today = date.today()
    from app.kernel.tenant_config import tenant_membership_config

    renewal_start_md = tenant_membership_config()["renewal_start_md"]
    if not renewal_start_md:
        return False
    try:
        month, day = (int(x) for x in renewal_start_md.split("-"))
        return today >= date(today.year, month, day)
    except (ValueError, TypeError):
        return False


def renewal_available(coverage_until: Optional[date], today: Optional[date] = None) -> bool:
    """Mag de vernieuwknop getoond worden? Geen dekking → altijd (kan (her)inschrijven);
    anders enkel als het venster open is **én** het lid nog niet voor volgend jaar
    gedekt is. Zo verbergt een al betaald volgend jaar de knop i.p.v. dat die op een
    409 'al vernieuwd' botst (#496). Voed dit met ``membership_coverage_until``."""
    if coverage_until is None:
        return True
    if today is None:
        today = date.today()
    return renewal_open(today) and coverage_until.year <= today.year


def is_member(db, email: str, ref_date: Optional[date] = None) -> bool:
    """Facade-vraag voor andere componenten (activities, §5.4): heeft dit
    e-mailadres vandaag een geldig lidmaatschap? Lost de persoon op via het
    auth-component (e-mail → Person) en past de geldigheidsregel toe."""
    from app.domains.auth.api import login_person_for_email

    person = login_person_for_email(db, email)
    return has_valid_membership(person, ref_date)


# ── Vernieuwingscampagne: welk jaar telt vandaag? (#582) ──────────────────────


def renewal_years(today: Optional[date] = None) -> tuple[int, int]:
    """(referentiejaar, doeljaar) van de lopende vernieuwingscampagne.

    Het doeljaar kantelt op de tenant-instelling ``membership_next_year_from_md``
    — dezelfde datum vanaf wanneer een betaling ook het volgende kalenderjaar
    dekt (``membership_valid_period``). Vóór die datum gaat de campagne nog over
    het lopende jaar; vanaf die datum over het volgende.

    Het referentiejaar is het jaar ervóór: daaruit komt de groep die *zou*
    moeten vernieuwen.
    """
    if today is None:
        today = date.today()
    from app.kernel.tenant_config import tenant_membership_config

    md = tenant_membership_config()["next_year_from_md"]
    try:
        maand, dag = (int(x) for x in str(md).split("-"))
        kantelt = date(today.year, maand, dag)
    except (ValueError, TypeError, AttributeError):
        # Zonder bruikbare instelling gaat de campagne over het lopende jaar.
        return today.year - 1, today.year
    if today < kantelt:
        return today.year - 1, today.year
    return today.year, today.year + 1


def members_with_membership_for_year(db, year: int) -> set[int]:
    """De member-id's met een actief lidmaatschap dat jaar ``year`` dekt.

    "Dekt" = de geldigheidsperiode overlapt het kalenderjaar. Een lidmaatschap
    dat na de kanteldatum betaald werd loopt tot 31 december van het jaar erna en
    dekt dus twee jaren — precies wat "al vernieuwd" betekent.

    Deliberately broader than "a member today" (`valid_on`, #1307): the
    newsletter's audience "leden" and the renewal count ask about a year, so a
    household that paid in October for next year belongs to both years here,
    while "today" asks only whether its period covers this one day.
    """
    from app.domains.membership.models import Membership

    begin, eind = date(year, 1, 1), date(year, 12, 31)
    rijen = (
        db.query(Membership.member_id)
        .filter(
            Membership.is_active.is_(True),
            Membership.valid_from.isnot(None),
            Membership.valid_to.isnot(None),
            Membership.valid_from <= eind,
            Membership.valid_to >= begin,
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rijen}


def default_relation(earlier: Sequence[str | None]) -> str:
    """The relation a new person in a household starts with (#1321): the stored code.

    Koen, 29 September 2026: *"Meestal werkt men zo: hoofdlid, partner,
    kinderen."* The first person is the head of household, the next one the
    partner as long as there is none yet, and everyone after that an (adult)
    child. Only the prefill: nothing is refused, a second partner stays possible.

    `earlier` are the relations of the persons before this one, as codes, in the
    order of the form. The one rule: the "Word lid" form prefills a new person
    with it, and the server falls back on it for a person without a relation.
    """
    from app.domains.mdm.api import RelationType

    if not earlier:
        return RelationType.PRIMARY_MEMBER.value
    if RelationType.PARTNER.value not in earlier:
        return RelationType.PARTNER.value
    return RelationType.ADULT_CHILD.value


def valid_on(day: date) -> tuple:
    """The one rule for "a member on ``day``" (#1307): the conditions on a Membership.

    Active, and ``day`` falls within [valid_from, valid_to], both set. The year
    printed on the membership plays no part: a household that pays after the
    turnover date gets next year's membership, valid from the day it paid, and is
    a member today.

    There were four definitions of "active household": the member list's KPI, the
    newsletter's audience, the dashboard tile (active membership ROWS with this
    year's number, so a household renewing in October dropped out until 1 January)
    and the reporting flag `f_members.is_valid_today` (without `is_active`). The
    Python side reads this function; the reporting views repeat it in SQL, and
    `test_active_households_parity` fails the day the two disagree.
    """
    from app.domains.membership.models import Membership

    return (
        Membership.is_active.is_(True),
        Membership.valid_from.isnot(None),
        Membership.valid_to.isnot(None),
        Membership.valid_from <= day,
        Membership.valid_to >= day,
    )


def members_valid_on(db, day: Optional[date] = None) -> set[int]:
    """De member-id's met een lidmaatschap dat op ``day`` geldig is (#582, #1307)."""
    from app.domains.membership.models import Membership

    rijen = db.query(Membership.member_id).filter(*valid_on(day or date.today())).distinct().all()
    return {r[0] for r in rijen}


def current_membership_counts(db, today: Optional[date] = None) -> tuple[int, int]:
    """Households that are a member today, and the persons in them (#294, #1307).

    Moved here from `payment.service`, where it was a leftover: it is the member
    list's KPI and Raakje's member count, and it reads the one rule `valid_on`.
    A household with two overlapping memberships counts once. Soft-deleted rows
    fall away through the global ORM filter. Returns ``(households, persons)``.
    """
    from sqlalchemy import distinct, func

    from app.domains.mdm.api import MemberPerson, Person
    from app.domains.membership.models import Membership

    valid = valid_on(today or date.today())
    households = db.query(func.count(distinct(Membership.member_id))).filter(*valid).scalar() or 0
    persons = (
        db.query(func.count(distinct(MemberPerson.person_id)))
        .join(Membership, Membership.member_id == MemberPerson.member_id)
        # Join Person so the global soft-delete filter drops removed persons (a
        # MemberPerson row would otherwise still point at them).
        .join(Person, Person.id == MemberPerson.person_id)
        .filter(*valid)
        .scalar()
    ) or 0
    return households, persons


def not_renewed_count(db, today: Optional[date] = None) -> int:
    """Gezinnen die lid waren in het referentiejaar maar het doeljaar nog niet
    dekken (#582). Soft-deleted rijen vallen weg via de globale ORM-filter."""
    referentie, doel = renewal_years(today)
    return len(
        members_with_membership_for_year(db, referentie)
        - members_with_membership_for_year(db, doel)
    )


def open_renewal_payment(db, member):
    """De openstaande vernieuwingsbetaling van dit gezin, of ``None`` (#618).

    Eén bron voor de vraag "loopt er nog een vernieuwing?". Ze werd gesteld door de
    guard in ``household_router`` (die een tweede procedure blokkeert) en moest ook
    door het gezinsportaal gesteld worden (dat anders het vernieuwformulier toont
    voor een handeling die gegarandeerd faalt). Twee eigen varianten die uit elkaar
    groeien is precies hoe je opnieuw een scherm krijgt dat iets anders beweert dan
    de knop doet.

    "Openstaand" = een membership-betaling van dit gezin die niet betaald, geannuleerd
    of mislukt is.
    """
    # Lokale imports: service.py houdt zijn modulehoofd vrij van model- en
    # domeinimports (de rest van het bestand doet dat ook zo).
    from app.domains.membership.models import Membership
    from app.domains.payment.api import PayableType, PaymentRecord, PaymentStatus

    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.MEMBERSHIP,
            PaymentRecord.status.notin_(
                [PaymentStatus.PAID, PaymentStatus.CANCELLED, PaymentStatus.FAILED]
            ),
        )
        .join(Membership, Membership.id == PaymentRecord.payable_id)
        .filter(Membership.member_id == member.id)
        .first()
    )


def set_relation_type(db, family_id: int, person_id: int, relation_type: str) -> bool:
    """Wijzig de rol van een persoon binnen zijn gezin (#635 F).

    Twee regels, en ze golden alleen zolang dit scherm ze onthield: je kan iemand
    niet tot HOOFDLID promoveren via dit pad, en een bestaand HOOFDLID wordt nooit
    overschreven. Dat laatste is de belangrijke: het hoofdlid is de drager van het
    adres, het lidmaatschap en de betaalcommunicatie — hem stil degraderen laat een
    gezin zonder aanspreekpunt achter.

    De regel stond in `mdm/ui.py`, met een rauwe query erbij, en was daardoor niet
    los testbaar (#498). Commit zelf, net als de andere gezinsbewerkingen: de
    transactiegrens ligt in de service (#635 regel 2).

    Geeft terug of er iets gewijzigd is.
    """
    # CR-12 phase 2: this used to apply `(x or "").strip().upper()` on both
    # sides — a normalisation that was needed because the column accepted any
    # spelling. The code list does that now: a value that is not in it does
    # not get in, and `RelationType(...)` already refuses it here with the
    # name of the list.
    from app.domains.mdm.api import MemberPerson, RelationType

    try:
        gevraagd = RelationType((relation_type or "").strip())
    except ValueError:
        return False
    if gevraagd is RelationType.PRIMARY_MEMBER:
        return False

    koppeling = (
        db.query(MemberPerson)
        .filter(MemberPerson.member_id == family_id, MemberPerson.person_id == person_id)
        .first()
    )
    if koppeling is None or koppeling.relation_type is RelationType.PRIMARY_MEMBER:
        return False

    koppeling.relation_type = gevraagd
    db.commit()
    return True


def membership_years(db) -> list[int]:
    """De lidmaatschapsjaren die écht in de data zitten (#582).

    De filterdropdown is data-gedreven, net als op Betalingen: een hardgecodeerde
    reeks klopt na nieuwjaar niet meer.
    """
    from app.domains.membership.models import Membership

    return [
        jaar
        for (jaar,) in db.query(Membership.year).distinct().order_by(Membership.year.desc()).all()
        if jaar
    ]


def parse_member_rows(form) -> list[dict]:
    """De `m<i>_`-velden van een gezinsformulier, als één rij per persoon.

    Gedeeld door het publieke "Word lid" en het beheer-aanmaakscherm (#1110): twee
    schermen met dezelfde veldnamen horen niet elk hun eigen ontleding te hebben.

    Gat-bestendig (#456): een verwijderd gezinslid laat een gat in de nummering,
    dus scan álle aanwezige indices in plaats van te stoppen bij het eerste
    ontbrekende. Een rij zonder naam telt niet mee — dat is een lege rij die de
    bezoeker openliet.
    """
    import re

    indices = sorted(
        {int(mo.group(1)) for k in form.keys() if (mo := re.match(r"m(\d+)_", str(k)))}
    )
    rijen: list[dict] = []
    for index in indices:
        rij = {
            k: (form.get(f"m{index}_{k}") or "").strip()
            for k in (
                "first_name",
                "last_name",
                "date_of_birth",
                "gender_code",
                "email",
                "phone",
                "mobile",
                "relation_type",
            )
        }
        # #1246: the extra e-mail rows of Word lid, in the order they were added.
        # `email` stays the first row — the primary address.
        rij["extra_emails"] = [
            value.strip()
            for key, value in form.items()
            if key.startswith(f"m{index}_email_new_") and isinstance(value, str) and value.strip()
        ]
        if rij["first_name"] or rij["last_name"]:
            rijen.append(rij)
    return rijen


def activate_after_payment(
    db: Session, membership_id: int, *, source: str, actor: Optional[str]
) -> None:
    """Make a membership active after its payment (#113), idempotently.

    The provider's webhook can arrive twice: an active membership is left alone, no
    second history row. A membership without a period gets the one that contains
    today. Moved here from `payment` in CR-13 phase 2 — the owner writes its rows.
    """
    from app.domains.audit.api import snapshot_membership
    from app.domains.membership.models import Membership
    from app.domains.payment.api import membership_valid_period

    membership = db.query(Membership).filter(Membership.id == membership_id).first()
    if membership is None or membership.is_active:
        return
    membership.is_active = True
    if membership.valid_from is None or membership.valid_to is None:
        valid_from, valid_to = membership_valid_period(date.today())
        membership.valid_from = membership.valid_from or valid_from
        membership.valid_to = membership.valid_to or valid_to
    db.flush()
    snapshot_membership(
        db,
        membership,
        operation="update",
        action="membership_activated",
        source=source,
        actor=actor,
    )

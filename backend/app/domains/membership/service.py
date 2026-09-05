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
from typing import Optional


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
            if (
                ms.is_active
                and ms.valid_from is not None
                and ms.valid_to is not None
                and ms.valid_from <= ref_date <= ms.valid_to
            ):
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
    from app.config import settings

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
    """
    from app.domains.membership.models import Membership

    begin, eind = date(year, 1, 1), date(year, 12, 31)
    rijen = (db.query(Membership.member_id)
             .filter(Membership.is_active.is_(True),
                     Membership.valid_from.isnot(None),
                     Membership.valid_to.isnot(None),
                     Membership.valid_from <= eind,
                     Membership.valid_to >= begin)
             .distinct().all())
    return {r[0] for r in rijen}


def members_valid_on(db, day: Optional[date] = None) -> set[int]:
    """De member-id's met een lidmaatschap dat op ``day`` geldig is (#582).

    Dit is de "actief"-definitie van het ledenscherm en van
    ``current_membership_counts``: actief én de dag valt binnen [valid_from,
    valid_to].
    """
    from app.domains.membership.models import Membership

    if day is None:
        day = date.today()
    rijen = (db.query(Membership.member_id)
             .filter(Membership.is_active.is_(True),
                     Membership.valid_from.isnot(None),
                     Membership.valid_to.isnot(None),
                     Membership.valid_from <= day,
                     Membership.valid_to >= day)
             .distinct().all())
    return {r[0] for r in rijen}


def not_renewed_count(db, today: Optional[date] = None) -> int:
    """Gezinnen die lid waren in het referentiejaar maar het doeljaar nog niet
    dekken (#582). Soft-deleted rijen vallen weg via de globale ORM-filter."""
    referentie, doel = renewal_years(today)
    return len(members_with_membership_for_year(db, referentie)
               - members_with_membership_for_year(db, doel))


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
    from app.domains.payment.api import PaymentRecord

    return (
        db.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == "membership",
                PaymentRecord.status.notin_(["paid", "cancelled", "failed"]))
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
    from app.domains.mdm.api import MemberPerson

    gevraagd = (relation_type or "").strip()
    if not gevraagd or gevraagd.upper() == "HOOFDLID":
        return False

    koppeling = (db.query(MemberPerson)
                 .filter(MemberPerson.member_id == family_id,
                         MemberPerson.person_id == person_id).first())
    if koppeling is None or (koppeling.relation_type or "").upper() == "HOOFDLID":
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

    return [jaar for (jaar,) in db.query(Membership.year).distinct()
            .order_by(Membership.year.desc()).all() if jaar]

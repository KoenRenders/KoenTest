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

"""Gedeelde domeinlogica voor het totaalbedrag van een activiteitsinschrijving.

Dit is de enige bron van waarheid voor "wat kost deze inschrijving". Hij wordt
gebruikt door:
  - de registratie-router (bedrag richting Mollie / betaalrecord),
  - de bevestigingsmail (regels + totaal tonen),
  - de betaal-admin (regels + totaal tonen).

Houd berekeningslogica hier — niet inline in routers of mailtemplates — zodat
scherm, mail en betaling nooit uit elkaar kunnen lopen.
"""
from decimal import Decimal
from typing import List, Tuple, TypedDict


class RegistrationLine(TypedDict):
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    is_free: bool
    pay_on_site: bool


def _unit_price(product, is_member: bool) -> Decimal:
    """De stukprijs van één product. De enige plek waar die bepaald wordt (#635-1).

    De ledenprijs geldt als de inschrijver op de peildatum lid is én het product
    er een heeft. De guard `>= 0` staat er omdat een negatieve member_price een
    invoerfout is die anders als korting doorwerkt in het te betalen bedrag.
    `Decimal(str(...))` en niet `Decimal(...)`: de kolom kan als float terugkomen
    en `Decimal(0.1)` levert 0.1000000000000000055511151231257827.
    """
    member_price = getattr(product, "member_price", None)
    if is_member and member_price is not None and member_price >= 0:
        return Decimal(str(member_price))
    return Decimal(str(product.price))


def _betaalbaar(product) -> bool:
    """Gratis en 'ter plaatse te betalen' staan wel op het scherm, maar worden
    niet afgerekend via de portaal (#373)."""
    return not bool(product.is_free) and not bool(getattr(product, "pay_on_site", False))


def _line(product, quantity: int, is_member: bool) -> RegistrationLine:
    """Eén toonbare regel: naam, aantal, stukprijs, subtotaal en de twee vlaggen."""
    unit_price = _unit_price(product, is_member)
    return {
        "name": product.name,
        "quantity": quantity,
        "unit_price": unit_price,
        "subtotal": unit_price * quantity,
        "is_free": bool(product.is_free),
        "pay_on_site": bool(getattr(product, "pay_on_site", False)),
    }


def _telt_mee(regel: RegistrationLine) -> bool:
    return not regel["is_free"] and not regel["pay_on_site"]


def quote_lines(component, quantities: dict[int, int],
                is_member: bool) -> Tuple[Decimal, List[RegistrationLine]]:
    """Wat kost deze keuze, vóórdat er iets is opgeslagen? (#635 punt 1)

    Dezelfde regel-per-product-logica als `compute_registration_total`, maar met
    de aantallen uit het formulier i.p.v. uit opgeslagen items. Zo kan de live
    quote op het inschrijfscherm niet afdrijven van het bedrag dat na het opslaan
    naar Mollie, de mail en het betaalrecord gaat.

    De peildatum voor `is_member` ligt bij de aanroeper. Voor het inschrijfscherm
    is dat "vandaag" (`has_valid_membership(person)` zonder datum): de bezoeker
    ziet wat hij nú zou betalen. `compute_registration_total` gebruikt de
    inschrijfdatum, want daar is de prijs al vastgeklikt.

    Producten met aantal 0 leveren geen regel op.
    """
    regels = [_line(p, quantities.get(p.id, 0), is_member)
              for p in (component.products or [])
              if quantities.get(p.id, 0) > 0]
    totaal = sum((r["subtotal"] for r in regels if _telt_mee(r)), Decimal("0"))
    return totaal, regels


def has_payable_products(component, is_member: bool) -> bool:
    """Valt er op dit onderdeel iets af te rekenen via de portaal? (#607)

    Afgeleid uit dezelfde regelberekening als het totaal, zodat het totaalblok
    niet kan verschijnen zonder bedrag of omgekeerd: een lid met ledenprijs 0
    telt niet als betalend, en gratis/ter-plaatse-producten evenmin.
    """
    return any(_betaalbaar(p) and _unit_price(p, is_member) > 0
               for p in (component.products or []))


def compute_registration_total(registration) -> Tuple[Decimal, List[RegistrationLine]]:
    """Bereken (totaal, regels) van een inschrijving op basis van haar items.

    Elke regel bevat naam, aantal, stukprijs, subtotaal en de vlaggen is_free /
    pay_on_site. Gratis producten (is_free=True) én 'ter plaatse te betalen'
    (pay_on_site=True, #373) worden wel als regel getoond maar niet in het totaal
    meegerekend. Items zonder gekoppeld product worden overgeslagen.

    Ledenprijs (#93, #111): is de inschrijving gekoppeld aan een persoon
    (``registration.person``) die op de inschrijfdatum een **geldig**
    lidmaatschap heeft, en heeft het product een ``member_price``, dan rekenen
    we die i.p.v. de gewone prijs. Een loutere koppeling aan een persoon volstaat
    niet — er moet een actief lidmaatschap zijn dat de inschrijfdatum dekt (zie
    ``app.services.membership.has_valid_membership``). De datum is de
    inschrijfdatum (``registered_at``), zodat de prijs deterministisch blijft en
    scherm, mail, Mollie-bedrag en betaalrecord nooit uit elkaar lopen.
    """
    from app.domains.membership.api import has_valid_membership

    person = getattr(registration, "person", None)
    registered_at = getattr(registration, "registered_at", None)
    ref_date = registered_at.date() if registered_at is not None else None
    is_member = has_valid_membership(person, ref_date)
    regels: List[RegistrationLine] = [
        _line(item.product, item.quantity, is_member)
        for item in (registration.items or [])
        if getattr(item, "product", None) is not None
    ]
    totaal = sum((r["subtotal"] for r in regels if _telt_mee(r)), Decimal("0"))
    return totaal, regels

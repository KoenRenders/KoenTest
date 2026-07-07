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
    from app.services.membership import has_valid_membership

    person = getattr(registration, "person", None)
    registered_at = getattr(registration, "registered_at", None)
    ref_date = registered_at.date() if registered_at is not None else None
    is_member = has_valid_membership(person, ref_date)
    regels: List[RegistrationLine] = []
    totaal = Decimal("0")
    for item in (registration.items or []):
        product = getattr(item, "product", None)
        if product is None:
            continue
        member_price = getattr(product, "member_price", None)
        if is_member and member_price is not None:
            unit_price = Decimal(str(member_price))
        else:
            unit_price = Decimal(str(product.price))
        subtotal = unit_price * item.quantity
        pay_on_site = bool(getattr(product, "pay_on_site", False))
        regels.append({
            "name": product.name,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "is_free": bool(product.is_free),
            "pay_on_site": pay_on_site,
        })
        # Gratis én 'ter plaatse te betalen' (eigen budget) tellen niet mee in het
        # (Mollie-)totaal; enkel betalende producten worden afgerekend (#373).
        if not product.is_free and not pay_on_site:
            totaal += subtotal
    return totaal, regels

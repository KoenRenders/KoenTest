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


def compute_registration_total(registration) -> Tuple[Decimal, List[RegistrationLine]]:
    """Bereken (totaal, regels) van een inschrijving op basis van haar items.

    Elke regel bevat naam, aantal, stukprijs en subtotaal. Gratis producten
    (is_free=True) worden wel als regel getoond (prijs €0,00) maar niet in het
    totaal meegerekend. Items zonder gekoppeld product worden overgeslagen.
    """
    regels: List[RegistrationLine] = []
    totaal = Decimal("0")
    for item in (registration.items or []):
        product = getattr(item, "product", None)
        if product is None:
            continue
        unit_price = Decimal(str(product.price))
        subtotal = unit_price * item.quantity
        regels.append({
            "name": product.name,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
        })
        if not product.is_free:
            totaal += subtotal
    return totaal, regels

"""Geldbedragen als tekst, in nl-BE-notatie (#735).

Het beheer schreef `€ 35.00` met een punt, de publieke site `€ 35,00` met een komma
(`cms/render.py` deed daar zijn eigen `.replace(".", ",")`). In het Nederlands is de
punt een duizendtalteken, dus `€ 1342.00` naast `€ 25,00` is niet alleen
inconsistent maar ook verkeerd te lezen.

Hier en niet in `app/ui`: de servicelaag heeft dezelfde opmaak nodig voor de
meldingen die sinds #723 op het scherm komen, en die mag niet van de UI-laag
afhangen.
"""
from decimal import Decimal


def bedrag(waarde) -> str:
    """`35` → `"35,00"`. Zonder euroteken — dat staat in de sjablonen zelf.

    Een negatief bedrag houdt zijn minteken: terugbetalingen dragen dat, en het
    hoort zichtbaar te blijven.
    """
    getal = Decimal(str(waarde if waarde is not None else 0))
    return f"{getal:.2f}".replace(".", ",")

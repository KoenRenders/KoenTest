"""Een meetwaarde als tekst, per opmaaksoort (#875).

Koen maakte een rapport met *Gemiddelde betaaltermijn* en kreeg `0E-20`,
`0.29629629629629630` en `12.1000000000000000` te zien, terwijl de geldkolom
ernaast netjes `€ 247,00` gaf. `0E-20` is geen rekenfout — zo drukt een `Decimal`
van nul met twintig decimalen zichzelf af.

**De oorzaak was breder dan die ene kolom, en breder dan gemeld.** Het issue
sprak van vijf opmaaksoorten; de gate hieronder vond er **zeven** — `YEAR` en
`DATE` stonden er ook, en gingen er net zo rauw doorheen. Het paneel kende er één:
geld. Al de rest ging rauw naar het
scherm, dus `DAYS` en `PERCENTAGE` waren gedeclareerd en werden genegeerd. Dezelfde
vorm als #852: de universe belooft iets dat de code niet nakomt.

Hier en niet in de sjablonen, om twee redenen. De opmaak stond op **twee** plekken
(de rij en de totaalrij hadden elk hun eigen geldtak), en twee kopieën ronden op een
dag verschillend af. En zo staat er één afbeelding van soort naar weergave die een
gate kan toetsen: `FORMATTERS` moet elke waarde van `Format` dekken, en een nieuwe
soort die hier niet in staat, faalt in `test_reporting_number_format.py` in plaats
van stil rauw op het scherm te komen.

Geen domeinkennis: de soort komt binnen als tekst, niet als de enum van de
rapportagelaag. Zo mag de UI-kit deze functie gebruiken zonder de universe te
kennen.
"""
from decimal import Decimal, InvalidOperation

from app.kernel.geld import bedrag


def _decimaal(waarde) -> Decimal | None:
    try:
        return Decimal(str(waarde))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _geheel(waarde) -> str:
    """Een telling: geen decimalen, want een half lid bestaat niet."""
    getal = _decimaal(waarde)
    if getal is None:
        return str(waarde)
    return f"{getal.to_integral_value():f}".split(".")[0]


def _dagen(waarde) -> str:
    """Een aantal dagen, op één decimaal.

    Eén en niet nul: een gemiddelde betaaltermijn van 12,1 dagen zegt meer dan 12,
    en twintig decimalen zeggen niets. De komma is nl-BE (#735).
    """
    getal = _decimaal(waarde)
    if getal is None:
        return str(waarde)
    return f"{getal:.1f}".replace(".", ",")


def _percentage(waarde) -> str:
    getal = _decimaal(waarde)
    if getal is None:
        return str(waarde)
    return f"{getal:.1f}".replace(".", ",") + "%"


def _jaar(waarde) -> str:
    """Een jaartal: vier cijfers, geen duizendtalteken.

    `1.999` in plaats van `1999` is precies wat een getalopmaak met een
    duizendtalteken van een jaar maakt, dus dit is geen dubbele van `count`.
    """
    getal = _decimaal(waarde)
    if getal is None:
        return str(waarde)
    return f"{getal.to_integral_value():f}".split(".")[0]


def _datum(waarde) -> str:
    """Een datum als `12-09-2026`, zoals elke andere beheertabel ze schrijft."""
    strftime = getattr(waarde, "strftime", None)
    return strftime("%d-%m-%Y") if strftime else str(waarde)


def _label(waarde) -> str:
    return str(waarde)


# Elke waarde van `Format` uit de universe, als tekst. De gate in
# `test_reporting_number_format.py` houdt deze afbeelding volledig.
FORMATTERS = {
    "money": bedrag,
    "count": _geheel,
    "days": _dagen,
    "percentage": _percentage,
    "year": _jaar,
    "date": _datum,
    "label": _label,
}


def meetwaarde(waarde, formaat: str = "label") -> str:
    """De waarde als tekst. Een onbekende soort valt terug op de ruwe waarde.

    Terugvallen en niet falen: een rapport op het scherm hoort niet wit te worden
    omdat iemand een soort toevoegde. De gate is de plek waar dat opvalt.
    """
    if waarde is None:
        return ""
    return FORMATTERS.get(formaat, _label)(waarde)

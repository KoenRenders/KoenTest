"""Gedeelde geld-invarianten (#622, laag 2).

Eén hulpfunctie die elke geldmutatie-test afsluit, in plaats van per test losse
assertions die net iets anders controleren. De invariant is dezelfde die
`reconcile_charges` belooft, en het is precies de invariant die niemand controleerde
toen #617 en #619 ontstonden.
"""
from decimal import Decimal


def assert_saldo_klopt(db, payable_type: str, payable_id: int, verwacht_totaal) -> list:
    """Som van de niet-verwijderde records == het verwachte totaal.

    Plus: nooit een openstaande post náást een terugbetaling — dat is geen geldige
    stand, want dan claimen we tegelijk geld te krijgen én terug te moeten geven.

    Geeft de records terug, zodat een test er verder op kan asserteren.
    """
    from app.domains.payment.api import get_records_for

    records = get_records_for(db, payable_type, payable_id)
    som = sum((Decimal(str(r.amount)) for r in records), Decimal("0"))
    assert som == Decimal(str(verwacht_totaal)), (
        f"som van de records is {som}, verwacht {verwacht_totaal} "
        f"voor {payable_type}/{payable_id}"
    )

    open_posten = [r for r in records if r.amount_paid is None and r.type == "charge"]
    refunds = [r for r in records if r.type == "refund"]
    assert not (open_posten and refunds), (
        "een openstaande post naast een terugbetaling is nooit een geldige stand"
    )
    return records


def assert_geen_pending_als_betaald(html: str) -> None:
    """Een record met status `pending` mag nergens als betaald/terugbetaald renderen.

    Label-naar-toestand, geen bedrag — dit is de controle die #617 zou hebben
    gevangen: daar klopte de databank en loog het scherm.
    """
    assert "✓ Terugbetaald" not in html, (
        "'✓ Terugbetaald' hoort alleen bij een refund met status paid (#617)"
    )


def assert_geen_wezen(db) -> None:
    """Na een mutatie mag er geen betaling zonder payable achterblijven."""
    from app.domains.payment.handlers import find_orphan_records

    wezen = find_orphan_records(db)
    assert not wezen, f"weesrecords na de mutatie: {[w.id for w in wezen]}"

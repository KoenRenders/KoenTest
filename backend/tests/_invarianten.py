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
    """Na een mutatie mag er geen betaling zonder payable achterblijven.

    De query staat sinds #824 HIER en niet meer in de applicatie. Het
    wees-mechanisme — een job, een werkbanktaak, een scherm — is toen verdwenen:
    een wees-betaling is geen gebeurtenis in het bedrijf maar een symptoom van een
    bug, en sinds #667 kan de applicatie er geen meer maken. Zoiets hoort opgelost te
    worden in de code, niet wekelijks weggeklikt door een penningmeester.

    Dat maakt deze invariant juist bruikbaarder: hij bewaakt in de TESTS dat onze
    eigen mutaties geen wees achterlaten, in plaats van in productie te wachten tot
    het misgaat. Het is dus geen vervanging van het verwijderde mechanisme maar de
    keerzijde ervan — voorkomen in plaats van signaleren.

    **Dit is de goede kant van hetzelfde argument, en daarom blijft hij staan**
    (beslist bij #824). Koens bezwaar was dat de gebruiker niet mag hoeven bewaken
    wat wij hadden moeten voorkomen. Een testinvariant is precies waar zo'n potentiële
    bug wél thuishoort: hij vangt hem vóór hij bestaat, in plaats van hem achteraf aan
    een penningmeester te tonen.

    En nu de detectie in productie weg is, is dit het enige wat er nog tussen staat —
    samen met de gate van #667, die verhindert dat de toestand kan ontstaan. Die twee
    horen bij elkaar: haal je deze invariant óók weg, dan verschuift het van "we
    voorkomen het" naar "we hopen het". Zie de docstring van
    `test_payable_delete_gate.py` voor de andere helft.
    """
    from app.domains.activities.api import Registration
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    # `include_deleted`: soft-deleted payables tellen als BESTAAND. Een normale
    # verwijdering levert dus geen wees op — alleen een harde delete doet dat, en
    # precies die verbiedt de gate van #667.
    reg_ids = {r for (r,) in db.query(Registration.id)
               .execution_options(include_deleted=True).all()}
    ms_ids = {m for (m,) in db.query(Membership.id)
              .execution_options(include_deleted=True).all()}
    wezen = [r for r in db.query(PaymentRecord).all()
             if (r.payable_type == "registration" and r.payable_id not in reg_ids)
             or (r.payable_type == "membership" and r.payable_id not in ms_ids)]
    assert not wezen, f"weesrecords na de mutatie: {[w.id for w in wezen]}"

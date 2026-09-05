"""Filter, aggregatie, kaartgroepering en afgeleide status van betalingen (#635 C).

Deze vier regels stonden in de UI-route, en de filter bovendien nóg eens half in
`exports.py`. Ze waren al uit elkaar gelopen: het scherm kende `failed`,
`cancelled` en vrij zoeken, de export niet; de export eiste bij een
onderdeelfilter `payable_type == "registration"`, het scherm niet. Wie op het
scherm filterde en dan exporteerde, kreeg iets anders in zijn .ods dan hij zag.

De regels wonen nu in `payment.service`. Deze test dekt ze rechtstreeks — dat is
wat een servicelaag oplevert: los testbaar, zonder scherm, zonder databank.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.payment.api import (
    aggregate, derived_status, filter_records, group_cards, matches_filter, may_delete,
)


def rec(**kw):
    velden = dict(
        id="r1", type="charge", status="pending", method="transfer",
        amount=Decimal("10"), amount_paid=None, payable_type="registration",
        payable_id=1, refund_of_id=None, membership_year=None, component_id=None,
        contact_name=None, structured_communication=None, description=None,
        component_name=None, created_at=0,
    )
    velden.update(kw)
    return SimpleNamespace(**velden)


# ── Filter ───────────────────────────────────────────────────────────────────

def test_zonder_filter_valt_er_niets_weg():
    records = [rec(id="a"), rec(id="b", type="refund")]
    assert filter_records(records) == records


@pytest.mark.parametrize("status", ["pending", "paid", "failed", "cancelled"])
def test_statusfilter_dekt_ook_mislukt_en_geannuleerd(status):
    """`failed`/`cancelled` bestonden alleen op het scherm; de export liet ze
    stilzwijgend door. Nu gelden ze overal."""
    passend = rec(id="ja", status=status)
    ander = rec(id="nee", status="paid" if status != "paid" else "pending")
    assert filter_records([passend, ander], status=status) == [passend]


def test_openstaand_komt_uit_het_saldo_niet_uit_de_statuskolom():
    """Betaald = waarheid (#198): een record met status 'pending' maar volledig
    betaald staat niet meer open."""
    open_saldo = rec(id="open", amount=Decimal("10"), amount_paid=Decimal("4"))
    vereffend = rec(id="dicht", amount=Decimal("10"), amount_paid=Decimal("10"))
    ruis = rec(id="ruis", amount=Decimal("10"), amount_paid=Decimal("9.9995"))
    uit = filter_records([open_saldo, vereffend, ruis], status="openstaand")
    assert [r.id for r in uit] == ["open"]      # afrondingsruis telt niet


def test_onderdeelfilter_eist_een_inschrijving():
    """De export-variant controleerde payable_type, het scherm niet. Een
    lidmaatschapsrecord hoort nooit onder een onderdeelfilter te vallen."""
    inschrijving = rec(id="reg", component_id=7)
    lidmaatschap = rec(id="lid", payable_type="membership", component_id=7)
    uit = filter_records([inschrijving, lidmaatschap], context="comp-7")
    assert [r.id for r in uit] == ["reg"]


def test_jaarfilter_kijkt_naar_het_lidmaatschapsjaar():
    lid25 = rec(id="25", payable_type="membership", membership_year=2025)
    lid26 = rec(id="26", payable_type="membership", membership_year=2026)
    uit = filter_records([lid25, lid26], context="year-2026")
    assert [r.id for r in uit] == ["26"]


def test_zoekterm_zoekt_binnen_het_gekozen_filter():
    """De zoekterm staat vóór de andere filters (#591): je zoekt binnen je
    selectie, niet erbuiten."""
    binnen = rec(id="binnen", component_id=7, contact_name="Jef Peeters")
    buiten = rec(id="buiten", component_id=9, contact_name="Jef Peeters")
    uit = filter_records([binnen, buiten], context="comp-7", q="jef")
    assert [r.id for r in uit] == ["binnen"]


def test_zoekterm_dekt_de_vier_velden_waarmee_je_terugvindt():
    velden = {"contact_name": "Ann", "structured_communication": "+++123+++",
              "description": "Quiz", "component_name": "Ploegen"}
    for veld, waarde in velden.items():
        treffer = rec(id=veld, **{veld: waarde})
        assert filter_records([treffer], q=waarde[:3].lower()) == [treffer], veld


def test_de_export_gebruikt_dezelfde_filter():
    """Geen tweede predicaat meer in exports.py — dat was de bron van de drift."""
    from app.domains.payment import exports

    assert not hasattr(exports, "_passes_filter")


def test_expliciete_verrijking_wint_van_het_record():
    """De export verrijkt rauwe records; het scherm krijgt ze al verrijkt binnen.
    Eén functie moet allebei aankunnen."""
    kaal = rec(component_id=None)
    assert matches_filter(kaal, context="comp-7", component_id=7) is True
    assert matches_filter(kaal, context="comp-7") is False


# ── Aggregatie ───────────────────────────────────────────────────────────────

def test_aggregatie_telt_te_betalen_ontvangen_en_saldo():
    uit = aggregate([rec(amount=Decimal("10"), amount_paid=Decimal("4")),
                     rec(amount=Decimal("5"), amount_paid=None)])
    assert uit == {"due": Decimal("15"), "paid": Decimal("4"), "saldo": Decimal("11")}


def test_aggregatie_van_niets_is_nul_geen_fout():
    assert aggregate([]) == {"due": Decimal("0"), "paid": Decimal("0"),
                             "saldo": Decimal("0")}


# ── Afgeleide status ─────────────────────────────────────────────────────────

def test_deels_betaald_is_een_afgeleide_toestand():
    """"Deels betaald" bestond alleen in de Jinja-template en was daardoor
    nergens testbaar (#635 punt 9)."""
    assert derived_status(rec(status="pending", amount_paid=Decimal("4"))) == "partial"
    assert derived_status(rec(status="pending", amount_paid=None)) == "pending"
    assert derived_status(rec(status="pending", amount_paid=Decimal("0"))) == "pending"


def test_een_openstaande_terugbetaling_heeft_haar_eigen_naam():
    assert derived_status(rec(type="refund", status="pending")) == "refund_due"
    assert derived_status(rec(type="refund", status="paid")) == "paid"


def test_een_onbekende_gatewaystatus_komt_ongewijzigd_terug():
    """Mollie kent ook `authorized`/`expired`; het scherm mag ze niet rauw tonen,
    dus geeft de service ze door en valt de template terug op haar labelmap."""
    assert derived_status(rec(status="authorized")) == "authorized"


# ── Verwijderbaarheid ────────────────────────────────────────────────────────

def test_een_online_betaalde_vordering_is_nooit_verwijderbaar():
    assert may_delete(rec(method="online", status="paid")) is False


def test_verwijderen_mag_zolang_er_niets_ontvangen_is():
    assert may_delete(rec(amount_paid=None)) is True
    assert may_delete(rec(amount_paid=Decimal("0"))) is True
    assert may_delete(rec(amount_paid=Decimal("1"))) is False


# ── Kaartgroepering ──────────────────────────────────────────────────────────

def test_refunds_hangen_onder_hun_eigen_vordering():
    charge = rec(id="c1", created_at=2)
    refund = rec(id="r1", type="refund", refund_of_id="c1", created_at=1,
                 amount=Decimal("3"), amount_paid=Decimal("3"))
    groepen = group_cards([charge, refund])
    assert len(groepen) == 1
    # Sinds #673 is een kaart een dict: charge, refunds, en twee vlaggen die niets
    # met elkaar te maken hebben (context uit #668, bijkomend uit #673).
    kaart = groepen[0]["kaarten"][0]
    assert kaart["charge"] is charge and kaart["refunds"] == [refund]
    assert kaart["is_context"] is False and kaart["is_extra"] is False


def test_een_wees_refund_verdwijnt_niet_van_het_scherm():
    """Valt de bijhorende vordering buiten het filter, dan hoort de terugbetaling
    nog steeds getoond te worden — anders verdwijnt geld stil."""
    wees = rec(id="r9", type="refund", refund_of_id="c-onzichtbaar", created_at=1)
    groepen = group_cards([wees])
    assert groepen[0]["kaarten"] == [
        {"charge": wees, "refunds": [], "is_context": False, "is_extra": False}]


def test_de_totaalregel_telt_de_hele_payable():
    """#617-2e: twee vorderingen op één inschrijving gaven twee totaalregels die
    geen van beide de inschrijving telden."""
    a = rec(id="a", payable_id=5, amount=Decimal("10"), created_at=2)
    b = rec(id="b", payable_id=5, amount=Decimal("7"), created_at=1)
    groepen = group_cards([a, b])
    assert len(groepen) == 1
    assert groepen[0]["totaal"]["due"] == Decimal("17")
    assert groepen[0]["toon_totaal"] is True


def test_een_enkele_vordering_krijgt_geen_totaalregel():
    groepen = group_cards([rec(id="a", payable_id=5)])
    assert groepen[0]["toon_totaal"] is False


def test_verschillende_payables_blijven_gescheiden():
    a = rec(id="a", payable_id=1, created_at=2)
    b = rec(id="b", payable_type="membership", payable_id=1, created_at=1)
    assert len(group_cards([a, b])) == 2

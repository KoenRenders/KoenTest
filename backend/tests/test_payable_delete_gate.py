"""#667 — geen hard verwijderen in een domein dat een payable bezit.

Koen zag weesbetalingen in de werkbank. De verwijderpaden zelf blijken correct:
`delete_membership` en `delete_registration` doen allebei `soft_delete`, en een
soft-deleted payable telt als bestaand. Er staat vandaag geen enkele `db.delete()`
op een payable in de codebase.

**Er hangt sinds #824 een beslissing aan deze gate, en dat hoort de volgende die
eraan zit te weten.** Het hele wees-mechanisme — de detectiejob, de werkbanktaak, het
scherm — is toen verwijderd, met als argument dat een wees-betaling geen gebeurtenis
in het bedrijf is maar een symptoom van een bug. Dat argument staat of valt met déze
gate: zij is de reden dat de toestand niet meer kan ontstaan. Verzwakt ze, of komt er
een uitzondering bij die een payable raakt, dan is er geen detectie meer die het
opvangt — en dan hoort die beslissing opnieuw op tafel, niet stilzwijgend te blijven
gelden.

Wat er wél overbleef is een invariant in de tests
(`_invarianten.assert_geen_wezen`): die controleert dat onze eigen mutaties geen
wees achterlaten. Voorkomen in plaats van signaleren.

Maar dat is discipline, geen constructie — en die zakt terug. Een foreign key kan
het niet bewaken: `PaymentRecord` verwijst met `payable_type`/`payable_id` naar een
rij in een ánder schema, en `test_schema_boundaries.py` verbiedt cross-schema FK's
(§8). Dat is een bewuste prijs van de schemascheiding, en deze gate is wat ervoor
in de plaats komt.

## Wat de gate wél en niet kan

In Python-broncode is `db.delete(x)` zonder typeinformatie niet naar een model te
herleiden: `x` kan van alles zijn. Een gate die belooft "enkel op payables" zou
dus liegen over zijn eigen dekking.

De gekozen heuristiek is grover en eerlijker: **in de twee domeinen die een
payable bezitten mag helemaal niet hard verwijderd worden.** Dat is ruimer dan
strikt nodig — een `ActivityDate` is geen payable — maar het is precies de grens
die met zekerheid te trekken is, en in die domeinen is soft delete sowieso de
norm. Uitzonderingen horen in `ALLOWLIST`, met een reden.

`RegistrationItem` valt er bewust onder. Geen payable, maar `delete_registration`
soft-delete hem mee "zodat ze niet in aantal-/saldoberekeningen lekken" (#194).
Hard verwijderen verstoort dus wel degelijk de saldi, en dat is dezelfde klasse
fout.

Buiten scope, zoals in het issue: de twaalf bestaande wezen (#619) en het
ontbrekende oplospad in de werkbank.

## De sleutel van een uitzondering (#1040)

Die was een REGELNUMMER en schoof in twee dagen drie keer mee met code die er
niets mee te maken had — de gate viel dan om zonder bevinding, en dat is precies
hoe een poort haar geloofwaardigheid verliest. Het is nu de functienaam.

Gemeten, vier keer:

* een functie toevoegen bóven `remove_organiser` → **groen**. Dat is het hele
  punt: met een regelnummer was dit rood geweest.
* dezelfde verwijdering in een ándere functie → rood.
* een tweede verwijdering ín `remove_organiser` → rood; de sleutel dekt één
  treffer, niet de functie.
* de sleutel naar een niet-bestaande functie laten wijzen → rood, én
  `test_elke_uitzondering_wijst_nog_iets_aan` spreekt. (De functie zelf
  hernoemen kon niet gemeten worden: `api.py` importeert haar, dus dan faalt de
  import-check vóór deze gate iets kan zeggen.)

Opgegeven met open ogen: een verplaatsing BINNEN dezelfde functie valt niet meer
op.
"""
import ast
from pathlib import Path

from tests._bestanden import bestanden

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# De domeinen die een payable-model bezitten. Geverifieerd tegen de code (alleen
# "membership" en "registration" komen voor als payable_type) en de databank.
PAYABLE_DOMEINEN = ("membership", "activities")

PAYABLE_MODELLEN = {
    "app.domains.membership.models.Membership",
    "app.domains.activities.models.Registration",
}

# (bestand, functie) → reden. Leeg is het doel; een uitzondering staat hier
# zichtbaar in de diff, niet verstopt in een commentaar.
#
# #1040: de sleutel was een REGELNUMMER en schoof in twee dagen drie keer mee met
# code die er niets mee te maken had. Een functienaam wijst hetzelfde aan en
# overleeft het toevoegen van een functie erboven. Wat we daarmee opgeven staat
# er bewust bij: een verplaatsing BINNEN dezelfde functie valt niet meer op.
#
# **De sleutel dekt één treffer, niet de functie.** Staat er een tweede
# `db.delete(...)` in dezelfde functie, dan faalt de poort alsnog — anders wordt
# een uitzondering voor één rij stilzwijgend een vrijbrief voor de hele functie.
# Een methode heet `Klasse.methode`; een verwijdering op moduleniveau kan geen
# uitzondering krijgen, want die heeft geen functie om naar te wijzen.
ALLOWLIST: dict[tuple[str, str], str] = {
    # #1004: een organisator is geen payable en draagt bewust geen soft delete —
    # de rij zegt "deze persoon trekt deze activiteit", en wie dat niet meer doet,
    # heeft geen grafsteen nodig. Er hangt geen betaling aan, dus er kan geen wees
    # ontstaan.
    ("domains/activities/service.py", "remove_organiser"): (
        "ActivityOrganiser: geen payable, geen soft delete (#1004)"),
}

REDEN = (
    "een PaymentRecord verwijst hiernaar via payable_type/payable_id zonder "
    "foreign key (cross-schema FK's zijn verboden, §8). Hard verwijderen maakt "
    "die betaling wees. Gebruik soft_delete()."
)


def _modules():
    return bestanden(
        *[(APP / "domains" / d).rglob("*.py") for d in PAYABLE_DOMEINEN],
        wat=f"alle modules van de payable-domeinen {', '.join(PAYABLE_DOMEINEN)}",
        minstens=10,
    )


# `@router.delete("/…")` is een HTTP-werkwoord, geen ORM-verwijdering. Zonder deze
# uitzondering slaat de gate aan op elke DELETE-route — tien stuks — en zegt hij
# niets over wat hij moet bewaken.
GEEN_ORM = {"router", "app"}


def _is_delete_aanroep(node: ast.AST) -> bool:
    """Een ORM-verwijdering: `<sessie>.delete(...)` of `query(...).delete()`.

    Beide vormen tellen. Een bulk-delete zonder argumenten verwijdert rijen even
    hard, en dan zónder ORM-events — dus ook zonder de soft-delete-hook.
    """
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "delete"):
        return False
    ontvanger = node.func.value
    return not (isinstance(ontvanger, ast.Name) and ontvanger.id in GEEN_ORM)


def _verwijderingen(boom: ast.AST) -> list[tuple[str, ast.Call]]:
    """(functienaam, aanroep) voor elke ORM-verwijdering in deze module.

    Per functie gelopen en niet met één `ast.walk` over de module: die verliest
    de omsluitende functie, en dat is sinds #1040 juist de sleutel. Een methode
    krijgt `Klasse.methode`; een verwijdering buiten elke functie krijgt "" en
    kan dus geen uitzondering hebben.
    """
    gevonden: list[tuple[str, ast.Call]] = []
    in_functie: set[int] = set()

    def loop(node: ast.AST, naam: str) -> None:
        for kind in ast.iter_child_nodes(node):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                loop(kind, f"{naam}.{kind.name}" if naam else kind.name)
            elif isinstance(kind, ast.ClassDef):
                loop(kind, f"{naam}.{kind.name}" if naam else kind.name)
            else:
                for binnen in ast.walk(kind):
                    if _is_delete_aanroep(binnen) and id(binnen) not in in_functie:
                        in_functie.add(id(binnen))
                        gevonden.append((naam, binnen))

    loop(boom, "")
    return gevonden


def test_geen_hard_verwijderen_in_een_payable_domein():
    fouten = []
    for pad in _modules():
        boom = ast.parse(pad.read_text())
        gezien: set[tuple[str, str]] = set()
        for functie, node in _verwijderingen(boom):
            naam = str(pad.relative_to(APP))
            sleutel = (naam, functie)
            # Eén treffer per sleutel: een tweede verwijdering in dezelfde functie
            # valt er NIET onder (#1040).
            if functie and sleutel in ALLOWLIST and sleutel not in gezien:
                gezien.add(sleutel)
                continue
            bron = ast.get_source_segment(pad.read_text(), node) or ".delete(…)"
            fouten.append(f"{naam}:{node.lineno} ({functie or 'moduleniveau'}): "
                          f"{bron[:80]}")
    assert not fouten, (
        f"Hard verwijderen in een domein met een payable — {REDEN}\n  "
        + "\n  ".join(fouten)
    )


def test_elke_uitzondering_wijst_nog_iets_aan():
    """Een lijst die alleen mag krimpen, kan dat niet met dode regels erin (#1040).

    Verdwijnt de functie of haar verwijdering, dan hoort de regel hier weg — en
    niet stil te blijven staan tot niemand meer weet waarom ze er was.
    """
    dood = []
    for (bestand, functie), reden in ALLOWLIST.items():
        pad = APP / bestand
        if not pad.exists():
            dood.append(f"{bestand} bestaat niet meer")
            continue
        functies = {f for f, _node in _verwijderingen(ast.parse(pad.read_text()))}
        if functie not in functies:
            dood.append(f"{bestand}:{functie} verwijdert niets (meer) — {reden}")
    assert not dood, ("Haal deze regels uit ALLOWLIST:\n  " + "\n  ".join(dood))


@pytest.mark.parametrize("volledige_naam", sorted(PAYABLE_MODELLEN))
def test_de_payable_modellen_bestaan_nog_waar_de_gate_ze_verwacht(volledige_naam):
    """Verhuist een model, dan bewaakt de gate stil het verkeerde domein."""
    import importlib

    modulenaam, klasse = volledige_naam.rsplit(".", 1)
    module = importlib.import_module(modulenaam)
    assert hasattr(module, klasse), f"{volledige_naam} bestaat niet meer"


def test_beide_payables_dragen_soft_delete():
    """De gate verbiedt hard verwijderen; dan moet de zachte weg er wel zijn."""
    from app.domains.activities.models import Registration
    from app.domains.membership.models import Membership

    for model in (Membership, Registration):
        assert hasattr(model, "deleted_at"), (
            f"{model.__name__} kent geen soft delete, dus er is geen alternatief")


def test_de_payable_types_in_de_code_zijn_de_twee_die_de_gate_kent():
    """Komt er een derde payable_type bij, dan mist de gate een domein."""
    import re

    gevonden = set()
    for pad in bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/",
                         minstens=100):
        for m in re.finditer(r'payable_type\s*=\s*"([a-z_]+)"', pad.read_text()):
            gevonden.add(m.group(1))
    assert gevonden <= {"membership", "registration"}, (
        f"onbekend payable_type: {sorted(gevonden - {'membership', 'registration'})} "
        "— voeg het domein toe aan PAYABLE_DOMEINEN")

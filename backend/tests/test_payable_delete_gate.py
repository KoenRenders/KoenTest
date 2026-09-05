"""#667 — geen hard verwijderen in een domein dat een payable bezit.

Koen zag weesbetalingen in de werkbank. De verwijderpaden zelf blijken correct:
`delete_membership` en `delete_registration` doen allebei `soft_delete`, en de
weesjob telt een soft-deleted payable als bestaand. Er staat vandaag geen enkele
`db.delete()` op een payable in de codebase.

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

# (bestand, regel) → reden. Leeg is het doel; een uitzondering staat hier
# zichtbaar in de diff, niet verstopt in een commentaar.
ALLOWLIST: dict[tuple[str, int], str] = {}

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


def test_geen_hard_verwijderen_in_een_payable_domein():
    fouten = []
    for pad in _modules():
        boom = ast.parse(pad.read_text())
        for node in ast.walk(boom):
            if not _is_delete_aanroep(node):
                continue
            naam = str(pad.relative_to(APP))
            if (naam, node.lineno) in ALLOWLIST:
                continue
            bron = ast.get_source_segment(pad.read_text(), node) or ".delete(…)"
            fouten.append(f"{naam}:{node.lineno}: {bron[:80]}")
    assert not fouten, (
        f"Hard verwijderen in een domein met een payable — {REDEN}\n  "
        + "\n  ".join(fouten)
    )


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

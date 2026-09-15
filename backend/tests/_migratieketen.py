"""De migratieketen lezen zonder hem te draaien (#951).

Drie CLI's werken parallel aan takken die elk een migratie kunnen toevoegen. Ze
kiezen allemaal "het volgende nummer", dus ze kiezen hetzelfde. Op 15 september
2026 gebeurde dat voor het eerst echt, tussen #945 en #939 — allebei `124`.

**Het kenmerk van die fout is dat geen van beide takken stuk is.** Elk apart staat
de CI groen; de botsing bestaat uitsluitend in de combinatie, en die bestaat pas
bij de merge. Een controle op de tak kan er dus per definitie niets aan doen.

Wat er dan gebeurde was bovendien onnodig luidruchtig: de hele suite viel om op
`MultipleHeads`, omdat de session-fixture de migraties draait. Dat leest als
"alles is kapot" terwijl het "één regel" is.

Deze module leest de bestanden, draait niets, heeft geen databank nodig, en levert
meldingen op die de **reparatie** benoemen. `conftest` roept hem aan vóór
`alembic upgrade head` — daar ontstaat de schade, dus daar hoort de melding — en
`test_migratieketen_gate.py` toetst hem apart.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tests._bestanden import bestanden

VERSIES = Path(__file__).resolve().parents[1] / "alembic" / "versions"


class Migratie:
    """Wat er in één migratiebestand staat, zonder het te importeren.

    Importeren zou de module-code draaien; `revision` en `down_revision` zijn
    gewone toekenningen bovenaan, dus de AST volstaat en kost niets.
    """

    def __init__(self, pad: Path):
        self.pad = pad
        self.naam = pad.name
        self.revision: str | None = None
        self.down_revision: str | None = None
        for node in ast.parse(pad.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign):
                continue
            for doel in node.targets:
                if (isinstance(doel, ast.Name)
                        and doel.id in ("revision", "down_revision")
                        and isinstance(node.value, ast.Constant)):
                    setattr(self, doel.id, node.value.value)

    @property
    def volgnummer(self) -> int:
        """Het cijfer vooraan in de bestandsnaam, of -1 als het er niet staat.

        Puur om "de jongste" te kunnen noemen in een foutmelding. Alembic leest
        dit niet: de keten loopt over `down_revision`.
        """
        gevonden = re.match(r"(\d+)_", self.naam)
        return int(gevonden.group(1)) if gevonden else -1

    def __repr__(self) -> str:  # pragma: no cover - alleen voor foutmeldingen
        return f"{self.naam} (revision={self.revision!r})"


def lees_migraties(map_: Path = VERSIES) -> list[Migratie]:
    paden = bestanden(map_.glob("[0-9]*.py"),
                      wat="de migraties in alembic/versions", minstens=20)
    return [Migratie(p) for p in paden]


def problemen(migraties: list[Migratie] | None = None) -> list[str]:
    """Wat er mis is met de keten, als leesbare meldingen. Leeg = in orde.

    Drie soorten, in de volgorde waarin ze elkaar veroorzaken: een dubbele id
    levert bijna altijd óók twee heads op, en dan helpt het om de oorzaak eerst
    te lezen.
    """
    migraties = lees_migraties() if migraties is None else migraties
    uit: list[str] = []

    per_id: dict[str | None, list[str]] = {}
    for migratie in migraties:
        per_id.setdefault(migratie.revision, []).append(migratie.naam)
    for rev, namen in sorted(per_id.items(), key=lambda p: str(p[0])):
        if len(namen) > 1:
            uit.append(
                f"Twee migraties dragen dezelfde revision-id {rev!r}: "
                f"{' en '.join(sorted(namen))}.\n"
                "  Geef de jongste een eigen id (een tijdstempel — zie "
                "alembic/README.md) en laat haar via down_revision onder de "
                "andere hangen.")

    bekend = {m.revision for m in migraties}
    for migratie in migraties:
        if migratie.down_revision is not None and migratie.down_revision not in bekend:
            uit.append(
                f"{migratie.naam} hangt onder {migratie.down_revision!r}, en dat "
                "is nergens een revision.\n"
                "  Meestal is de voorganger hernoemd of nooit mee gecommit.")

    verwezen = {m.down_revision for m in migraties if m.down_revision}
    heads = [m for m in migraties if m.revision not in verwezen]
    if len(heads) > 1:
        op_leeftijd = sorted(heads, key=lambda m: (m.volgnummer, m.revision or ""))
        namen = "\n".join(f"    {m.naam} (revision={m.revision!r})"
                          for m in op_leeftijd)
        jongste = op_leeftijd[-1]
        gelijk = [m for m in op_leeftijd if m.volgnummer == jongste.volgnummer]
        if len(gelijk) > 1:
            advies = ("  Ze dragen hetzelfde volgnummer, dus er is geen jongste "
                      "aan te wijzen. Kies er één en laat de andere eronder "
                      "hangen — de volgorde maakt hier niet uit, zolang er maar "
                      "één head overblijft.")
        else:
            advies = (f"  De jongste is {jongste.naam}. Zet daarin "
                      f"down_revision = {op_leeftijd[-2].revision!r}.\n"
                      "  Dat is de hele reparatie: hernoemen hoeft niet, want "
                      "alembic leest de bestandsnaam niet.")
        uit.append(f"De keten heeft {len(heads)} heads in plaats van één:\n"
                   f"{namen}\n{advies}")
    return uit


def melding(fouten: list[str]) -> str:
    kop = ("De migratieketen klopt niet (#951). Dit is géén kapotte suite — het "
           "is een tak die onder een verouderde head hangt:")
    return "\n\n".join(["", kop, *fouten, ""])

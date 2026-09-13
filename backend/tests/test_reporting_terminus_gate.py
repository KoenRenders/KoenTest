"""Reporting is a terminus: nothing builds a process on top of it (CR-07 §6.6).

The reporting views are read models — question-shaped, derived, and free to
change with the universe. A business process that reads them couples itself to a
shape that may move per release, reads derived data where it should read the
source, and turns downstream into upstream. Measured on 13 September 2026 the
rule already held, but by discipline only: `test_import_boundaries.py` allows any
domain to import any other domain's `api`, so `payment` importing `reporting.api`
would have passed green, and nothing at all watched raw SQL against
`reporting.*`.

Two levels, because the import is only the front door:

1. **Who imports the domain** — an explicit allowlist. A new importer is a red
   build with a message that explains the rule rather than only refusing (#680):
   whoever hits this is usually one line away from the right move (grow the
   owning domain's facade, or add a universe object) and needs to know which.
2. **Who addresses the schema** — a source scan on the `reporting.` prefix, for
   the caller who skips the import and writes the SQL by hand.

Both prove they found the legitimate occurrences before concluding anything
(#678): a moved directory or a renamed schema makes a scan find zero, and zero
findings and zero files scanned look identical from the outside.

Broken on purpose to see them go red, in this order:
  - `app/domains/payment/service.py` importing `app.domains.reporting.api`
    → level 1 names payment and prints the rule;
  - the same file querying `FROM reporting.f_payments`
    → level 2 names the file;
  - `EXPECTED_SQL_SITES` raised to a file count nothing reaches
    → the proof-of-coverage assertion fires instead of the gate silently passing.
"""
import re

from tests._bestanden import bestanden

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MIGRATIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Who may consume the reporting domain. Not a list that grows with each new need:
# a new entry means a new process reading a read model, which is the thing this
# gate exists to catch. Add one only with the reasoning written down.
ALLOWED_IMPORTERS = {
    "app.main",              # route registration
    "app.ui.system_ui",      # the dashboard tiles
    # The assistant's capability pack (CR-07 §4.1): reporting supplies the tools,
    # the chatbot kernel runs them. Reporting imports chatbot, never the reverse.
    "app.domains.chatbot.assistant",
}

# The rule, in the failure message — refusing without explaining sends the reader
# looking for a workaround instead of the right door.
_RULE = """
Reporting is a terminus (CR-07 §6.6): its views are read models, shaped by the
question they answer and free to change per release. A process that reads them
couples itself to that shape, reads derived data where the source exists, and
reverses the dependency.

What to do instead:
  - need a number in a screen or a process? read the owning domain's facade
    (membership.api, payment.api, ...) — that is the source;
  - need a business rule the universe lacks? the universe grows an object; the
    tool list and the consumer list do not;
  - genuinely a reporting consumer (a new panel, a new assistant capability)?
    add it to ALLOWED_IMPORTERS with the reason, in this file.
"""

_IMPORT = re.compile(r"^\s*(?:from|import)\s+(app\.domains\.reporting[\w.]*)", re.M)
# `reporting.` as a schema prefix: followed by a name or an f-string placeholder,
# and not preceded by a dot (which would make it the tail of `app.domains.`).
_SCHEMA = re.compile(r"(?<![.\w])reporting\.(?:[a-z_]+|\{)")

# The legitimate SQL sites, counted so the scan cannot go quietly green. The
# engine writes the FROM clauses, the service its own statements, the universe
# names views in its docstrings, and the migrations create the schema. If this
# number drops, either the scan broke or the star schema moved — both worth a
# red build.
EXPECTED_SQL_SITES = 20


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP.parent).with_suffix("").parts).removesuffix(
        ".__init__"
    )


def test_only_the_allowed_consumers_import_reporting():
    offenders = []
    for path in bestanden(
        APP.rglob("*.py"), wat="alle Python-modules onder app/", minstens=100
    ):
        module = _module_name(path)
        if module.startswith("app.domains.reporting"):
            continue  # the domain itself
        if _IMPORT.search(path.read_text(encoding="utf-8")):
            if module not in ALLOWED_IMPORTERS:
                offenders.append(module)

    assert not offenders, (
        "deze modules consumeren het reporting-domein zonder op de lijst te staan: "
        + ", ".join(sorted(offenders))
        + "\n"
        + _RULE
    )


def test_the_allowlist_names_only_modules_that_exist():
    """An allowlist entry that no longer imports reporting is dead weight.

    Left standing, it silently re-permits the day someone recreates that module —
    the same reason `LEGACY_ALLOWLIST` in `test_import_boundaries.py` may only
    shrink. `chatbot.assistant` is exempt while it is being built (CR-07 phase 1).
    """
    stale = []
    for module in ALLOWED_IMPORTERS:
        path = APP.parent / Path(*module.split(".")).with_suffix(".py")
        if module == "app.domains.chatbot.assistant" and not path.exists():
            continue
        assert path.exists(), f"allowlist noemt {module}, maar dat bestand bestaat niet"
        if not _IMPORT.search(path.read_text(encoding="utf-8")):
            stale.append(module)

    assert not stale, (
        "deze allowlist-regels importeren reporting niet (meer) — haal ze weg, "
        "anders geven ze stilzwijgend toestemming aan wie de module ooit opnieuw "
        f"aanmaakt: {', '.join(sorted(stale))}"
    )


def test_the_reporting_schema_is_addressed_only_from_its_own_domain():
    """Level 2: the caller who skips the import and writes `FROM reporting.…`."""
    sources = bestanden(
        APP.rglob("*.py"),
        APP.rglob("*.html"),
        MIGRATIONS.glob("*.py"),
        wat="Python- en templatebronnen onder app/ plus de migraties",
        minstens=200,
    )

    sites, offenders = [], []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        if not _SCHEMA.search(text):
            continue
        sites.append(path)
        in_domain = "domains/reporting" in path.as_posix()
        is_migration = path.parent == MIGRATIONS
        if not (in_domain or is_migration):
            offenders.append(path.relative_to(APP.parent.parent).as_posix())

    assert len(sites) >= EXPECTED_SQL_SITES, (
        f"de scan vond {len(sites)} bestanden die het schema `reporting.` "
        f"aanspreken, verwacht minstens {EXPECTED_SQL_SITES}. Nul treffers en "
        "nergens gekeken zien er hetzelfde uit — controleer het patroon of de "
        "paden voor je concludeert dat alles in orde is (#678)."
    )
    assert not offenders, (
        "deze bestanden spreken het schema `reporting.` rechtstreeks aan, buiten "
        "het reporting-domein en zijn migraties: " + ", ".join(sorted(offenders))
        + "\n" + _RULE
    )

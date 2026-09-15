from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.domains.registry import load_all_models

# Laad alle domein-/kernel-modellen via de canonieke loader zodat Base.metadata
# compleet is voor autogenerate (#449). Dezelfde bron als app.main (dat via
# app.models naar deze loader shimt), zodat de metadata niet uit elkaar drijft.
load_all_models()

config = context.config

if config.config_file_name is not None:
    # #777: `disable_existing_loggers=False`. Zonder die parameter zet `fileConfig`
    # elke logger die op dat moment al bestaat op `disabled = True` — dat is haar
    # standaardgedrag, en alembic heeft er geen enkele reden voor: ze wil enkel haar
    # eigen configuratie inlezen.
    #
    # Op de server viel het niet op, want `startup.sh` draait `alembic upgrade head`
    # als een APART proces vóór uvicorn; die loggers zijn dus niemands loggers. In de
    # tests draait conftest alembic in HETZELFDE proces, en daarna zag `caplog` niets
    # meer van `app.*`. Het gevolg is niet dat er logregels wegvallen op productie,
    # maar dat elke assertie op een logregel niets meet en tóch groen staat —
    # dezelfde vorm als de veertien gates uit #678.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True,
                      process_revision_directives=_nieuwe_id)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          process_revision_directives=_nieuwe_id)
        with context.begin_transaction():
            context.run_migrations()


# ── De id van een nieuwe migratie (#951) ─────────────────────────────────────

def _volgende_volgnummer() -> int:
    """Het hoogste volgnummer in `versions/`, plus één.

    Puur voor de bestandsnaam: alembic sorteert op de keten, niet op het pad. Een
    mens wel — `ls` moet de migraties in de volgorde tonen waarin ze draaien.
    """
    import re
    from pathlib import Path

    map_ = Path(__file__).resolve().parent / "versions"
    nummers = [int(m.group(1)) for p in map_.glob("*.py")
               if (m := re.match(r"(\d+)_", p.name))]
    return (max(nummers) + 1) if nummers else 1


def _nieuwe_id(_context, _revision, directives) -> None:
    """Geef een nieuwe migratie een id die niet kan botsen (#951).

    Tot 15 september 2026 was de id het volgnummer (`revision = "124"`). Drie
    CLI's die parallel werken kiezen allemaal "het volgende nummer", dus ze kiezen
    hetzelfde — en dat gebeurde die dag ook echt, tussen #945 en #939. Geen van
    beide takken was stuk: de botsing bestaat alleen in de combinatie, en die
    bestaat pas bij de merge.

    Een tijdstempel tot op de seconde lost dat op. Twee hoofden kunnen nog steeds
    ontstaan — twee takken die op hetzelfde punt aftakken — maar de reparatie is
    dan één regel: waar hang ik onder? Geen hernoeming, geen verwijzingen nalopen.

    Het volgnummer blijft vooraan staan zodat de map leesbaar en sorteerbaar
    blijft. Dat het bij een botsing twee keer hetzelfde nummer kan dragen is
    onschadelijk: het is een etiket, en alembic leest het niet.
    """
    from datetime import datetime, timezone

    for directive in directives:
        if getattr(directive, "rev_id", None) is None:
            continue
        stempel = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H%M%S")
        directive.rev_id = f"{_volgende_volgnummer():03d}_{stempel}"


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

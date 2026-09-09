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
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Compat-shim (#449).

Historisch de model-aggregator die elk domein-model expliciet importeerde. Nu is
er één canonieke bron: dit delegeert naar
:func:`app.domains.registry.load_all_models`. ``app.main`` doet
``from app.models import *`` puur voor de registratie-side-effect en blijft dus
ongewijzigd werken, terwijl ``alembic/env.py`` en de seeds dezelfde loader
rechtstreeks aanroepen — geen twee bronnen die uit elkaar kunnen drijven.
"""
from app.domains.registry import load_all_models

load_all_models()

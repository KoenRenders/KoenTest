"""The shared fixtures of `tests/conftest.py`, for this domain's tests (CR-13 R15).

The root fixtures live in `tests/conftest.py`; a `conftest.py` in `backend/` would
also load for `tests_e2e/`, whose run must never drop the test schemas.
"""

from tests.conftest import *  # noqa: F403 — the fixtures and helpers every test may use
from tests.conftest import _migrate_schema, _reset_rate_limiters  # noqa: F401 — autouse fixtures

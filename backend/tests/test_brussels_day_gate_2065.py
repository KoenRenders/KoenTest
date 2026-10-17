"""Refuses a day taken from the container's clock, and a moment column without its time zone · hard · since #2065.

The day of a moment is its Brussels day (`app.kernel.clock`, #974, #1976, #2065).
Two ways to lose that, each refused here:

- **`date.today()` in `app/`** outside test code: on the server it is the UTC day,
  so a rule about a day is two hours late in summer between midnight and 02:00.
  The day is `belgian_today()`, and the day of a stored moment is `belgian_day()`;
- **`date.today()` in a test** (#2091): a test that asks the container's clock for
  "today" expects the UTC day while the app answers with the Brussels day, so it
  went red between 22:00 and 24:00 UTC (nine tests on 16 October 2026). A test asks
  the clock the app asks: `belgian_today()`;
- **a `DateTime` column in a `models.py` without `timezone=True`**: such a column
  hands a moment back naive, and a naive moment has no day to speak of.

The gate counts before it judges: it must find the `DateTime` columns and the files
it reads, or its pattern broke and it would pass anything.

Broken on purpose (16 October 2026, each by adding a line, each put back):
- a line holding `date.today()` in `app/domains/media/service.py` → the first test
  failed naming that line;
- a line `DateTime()` in `app/domains/media/models.py` → the second failed naming
  that line;
- (17 October 2026, #2091) a line `date.today()` added to `tests/test_health_version.py`
  → the third failed naming that line.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests._bestanden import bestanden, is_app_test

APP = Path(__file__).resolve().parents[1] / "app"

_TODAY = re.compile(r"\b_?date\.today\(\)|\bdatetime\.today\(\)")
#: The module that names the rule in its own docstring.
_CLOCK = APP / "kernel" / "clock.py"


def _python_files():
    return [p for p in sorted(APP.rglob("*.py")) if not is_app_test(p)]


def test_nothing_in_the_app_takes_the_day_from_the_container():
    files = _python_files()
    assert len(files) > 100, "the gate found too few files to be reading the app"
    found = []
    for path in files:
        if path == _CLOCK:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if _TODAY.search(line):
                found.append(f"{path.relative_to(APP.parent)}:{number}: {line.strip()}")
    assert not found, "use belgian_today() / belgian_day():\n" + "\n".join(found)


def _test_files():
    tests = Path(__file__).resolve().parent
    return bestanden(
        tests.glob("**/*.py"),
        (tests.parent / "tests_e2e").glob("**/*.py"),
        APP.glob("domains/*/tests/**/*.py"),
        wat="the test modules of the backend",
        minstens=500,
        met_tests=True,
    )


def _container_day_calls(path: Path) -> list[int]:
    """Lines that call `date.today()` or `datetime.today()` — calls, so a docstring or
    a comment that names the rule is not one."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "today"
        and isinstance(node.func.value, (ast.Name, ast.Attribute))
        and getattr(node.func.value, "id", getattr(node.func.value, "attr", ""))
        in {"date", "datetime"}
    ]


def test_no_test_takes_the_day_from_the_container():
    found = [
        f"{path.relative_to(APP.parent)}:{number}"
        for path in _test_files()
        for number in _container_day_calls(path)
    ]
    assert not found, "ask belgian_today() (app.kernel.clock), as the app does:\n" + "\n".join(
        found
    )


def _datetime_columns():
    for path in sorted(APP.rglob("models.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "DateTime"
            ):
                yield path, node


def test_every_datetime_column_carries_its_time_zone():
    columns = list(_datetime_columns())
    assert len(columns) > 20, "the gate found too few DateTime columns to be reading the models"
    bare = [
        f"{path.relative_to(APP.parent)}:{call.lineno}"
        for path, call in columns
        if not any(
            kw.arg == "timezone" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in call.keywords
        )
    ]
    assert not bare, "DateTime(timezone=True) in:\n" + "\n".join(bare)

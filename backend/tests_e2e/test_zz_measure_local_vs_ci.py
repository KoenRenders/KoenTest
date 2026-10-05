"""MEASUREMENT ONLY — never merged (#1605).

Prints the measurements of every screen of `measures.SCREENS`, taken against
the ordinary e2e server at the END of the e2e run (the name sorts last), so
that the same test run locally (Debian 13) and on the CI runner (Ubuntu) can be
laid side by side: does a position differ by more than the 1 px tolerance
between the two machines?
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e import measures  # noqa: E402
from tests_e2e.schermen import BASE  # noqa: E402


def test_print_the_measurements(capsys):
    import platform
    import time

    started = time.monotonic()
    first = measures.measure_all(BASE)
    seconds = time.monotonic() - started
    second = measures.measure_all(BASE)
    drift = {
        f"{key}@{width}": measures.differences(first[key][width], second[key][width], tolerance=0)
        for key in first
        for width in first[key]
        if measures.differences(first[key][width], second[key][width], tolerance=0)
    }
    with capsys.disabled():
        print("\nMEASURE-MACHINE", platform.platform(), f"{seconds:.1f}s for one pass")
        print("MEASURE-DRIFT", json.dumps(drift, sort_keys=True))
        print("MEASURE-JSON", json.dumps(first, sort_keys=True))

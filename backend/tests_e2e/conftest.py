"""The browser tests stand in a folder per domain (CR-29 phase 2, #1745).

`forms/`, `media/`, `pages/`, `meetings/`, `members/`, `activities/`,
`assistant/`, `reports/` and `shell/` each hold the tests of one area; the two
flows that walk several domains and the two measurement files stay beside this
file. A folder runs alone — `pytest tests_e2e/forms` — and the CI job runs the
folders in parts.

Every test imports its helpers as `tests_e2e.schermen`, and some import a
helper from another test file by its dotted path. Both need `backend/` on the
import path, whichever folder pytest was pointed at; this file puts it there
once. (Each test file still inserts a path of its own, written when all of them
stood one level higher; from a folder it now names `tests_e2e/` itself, which
harms nothing and helps nothing.)

The tests share one seeded database and one backend, and no order is kept
between files: a test makes or measures its own subject and does not lean on
what another file left behind or has not yet done.
"""

import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

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

**A visitor of its own (#1787).** The backend counts some things per visitor
address: five sends of the sign-in forms a minute (`login_limiter`), the other
limiters, the public chat's budget. Every browser test reached it from one
address, so a test that signs in through the form was refused whenever the
tests before it had used the minute up — which depends on how fast they ran.
`own_visitor` below gives every test an address of its own, for every page and
context it opens; no test asks for it and none can forget it.
"""

import itertools
import sys
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).resolve().parents[1])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

#: The three blocks reserved for documentation (RFC 5737): 762 addresses nobody has.
_BLOCKS = ("192.0.2", "198.51.100", "203.0.113")
_numbers = itertools.count()


def visitor_address(number: int) -> str:
    """The `number`-th address of the documentation blocks, around and around."""
    return f"{_BLOCKS[(number // 254) % len(_BLOCKS)]}.{number % 254 + 1}"


@pytest.fixture(autouse=True)
def own_visitor(monkeypatch) -> str:
    """This test's own visitor address, on every page and context it opens.

    Without a proxy in front, the backend reads the visitor's address from
    `X-Forwarded-For` (`app.limiter._client_ip`), as it reads the one the proxy
    sets in production. The header is added where a browser opens a page or a
    context — `Browser.new_page` and `Browser.new_context` — unless the test set
    one itself, so a test that plays two visitors still can.

    A page opened by a fixture of a wider scope (a module's signed-in page) is
    opened before this runs and keeps the default address; such pages carry a
    session and send no sign-in form.
    """
    from playwright.sync_api import Browser

    address = visitor_address(next(_numbers))
    for name in ("new_page", "new_context"):
        original = getattr(Browser, name)

        def opened(self, *args, _original=original, **kwargs):
            headers = dict(kwargs.get("extra_http_headers") or {})
            headers.setdefault("X-Forwarded-For", address)
            kwargs["extra_http_headers"] = headers
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(Browser, name, opened)
    return address

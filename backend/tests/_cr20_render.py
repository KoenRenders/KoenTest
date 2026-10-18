"""CR-20 test 11 — what each site renders, read in a process of its own.

`python -m tests._cr20_render <database url> <file>` writes, as JSON, per tenant the
parts migration 313 could change: the site header and footer of its sign-in page,
the cards of the two sites placeholders, and the meeting circle. It runs in a
fresh process with `DATABASE_URL` pointing at the database it reads, so every
session, cache and lookup of the app sees that database and nothing of the
suite's.

It touches the app only through HTTP and the session cookie, which the code
before migration 313 and the code after it both answer the same way: the same
file renders the snapshot of the code before (`cr20_rendered_before.json`) and
what the test reads after. How the snapshot was made stands in
`tests/test_tenants_apart_migration_cr20.py`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

USER_EMAIL = "cr20@example.org"
#: The pages `_write_the_cases` puts on Raak Millegem.
PAGES = ("sites-cr20", "alle-sites-cr20")
PLATFORM_HOST = "platform.cr20.test"


def _element(html: str, opening: str) -> str:
    """The element that starts with the first match of `opening`, up to its own
    closing tag (nested tags of the same name counted), or "" when absent."""
    start = re.search(opening, html)
    if start is None:
        return ""
    tag = re.match(r"<(\w+)", start.group(0)).group(1)
    depth = 0
    for match in re.finditer(rf"<(/?){tag}\b[^>]*>", html[start.start() :]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return html[start.start() : start.start() + match.end()]
    return ""


def _normalised(html: str) -> str:
    """Without what differs per request or per day: the CSRF token, a nonce,
    the year of the footer and today's date (the circle's start-date field)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    html = re.sub(r'(name="csrf_token" value=")[^"]*', r"\1…", html)
    html = re.sub(r'(nonce=")[^"]*', r"\1…", html)
    html = re.sub(r"© \d{4}", "© <year>", html)
    # The example address in an e-mail field is the app's copy; the gate on
    # test e-mail domains reads the snapshot.
    html = re.sub(r'placeholder="[^"@]*@[^"]*"', 'placeholder="<example address>"', html)
    now = datetime.now(timezone.utc)
    for today in {now.date(), now.astimezone(ZoneInfo("Europe/Brussels")).date()}:
        html = html.replace(today.isoformat(), "<today>")
    return html


def _tenant_codes(conn) -> list[tuple[str, bool]]:
    from sqlalchemy import text

    has_tenants = conn.execute(text("SELECT to_regclass('mdm.tenants')")).scalar()
    sql = (
        "SELECT code, kind = 'PLATFORM' FROM mdm.tenants WHERE is_active ORDER BY id"
        if has_tenants
        else "SELECT code, org_type = 'PLATFORM' FROM mdm.organizations "
        "WHERE org_type IN ('UNIT', 'PLATFORM') AND is_active AND deleted_at IS NULL ORDER BY id"
    )
    return [(row[0], row[1]) for row in conn.execute(text(sql))]


def render(url: str) -> dict[str, dict[str, str]]:
    os.environ["DATABASE_URL"] = url
    # The platform has no path prefix: it answers on a platform host.
    os.environ["PLATFORM_HOSTS"] = PLATFORM_HOST
    from fastapi.testclient import TestClient

    from app.database import engine
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.main import app

    with engine.connect() as conn:
        codes = _tenant_codes(conn)
    rendered: dict[str, dict[str, str]] = {}
    # Without the lifespan: no jobs and no clean-up run against this database.
    client = TestClient(app)
    for code, is_platform in codes:
        client.cookies.clear()
        client.headers["host"] = PLATFORM_HOST if is_platform else "testserver"
        prefix = "" if is_platform else f"/{code}"
        # The sign-in page: every site has it in the site shell, also a
        # site without a home page of its own.
        shell = client.get(f"{prefix}/aanmelden").text
        parts = {
            "header": _element(shell, r'<header class="site-header"'),
            "footer": _element(shell, r'<footer class="site-footer"'),
        }
        for slug in PAGES:
            page = client.get(f"{prefix}/{slug}")
            parts[slug] = (
                _element(page.text, r"<main\b")
                if page.status_code == 200
                else str(page.status_code)
            )
        client.cookies.set(SESSION_COOKIE, make_session_value(USER_EMAIL))
        circle = client.get(f"{prefix}/admin/vergaderingen/kring", follow_redirects=False)
        parts["circle"] = (
            _element(circle.text, r'<div id="vg-kring"')
            if circle.status_code == 200
            else str(circle.status_code)
        )
        rendered[code] = {key: _normalised(value) for key, value in parts.items()}
    return rendered


if __name__ == "__main__":
    # To a file: the app logs to stdout.
    Path(sys.argv[2]).write_text(
        json.dumps(render(sys.argv[1]), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    )

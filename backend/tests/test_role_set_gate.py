"""Gate (#1513): the back-office role set is spelled out in one place.

"Who may enter the back office" is `_GENERAL_ADMIN_ROLES` in
`app/domains/auth/session.py`, asked through `auth.admits_admin_ui` (#1499).
Four places kept their own copy of `{"ADMIN", "OPERATOR"}` until #1513, and one
of them (the JSON API's `is_admin`) had drifted to ADMIN alone. This gate fails
when any module writes that set as a literal again — in either order — outside
its one definition. Comment lines are not code and are skipped.

Proven by violation: `ROLES = {"OPERATOR", "ADMIN"}` added to
`app/domains/cms/service.py` turned this red, naming the file and line; the
line removed, green again.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
HOME = APP / "domains" / "auth" / "session.py"
LITERAL = re.compile(r"""\{\s*["'](ADMIN|OPERATOR)["']\s*,\s*["'](ADMIN|OPERATOR)["']\s*\}""")


def test_the_back_office_role_set_has_one_definition():
    scanned = 0
    copies = []
    for path in APP.rglob("*.py"):
        if "tests" in path.parts:
            continue
        scanned += 1
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            match = LITERAL.search(line)
            if match and match.group(1) != match.group(2):
                copies.append(f"{path.relative_to(APP)}:{number}")
    assert scanned > 100, f"the gate read only {scanned} files"
    home = str(HOME.relative_to(APP))
    assert any(c.startswith(home + ":") for c in copies), "the definition itself is not found"
    others = [c for c in copies if not c.startswith(home + ":")]
    assert not others, (
        f"the back-office role set spelled out again — use auth.admits_admin_ui: {others}"
    )

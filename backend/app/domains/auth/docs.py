"""`docs/rollen-en-rechten.md`, rendered from the bundles and the routes (CR-24 F4, T7).

Who may do what was a document written by hand beside the gates, and it drifted:
by October 2026 it named gates that no longer existed and missed whole screens.
It is rendered now, never written, from the two things that decide it:

- **the bundles** — the rows of `auth.role_rights`, with the labels of the role
  and the right code lists: which role holds which right;
- **the running routes** — the right the gate of each route asks.

So the document cannot say something the application does not do, and a test
holds it against both (`test_roles_document_matches_the_bundles`).

    python -m app.domains.auth.docs

writes it; that needs a migrated database, because the bundles are data.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.domains.auth.models import Right, RoleRight
from app.kernel.codes import code_label, code_labels

DOC_PATH = Path(__file__).resolve().parents[4] / "docs" / "rollen-en-rechten.md"

_HEADER = """# Roles and rights

> **Rendered, never written.** This document comes from `app/domains/auth/docs.py`:
> the bundles in `auth.role_rights` and the right each route's gate asks. Change a
> bundle (a migration) or a gate, then run `python -m app.domains.auth.docs`; a
> test fails while the two differ. Design: CR-24, *Rights, part 1*.

## How it works

- **A gate asks a right, never a role.** A route names one right in its
  dependencies (`require_right`); whoever holds it in this workspace gets in.
- **A right is about one kind of object**, and there are two per object: viewing
  (`<object>.view`), asked by a route that only reads (GET), and changing
  (`<object>.manage`, for master data `<object>.masterdata`), asked by every
  other method.
- **A role is a bundle of rights**, kept as rows and the same in every workspace.
  A user may hold several roles; he holds a right when one of them bundles it.
- **Roles are given per workspace** (`auth.user_roles.tenant_id`): a role in
  workspace A is no role in workspace B. One role is platform-wide — the row
  without a workspace — and it is granted inside the platform workspace only.
- **A platform screen asks its right and the platform workspace**
  (`require_platform_right`): in a tenant's workspace it does not exist, also
  for who holds the right.
- **Everyone with a back-office role enters the back office by the workbench**,
  and sees in its menu the screens whose right he holds — nothing else.
- **A visitor and a member hold no role and no right.** What a member may do with
  his own household is decided by ownership, not by a right.
"""


def _rights_per_role(db: Session) -> dict[str, set[str]]:
    held: dict[str, set[str]] = {}
    for role, right in db.query(RoleRight.role_code, RoleRight.right_code).all():
        held.setdefault(role.value, set()).add(right.value)
    return held


def _routes_per_right() -> dict[str, list[str]]:
    """Right → the routes whose gate asks it, as "METHOD /path", from the running app."""
    from app.main import app  # lazy: `app.main` imports every domain

    found: dict[str, set[str]] = {}

    def walk(items, prefix: str = "") -> None:
        for item in items:
            context = getattr(item, "include_context", None)
            if context is not None:
                walk(item.original_router.routes, prefix + (context.prefix or ""))
            elif hasattr(item, "dependant"):
                for dependency in item.dependant.dependencies:
                    right = getattr(dependency.call, "right", None)
                    if right is not None:
                        for method in sorted((item.methods or set()) - {"HEAD", "OPTIONS"}):
                            found.setdefault(right.value, set()).add(
                                f"{method} {prefix + item.path}"
                            )

    walk(app.routes)
    return {
        right: sorted(routes, key=lambda r: r.split(" ", 1)[::-1])
        for right, routes in found.items()
    }


def render(db: Session) -> str:
    """The whole document as it should be on disk."""
    # The routes first: reading them loads the application, and with it the code
    # lists the labels below come from.
    asked = _routes_per_right()
    roles = code_labels("role", "nl", db)
    held = _rights_per_role(db)
    lines = [_HEADER, "## The roles", ""]
    lines += ["| Role | On screen | Rights it bundles |", "|---|---|---|"]
    for code, label in roles:
        lines.append(f"| `{code}` | {label} | {len(held.get(code, ()))} |")
    lines += [
        "",
        "A role that bundles nothing opens nothing of the back office.",
        "",
        "## Which role holds which right",
        "",
        "| Right | On screen | " + " | ".join(f"`{code}`" for code, _label in roles) + " |",
        "|---|---|" + "---|" * len(roles),
    ]
    for right in Right:
        ticks = " | ".join("✓" if right.value in held.get(code, ()) else "" for code, _l in roles)
        label = code_label("right", right.value, "nl", db)
        lines.append(f"| `{right.value}` | {label} | {ticks} |")
    lines += ["", "## What each right opens", ""]
    lines.append(
        "Every route whose gate asks the right. A right without a route here opens "
        "nothing yet: its screens come with a later change."
    )
    for right in Right:
        routes = asked.get(right.value, [])
        lines += ["", f"### `{right.value}` — {len(routes)} routes", ""]
        lines += [f"- `{route}`" for route in routes] or ["- none"]
    return "\n".join(lines).rstrip() + "\n"


def write() -> Path:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        DOC_PATH.write_text(render(db), encoding="utf-8")
    finally:
        db.close()
    return DOC_PATH


if __name__ == "__main__":  # pragma: no cover - a developer command
    print(f"written: {write()}")

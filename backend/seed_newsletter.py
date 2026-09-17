"""Example newsletter subscribers for the test environments (CR-05 §3.6, #984).

Koen, 16 September 2026: the real list of about 800 addresses "mag enkel in PROD
geladen worden. Tot dan voorbeeldadressen." It is loaded on PROD through the
import screen, by a person. The test environments get these instead, so the
subscriber screen, the audiences and a send can be tried without real people.

**Never on PROD.** Not "only when empty": an empty PROD table is exactly the
moment before the real import, and example addresses there would be mailed.
Only `@example.org` addresses, which no mail server delivers.
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone

EXAMPLE_ENVIRONMENTS = {"dev", "hdev", "uat", "e2e", "test"}

EXAMPLES = [
    ("an.voorbeeld@example.org", "An", "confirmed", "import"),
    ("bert.voorbeeld@example.org", None, "confirmed", "import"),
    ("info@bakkerij.example.org", None, "confirmed", "import"),
    ("nora.voorbeeld@example.org", "Nora", "confirmed", "public_form"),
    ("wacht.voorbeeld@example.org", None, "pending", "public_form"),
    ("weg.voorbeeld@example.org", None, "unsubscribed", "import"),
]


def seed(db, app_env: str) -> int:
    """Add the examples when allowed and the table is empty. Returns how many."""
    from app.domains.newsletter.api import Subscriber

    if (app_env or "").lower() not in EXAMPLE_ENVIRONMENTS:
        return 0
    if db.query(Subscriber).count():
        return 0
    now = datetime.now(timezone.utc)
    for email, first_name, status, source in EXAMPLES:
        db.add(Subscriber(
            email=email, first_name=first_name, status=status, source=source,
            imported_at=now if source == "import" else None,
            consented_at=now if source == "public_form" else None,
            confirmed_at=now if status == "confirmed" else None,
            unsubscribed_at=now if status == "unsubscribed" else None,
            unsubscribe_token=secrets.token_urlsafe(32)))
    db.commit()
    return len(EXAMPLES)


if __name__ == "__main__":
    from app.config import settings
    from app.database import SessionLocal
    from app.domains.registry import load_all_models

    load_all_models()
    session = SessionLocal()
    try:
        added = seed(session, settings.app_env)
    finally:
        session.close()
    print(f"  {added} voorbeeldabonnees toegevoegd (omgeving {settings.app_env}).")
    sys.exit(0)

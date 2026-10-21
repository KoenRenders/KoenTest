"""freeze the sent letters at the head of the chain (#2195)

A letter that has started to send keeps the body it went with in
`newsletter.newsletters.sent_body_html` (CR-17 phase 7b, #2023). Migration 212 added the
column and used to fill it for the letters sent before; it could not do that on PROD:
rendering a letter asks the clock for a day and the settings of its tenant, and a migration
in the middle of the chain runs the app's code of the head on a schema that is still
older (no `mdm.tenants` before 313). So the freeze is the last step of the chain, where
code and schema agree, and each letter is rendered in its own tenant: the tenant is set
before the render and reset after it, also on an error. A letter without a tenant still
fails; there is no fallback day. The body is built as the send builds it
(`render_body`), so a letter frozen here is the closest to what went out.

Idempotent: a letter that has its body is left alone (HDEV and UAT filled theirs in 212),
and the CHECK that requires the body of a sent letter is dropped and set again.

Downgrade drops the CHECK only; the frozen bodies stay, they are data.
"""

import logging

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "320_2026_10_21_143627"
down_revision = "319_2026_10_21_085617"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

CHECK = "ck_newsletter_sent_has_body"


def freeze_sent_letters(bind) -> int:
    """Fill `sent_body_html` for every letter that has started to send and has none; returns
    how many. Imports the app's code at the head: this runs last."""
    from sqlalchemy.orm import Session

    from app.domains.newsletter.models import LetterStatus, Newsletter
    from app.domains.newsletter.service import render_body
    from app.kernel.tenancy import current_tenant_id

    with Session(bind=bind) as session:
        letters = (
            session.query(Newsletter)
            .filter(Newsletter.status != LetterStatus.DRAFT, Newsletter.sent_body_html.is_(None))
            .order_by(Newsletter.id)
            .all()
        )
        for letter in letters:
            token = current_tenant_id.set(letter.tenant_id)
            try:
                letter.sent_body_html = render_body(
                    session, letter, base_url=(letter.link_base or "").rstrip("/")
                )
            finally:
                current_tenant_id.reset(token)
        session.flush()
        return len(letters)


def upgrade() -> None:
    bind = op.get_bind()
    log.info("#2195: %s sent letters frozen as they build now", freeze_sent_letters(bind))
    op.execute(f"ALTER TABLE newsletter.newsletters DROP CONSTRAINT IF EXISTS {CHECK}")
    op.execute(
        f"ALTER TABLE newsletter.newsletters ADD CONSTRAINT {CHECK} "
        "CHECK (status = 'draft' OR sent_body_html IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE newsletter.newsletters DROP CONSTRAINT IF EXISTS {CHECK}")

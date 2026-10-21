"""The text of a letter is a document of the page editor (CR-17 phase 7b, #2023).

The body of a letter was Trix HTML in `newsletter.newsletters.body_html`, with
three markers in its text (`[[activiteit:…]]`, `[[kalender]]`, `[[afsluiting]]`). It
now is a document of the editor's `letter` set in `body_document`; the mail is built
from it when the letter is sent. Koen, 15 October 2026: if the new editor leaves the
HTML column without a writer, convert EVERYTHING — the sent letters too (two in
PROD, no drafts) — and drop the column in the same change. Measured: every reader of
the stored text (the preview line, the placeholder check, the copy, the archive, the
test mail, the send and Raakje) goes through the one place that renders the
document, or through the marker text derived from it (`letter_markup.py`), so no
reader needs the old column.

The conversion is `markup_to_document`: the lenient one of a page's draft (formatting
may soften, no word is lost) with the three markers become blocks. Measured on PROD and UAT on 16 October 2026: no picture in any
stored letter (0 `<img` and 0 `<figure`), so the conversion has no figure to map.

The archive of a sent letter shows the letter as it went (Koen, 16 October 2026: "a"): a new column
`sent_body_html` holds the rendered body, written once when the send starts. For the
letters sent before it, this migration fills it with the body rendered at migration
time — the closest to what went out that still exists.

This migration does not read the models of today. Both migrations of a deploy run
with the models of the deploy's last revision, so a model that knows a column a
later migration adds would fail here, halfway through the upgrade and after the HTML
column is dropped. Chosen: the facts of an activity and the closing's name are read by
plain SQL on the columns of this revision, and the pure parts of the app render them
(the page renderer and the letter's block and line formats). The cost, said plainly:
a letter frozen here has no registration link, picture or album link in its activity
blocks, and an activity that is no longer published or has no date leaves its block
out; the mail that went is in the delivery log. What stays outside the plain SQL is
the page renderer's own read of the membership settings, which only a configuration
code in the text uses. The migration imports the app's pure render functions and the `ActivityFacts` constructor
as they are today: a later change to them breaks the migration's test, not a deploy,
because a deploy of this revision runs once and the test runs on every change. A CHECK then holds the invariant at the database: a letter
that is not a draft has its frozen body.

Downgrade restores the text with markers from the documents and drops the column;
the exact Trix markup is not restored.

Amended after v2.17.0 (#2195), the named exception to "a merged migration is never
modified": this migration never completed on PROD (its transaction rolled back whole to
202), and HDEV and UAT are past it. Rendering prose asks the clock for today's day, and
since #2156 the clock needs a tenant, which a migration does not have: PROD's deploy died
here with `NoTenantContext`. Each letter is now rendered in its own tenant
(`newsletters.tenant_id`), set before the render and reset after it, also on an error. A
letter without a tenant still fails; there is no fallback day. Koen, 21 October 2026, to
"Mag migratie 212 aangepast worden, omdat ze op PROD nooit is afgelopen?": "ja, 212 mag
aangepast worden".
"""

import logging

import sqlalchemy as sa
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
revision = "212_2026_10_15_172727"
down_revision = "211_2026_10_16_021737"
branch_labels = None
depends_on = None


log = logging.getLogger("alembic.runtime.migration")


def _columns(bind) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'newsletter' AND table_name = 'newsletters'"
            )
        )
    }


def convert_letters(bind) -> int:
    """The upgrade, on a connection (so a test can run it on a throwaway state):
    add the document column, convert every letter, drop the HTML column.
    Returns how many letters were converted. Idempotent."""
    import json

    from app.domains.newsletter.letter_markup import markup_to_document

    columns = _columns(bind)
    if "body_document" not in columns:
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters ADD COLUMN body_document JSONB"))
    converted = 0
    if "body_html" in columns:
        rows = bind.execute(sa.text("SELECT id, body_html FROM newsletter.newsletters")).fetchall()
        for letter_id, body in rows:
            bind.execute(
                sa.text(
                    "UPDATE newsletter.newsletters SET body_document = CAST(:d AS JSONB) "
                    "WHERE id = :i"
                ),
                {"d": json.dumps(markup_to_document(body)), "i": letter_id},
            )
        converted = len(rows)
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN body_html"))
    bind.execute(
        sa.text(
            "UPDATE newsletter.newsletters SET body_document = CAST(:d AS JSONB) "
            "WHERE body_document IS NULL"
        ),
        {"d": json.dumps({"type": "doc", "content": []})},
    )
    bind.execute(
        sa.text("ALTER TABLE newsletter.newsletters ALTER COLUMN body_document SET NOT NULL")
    )
    return converted


def _activity_facts(bind, ids, tenant_id, base_url, today):
    """The facts a block states, by plain SQL on the columns that stood at this revision
    — the model of today is not read (see the docstring). No registration link, no
    picture, no album: the letters this fills went out before this migration, and what
    those carried is in the mail that went."""
    from app.domains.newsletter.service import ActivityFacts

    facts = {}
    for row in bind.execute(
        sa.text(
            "SELECT id, name, slug, location, description, members_only "
            "FROM activities.activities WHERE id = ANY(:ids) AND tenant_id = :t "
            "AND deleted_at IS NULL AND status = 'published'"
        ),
        {"ids": list(ids), "t": tenant_id},
    ):
        days = bind.execute(
            sa.text(
                "SELECT start_date, end_date, start_time, end_time FROM activities.activity_dates "
                "WHERE activity_id = :a AND deleted_at IS NULL ORDER BY start_date, start_time"
            ),
            {"a": row.id},
        ).fetchall()
        if not days:
            continue
        end = max((d.end_date or d.start_date) for d in days)
        facts[row.id] = ActivityFacts(
            id=row.id,
            name=row.name,
            start=days[0].start_date,
            end=end,
            start_time=days[0].start_time,
            end_time=days[0].end_time,
            location=row.location or "",
            url=f"{base_url}/activiteiten/{row.slug or row.id}",
            photos_url=None,
            is_full=False,
            prices=(),
            is_past=end < today,
            members_only=bool(row.members_only),
            days=tuple((d.start_date, d.end_date or d.start_date) for d in days),
            description=(row.description or "").strip(),
        )
    return facts


def _closing(bind, tenant_id):
    import html

    row = bind.execute(
        sa.text("SELECT site_name, name FROM mdm.organizations WHERE id = :t"), {"t": tenant_id}
    ).first()
    name = ((row.site_name or "").strip() or row.name) if row else "Raak Millegem"
    esc = html.escape
    return f"<div>{esc('Tot binnenkort!')}<br>{esc('Het bestuur van ' + name)}</div>"


def freeze_sent_letters(bind) -> int:
    """Add `sent_body_html`, fill it, for every letter that has started to send, with the
    body built now, and make the column required for such a letter. Returns how many
    were filled. Idempotent."""
    from datetime import date

    from app.domains.cms.render import render_document
    from app.domains.newsletter.service import activity_block_html, calendar_list_html
    from app.kernel.tenancy import current_tenant_id

    if "sent_body_html" not in _columns(bind):
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters ADD COLUMN sent_body_html TEXT"))
    rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, body_document, link_base, draft_activity_ids "
            "FROM newsletter.newsletters WHERE status <> 'draft' AND sent_body_html IS NULL "
            "ORDER BY id"
        )
    ).fetchall()
    today = date.today()
    for letter_id, tenant_id, document, link_base, choices in rows:
        base = (link_base or "").rstrip("/")
        # The calendar's activities: the group of a letter that stores three, all of an
        # older letter that stores one list.
        calendar_ids = (
            (choices.get("calendar") or []) if isinstance(choices, dict) else list(choices or [])
        )

        def facts_of(ids):
            return _activity_facts(bind, {int(i) for i in ids}, tenant_id, base, today)

        def activity(node):
            fact = facts_of([node["attrs"]["activity_id"]]).get(node["attrs"]["activity_id"])
            return activity_block_html(fact) if fact else ""

        def calendar(node):
            facts = facts_of(calendar_ids)
            return calendar_list_html(sorted(facts.values(), key=lambda f: (f.start, f.id)))

        token = current_tenant_id.set(tenant_id)
        try:
            body = render_document(
                document,
                None,
                blocks={
                    "activity": activity,
                    "calendar": calendar,
                    "closing": lambda node: _closing(bind, tenant_id),
                    # The letters of this revision came from Trix HTML: no picture (measured)
                    # and no button in any of them.
                    "figure": lambda node: "",
                    "button": lambda node: "",
                },
            )
        finally:
            current_tenant_id.reset(token)
        bind.execute(
            sa.text("UPDATE newsletter.newsletters SET sent_body_html = :b WHERE id = :i"),
            {"b": body, "i": letter_id},
        )
    bind.execute(
        sa.text(
            "ALTER TABLE newsletter.newsletters DROP CONSTRAINT IF EXISTS ck_newsletter_sent_has_body"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE newsletter.newsletters ADD CONSTRAINT ck_newsletter_sent_has_body "
            "CHECK (status = 'draft' OR sent_body_html IS NOT NULL)"
        )
    )
    return len(rows)


def upgrade() -> None:
    bind = op.get_bind()
    log.info("#2023: %s letters converted to documents", convert_letters(bind))
    log.info("#2023: %s sent letters frozen as they build now", freeze_sent_letters(bind))


def downgrade() -> None:
    from app.domains.newsletter.letter_markup import document_to_markup

    bind = op.get_bind()
    columns = _columns(bind)
    if "body_html" not in columns:
        bind.execute(
            sa.text(
                "ALTER TABLE newsletter.newsletters ADD COLUMN body_html TEXT NOT NULL DEFAULT ''"
            )
        )
    if "body_document" in columns:
        rows = bind.execute(
            sa.text("SELECT id, body_document FROM newsletter.newsletters")
        ).fetchall()
        for letter_id, document in rows:
            bind.execute(
                sa.text("UPDATE newsletter.newsletters SET body_html = :b WHERE id = :i"),
                {"b": document_to_markup(document), "i": letter_id},
            )
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN body_document"))
    if "sent_body_html" in columns:
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN sent_body_html"))

"""Fase 5c (#406): demo-seed voor de voorbeeldafdeling (tenant 3) — CMS-intro,
twee fictieve voorbeeldactiviteiten en een demo-formulier. Plus: cms-slug
uniek PER TENANT (i.p.v. globaal), zodat elke tenant een eigen 'home-intro'
kan hebben.

Revision ID: 088
Revises: 087
"""
from alembic import op
import sqlalchemy as sa

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None

DEMO = 3


def upgrade() -> None:
    conn = op.get_bind()

    # 1. cms-slug uniek per tenant.
    op.execute("DROP INDEX IF EXISTS cms.ix_cms_pages_slug")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_cms_pages_tenant_slug "
               "ON cms.cms_pages (tenant_id, slug)")

    # 2. CMS-intro voor de demo (idempotent op tenant+slug).
    bestaat = conn.execute(sa.text(
        "SELECT 1 FROM cms.cms_pages WHERE tenant_id = :t AND slug = 'home-intro'"),
        {"t": DEMO}).scalar()
    if not bestaat:
        conn.execute(sa.text(
            "INSERT INTO cms.cms_pages (title, slug, content, is_published, "
            "show_in_nav, sort_order, created_at, updated_at, tenant_id) VALUES "
            "('Welkom', 'home-intro', :c, TRUE, FALSE, 0, now(), now(), :t)"),
            {"t": DEMO, "c": (
                "<p><strong>Welkom bij Raak Voorbeeldafdeling</strong> — dit is de "
                "demo-omgeving van het Raak Digital Platform. Alles wat je hier ziet "
                "is fictief: schrijf gerust in, betalingen lopen in Mollie-testmodus "
                "en e-mails worden enkel gelogd, nooit verstuurd.</p>")})

    # 3. Twee voorbeeldactiviteiten met een datum in de toekomst.
    demo_activiteiten = [
        ("Voorbeeldquiz", "Parochiezaal (demo)", "TEAM", 30),
        ("Demowandeling", "Vertrek aan de kerk (demo)", "INDIVIDUAL", 60),
    ]
    for naam, locatie, form_type, dagen in demo_activiteiten:
        bestaat = conn.execute(sa.text(
            "SELECT id FROM activities.activities WHERE tenant_id = :t AND name = :n"),
            {"t": DEMO, "n": naam}).scalar()
        if bestaat:
            continue
        activity_id = conn.execute(sa.text(
            "INSERT INTO activities.activities (name, location, reg_form_type, "
            "members_only, is_cancelled, created_at, tenant_id) VALUES "
            "(:n, :l, :f, FALSE, FALSE, now(), :t) RETURNING id"),
            {"n": naam, "l": locatie, "f": form_type, "t": DEMO}).scalar()
        conn.execute(sa.text(
            "INSERT INTO activities.activity_dates (activity_id, start_date, tenant_id) "
            f"VALUES (:a, CURRENT_DATE + {dagen}, :t)"),
            {"a": activity_id, "t": DEMO})

    # 4. Demo-formulier (open, met één sectie en twee velden).
    bestaat = conn.execute(sa.text(
        "SELECT 1 FROM form.forms WHERE share_token = 'demo-formulier'")).scalar()
    if not bestaat:
        form_id = conn.execute(sa.text(
            "INSERT INTO form.forms (title, description, share_token, status, "
            "is_anonymous, requires_login, send_confirmation, allow_edit, "
            "created_at, updated_at, tenant_id) VALUES "
            "('Demo-formulier', 'Een voorbeeldformulier van het platform.', "
            "'demo-formulier', 'open', TRUE, FALSE, FALSE, FALSE, now(), now(), :t) "
            "RETURNING id"), {"t": DEMO}).scalar()
        sectie_id = conn.execute(sa.text(
            "INSERT INTO form.form_sections (form_id, title, position, tenant_id) "
            "VALUES (:f, 'Jouw mening', 0, :t) RETURNING id"),
            {"f": form_id, "t": DEMO}).scalar()
        conn.execute(sa.text(
            "INSERT INTO form.form_fields (form_id, section_id, field_type, label, "
            "required, position, tenant_id) VALUES "
            "(:f, :s, 'text', 'Wat vind je van het platform?', TRUE, 0, :t), "
            "(:f, :s, 'rating', 'Geef een score', FALSE, 1, :t)"),
            {"f": form_id, "s": sectie_id, "t": DEMO})


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS cms.ix_cms_pages_tenant_slug")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_cms_pages_slug "
               "ON cms.cms_pages (slug)")

"""Fase 5b (#406): per-tenant config/secrets-store (kernel_tenant_settings),
platformrollen OPERATOR/ACCOUNT_ADMIN, en de demo-tenant-config van de
voorbeeldafdeling (mails enkel loggen, noindex, eigen naam/base-URL).

Rollen-beslissing (Koen, 2026-07-13): Koen = OPERATOR (platformbreed);
Raak Millegem FINANCE = Steven én Koen.

Revision ID: 087
Revises: 086
"""
from alembic import op
import sqlalchemy as sa

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None

VOORBEELD_TENANT_ID = 3

DEMO_SETTINGS = [
    ("display_name", "Raak Voorbeeldafdeling"),
    ("mail_mode", "log_only"),
    ("noindex", "1"),
    ("base_url", "https://renko.be/raakvoorbeeldafdeling"),
]

NIEUWE_ROLLEN = [
    ("OPERATOR", "Platformbeheerder", "Ziet en beheert alle tenants (platformniveau)"),
    ("ACCOUNT_ADMIN", "Accountbeheerder", "Beheert alle units binnen één account"),
]

OPERATOR_EMAILS = ["koen.renders@gmail.com"]
FINANCE_EMAILS = ["steven.paepen@ik.me", "koen.renders@gmail.com"]


def _geef_rol(conn, email: str, role_code: str) -> None:
    row = conn.execute(sa.text("SELECT id FROM auth.users WHERE email = :e"),
                       {"e": email}).fetchone()
    if not row:
        return
    bestaat = conn.execute(sa.text(
        "SELECT 1 FROM auth.user_roles WHERE user_id = :u AND role_code = :r"),
        {"u": row[0], "r": role_code}).scalar()
    if not bestaat:
        conn.execute(sa.text(
            "INSERT INTO auth.user_roles (user_id, role_code, created_at) "
            "VALUES (:u, :r, now())"), {"u": row[0], "r": role_code})


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Config/secrets-store.
    op.execute("""
        CREATE TABLE IF NOT EXISTS kernel_tenant_settings (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            key VARCHAR(100) NOT NULL,
            value TEXT,
            value_encrypted TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tenant_setting UNIQUE (tenant_id, key)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kernel_tenant_settings_tenant_id "
               "ON kernel_tenant_settings (tenant_id)")

    # 1b. Mail-status 'logged' toestaan (demo-tenant logt zonder te versturen).
    op.execute("ALTER TABLE mail.email_log DROP CONSTRAINT IF EXISTS ck_email_log_status")
    op.execute("ALTER TABLE mail.email_log ADD CONSTRAINT ck_email_log_status "
               "CHECK (status IN ('sent', 'failed', 'skipped', 'logged'))")

    # 2. Rolcodes verbreden (ACCOUNT_ADMIN > 10 tekens) + nieuwe platformrollen.
    op.execute("ALTER TABLE role_codes ALTER COLUMN code TYPE VARCHAR(20)")
    op.execute("ALTER TABLE auth.user_roles ALTER COLUMN role_code TYPE VARCHAR(20)")
    for code, value, omschrijving in NIEUWE_ROLLEN:
        conn.execute(sa.text(
            "INSERT INTO role_codes (code, language, value, description, created_at, updated_at) "
            "VALUES (:c, 'nl', :v, :d, now(), now()) ON CONFLICT DO NOTHING"),
            {"c": code, "v": value, "d": omschrijving})

    # 3. Rollen-beslissing toepassen.
    for email in OPERATOR_EMAILS:
        _geef_rol(conn, email, "OPERATOR")
    for email in FINANCE_EMAILS:
        _geef_rol(conn, email, "FINANCE")

    # 4. Demo-tenant-config (idempotent).
    for key, value in DEMO_SETTINGS:
        conn.execute(sa.text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
            "VALUES (:t, :k, :v) ON CONFLICT ON CONSTRAINT uq_tenant_setting DO NOTHING"),
            {"t": VOORBEELD_TENANT_ID, "k": key, "v": value})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kernel_tenant_settings")

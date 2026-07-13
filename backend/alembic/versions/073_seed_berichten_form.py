"""Berichten (#398, §5.7): seed het 'Contacteer ons'-formulier (slug 'berichten')

Vervangt op termijn de ideas-component; de behartigen-taak (workflow) is het
vervolgproces. Idempotent: bestaat de slug al, dan gebeurt er niets.

Revision ID: 073
Revises: 072
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text("SELECT id FROM form.forms WHERE slug = 'berichten'")).scalar()
    if exists:
        return
    form_id = bind.execute(sa.text("""
        INSERT INTO form.forms (title, slug, description, share_token, status,
                                requires_login, send_confirmation, confirmation_message,
                                allow_edit, is_anonymous, created_at, updated_at)
        VALUES ('Contacteer ons', 'berichten',
                'Een vraag, idee of voorstel voor Raak? Laat het ons weten.',
                :token, 'open', false, true,
                'Bedankt voor je bericht! We behartigen het zo snel mogelijk en laten iets weten als dat nodig is.',
                false, false, now(), now())
        RETURNING id"""), {"token": secrets.token_hex(16)}).scalar()
    bind.execute(sa.text("""
        INSERT INTO form.form_fields (form_id, label, field_type, required, position)
        VALUES (:fid, 'Je bericht', 'textarea', true, 1)"""), {"fid": form_id})


def downgrade() -> None:
    op.execute("DELETE FROM form.forms WHERE slug = 'berichten'")

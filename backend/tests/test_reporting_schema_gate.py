"""Schema gate on the `reporting` views (#832 test 2, CR-06 §7.1).

Two invariants that must hold for **every** view in the schema, including the ones
phases 3 to 5 add, which is why this reads `information_schema` instead of a list
kept by hand:

1. **`tenant_id` on every view.** The engine filters on it unconditionally; a view
   without the column would make that filter impossible and the leak silent.
2. **A comment on every view**, because the soft-delete decision is per view and
   has to be written down somewhere a reader will find it. `f_payments`
   deliberately reaches through soft-deleted payables; without the comment that is
   indistinguishable from a forgotten filter.

**The counter-proof (#678 / CLAUDE.md, "bij een gate volstaat die vraag niet").**
Both rules were broken on purpose against a live database:

- `CREATE VIEW reporting.d_lek AS SELECT 1 AS x` — the first test failed with
  `d_lek` named in the message, as intended. Dropped again.
- `COMMENT ON VIEW reporting.d_date IS NULL` — the second test failed naming
  `d_date`. Comment restored by re-running the migration.

And the gate refuses to pass on an empty scan: a renamed schema or a migration
that never ran would otherwise leave it green forever while guarding nothing.
"""
from __future__ import annotations

from sqlalchemy import text

# Every view the schema is supposed to have. Listed so the gate can prove it
# looked at a real schema, and updated per phase — a phase that adds a view and
# forgets this list is exactly what the minimum below catches. It also catches a
# RENAME that left the old name behind: `d_household` became `d_member` in #848,
# and the gate went red until the list said so.
EXPECTED_VIEWS = {
    "d_activity", "d_date", "d_member", "d_membership_status",
    "d_payment_method", "d_payment_status", "d_person", "d_form",
    "f_memberships", "f_payments", "f_registrations", "f_membership_persons",
    "f_form_submissions", "f_tasks", "f_members", "f_activities",
}


def _views(db) -> list[str]:
    rows = db.execute(text(
        "SELECT table_name FROM information_schema.views "
        "WHERE table_schema = 'reporting' ORDER BY table_name"))
    return [row[0] for row in rows]


def test_the_gate_actually_looks_at_the_reporting_schema(db_session):
    """A gate that scans nothing is green without guarding anything (#678)."""
    found = set(_views(db_session))
    assert len(found) >= len(EXPECTED_VIEWS), (
        f"deze gate vond {len(found)} weergaven in schema 'reporting', verwacht "
        f"minstens {len(EXPECTED_VIEWS)}. Draaide de migratie, of heet het schema "
        "anders?")
    ontbreekt = EXPECTED_VIEWS - found
    assert not ontbreekt, f"verwachte weergaven ontbreken: {sorted(ontbreekt)}"
    onverwacht = found - EXPECTED_VIEWS
    assert not onverwacht, (
        f"weergaven die deze lijst niet kent: {sorted(onverwacht)} — een nieuwe "
        "hoort erbij te komen, een hernoemde hoort de oude te vervangen")


def test_every_reporting_view_carries_tenant_id(db_session):
    """The tenant fence has to be possible before it can be applied."""
    rows = db_session.execute(text(
        "SELECT v.table_name FROM information_schema.views v "
        "WHERE v.table_schema = 'reporting' "
        "  AND NOT EXISTS ("
        "      SELECT 1 FROM information_schema.columns c "
        "      WHERE c.table_schema = 'reporting' AND c.table_name = v.table_name "
        "        AND c.column_name = 'tenant_id') "
        "ORDER BY v.table_name"))
    zonder = [row[0] for row in rows]
    assert not zonder, (
        "elke weergave in schema 'reporting' draagt tenant_id (CR-06 §7.1); "
        f"zonder: {zonder}")


def test_every_reporting_view_says_what_it_excludes(db_session):
    """The soft-delete decision is per view, so it is documented per view."""
    rows = db_session.execute(text(
        "SELECT c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'reporting' AND c.relkind = 'v' "
        "  AND COALESCE(obj_description(c.oid, 'pg_class'), '') = '' "
        "ORDER BY c.relname"))
    zonder = [row[0] for row in rows]
    assert not zonder, (
        "elke weergave krijgt een COMMENT dat zegt wat ze uitsluit; "
        f"zonder: {zonder}")


def test_the_facts_exclude_soft_deleted_rows(db_session):
    """Not the comment but the behaviour: a removed row leaves the fact.

    The seed's soft-deleted registration and membership are the ones being checked
    here; this is the test that goes red when a `WHERE deleted_at IS NULL` is lost,
    while the comment above it still claims otherwise.
    """
    from app.domains.activities.api import Registration
    from app.soft_delete import soft_delete
    from tests._reporting_seed import TENANT_A, seed

    situation = seed(db_session)
    before = db_session.execute(text(
        "SELECT COUNT(DISTINCT registration_id) FROM reporting.f_registrations "
        "WHERE tenant_id = :t"), {"t": TENANT_A}).scalar()

    registration = db_session.query(Registration).filter(
        Registration.id == situation["registrations"]["guest"]).first()
    soft_delete(registration)
    db_session.commit()

    after = db_session.execute(text(
        "SELECT COUNT(DISTINCT registration_id) FROM reporting.f_registrations "
        "WHERE tenant_id = :t"), {"t": TENANT_A}).scalar()
    assert after == before - 1, (
        "een verwijderde inschrijving hoort uit f_registrations te verdwijnen")

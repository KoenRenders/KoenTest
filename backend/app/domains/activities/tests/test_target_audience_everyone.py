"""#1451 — the target audience "Gezinnen" (`families`) becomes "Iedereen" (`everyone`).

Migration 184 runs here against the state it was written for: the database the
environments have today, where `families` exists and activities carry it. A
fresh test database never had that state — migration 180 seeds the list from
`codes.py`, which already says `everyone` — so the test builds it first, inside
the test's transaction, and then runs the migration's `upgrade()` on that same
connection.

Red against master `15f81891`: there is no migration 184, and the code list
still holds `families`.
"""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text as sql

MIGRATION = next(
    (Path(__file__).resolve().parents[4] / "alembic" / "versions").glob(
        "184_*target_audience_families_becomes_*.py"
    )
)


def _migration():
    spec = importlib.util.spec_from_file_location("m184", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, step: str) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(_migration(), step)()


def _state_before(db) -> list[int]:
    """`families` back in the list, and two activities on it — one soft-deleted,
    since a foreign key does not know `deleted_at`."""
    db.execute(sql("DELETE FROM activities.target_audience_labels WHERE code = 'everyone'"))
    db.execute(sql("DELETE FROM activities.target_audience_codes WHERE code = 'everyone'"))
    db.execute(
        sql(
            "INSERT INTO activities.target_audience_codes (code, sort_order, is_active) "
            "VALUES ('families', 10, true) ON CONFLICT (code) DO NOTHING"
        )
    )
    db.execute(
        sql(
            "INSERT INTO activities.target_audience_labels (code, language, value) "
            "VALUES ('families', 'nl', 'Gezinnen'), ('families', 'en', 'Families') "
            "ON CONFLICT (code, language) DO NOTHING"
        )
    )
    ids = []
    for name, deleted in (("Gezinsdag", "NULL"), ("Oude gezinsdag", "now()")):
        ids.append(
            db.execute(
                sql(
                    "INSERT INTO activities.activities "
                    "(name, tenant_id, target_audience, created_at, updated_at, deleted_at) "
                    f"VALUES (:name, 2, 'families', now(), now(), {deleted}) RETURNING id"
                ),
                {"name": name},
            ).scalar_one()
        )
    return ids


def _audiences(db, ids):
    return (
        db.execute(
            sql("SELECT target_audience FROM activities.activities WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        .scalars()
        .all()
    )


def test_the_migration_moves_every_activity_from_families_to_everyone(db_session):
    ids = _state_before(db_session)
    _run(db_session, "upgrade")

    assert _audiences(db_session, ids) == ["everyone", "everyone"]
    left = db_session.execute(
        sql("SELECT count(*) FROM activities.activities WHERE target_audience = 'families'")
    ).scalar_one()
    assert left == 0, "an activity still carries families"
    codes = db_session.execute(
        sql("SELECT code, sort_order FROM activities.target_audience_codes ORDER BY sort_order")
    ).all()
    assert ("families" not in {c for c, _ in codes}) and codes[0] == ("everyone", 10)
    labels = dict(
        db_session.execute(
            sql(
                "SELECT language, value FROM activities.target_audience_labels "
                "WHERE code = 'everyone'"
            )
        ).all()
    )
    assert labels == {"nl": "Iedereen", "en": "Everyone"}


def test_a_second_run_changes_nothing(db_session):
    ids = _state_before(db_session)
    _run(db_session, "upgrade")
    _run(db_session, "upgrade")
    assert _audiences(db_session, ids) == ["everyone", "everyone"]


def test_the_code_list_offers_everyone_and_not_families():
    from app.domains.activities.codes import TARGET_AUDIENCE_CODES

    codes = {seed.code: seed for seed in TARGET_AUDIENCE_CODES}
    assert "families" not in codes
    assert (codes["everyone"].nl, codes["everyone"].sort_order) == ("Iedereen", 10)


def test_the_form_and_the_programme_say_iedereen(client, db_session):
    """The activity form offers "Iedereen" and no "Gezinnen"; the reporting view
    behind the annual programme reads the label through the code, so an activity
    on `everyone` shows "Iedereen" there too."""
    from app.domains.activities.api import Activity
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity = Activity(name="Voor iedereen", target_audience="everyone")
    db_session.add(activity)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    form = html[html.index('id="target_audience"') :]
    form = form[: form.index("</select>")]
    assert '<option value="everyone"' in form and "Iedereen" in form
    assert "Gezinnen" not in form and 'value="families"' not in form

    label = db_session.execute(
        sql("SELECT target_audience_label FROM reporting.d_activity WHERE activity_id = :id"),
        {"id": activity.id},
    ).scalar_one()
    assert label == "Iedereen"

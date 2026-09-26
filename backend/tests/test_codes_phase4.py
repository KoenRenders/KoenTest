"""What phase 4 of CR-12 must prove, so far: the remaining domains (§B8).

Built: workflow, forms, mail, activities, reporting, the history operation and
the AI call log. Still open, and why: **media** waits for the rebase onto
v2.6.0, whose #1173 changed the very CHECK the media list must drop.

The AI log carries the one data change of this phase, decided by Koen on 26
September 2026: an empty `capability` becomes `chat`, an empty `provider`
becomes NULL. Counted on UAT and PROD first — 2 empty capabilities on PROD, no
empty provider anywhere.

Three things carry this phase, each a test below.

1. **The same words as before** (§B8.5, AC3). Eight of these lists had a
   dictionary on a screen; the label table must say what it said.
2. **A derived list cannot rely on a key.** `task_category` and
   `registration_state` have no storing column, so no foreign key guarantees
   completeness. For the state the enum = codes gate does it — `RegistrationState`
   is its enum. For the category the source is the text before a dot in another
   list, and only a test can tie the two together.
3. **History has no key, so it gets a value test** (§B4.10 / F4): every
   `operation` in every `*_history` table must be a code of `kernel_operation`.

## Proof that these can go red

The method of the css gate (#652), 26 September 2026:

| Test | Violation | Fired |
|---|---|---|
| The same words | the `textarea` seed back to the catalogue's "Tekstvak" | yes |
| Every kind has its category | `crm.follow_up` registered without its `crm` category row | yes — names `crm` |
| The database refuses a non-code | `fk_email_log_status_code` dropped again at the end of migration 160 | yes — *DID NOT RAISE* |
| History operations are codes | a `membership_history` row with `operation='upsert'`, inserted before the check | yes — names the table and `upsert` |
| The dropped checks are gone | `ck_form_fields_type` left out of 159's `CHECKS` | yes |
| The same words (AI) | the `reporting` seed changed to "Rapportering" | yes — `ai_capability` |
| Raw codes now have a word (AI) | the `bfl` seed given the word `bfl` | yes |
| The database refuses a non-code (AI) | `fk_ai_call_log_status_code` dropped at the end of migration 163 | yes — `status`, `misschien` |
| The AI backfill | `CAPABILITY_BACKFILL` pointed at `'x'` instead of `''` | yes |

**One measurement had to be redone.** The first try at the key violation put
`None` where the column name of the `mail_status` list stands in migration 160.
That crashed the migration instead of leaving the key out, so the test was red
for a reason that proves nothing. The clean violation drops the one key and
keeps everything else.

**And the refusal test found a real gap on its first run**, the second time in
CR-12 (phase 3 found `ck_meeting_sections_kind`): `ck_forms_status` of
migration 062 still stood beside the new key and refused the value with
SQLSTATE 23514. Migration 159 now drops it too.
"""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.kernel.codes import code_label, reset_label_cache

#: The words the screens showed before CR-12, taken literally from the
#: dictionaries these lists replace:
#: `workflow/ui.py` (`KIND_LABELS`, `CAT_LABELS`), `forms/admin_ui.py`
#: (`veldtype_labels`, `_status_labels`), `mail/ui.py` (`_TYPE_LABELS`,
#: `_STATUS_LABELS`), `activities/service.py` (`STATUS_LABELS`) and
#: `audit/changes.py` (`_OPERATION_LABELS`) and `chatbot/admin_ui.py`
#: (`SURFACE_LABELS`, `CAPABILITY_LABELS` — whose fallback for an empty
#: capability was "Chat" — and `STATUS_LABELS`).
LABELS_BEFORE_CR12 = {
    "task_kind": {"payment.webhook_mismatch": "Betaling: webhook wijkt af",
                  "payment.refund_bevestigen": "Betaling: terugbetaling bevestigen",
                  "mail.definitief_gefaald": "E-mail: definitief mislukt",
                  "kernel.job_gefaald": "Achtergrondtaak mislukt"},
    "task_category": {"payment": "Betalingen", "mail": "E-mail", "kernel": "Systeem"},
    "field_type": {"text": "Korte tekst", "textarea": "Lange tekst", "number": "Getal",
                   "email": "E-mailadres", "select": "Keuzelijst", "radio": "Eén keuze",
                   "checkbox": "Meerdere keuzes", "rating": "Score",
                   "phone": "Telefoonnummer"},
    "form_status": {"draft": "Concept", "open": "Open", "closed": "Gesloten"},
    "email_type": {"membership_confirmation": "Lidmaatschap",
                   "activity_confirmation": "Activiteit",
                   "idea_ack": "Idee (bevestiging)", "idea_board": "Idee (bestuur)",
                   "magic_link": "Inloglink", "member_contact_notice": "Contactbericht",
                   "form_confirmation": "Formulier (bevestiging)", "other": "Overig"},
    "mail_status": {"sent": "Verstuurd", "failed": "Mislukt", "skipped": "Overgeslagen"},
    "registration_state": {"open": "Open", "closed": "Afgesloten", "past": "Voorbij",
                           "cancelled": "Geannuleerd"},
    "kernel_operation": {"insert": "Toegevoegd", "update": "Gewijzigd",
                         "delete": "Verwijderd"},
    "ai_surface": {"public": "Publiek", "admin": "Beheer"},
    "ai_capability": {"chat": "Chat", "reporting": "Rapporten",
                      "newsletter_drafting": "Nieuwsbrief", "ocr": "Documenten lezen",
                      "dictation": "Dicteren"},
    "ai_status": {"ok": "Gelukt", "blocked": "Tegengehouden", "error": "Mislukt",
                  "moderated": "Geweigerd door de provider"},
}


@pytest.fixture(autouse=True)
def _clean_label_cache():
    reset_label_cache()
    yield
    reset_label_cache()


# ── §B8.5 / AC3 The same words as before ─────────────────────────────────────

@pytest.mark.parametrize("code_list", sorted(LABELS_BEFORE_CR12))
def test_every_screen_shows_the_same_dutch_word_as_before(db_session, code_list):
    for code, before in LABELS_BEFORE_CR12[code_list].items():
        assert code_label(code_list, code, language="nl", db=db_session) == before, (
            f"`{code_list}` code {code!r} used to read {before!r}")


def test_codes_that_reached_the_screen_raw_now_have_a_word(db_session):
    """Codes that had no entry in their screen's dictionary and were shown as
    the code itself. Existing bugs, fixed by this phase — so the test says that
    they now read as a word, whatever the word. `mock` is left out on purpose:
    its word is the code, it names a stand-in nobody outside development sees."""
    for code_list, code in (("email_type", "meeting"), ("email_type", "newsletter"),
                            ("email_type", "newsletter_confirmation"),
                            ("mail_status", "logged"),
                            ("ai_surface", "designstudio"),
                            ("ai_capability", "translate"), ("ai_capability", "image"),
                            ("ai_provider", "mistral"), ("ai_provider", "bfl")):
        assert code_label(code_list, code, language="nl", db=db_session) != code


# ── A derived list: completeness is a test, not a key ────────────────────────

def test_every_task_kind_has_a_row_for_its_category(db_session):
    """The category is the text before the dot and is stored nowhere.

    Add a kind in a new category and forget the category row, and
    `code_label()` falls back to the code: the workbench heads a group `crm`.
    No foreign key can see that, because there is no column to hang one on.
    """
    kinds = [row[0] for row in db_session.execute(text(
        "SELECT code FROM workflow.task_kind_codes")).all()]
    categories = {row[0] for row in db_session.execute(text(
        "SELECT code FROM workflow.task_category_codes")).all()}
    assert kinds, "no task kinds found — is this test still looking at the table?"
    missing = sorted({kind.split(".", 1)[0] for kind in kinds} - categories)
    assert not missing, f"task kinds in a category without a row: {missing}"


# ── History: a value test instead of a key (§B4.10 / F4) ─────────────────────

def test_every_history_operation_is_a_code(db_session):
    """No key on history, on purpose: it is append-only and must survive a
    retired code. What replaces the key is this: every value is a code."""
    codes = {row[0] for row in db_session.execute(text(
        "SELECT code FROM public.kernel_operation_codes")).all()}
    assert codes == {"insert", "update", "delete"}
    for table in _history_tables_with_operation(db_session):
        stray = [row[0] for row in db_session.execute(text(
            f"SELECT DISTINCT operation FROM {table}")).all() if row[0] not in codes]
        assert not stray, f"{table} holds operation(s) that are no code: {stray}"


def _history_tables_with_operation(db) -> list[str]:
    rows = db.execute(text(
        "SELECT table_schema || '.' || table_name FROM information_schema.columns "
        "WHERE column_name = 'operation' AND table_name LIKE '%\\_history'")).all()
    tables = sorted(row[0] for row in rows)
    assert len(tables) >= 4, f"expected the history tables, found {tables}"
    return tables


# ── §B8.2 / AC1 The database refuses what is not a code ──────────────────────

NOT_A_CODE = [
    ("form.forms", "status", "gepubliceerd"),
    ("mail.email_log", "status", "verzonden"),
    ("mail.email_log", "email_type", "registration"),
    ("reporting.export_log", "kind", "rapport"),
    ("ai.ai_call_log", "surface", "extern"),
    ("ai.ai_call_log", "capability", "design"),
    ("ai.ai_call_log", "status", "misschien"),
    ("ai.ai_call_log", "provider", "openai"),
    ("ai.ai_call_log", "provider", ""),
]


@pytest.mark.parametrize("table, column, value", NOT_A_CODE)
def test_a_value_that_is_not_a_code_never_reaches_the_column(db_session, table, column, value):
    """AC1, and for the right reason: SQLSTATE 23503 is a foreign-key violation.

    One real row per table, created through the ORM, then a raw `UPDATE` —
    an `INSERT` with one column would fail on some other `NOT NULL` and stay
    green without the key."""
    row_id = _one_row(db_session, table)
    with pytest.raises(IntegrityError) as caught:
        db_session.execute(text(f"UPDATE {table} SET {column} = :v WHERE id = :i"),
                           {"v": value, "i": row_id})
    assert caught.value.orig.pgcode == "23503", (
        f"{table}.{column} refused {value!r} with SQLSTATE "
        f"{caught.value.orig.pgcode}, not with a foreign key (23503)")
    db_session.rollback()


def _one_row(db, table: str) -> int:
    from app.domains.chatbot.models import AiCallLog, AiStatus, AiSurface
    from app.domains.forms.api import Form
    from app.domains.mail.models import EmailLog
    from app.domains.reporting.models import ExportLog

    if table == "form.forms":
        row = Form(title="Proef", share_token="phase4-proof-token")
    elif table == "ai.ai_call_log":
        row = AiCallLog(tenant_id=2, surface=AiSurface.ADMIN, status=AiStatus.OK,
                        model="proef", payload="")
    elif table == "mail.email_log":
        row = EmailLog(recipient="phase4@example.com", subject="Proef")
    else:
        row = ExportLog(tenant_id=2, kind="report", subject="Proef", row_count=0)
    db.add(row)
    db.flush()
    return row.id


def test_both_registration_type_columns_carry_the_moved_key(db_session):
    """The list left `public`, and the two columns that store it got back the
    key migration 081 had to take away (§8: no key across schemas)."""
    fks = []
    for table, column in (("registrations", "registration_type"),
                          ("activity_sub_registrations", "registration_type_code")):
        fks += [fk for fk in inspect(db_session.bind).get_foreign_keys(table, schema="activities")
                if column in fk["constrained_columns"]
                and fk["referred_table"] == "registration_type_codes"
                and fk["referred_schema"] == "activities"]
    assert len(fks) == 2
    assert not inspect(db_session.bind).has_table("registration_type_codes", schema="public"), (
        "the orphan in `public` should be gone")


# ── §B8.3 The CHECK constraints the keys replace ─────────────────────────────

@pytest.mark.parametrize("schema, table, constraint", [
    ("form", "form_fields", "ck_form_fields_type"),
    ("form", "forms", "ck_forms_status"),
    ("mail", "email_log", "ck_email_log_status"),
])
def test_a_check_that_says_what_the_foreign_key_says_is_gone(db_session, schema, table, constraint):
    names = {c["name"] for c in inspect(db_session.bind).get_check_constraints(
        table, schema=schema)}
    assert constraint not in names


# ── The card reads booleans, not codes (§B4.7) ───────────────────────────────

def test_the_card_booleans_follow_the_state():
    from app.schemas.activity import ActivityResponse, ComponentResponse

    for cls in (ActivityResponse, ComponentResponse):
        fields = {name for name in cls.model_fields}
        assert "registration_state" in fields
        for state, is_open, is_closed in (("open", True, False), ("closed", False, True),
                                           ("past", False, False), (None, False, False)):
            obj = cls.model_construct(registration_state=state)
            assert (obj.registration_open, obj.registration_closed) == (is_open, is_closed), (
                cls.__name__, state)


# ── The one data change: '' → chat, '' → NULL ───────────────────────────────

def test_the_ai_backfill_turns_empty_into_chat_and_null_and_loses_no_row(db_session):
    """Migration 163 on rows written the way the old code wrote them.

    The suite migrates an empty database, so the two statements run here, on
    rows this test writes with the key triggers set aside — the old shape is
    exactly what the new keys refuse.
    """
    import importlib.util
    from pathlib import Path

    [path] = Path(__file__).resolve().parents[1].glob("alembic/versions/163_*.py")
    spec = importlib.util.spec_from_file_location("migration_163", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    db_session.execute(text("SET LOCAL session_replication_role = replica"))
    for capability, provider in (("", "mistral"), ("", ""), ("reporting", "mistral")):
        db_session.execute(text(
            "INSERT INTO ai.ai_call_log (tenant_id, surface, capability, actor, model, "
            "payload, blocked_reason, provider, endpoint, provider_request_id, status) "
            "VALUES (2, 'public', :c, '', 'proef-163', '', '', :p, '', '', 'ok')"),
            {"c": capability, "p": provider})
    db_session.execute(text(migration.CAPABILITY_BACKFILL))
    db_session.execute(text(migration.PROVIDER_BACKFILL))
    db_session.execute(text("SET LOCAL session_replication_role = origin"))

    rows = db_session.execute(text(
        "SELECT capability, provider FROM ai.ai_call_log WHERE model = 'proef-163' "
        "ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [
        ("chat", "mistral"), ("chat", None), ("reporting", "mistral")]
    db_session.rollback()

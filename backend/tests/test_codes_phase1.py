"""What phase 1 of CR-12 must prove: the money domain (§B8).

Five lists, four of them in `payment` and the payment method in `mdm`. The
money domain went first because it held the most loose comparisons and because
AC1, AC2, AC3 and AC6 are measured on these screens.

The tests that matter here are the ones about **the one data change** (§B4.6).
Every other phase of this change request leaves stored values alone; this one
rewrites `activities.registrations.payment_method` once, and three separate
things had to be true for that to be safe. Each of them is a test below.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import PaymentMethod
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentStatus,
    PaymentType,
    create_payment_record,
)
from app.kernel.codes import code_label, code_labels, reset_label_cache

#: The Dutch words the payment screens and exports showed before CR-12, taken
#: literally from `payment/exports.py:_STATUS/_TYPE/_METHOD` and the two label
#: dictionaries in `payment/ui.py` as they stood on 25 September 2026. §B8.5:
#: AC3 says the screen, the export and the report dimension show the same word;
#: this snapshot is what "the same" is measured against.
LABELS_BEFORE_CR12 = {
    "payment_status": {"pending": "In afwachting", "paid": "Betaald",
                       "failed": "Mislukt", "cancelled": "Geannuleerd"},
    "payment_type": {"charge": "Vordering", "refund": "Terugbetaling"},
    "payment_method": {"online": "Online", "transfer": "Overschrijving",
                       "cash": "Cash"},
}


@pytest.fixture(autouse=True)
def _clean_label_cache():
    reset_label_cache()
    yield
    reset_label_cache()


def _charge(db, **kw) -> PaymentRecord:
    fields = dict(payable_type=PayableType.REGISTRATION, payable_id=4242,
                  amount=Decimal("10.00"), method=PaymentMethod.TRANSFER,
                  status=PaymentStatus.PENDING, type=PaymentType.CHARGE)
    fields.update(kw)
    record = PaymentRecord(**fields)
    db.add(record)
    db.flush()
    return record


# ── §B8.2 / AC1 The database refuses a value that is not in the list ─────────

def test_the_database_refuses_a_status_that_is_not_a_code(db_session):
    """AC1, literally: `payed` does not get into the ledger, not even by raw SQL.

    This is the acceptance criterion the whole change request is built on. Until
    now `status` was a `String(20)` with a comment; a typo in a script, a bad
    migration or a direct `UPDATE` would simply be stored, and every screen
    would show it.
    """
    record = _charge(db_session)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE payment.payment_records SET status = 'payed' "
                 "WHERE id = :id"), {"id": record.id})


def test_the_database_refuses_an_unknown_payment_method(db_session):
    record = _charge(db_session)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE payment.payment_records SET method = 'cheque' "
                 "WHERE id = :id"), {"id": record.id})


def test_the_registration_column_refuses_the_old_dutch_spelling(db_session):
    """`OVERSCHRIJVING` cannot come back, and that is why the form had to change.

    The public form posted this word and `router.py` stored it verbatim. With
    the foreign key in place and the form unchanged, the *next* registration by
    bank transfer would have failed on the constraint — which is exactly what
    this test reproduces. Form and migration therefore shipped in one commit.
    """
    from app.domains.activities.api import Activity, Registration

    activity = Activity(name="Proef", location="Miloheem")
    db_session.add(activity)
    db_session.flush()
    db_session.add(Registration(activity_id=activity.id, contact_name="X",
                                contact_email="x@example.org",
                                registration_type="INDIVIDUAL"))
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "UPDATE activities.registrations SET payment_method = 'OVERSCHRIJVING'"))


# ── §B8.3 The round trip, on the money columns ───────────────────────────────

def test_the_four_columns_store_codes_and_not_member_names(db_session):
    """Read raw, the ledger holds `paid`/`charge`/`registration`/`transfer`.

    Had these columns been declared against `sa.Enum`, they would hold `PAID`,
    `CHARGE`, `REGISTRATION` and `TRANSFER` — and every export, every report and
    every query written against the codes would have gone quietly wrong. On the
    money domain that is not a rendering bug.
    """
    record = _charge(db_session, status=PaymentStatus.PAID,
                     method=PaymentMethod.TRANSFER, type=PaymentType.CHARGE,
                     payable_type=PayableType.REGISTRATION)
    db_session.flush()

    raw = db_session.execute(text(
        "SELECT status, type, payable_type, method FROM payment.payment_records "
        "WHERE id = :id"), {"id": record.id}).one()
    assert tuple(raw) == ("paid", "charge", "registration", "transfer")


def test_a_plain_enum_is_not_equal_to_its_code(db_session):
    """The property the whole phase leans on, stated once.

    With `str, Enum` every loose comparison left behind would stay quietly true
    and nobody would find them. Plain, they are quietly false — which is why
    they all had to go in one commit, and why the gate is an AST walk.
    """
    record = _charge(db_session, status=PaymentStatus.PAID)
    assert record.status is PaymentStatus.PAID
    assert record.status != "paid"


def test_assigning_a_code_yields_the_member(db_session):
    """A service that is handed a raw code keeps working, and reads back as one.

    The kernel coerces on assignment, so the attribute never holds a string that
    would compare false against every member until the row is refreshed.
    """
    record = _charge(db_session)
    record.status = "paid"
    assert record.status is PaymentStatus.PAID


# ── §B8.5 / AC3 The same word everywhere ─────────────────────────────────────

@pytest.mark.parametrize("code_list", sorted(LABELS_BEFORE_CR12))
def test_the_labels_are_the_words_the_screens_showed_before(db_session, code_list):
    for code, expected in LABELS_BEFORE_CR12[code_list].items():
        assert code_label(code_list, code, language="nl") == expected


def test_every_money_list_has_english_labels_too(db_session):
    """AC2: an English-speaking unit reads English badges, not raw codes."""
    for code_list in ("payment_status", "payment_type", "payable_type",
                  "payment_provider", "payment_method"):
        for code, _nl in code_labels(code_list, language="nl"):
            english = code_label(code_list, code, language="en")
            assert english and english != code, f"{code_list}.{code} has no en label"


def test_the_export_writes_labels_and_not_codes(db_session):
    """The export lost its own three dictionaries; it reads the same table now.

    AC3 in its cheapest form: if the export and the screen disagree, one of them
    kept a dictionary.
    """
    import io
    import zipfile

    from app.domains.payment.exports import build_payments_export_ods

    _charge(db_session, status=PaymentStatus.PAID, method=PaymentMethod.ONLINE,
            type=PaymentType.REFUND)
    db_session.commit()
    content = zipfile.ZipFile(io.BytesIO(build_payments_export_ods(db_session))) \
        .read("content.xml").decode("utf-8")

    assert "Betaald" in content and "Online" in content and "Terugbetaling" in content
    # And not the codes: that is what happened before CR-12 as soon as a value
    # was not in this file's own dictionary.
    for code in (">paid<", ">online<", ">refund<"):
        assert code not in content, f"raw code {code} in the export"


# ── §B4.6 The one data change ────────────────────────────────────────────────

def _migration_module():
    """The phase-1 migration, imported by path so its mapping can be asserted."""
    import importlib.util
    from pathlib import Path

    path = next((Path(__file__).resolve().parents[1] / "alembic" / "versions")
               .glob("153_*_the_payment_vocabularies_become_code_*.py"))
    spec = importlib.util.spec_from_file_location("cr12_phase1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_method_mapping_covers_what_hdev_actually_held(db_session):
    """Every value measured on HDEV maps onto a code that exists.

    The document first said only `ONLINE -> online`. HDEV held fifteen rows of
    `OVERSCHRIJVING`, which is in no code list, so the migration would have
    aborted on its own guard — correct behaviour, and a wasted release. This
    test freezes the measurement so the mapping cannot silently lose a case.
    """
    module = _migration_module()
    measured_on_hdev = {"ONLINE", "OVERSCHRIJVING", "transfer", None}
    codes = {m.value for m in PaymentMethod}

    for value in measured_on_hdev:
        if value is None or value in codes:
            continue  # stays as it is
        assert value in module.METHOD_FIX, (
            f"{value!r} was on HDEV but has no mapping")
        assert module.METHOD_FIX[value] in codes

    for source, target in module.METHOD_FIX.items():
        assert target in codes, f"{source!r} points to {target!r}, not a valid code"
        assert source not in codes, (
            f"{source!r} is already a code — then it does not belong in the mapping")


def test_the_migration_counts_the_whole_table_and_not_the_living_rows(db_session):
    """A foreign key holds for a soft-deleted row too, so the UPDATE must.

    Five rows on HDEV are soft-deleted (4× `ONLINE`, 1× `OVERSCHRIJVING`). An
    UPDATE with `WHERE deleted_at IS NULL` would leave exactly those behind and
    the key would fail on them. The rest of this codebase filters soft-deleted
    rows almost everywhere, which is why this one is easy to miss — so the
    absence of that filter is asserted rather than trusted.
    """
    import ast
    import inspect
    import textwrap

    # Through the AST and not through a text search: Python already joins
    # adjacent string literals, so the whole statement is here. A search on
    # the source code saw only its first line.
    tree = ast.parse(textwrap.dedent(inspect.getsource(_migration_module().upgrade)))
    updates = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value.startswith("UPDATE activities.registrations")]
    assert updates, ("no UPDATE on activities.registrations found — is "
                     "this test still looking at the migration?")
    for statement in updates:
        flat = " ".join(statement.split())
        assert flat.endswith("WHERE payment_method = :old"), (
            f"the UPDATE ends in {flat!r}; it should have exactly one condition "
            f"— an extra `AND deleted_at IS NULL` leaves the soft-deleted rows "
            f"behind and then the foreign key fails on exactly those rows")


def test_the_history_table_has_no_payment_method_to_migrate(db_session):
    """§B4.6 said "and its history"; there is none. Verified, not assumed."""
    columns = {r[0] for r in db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'activities' AND table_name = 'registration_history'"
    )).all()}
    assert "payment_method" not in columns

    everywhere = db_session.execute(text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE column_name = 'payment_method'")).scalar_one()
    assert everywhere == 1, "payment_method is in more than one place in the schema"


# ── The gateway keeps its own vocabulary (§B4.10) ────────────────────────────

def test_mollie_statuses_map_to_ours_and_the_unknown_one_stays_pending():
    """Their list, our list, and an explicit branch for the word we do not know.

    Raising here would mean losing a payment notification over a status Mollie
    added — at the moment money is moving. So it logs and leaves the record
    where it was.
    """
    from app.domains.payment.providers.mollie import (
        MOLLIE_STATUS_MAP, MollieStatus, our_status,
    )

    assert our_status("paid") is PaymentStatus.PAID
    assert our_status("canceled") is PaymentStatus.CANCELLED
    assert our_status("expired") is PaymentStatus.FAILED
    assert our_status("iets_nieuws_van_mollie") is PaymentStatus.PENDING
    assert set(MOLLIE_STATUS_MAP) == set(MollieStatus), (
        "every Mollie status we know should have a mapping")


def test_the_gateway_status_column_has_no_foreign_key(db_session):
    """Deliberately unconstrained, and that decision is worth a test.

    A foreign key here would make Mollie's next release our webhook's failure.
    If someone later "completes" the pattern by adding one, this goes red and
    points at §B4.10.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.kernel.codes import registry

    # Two sides, because there are two moments at which this goes wrong. First
    # the declaration: it changes with a reviewable line and exists before any
    # migration does. Measured — with only the database check this test stayed
    # green when I added the column to `fk_from`, because the migration had
    # already run. A test that does not see the cheapest mistake does not
    # reliably guard against the most expensive one either.
    declared = {column for code_list in registry().values() for column in code_list.fk_from}
    assert "payment.gateway_payments.status" not in declared, (
        "a CodeList claims gateway_payments.status — that is Mollie's list "
        "(§B4.10), not ours")

    # And then the database, in case someone adds the FK by hand.
    fks = sa_inspect(db_session.bind).get_foreign_keys(
        "gateway_payments", schema="payment")
    on_status = [fk for fk in fks if "status" in fk["constrained_columns"]]
    assert not on_status, (
        "gateway_payments.status has been given an FK — an unknown status "
        "from Mollie would then make the webhook fail at the moment money "
        "is moving")


# ── The service takes a code or a member, and says so ────────────────────────

def test_the_service_accepts_a_raw_code_from_an_older_caller(db_session):
    """Four domains call this function; they may hand over a code or a member."""
    record = create_payment_record(
        db_session, "registration", 77, Decimal("12.00"), "cash")
    assert record.payable_type is PayableType.REGISTRATION
    assert record.method is PaymentMethod.CASH


def test_the_service_refuses_a_value_that_is_in_no_list(db_session):
    with pytest.raises(ValueError):
        create_payment_record(
            db_session, "registration", 78, Decimal("12.00"), "cheque")


def test_the_payment_hint_follows_the_radio_values():
    """Each payment-method hint must compare against a value a radio can carry.

    Phase 1 changed the radio values from `ONLINE`/`OVERSCHRIJVING` to the codes
    `online`/`transfer`, but the two Alpine hints under them kept comparing
    `pm` with the old words — so neither hint ever showed again, and nothing
    went red. Found while translating this branch, not by a test; hence this one.

    Broken on purpose to check it can go red: one `x-show` back to
    `pm === 'ONLINE'` → the set difference names `ONLINE`.
    """
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "domains" / "activities"
              / "templates" / "_inschrijf_form.html").read_text(encoding="utf-8")
    radios = set(re.findall(r'name="payment_method" value="([^"]+)"', source))
    hints = set(re.findall(r"x-show=\"pm === '([^']+)'\"", source))
    assert radios and hints, "the form no longer has payment radios or hints"
    assert hints <= radios, f"hints compare with values no radio carries: {hints - radios}"

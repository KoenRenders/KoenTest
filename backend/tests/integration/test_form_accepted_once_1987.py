"""A registration form that is shown is accepted once (#1987).

A registration was made once per press of its button only because the browser
greyed the button out after the first press; the server took the same form as
often as it came. A phone that sends it again after a lost connection, or two
presses on a slow line, made two registrations — and with online payment, two
payments.

Koen, 15 October 2026: the signed hidden field every public form carries gets a
random part and becomes the key, nothing stored for it beforehand ("a"). The
registration stores the key under a unique index per tenant; a second post of
the form answers with what the first one made — the same thank-you, or the same
payment page — and creates nothing. A form without a key of ours is refused
once with a sentence and comes back with a fresh token (#2039's answer), on the
board's channel too, which skips the guard but not the key.

Broken on purpose (16 October 2026, each put back):
- the lookup of the earlier registration taken out of `submit` → the full
  component's repeat fails on "volzet" (the unique index alone still keeps one
  registration from two posts in a row), and the race test on its barrier;
- the unique index's `form_guard.is_repeat` answer turned into a re-raise →
  the race test and the online race fail: the second post ends on the
  database's refusal;
- the second lookup after a refusal by a rule taken out (review of dev1,
  finding 1) → the post held until the first took the last place fails on
  "volzet";
- the index without `deleted_at IS NULL` (finding 2) → the repost after a
  delete fails on the database's refusal.
"""

from __future__ import annotations

import threading

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.kernel import form_guard
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

CHANNELS = ["public", "board"]
VISITOR = "deelnemer-1987@example.org"


@pytest.fixture(autouse=True)
def _limits():
    from app.limiter import registration_limiter

    registration_limiter._calls.clear()
    yield
    registration_limiter._calls.clear()


@pytest.fixture
def paid(db_session):
    return seed_activity_with_product(db_session, price="10.00")


def _token() -> str:
    """The token of a form shown five seconds ago, as the guard wants it."""
    import time

    return form_guard.issue_token(now=time.time() - 5)


def _form(act, *, token: str | None, method: str = "transfer") -> dict:
    data = {
        "contact_name": "Deelnemer 1987",
        "contact_email": VISITOR,
        "phone": "0470000000",
        f"product_{act[2].id}": "1",
        "payment_method": method,
        form_guard.HONEYPOT_FIELD: "",
    }
    if token is not None:
        data[form_guard.TOKEN_FIELD] = token
    return data


def _post(client, channel: str, act, data: dict):
    activity, component, _product = act
    if channel == "public":
        client.cookies.clear()
        return client.post(
            f"/activiteiten/{activity.id}/inschrijven/{component.id}",
            data=data,
            headers={"HX-Request": "true"},
        )
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw",
        data={"onderdeel": str(act[1].id), **data},
        headers={"HX-Request": "true", "X-CSRF-Token": csrf_token_for(value)},
    )


def _saved(db, act) -> list:
    return db.query(Registration).filter(Registration.activity_id == act[0].id).all()


def _records(db, registration_id: int) -> list:
    from app.domains.payment.api import PayableType, get_records_for

    return get_records_for(db, PayableType.REGISTRATION, registration_id)


@pytest.mark.parametrize("channel", CHANNELS)
def test_two_posts_of_one_form_make_one_registration_and_the_same_answer(
    client, db_session, paid, channel
):
    form = _form(paid, token=_token())
    first = _post(client, channel, paid, form)
    second = _post(client, channel, paid, form)

    assert first.status_code == second.status_code == 200, second.text[:300]
    saved = _saved(db_session, paid)
    assert len(saved) == 1, f"{len(saved)} registrations from one form"
    assert len(_records(db_session, saved[0].id)) == 1, "a second transfer record"
    if channel == "board":
        assert first.headers["HX-Redirect"] == second.headers["HX-Redirect"]
        assert second.headers["HX-Redirect"] == f"/admin/inschrijvingen/{saved[0].id}"
    else:
        # The same thank-you: the name and the amount to transfer.
        for page in (first.text, second.text):
            assert "Deelnemer 1987" in page and "10,00" in page


@pytest.mark.parametrize("channel", CHANNELS)
def test_a_repeat_is_answered_before_the_rules_the_first_post_changed(client, db_session, channel):
    """The first post took the last place; the second post of the same form is
    answered with that registration, not with "volzet"."""
    full = seed_activity_with_product(db_session, price="10.00", max_participants=1)
    form = _form(full, token=_token())
    first = _post(client, channel, full, form)
    second = _post(client, channel, full, form)

    assert first.status_code == second.status_code == 200, second.text[:300]
    assert "volzet" not in second.text.lower()
    assert len(_saved(db_session, full)) == 1


@pytest.mark.parametrize("channel", CHANNELS)
def test_online_two_posts_go_to_the_same_payment(client, db_session, paid, channel, mock_mollie):
    form = _form(paid, token=_token(), method="online")
    first = _post(client, channel, paid, form)
    second = _post(client, channel, paid, form)

    assert first.headers.get("HX-Redirect") == "https://mollie.test/checkout/tr_test_123"
    assert second.headers.get("HX-Redirect") == first.headers.get("HX-Redirect")
    saved = _saved(db_session, paid)
    assert len(saved) == 1
    assert len(_records(db_session, saved[0].id)) == 1, "a second payment was started"


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize(
    "token",
    [None, "1760000000.0123456789abcdef.00000000000000000000000000000000", "1760000000.a1b2c3"],
    ids=["none", "made-up", "before-1987"],
)
def test_a_form_without_a_key_of_ours_is_refused_with_a_sentence(
    client, db_session, paid, channel, token
):
    """Without a token, with one we never issued, or with one of the shape before
    #1987: refused, nothing made, the sentence and a fresh token on the answer —
    so the second press of the same page goes through."""
    answer = _post(client, channel, paid, _form(paid, token=token))

    assert answer.status_code == 422
    assert form_guard.STALE_MESSAGE in answer.text
    assert 'name="form_ts"' in answer.text and "hx-swap-oob" in answer.text
    assert _saved(db_session, paid) == []


def _committed_activity(**product) -> tuple[int, int, int]:
    """An activity made and committed on a connection of its own, so the posts'
    own connections see it. Removed again by `_remove`."""
    from app.database import SessionLocal

    setup = SessionLocal()
    try:
        activity, component, made = seed_activity_with_product(setup, **product)
        setup.commit()
        return activity.id, component.id, made.id
    finally:
        setup.close()


def _remove(ids: tuple[int, int, int]) -> None:
    """The rows the posts committed on their own connections, taken out by hand
    so no later test counts this activity."""
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        RegistrationItem,
    )
    from app.domains.payment.api import (
        GatewayPayment,
        PayableType,
        PaymentRecord,
        PaymentRecordHistory,
    )

    gone = {"synchronize_session": False}
    db = SessionLocal()
    try:
        regs = [
            r.id
            for r in db.query(Registration.id)
            .execution_options(include_deleted=True)
            .filter(Registration.activity_id == ids[0])
        ]
        records = db.query(PaymentRecord).filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id.in_(regs),
        )
        gateways = [r.gateway_payment_id for r in records if r.gateway_payment_id]
        # The history rows of those records too: they have no foreign key and outlive
        # their record, so a later test that reads the history would find them (#2056).
        db.query(PaymentRecordHistory).filter(
            PaymentRecordHistory.payment_record_id.in_([r.id for r in records])
        ).delete(**gone)
        records.delete(**gone)
        db.query(GatewayPayment).filter(GatewayPayment.id.in_(gateways)).delete(**gone)
        db.query(RegistrationItem).filter(RegistrationItem.registration_id.in_(regs)).delete(**gone)
        db.query(Registration).filter(Registration.id.in_(regs)).delete(**gone)
        db.query(ActivityProduct).filter(ActivityProduct.id == ids[2]).delete(**gone)
        db.query(ActivitySubRegistration).filter(ActivitySubRegistration.id == ids[1]).delete(
            **gone
        )
        db.query(ActivityDate).filter(ActivityDate.activity_id == ids[0]).delete(**gone)
        db.query(Activity).filter(Activity.id == ids[0]).delete(**gone)
        db.commit()
    finally:
        db.close()


def _post_on_its_own(ids, form, outcomes: list, errors: list) -> None:
    """One post of the form as the public door makes it, in a transaction and on
    a connection of its own, committed."""
    from fastapi import BackgroundTasks

    from app.database import SessionLocal
    from app.domains.activities.api import Activity, public_channel, submit

    db = SessionLocal()
    try:
        act = db.get(Activity, ids[0])
        comp = next(c for c in act.sub_registrations if c.id == ids[1])
        outcome = submit(
            db,
            public_channel(db, act, comp, ""),
            act,
            comp,
            form,
            BackgroundTasks(),
            proof=form_guard.Proof.from_values(form),
        )
        db.commit()
        outcomes.append(outcome)
    except Exception as exc:  # noqa: BLE001 — reported by the test's assertion
        errors.append(exc)
    finally:
        db.close()


def _race(ids, form, lookup) -> tuple[list, list]:
    """Two posts of one form on two threads, with `lookup` in place of the
    registration lookup (to hold them where the test wants)."""
    from app.domains.activities import service

    outcomes: list = []
    errors: list = []
    real = service.registration_for_submission
    service.registration_for_submission = lookup
    try:
        threads = [
            threading.Thread(target=_post_on_its_own, args=(ids, form, outcomes, errors), name=n)
            for n in ("first", "second")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
    finally:
        service.registration_for_submission = real
    return outcomes, errors


def _made(ids) -> list:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return db.query(Registration).filter(Registration.activity_id == ids[0]).all()
    finally:
        db.close()


def _form_for(ids, *, method: str = "transfer") -> dict:
    form = _form((None, None, type("P", (), {"id": ids[2]})()), token=_token(), method=method)
    return form


def test_the_constraint_decides_when_two_posts_come_at_once():
    """Two posts of one form at the same moment, on two connections, each in its
    own committed transaction: both look for an earlier registration and find
    none before either inserts (a barrier holds them there); the unique index lets
    one through, and the other answers with it. One registration."""
    import app.main  # noqa: F401  the subscribers of a registration
    from app.domains.activities import service
    from app.domains.activities.api import OutcomeKind

    ids = _committed_activity(price="0", is_free=True)
    form = _form_for(ids)
    form.pop("payment_method")
    barrier = threading.Barrier(2, timeout=20)
    real = service.registration_for_submission
    calls = {"n": 0}

    def lookup_together(db, key):
        found = real(db, key)
        calls["n"] += 1
        if calls["n"] <= 2:  # the first look of each post; not the one after the clash
            barrier.wait()
        return found

    try:
        outcomes, errors = _race(ids, form, lookup_together)
        made = _made(ids)
        assert not errors, errors
        assert [o.kind for o in outcomes] == [OutcomeKind.DONE, OutcomeKind.DONE], outcomes
        assert len(made) == 1, f"{len(made)} registrations from one form posted twice at once"
        assert {o.registration_id for o in outcomes} == {made[0].id}
        assert calls["n"] == 3, "the second post did not look again after the clash"
    finally:
        _remove(ids)


def test_a_post_that_looked_before_the_first_one_took_the_last_place():
    """Review of dev1, finding 1: the second post looked its key up before the
    first committed, and then met the rule the first one changed — the last
    place taken. It is answered with that registration, not with "volzet"."""
    import app.main  # noqa: F401
    from app.domains.activities import service
    from app.domains.activities.api import OutcomeKind

    ids = _committed_activity(price="0", is_free=True, max_participants=1)
    form = _form_for(ids)
    form.pop("payment_method")
    second_looked = threading.Event()
    first_done = threading.Event()
    real = service.registration_for_submission
    looked = {"first": 0, "second": 0}

    def held(db, key):
        name = threading.current_thread().name
        looked[name] += 1
        if name == "first" and looked["first"] == 1:
            second_looked.wait(20)  # the second has looked and found nothing
            return real(db, key)
        found = real(db, key)
        if name == "second" and looked["second"] == 1:
            second_looked.set()
            first_done.wait(20)  # until the first registration is committed
        return found

    real_post = _post_on_its_own

    def post_and_mark(ids_, form_, outcomes, errors):
        real_post(ids_, form_, outcomes, errors)
        if threading.current_thread().name == "first":
            first_done.set()

    try:
        globals()["_post_on_its_own"] = post_and_mark
        outcomes, errors = _race(ids, form, held)
        made = _made(ids)
        assert not errors, errors
        assert [o.kind for o in outcomes] == [OutcomeKind.DONE, OutcomeKind.DONE], [
            (o.kind, o.errors) for o in outcomes
        ]
        assert len(made) == 1
        assert {o.registration_id for o in outcomes} == {made[0].id}
    finally:
        globals()["_post_on_its_own"] = real_post
        _remove(ids)


def test_two_online_posts_at_once_start_one_payment(monkeypatch):
    """Review of dev1, finding 5: the money half of the race. Two online posts of
    one form at once, a provider stand-in that takes 0.3 s while the transaction
    is open: one registration, one payment record, one call to the provider, and
    both answers go to the same checkout."""
    import time

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.activities.api import OutcomeKind
    from app.domains.payment.api import PayableType, PaymentRecord
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult

    calls = {"provider": 0}

    def slow_create(self, amount, description, redirect_url, webhook_url, metadata):
        calls["provider"] += 1
        time.sleep(0.3)
        return PaymentResult(
            provider_payment_id="tr_race_1987",
            checkout_url="https://mollie.test/checkout/tr_race_1987",
            status="pending",
        )

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", slow_create)
    ids = _committed_activity(price="10.00")
    form = _form_for(ids, method="online")
    barrier = threading.Barrier(2, timeout=20)
    real = service.registration_for_submission
    looks = {"n": 0}

    def lookup_together(db, key):
        found = real(db, key)
        looks["n"] += 1
        if looks["n"] <= 2:
            barrier.wait()
        return found

    try:
        outcomes, errors = _race(ids, form, lookup_together)
        made = _made(ids)
        assert not errors, errors
        assert len(made) == 1
        assert [o.kind for o in outcomes] == [OutcomeKind.CHECKOUT, OutcomeKind.CHECKOUT]
        assert {o.checkout_url for o in outcomes} == {"https://mollie.test/checkout/tr_race_1987"}
        assert calls["provider"] == 1, "a second payment was started at the provider"
        db = SessionLocal()
        try:
            records = (
                db.query(PaymentRecord)
                .filter(
                    PaymentRecord.payable_type == PayableType.REGISTRATION,
                    PaymentRecord.payable_id == made[0].id,
                )
                .count()
            )
        finally:
            db.close()
        assert records == 1
    finally:
        _remove(ids)


def test_a_repost_after_the_registration_was_deleted_makes_a_new_one(client, db_session, paid):
    """Review of dev1, finding 2: a deleted registration frees its key (the index
    holds `deleted_at IS NULL`, as the lookup sees it), so a repost of its form —
    a back button on an old tab — is a new registration, as a first post is; not
    a database error out of the route."""
    from app.soft_delete import soft_delete

    form = _form(paid, token=_token())
    first = _post(client, "public", paid, form)
    assert first.status_code == 200
    [made] = _saved(db_session, paid)
    soft_delete(made)
    db_session.commit()

    again = _post(client, "public", paid, form)

    assert again.status_code == 200, again.text[:300]
    living = _saved(db_session, paid)
    assert len(living) == 1 and living[0].id != made.id


def test_the_key_is_the_tokens_time_and_random_part():
    token = form_guard.issue_token(now=1_760_000_000)
    stamp, nonce, _signature = token.split(".")
    assert form_guard.submission_key({form_guard.TOKEN_FIELD: token}) == f"{stamp}.{nonce}"
    assert form_guard.issue_token(now=1_760_000_000) != token, "two forms, one key"
    assert form_guard.submission_key({}) is None
    forged = f"{stamp}.{'0' * 16}.{_signature}"
    assert form_guard.submission_key({form_guard.TOKEN_FIELD: forged}) is None

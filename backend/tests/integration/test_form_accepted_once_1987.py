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
  the race test fails: the second post ends on the database's refusal.
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


def test_the_constraint_decides_when_two_posts_come_at_once():
    """Two posts of one form at the same moment, on two connections, each in its
    own committed transaction: both look for an earlier registration and find
    none before either inserts (a barrier holds them there); the unique index lets
    one through, and the other answers with it. One registration."""
    from fastapi import BackgroundTasks

    import app.main  # noqa: F401  the subscribers of a registration
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.activities.api import (
        Activity,
        OutcomeKind,
        public_channel,
        submit,
    )

    setup = SessionLocal()
    try:
        activity, component, product = seed_activity_with_product(setup, price="0", is_free=True)
        setup.commit()
        ids = (activity.id, component.id, product.id)
    finally:
        setup.close()

    form = _form((None, None, type("P", (), {"id": ids[2]})()), token=_token())
    form.pop("payment_method")
    barrier = threading.Barrier(2, timeout=20)
    real_lookup = service.registration_for_submission
    calls = {"n": 0}

    def lookup_together(db, key):
        found = real_lookup(db, key)
        calls["n"] += 1
        if calls["n"] <= 2:  # the first look of each post; not the one after the clash
            barrier.wait()
        return found

    outcomes: list = []
    errors: list = []

    def post():
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
        except Exception as exc:  # noqa: BLE001 — reported by the assertion below
            errors.append(exc)
        finally:
            db.close()

    service.registration_for_submission = lookup_together
    try:
        threads = [threading.Thread(target=post) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
    finally:
        service.registration_for_submission = real_lookup

    check = SessionLocal()
    try:
        made = check.query(Registration).filter(Registration.activity_id == ids[0]).all()
        assert not errors, errors
        assert [o.kind for o in outcomes] == [OutcomeKind.DONE, OutcomeKind.DONE], outcomes
        assert len(made) == 1, f"{len(made)} registrations from one form posted twice at once"
        assert {o.registration_id for o in outcomes} == {made[0].id}
        assert calls["n"] == 3, "the second post did not look again after the clash"
    finally:
        # The rows were committed on connections of their own: taken out by
        # hand, so no later test counts this activity.
        from app.domains.activities.api import (
            ActivityDate,
            ActivityProduct,
            ActivitySubRegistration,
            RegistrationItem,
        )

        gone = {"synchronize_session": False}
        regs = [
            r.id for r in check.query(Registration.id).filter(Registration.activity_id == ids[0])
        ]
        check.query(RegistrationItem).filter(RegistrationItem.registration_id.in_(regs)).delete(
            **gone
        )
        check.query(Registration).filter(Registration.id.in_(regs)).delete(**gone)
        check.query(ActivityProduct).filter(ActivityProduct.id == ids[2]).delete(**gone)
        check.query(ActivitySubRegistration).filter(ActivitySubRegistration.id == ids[1]).delete(
            **gone
        )
        check.query(ActivityDate).filter(ActivityDate.activity_id == ids[0]).delete(**gone)
        check.query(Activity).filter(Activity.id == ids[0]).delete(**gone)
        check.commit()
        check.close()


def test_the_key_is_the_tokens_time_and_random_part():
    token = form_guard.issue_token(now=1_760_000_000)
    stamp, nonce, _signature = token.split(".")
    assert form_guard.submission_key({form_guard.TOKEN_FIELD: token}) == f"{stamp}.{nonce}"
    assert form_guard.issue_token(now=1_760_000_000) != token, "two forms, one key"
    assert form_guard.submission_key({}) is None
    forged = f"{stamp}.{'0' * 16}.{_signature}"
    assert form_guard.submission_key({form_guard.TOKEN_FIELD: forged}) is None

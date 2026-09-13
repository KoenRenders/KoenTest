"""The data half of the evaluation harness (#917, CR-07 §9).

The bar for a release is 6/6 on the test set, graded by a person against a real
model. What runs here is the half a machine can judge: that every question still
HAS an answer in the universe, and that the answer is the number worked out by
hand in the seeded situation.

That half is worth its own tests because it is the half that rots silently. A
renamed object, a changed join, a measure that moves to another fact — none of
those break a screen, and all of them turn a question the assistant used to answer
into "dat kan ik niet". The model half would notice too, but only at the next
by-hand run, which is by definition after the change went in.

Would these tests be green if the subject were broken? The numbers come from
`_assistant_seed`, worked out from the description rather than read off a run, and
the seed is deliberately large enough that the small-cell threshold does not merge
the answers away. A broken join gives a different number, not an empty table.
"""
import json

import pytest

from app.domains.reporting.assistant import dispatcher
from app.domains.reporting.evaluation import (
    AGGREGATE_QUESTIONS, CATEGORY_COHORT, QUESTIONS,
)
from tests._assistant_seed import EXPECTED, TENANT, seed


@pytest.fixture
def situatie(db_session):
    return seed(db_session)


def test_the_set_is_the_set_the_change_request_describes():
    """Eight questions, six of them expressible today (CR-07 §3).

    A harness that quietly lost a question would still report a full score, which
    is the one failure mode a harness must not have.
    """
    assert [q.number for q in QUESTIONS] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(AGGREGATE_QUESTIONS) == 6
    cohort = [q for q in QUESTIONS if q.category == CATEGORY_COHORT]
    assert [q.number for q in cohort] == [7, 8]
    for vraag in QUESTIONS:
        assert vraag.must_contain, f"vraag {vraag.number} zegt niet wat goed is"


def test_every_aggregate_question_still_has_an_answer(db_session, situatie):
    """Each of the six, run through the real tool, checked against the hand count.

    Broken to see it red: `registration_quantity` swapped for
    `registration_count` in question 1 — the answer then reads 6 registrations
    where the seed has 6 places, which happens to be the same number here, so the
    test is written against the TOP ROW's full content and not against one figure.
    """
    dispatch = dispatcher(tenant_id=TENANT)
    for vraag in AGGREGATE_QUESTIONS:
        out = json.loads(dispatch("run_report", vraag.selection, db_session))
        assert "error" not in out, f"vraag {vraag.number}: {out.get('error')}"
        assert out["rows"], f"vraag {vraag.number} gaf geen rijen"
        top = out["rows"][0]
        for key, waarde in vraag.expect_top.items():
            gekregen = top.get(key)
            # De motor geeft geld als string terug; vergelijk op waarde.
            if isinstance(waarde, (int, float)) or hasattr(waarde, "quantize"):
                assert str(gekregen) == str(waarde), (
                    f"vraag {vraag.number}, kolom {key}: {gekregen} i.p.v. {waarde}")
            else:
                assert gekregen == waarde, (
                    f"vraag {vraag.number}, kolom {key}: {gekregen} i.p.v. {waarde}")


def test_the_seeded_situation_is_the_one_that_was_written_down(db_session,
                                                               situatie):
    """The seed's own numbers, checked before anything is graded against them.

    A harness resting on a seed nobody verified grades the seed. These four are
    the totals the questions lean on: how many households, how many people, what
    came in and what is still open.
    """
    dispatch = dispatcher(tenant_id=TENANT)

    gezinnen = json.loads(dispatch("run_report",
                                   {"objects": ["member_total_count"]}, db_session))
    assert gezinnen["totals"]["member_total_count"] == EXPECTED["households"]

    personen = json.loads(dispatch(
        "run_report", {"objects": ["person_age_group", "membership_person_count"]},
        db_session))
    assert (personen["totals"]["membership_person_count"]
            == EXPECTED["persons"])
    assert {r["person_age_group"]: r["membership_person_count"]
            for r in personen["rows"]} == EXPECTED["age_groups"]

    geld = json.loads(dispatch(
        "run_report", {"objects": ["payment_amount", "payment_amount_paid",
                                   "payment_open_amount"]}, db_session))
    totalen = geld["totals"]
    assert totalen["payment_amount_paid"] == str(EXPECTED["received"])
    assert totalen["payment_open_amount"] == str(EXPECTED["outstanding"])


def test_the_board_member_answer_is_a_token_and_not_a_name(db_session, situatie):
    """Question 5 is the one that needs phase 2 to exist at all.

    It asks which board member has the most members, and a board member is a
    person — so in phase 1 it was refused and the set could not be 6/6. It is
    answerable because the name travels as `persoon-90` and becomes a name again
    only on the screen. Worth its own test: this is the question that proves the
    tokenisation earns its keep rather than merely being safe.
    """
    from app.domains.reporting.assistant import detokenise

    out = json.loads(dispatcher(tenant_id=TENANT)(
        "run_report", {"objects": ["board_member", "membership_households"],
                       "sort": [{"object": "membership_households",
                                 "direction": "desc"}]}, db_session))
    top = out["rows"][0]
    assert top["board_member"].startswith("persoon-")
    assert top["membership_households"] == EXPECTED["per_board_member"]["A"]
    assert "Bestuur" not in json.dumps(out)

    # En op het scherm staat wél een naam.
    gerenderd = detokenise(db_session, f"Dat is {top['board_member']}.",
                           tenant_id=TENANT)
    assert "Bestuur" in gerenderd


# ── Phase 3: the cohort convention lives in the prompt ───────────────────────

def test_the_prompt_forbids_an_invented_probability(db_session):
    """Cohort reasoning is indicators and reasons, never a number (CR-07 §8).

    "70% kans dat dit gezin stopt" reads like a measurement and is not one; there
    is no model behind it and no history that was fitted. "Elk jaar lid sinds
    2019, dit jaar niet vernieuwd, geen inschrijvingen" says the same useful thing
    and can be checked by the person reading it.

    A prompt rule is weaker than a gate and this test does not pretend otherwise —
    what it holds is that the rule is still THERE. It is the kind of line that
    disappears in a rewrite because it reads like advice.
    """
    from app.domains.reporting.assistant import build_system_prompt

    prompt = build_system_prompt()
    assert "Vooruitkijken" in prompt
    assert "NOOIT een kans of een percentage" in prompt
    assert "INDICATOREN" in prompt
    # De weg naar de gegevens staat er ook: zonder 'list' kan hij de gezinnen zelf
    # niet ophalen en valt hij terug op tellingen.
    assert "layout op 'detail'" in prompt


def test_a_listing_answers_which_instead_of_how_many(db_session, situatie):
    """The shape a cohort answer needs, with the tokens doing the protecting.

    A listing has no GROUP BY, so the small-cell threshold has nothing to hold on
    to — this is precisely the row-level shape CR-07 §5.5 says the tokens are for.
    Without it, "welke gezinnen" can only be answered as a count, and questions 7
    and 8 have no data path at all — a grouped table on `member` is merged away by
    the threshold, because a household is a group of three.

    `membership_is_active` is in the selection because a listing needs at least one
    field of the fact itself to know which fact it is about. The engine says so in
    its refusal and the catalogue repeats it, so the model does not have to spend a
    round finding out.
    """
    out = json.loads(dispatcher(tenant_id=TENANT)(
        "run_report", {"objects": ["member", "membership_year",
                                   "membership_status", "membership_is_active"],
                       "layout": "detail"}, db_session))
    assert "error" not in out, out.get("error")
    assert len(out["rows"]) == EXPECTED["households"]
    assert all(str(r["member"]).startswith("gezin-") for r in out["rows"])

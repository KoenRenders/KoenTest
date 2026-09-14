"""The evaluation harness: can Raakje actually answer the questions? (#917, CR-07 §9)

The bar is **6/6 on the seeded test set, run by hand before each release that
touches the assistant**, with the result recorded in the release tracker. A
clarifying question counts as correct — asking which of two readings is meant is
a right answer, not a failure to answer.

Two halves, and the split is the whole idea:

- **The data half runs in CI.** Every question names the universe path that
  answers it and the number that path must produce on the seeded situation
  (`tests/_assistant_seed.py`). A test executes those selections and compares. It
  says nothing about the model — it says the question is still answerable, which
  is what quietly stops being true when an object is renamed or a join changes.
- **The model half is run by hand**, with a key, because it costs money and is not
  deterministic. `python -m app.domains.reporting.evaluation` puts each question
  to the assistant and prints the answer next to what a correct one must contain,
  so a person grades it in two minutes.

Why not automate the second half against the real model? Because a test whose
verdict depends on a model's wording is a test that goes red for reasons nobody
can fix, and gets switched off — and then the first half goes with it. Judgement
by a person, on a schedule, beats a flaky gate that everybody learns to ignore.

Questions 7 and 8 are cohort reasoning (§8) and carry no expected number: what is
graded there is the SHAPE of the answer — indicators and reasons, never an
invented percentage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

CATEGORY_AGGREGATE = "aggregaat"
CATEGORY_COHORT = "cohort"


@dataclass(frozen=True)
class Question:
    """One test-set question, with everything needed to grade an answer."""

    number: int
    text: str
    #: What a correct answer must contain, for the person doing the by-hand run.
    must_contain: str
    category: str = CATEGORY_AGGREGATE
    #: The universe path that answers it. Empty for a cohort question, which has
    #: no single selection — that is what makes it a cohort question.
    selection: dict[str, Any] = field(default_factory=dict)
    #: Per column key, the value the top row must carry on the seeded situation.
    expect_top: dict[str, Any] = field(default_factory=dict)


QUESTIONS: tuple[Question, ...] = (
    Question(
        number=1,
        text="Hoeveel mensen namen deel aan de Quiz?",
        must_contain="6 deelnemers aan de Quiz",
        selection={"objects": ["activity", "registration_quantity"],
                   "sort": [{"object": "registration_quantity",
                             "direction": "desc"}]},
        expect_top={"activity": "Quiz", "registration_quantity": 6},
    ),
    Question(
        number=2,
        text="Welke activiteiten trekken de meeste deelnemers?",
        must_contain="Quiz (6) vóór Wandeling (5)",
        selection={"objects": ["activity", "registration_quantity"],
                   "sort": [{"object": "registration_quantity",
                             "direction": "desc"}]},
        expect_top={"activity": "Quiz", "registration_quantity": 6},
    ),
    Question(
        number=3,
        text="Wat is de omzet per activiteit?",
        must_contain=("Quiz €30 en Wandeling €20, én het woord 'gefactureerd' of "
                      "'te betalen' — de standaardbetekenis moet benoemd zijn"),
        selection={"objects": ["activity", "payment_amount"],
                   "sort": [{"object": "payment_amount", "direction": "desc"}]},
        expect_top={"activity": "Quiz", "payment_amount": Decimal("30.00")},
    ),
    Question(
        number=4,
        text="In welke straat wonen de meeste leden?",
        must_contain="Dorpsstraat, met 12 personen",
        selection={"objects": ["address_street", "membership_person_count"],
                   "sort": [{"object": "membership_person_count",
                             "direction": "desc"}]},
        expect_top={"address_street": "Dorpsstraat",
                    "membership_person_count": 12},
    ),
    Question(
        number=5,
        text="Welk bestuurslid heeft de meeste leden?",
        must_contain=("het bestuurslid met 5 gezinnen, bij naam — op het scherm "
                      "staat een naam, in de payload een token"),
        selection={"objects": ["board_member", "membership_households"],
                   "sort": [{"object": "membership_households",
                             "direction": "desc"}]},
        expect_top={"membership_households": 5},
    ),
    Question(
        number=6,
        text="Wat is de verdeling per leeftijdsgroep?",
        must_contain="drie groepen van 9: 6-12, 26-40 en 41-60",
        selection={"objects": ["person_age_group", "membership_person_count"],
                   "sort": [{"object": "membership_person_count",
                             "direction": "desc"}]},
        expect_top={"membership_person_count": 9},
    ),
    Question(
        number=7,
        text="Welke leden vernieuwen volgend jaar waarschijnlijk niet?",
        must_contain=("indicatoren en redenen — 'elk jaar lid sinds X, dit jaar "
                      "niet vernieuwd, geen inschrijvingen' — en GEEN percentage"),
        category=CATEGORY_COHORT,
    ),
    Question(
        number=8,
        text="Wie komt er waarschijnlijk naar de Quiz?",
        must_contain=("patronen uit eerdere inschrijvingen, per gezin benoemd, "
                      "zonder verzonnen kans"),
        category=CATEGORY_COHORT,
    ),
)

AGGREGATE_QUESTIONS = tuple(q for q in QUESTIONS
                            if q.category == CATEGORY_AGGREGATE)


def ask(db, question: Question, *, tenant_id: int, actor: str = "evaluatie") -> str:
    """Put one question to the assistant, exactly as the screen does.

    Same loop, same guard, same log — anything else would grade a path nobody
    uses.
    """
    import time

    from app.config import settings
    from app.domains.chatbot.api import (
        GuardedProvider, admin_rules, get_provider, run_chat, sink_for,
    )
    from app.domains.mdm.api import person_name_parts
    from app.domains.reporting.assistant import (
        CAPABILITY, TOOL_SPECS, build_system_prompt, detokenise, dispatcher,
        scrub_question,
    )

    messages = [{"role": "system", "content": build_system_prompt()},
                {"role": "user",
                 "content": scrub_question(db, question.text, tenant_id=tenant_id)}]
    provider = GuardedProvider(
        get_provider(settings.admin_chat_model),
        admin_rules(lambda: person_name_parts(db), capability=CAPABILITY),
        sink_for(actor))
    antwoord = run_chat(db, messages, provider,
                        max_rounds=settings.admin_chat_max_tool_rounds,
                        tools=TOOL_SPECS, dispatch=dispatcher(tenant_id=tenant_id),
                        deadline=time.monotonic() + settings.admin_chat_timeout_seconds)
    return detokenise(db, antwoord, tenant_id=tenant_id)


def main() -> None:  # pragma: no cover - a by-hand command
    """Run the whole set and print it for grading.

    Against whatever data the database holds — so run it on HDEV after seeding, or
    locally against the test situation. The expectations printed alongside are the
    ones from the seeded situation; on other data, grade on shape.
    """
    from app.database import SessionLocal
    from app.kernel.tenancy import DEFAULT_TENANT_ID

    db = SessionLocal()
    try:
        for vraag in QUESTIONS:
            print("=" * 72)
            print(f"{vraag.number}. {vraag.text}")
            print(f"   verwacht: {vraag.must_contain}")
            print("-" * 72)
            try:
                print(ask(db, vraag, tenant_id=DEFAULT_TENANT_ID))
            except Exception as fout:
                print(f"   MISLUKT: {fout}")
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    main()

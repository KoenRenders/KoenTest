"""The guard and the writer's cleaning read the same text with the same word rule (#1969).

Every question to the newsletter assistant was refused for "a name from the
member administration" (production, 13 October 2026) while no question held
one. The refused payload carried examples of earlier letters that the writer's
cleaning (`scrub_names`) had cleaned — and the guard still found a name in
them. The two did not read the same thing: the cleaning read the text, the
guard read the payload's serialised form, in which a line's first word is read
with a letter glued on ("Even" as "neven", after a tab "Om" as "tom").

Since #1969 there is one function for "the words of a text that are name
parts", `name_words`; the cleaning replaces exactly those and the guard refuses
on exactly those, and the guard reads every string of the payload as text.
This file feeds one corpus of awkward texts through both.

Broken on purpose (13 October 2026, each put back):
- `findings`: the name check given the serialised payload again (`json.dumps`
  of the messages, lower-cased, with the old word pattern) → "the guard finds a
  name in what the cleaning returned" for the line-start texts, and "a line's
  first word is refused";
- `scrub_names`: a word rule of its own (`[a-z]+`) instead of `name_words` →
  "the guard finds a name in what the cleaning returned" for the accented and
  the capitalised names;
- `_texts`: a string that is JSON no longer read as its tree → the tool-result
  texts of the corpus fail both ways.
"""

import json

import pytest

from app.domains.chatbot.models import AiCapability, AiSurface
from app.domains.chatbot.seam import GuardRules, findings, name_words, scrub_names

#: Made-up name parts, as `mdm.person_name_parts` gives them: lower case.
NAMES = {"neven", "nels", "nijs", "nina", "tom", "peeters", "renée", "müller", "łukasz", "broeck"}
RULES = GuardRules(
    surface=AiSurface.ADMIN,
    capability=AiCapability.NEWSLETTER_DRAFTING,
    match_names=True,
    match_email=True,
    names=lambda: NAMES,
)


def _named(texts: list[str], role: str = "user") -> bool:
    payload = [{"role": "system", "content": "Schrijf een brief."}]
    payload += [{"role": role, "content": text} for text in texts]
    return any("naam" in reason for reason in findings(payload, RULES))


#: Texts without a name part, each with a word that a reader of the serialised
#: payload would glue to a line break or a tab: Even, Els, IJs, Ina, Om.
NO_NAME = [
    "Beste leden,\nEven voorstellen: het nieuwe seizoen.",
    "Programma\nEls dan niet, wel de anderen.\nIJs voor iedereen.\nIna-dag is voorbij.",
    "Kolom\tOm tien uur\tOp het plein",
    "Eerste brief.\n---\nEven later volgde de tweede.\r\nEls kwam niet.",
    "- punt een\n- punt twee\n\nEven goed nieuws.",
    json.dumps({"rows": [{"label": "Dag\nEven wachten", "notes": "Kolom\tOm tien uur"}]}),
]

#: Texts that hold a name part at an awkward place.
WITH_NAME = [
    "Peeters komt ook.",
    "Beste,\nPeeters komt ook.",
    "Beste,\n\nNina en Tom schrijven zich in.",
    "Kolom\tPeeters\tNina",
    'Ze zei: "Peeters" en ging.',
    "Dank aan (Peeters), Nina; Tom!",
    "PEETERS, peeters en Peeters.",
    "De familie Peeters-Nijs en Renée Müller.",
    "Łukasz komt ook, zegt Van den Broeck.",
    "Peeters's wafels en Tom’s koffie.",
    "Zie Nina&nbsp;en&nbsp;Tom op de foto.",
    "Onder­breking: Peeters komt.",
    "Regel een\r\nNina\r\nTom",
    json.dumps({"rows": [{"notes": "Dag\nPeeters komt", "contact": "Nina"}]}, ensure_ascii=False),
    json.dumps([{"notes": "Tabel\tTom", "more": ["Renée", {"deep": "Müller"}]}]),
]


@pytest.mark.parametrize("text", NO_NAME)
def test_a_lines_first_word_is_read_as_the_word_it_is(text):
    """What Koen met: no name in the text, and the call refused."""
    role = "tool" if text.startswith(("{", "[")) else "user"
    assert not _named([text], role), "a line's first word is refused"
    assert scrub_names(text, NAMES, "[naam]") == text or role == "tool"


@pytest.mark.parametrize("text", WITH_NAME)
def test_the_guard_finds_nothing_in_what_the_cleaning_returned(text):
    """One corpus through both: whatever the guard would refuse, the cleaning
    removes first — as a typed text and as a tool's result."""
    cleaned = scrub_names(text, NAMES, "[naam]")
    for role in ("user", "assistant", "tool"):
        assert not _named([cleaned], role), (
            f"the guard finds a name in what the cleaning returned ({role}): {cleaned!r}"
        )
    assert "[naam]" in cleaned


@pytest.mark.parametrize("text", WITH_NAME)
def test_the_guard_finds_a_name_part_at_every_position_of_a_text(text):
    """The same corpus, not cleaned: the guard refuses each, wherever in the
    text the name part stands — at its start, after a line break, a tab, a quote
    or a bracket, inside a tool's result."""
    for role in ("user", "tool"):
        assert _named([text], role), f"not refused ({role}): {text!r}"


def test_the_cleaning_replaces_exactly_the_words_the_guard_refuses_on():
    for text in WITH_NAME + NO_NAME:
        if text.startswith(("{", "[")):
            continue  # a tool's result is cleaned value by value, see above
        words = [match.group(0) for match in name_words(text, NAMES)]
        assert scrub_names(text, NAMES, "[naam]").count("[naam]") == len(words), text
        assert all(word.lower() in NAMES and len(word) >= 3 for word in words)


def test_a_short_word_and_a_word_inside_a_word_are_no_name_part():
    names = NAMES | {"an", "tom"}
    assert name_words("An en Jo, een automaat en atomen.", names) == []
    assert [m.group(0) for m in name_words("Tom2 en tom_3", names)] == ["Tom", "tom"]


def test_an_address_and_a_number_are_found_and_cleaned_at_a_lines_start_too():
    text = "Bel of mail:\n0473 12 34 56\ninfo@example.org\nBE68 5390 0754 7034"
    payload = [{"role": "user", "content": text}]
    assert findings(payload, RULES) == [
        "een e-mailadres",
        "een telefoonnummer",
        "een rekeningnummer",
    ]
    cleaned = scrub_names(text, NAMES, "[naam]")
    assert findings([{"role": "user", "content": cleaned}], RULES) == []


#: A JSON string in which a key stands twice, at the top and one level down.
REPEATED_KEY = [
    '{"notes": "Peeters komt", "notes": "niemand"}',
    '{"rows": [{"contact": "Nina", "contact": "de voorzitter"}]}',
]


@pytest.mark.parametrize("text", REPEATED_KEY)
def test_a_json_string_is_read_by_its_pairs(text):
    """A JSON string is read by its pairs, so what is read is what leaves: every
    value of a key that stands twice is read, as a typed text and as a tool's
    result, and the cleaning returns a text the guard finds nothing in.

    Proven red by reading the string as a mapping again (`json.loads` without
    the pairs hook): both strings fail on the first assertion."""
    for role in ("user", "tool"):
        assert _named([text], role), f"not refused ({role}): {text!r}"
    cleaned = scrub_names(text, NAMES, "[naam]")
    for role in ("user", "tool"):
        assert not _named([cleaned], role), cleaned


def test_a_string_nested_too_deep_to_parse_is_read_as_plain_text():
    """Very many opening brackets make the parser give up; the string is then
    no tree but the text it is, for the guard and for the cleaning alike.

    Proven red by catching `ValueError` only: the call raises `RecursionError`
    instead of answering."""
    text = "[" * 100_000 + " Peeters komt ook."
    for role in ("user", "tool"):
        assert _named([text], role)
    cleaned = scrub_names(text, NAMES, "[naam]")
    assert cleaned.endswith(" [naam] komt ook.")
    assert not _named([cleaned])


#: Closed nesting at a depth the parser still takes and a walk does not.
DEEP = 1_500
TOO_DEEP_TO_WALK = [
    "[" * DEEP + '"Peeters komt ook."' + "]" * DEEP,
    '{"a": ' * DEEP + '"Peeters komt ook."' + "}" * DEEP,
]


@pytest.mark.parametrize("text", TOO_DEEP_TO_WALK, ids=["list", "object"])
def test_a_string_that_parses_but_nests_too_deep_to_walk_is_plain_text(text):
    """Between the depth a walk takes and the depth the parser gives up at, the
    string is no tree either: the guard and the cleaning read it as plain text
    and both answer.

    Proven red by letting `_too_deep` answer False: the guard's reading and the
    cleaning raise `RecursionError` for the list and for the object."""
    for role in ("user", "tool"):
        assert _named([text], role)
    cleaned = scrub_names(text, NAMES, "[naam]")
    assert "[naam] komt ook." in cleaned and "Peeters" not in cleaned
    assert not _named([cleaned])


def test_a_tree_of_an_ordinary_depth_is_still_read_as_a_tree():
    """The ceiling refuses nothing a tool sends: twenty levels deep, a line's
    first word is still read as the word it is (as plain text the escaped line
    break would glue a letter to it).

    Proven red by setting the ceiling to 5: the word is refused."""
    text = json.dumps({"rows": [[[[[[[[[[[[[[[[[["Dag\nEven wachten"]]]]]]]]]]]]]]]]]]})
    assert not _named([text], "tool")

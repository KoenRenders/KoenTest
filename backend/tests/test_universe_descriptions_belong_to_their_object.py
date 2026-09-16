"""Each description is about ITS object, not its neighbour's (#980).

In CR-07 phase 1 a script sharpened the object descriptions by finding, per key,
the next `description="…"`. Where the target already had a parenthesised
description it skipped it and overwrote the NEXT object's — and that ran on as a
chain. On master "Activiteit" was described as a revenue amount and "Locatie" as a
year. That text is both the tooltip in the reports panel and the whole of what the
assistant knows about the object.

**Why the existing gate could not see it.** `test_every_description_can_carry_its_weight`
checks that a description is long enough, ends in a full stop, and appears only
once. A shifted text still appears only once. A list-driven gate checks that there
IS a description, not what it is ABOUT — so this file pins the meaning per object,
by hand, the way the name regression of #954 was pinned.

Each row names a word that belongs to that object and a word that belongs to the
text that was wrongly on it. The second one is what makes the row able to go red:
put the shifted text back and it is there.

Broken to see it red: `activity` given back the revenue text — the first row
names it.
"""
import pytest

from app.domains.reporting.universe import BY_KEY

# (object, hoort erin, hoort er NIET in — het woord uit de verschoven tekst)
PINS = [
    ("activity", "Naam van de activiteit", "omzet"),
    ("registration_amount", "inschrijfregels", "Klik door"),
    ("activity_year", "jaar", "Waar de activiteit doorgaat"),
    ("activity_location", "Waar de activiteit doorgaat", "jaar van de eerste datum"),
    ("activity_cancelled", "geannuleerd", "Waar de activiteit doorgaat"),
    ("activity_members_only", "leden", "geannuleerd"),
    ("membership_year", "lidmaatschap", "betaald"),
    ("paid_date_year", "betaald", "lidmaatschap gaat"),
    ("person_gender", "geslacht", "Hoofdlid, partner"),
    ("person_relation_type", "Hoofdlid, partner", "geslacht"),
]


@pytest.mark.parametrize("key, hoort, hoort_niet", PINS, ids=[p[0] for p in PINS])
def test_the_description_is_about_this_object(key, hoort, hoort_niet):
    tekst = BY_KEY[key].description
    assert hoort.lower() in tekst.lower(), (
        f"de beschrijving van `{key}` ({BY_KEY[key].name}) gaat niet over dit "
        f"object: {tekst[:120]!r}")
    assert hoort_niet.lower() not in tekst.lower(), (
        f"de beschrijving van `{key}` ({BY_KEY[key].name}) bevat "
        f"{hoort_niet!r} — dat is de tekst van een buurobject (#980)")

"""CR-07 §5.1 — every universe object declares how far it may travel towards an LLM.

The assistant sends data to Mistral. What may go out is therefore a property of the object
itself, declared once, and **not a rule someone applies at the call site**: a flag somebody
can forget is the wrong default on an outbound channel, because then forgetting decides what
leaves.

Hence `ai_exposure` has **no default in the dataclass**. Adding an object without deciding its
exposure is an import error — CI is red before a single test runs. That is the strongest of
the three guards here, and it is the one this file cannot test directly: a missing field means
the module does not import, so the failure lands everywhere at once rather than in one
assertion. What these tests add is the coherence the dataclass cannot express.

Broken on purpose to check that they can go red, the #678 way:

- `ai_exposure=AiExposure.TOKENISED` on `activity_year` (a plain year, no entity id) → the
  entity-id test falls over naming that object;
- the whole field removed from one declaration → **the module does not import**, and the
  entire suite goes red rather than this file alone. That is the intended shape: a
  classification you can forget is no classification.
"""
import pytest

from app.domains.reporting.universe import OBJECTS, AiExposure

pytestmark = pytest.mark.ui_agnostisch


def test_every_object_declares_an_exposure_from_the_enum():
    """De dataclass eist het veld; deze test eist dat er een geldige waarde in staat.

    Een string die toevallig klopt (`"admin_plain"` i.p.v. de enum) zou anders door elke
    vergelijking heen glippen die op de enum test.
    """
    assert OBJECTS, "geen objecten gevonden — deze poort bewaakt niets (#678)"

    fout = [o.key for o in OBJECTS if not isinstance(o.ai_exposure, AiExposure)]

    assert not fout, f"deze objecten dragen geen AiExposure-waarde: {fout}"


def test_a_tokenised_object_has_an_entity_id():
    """CR-07 §5.2: een token wordt gebouwd uit het entiteit-id van de rij.

    Een object dat een persoon aanwijst maar geen id in zijn rij heeft, kan niet
    getokeniseerd worden — dan zou de naam zelf naar Mistral moeten of het object zou
    stilzwijgend ongemaskeerd doorgaan. Zo'n object hoort dus `none` te zijn, niet
    `admin_tokenised`, en deze test is wat dat afdwingt.
    """
    getokeniseerd = [o for o in OBJECTS if o.ai_exposure is AiExposure.TOKENISED]

    assert getokeniseerd, "geen enkel object is getokeniseerd — dan toetst dit niets"
    zonder = [o.key for o in getokeniseerd if not o.entity_source]
    assert not zonder, (
        f"deze objecten zijn admin_tokenised maar dragen geen entiteit-id: {zonder}. "
        f"Zonder id valt er niets te tokeniseren — declareer ze als `none`, of geef ze "
        f"een `entity_sql`.")


def test_the_three_values_are_all_in_use():
    """De tegenproef bij de twee tests hierboven.

    Zou alles `admin_plain` zijn, dan staan die groen en beschermt de classificatie
    niets. Deze test faalt zodra iemand de classificatie tot een formaliteit maakt.
    """
    in_gebruik = {o.ai_exposure for o in OBJECTS}

    assert in_gebruik == set(AiExposure), (
        f"niet elke waarde wordt gebruikt: {sorted(w.value for w in set(AiExposure) - in_gebruik)} "
        f"ontbreekt — is de classificatie nog een afweging of een invuloefening?")


def test_the_objects_that_name_a_person_are_not_plain():
    """De concrete lijst uit §5.1, als vangrail tegen een herclassificatie die niemand
    opmerkt.

    Deze namen staan in de CR met zoveel woorden: hoofdlid, partner, adresregel,
    huisnummer, bus, en de gezins-/persoonsdimensies. Ze mogen alles zijn behalve
    `admin_plain`.
    """
    per_key = {o.key: o for o in OBJECTS}
    persoonsnamen = ("member", "member_head_name", "member_partner_name", "address_line",
                     "address_house_number", "address_bus", "board_member")

    for key in persoonsnamen:
        assert key in per_key, f"{key} bestaat niet meer — is deze lijst nog actueel?"
        assert per_key[key].ai_exposure is not AiExposure.PLAIN, (
            f"{key} wijst een persoon aan en staat op admin_plain; dan gaat een naam "
            f"ongemaskeerd naar Mistral")


def test_free_text_fields_reach_no_model():
    """Vrije tekst is niet te classificeren per veld: er kan van alles in staan.

    Een notitie van de penningmeester, het onderwerp van een taak, een betaallabel dat een
    persoonsnaam draagt (migratie 102 zegt dat met zoveel woorden) — daar valt geen token
    op te plakken, dus die gaan nergens heen.
    """
    per_key = {o.key: o for o in OBJECTS}

    for key in ("payment_note", "task_detail", "payment_payable_label"):
        assert per_key[key].ai_exposure is AiExposure.NONE, (
            f"{key} is vrije tekst en zou een model kunnen bereiken")


# ── Phase 2: a token needs a prefix as much as it needs an id ────────────────

KNOWN_PREFIXES = {"gezin", "persoon"}


def test_a_tokenised_object_declares_what_its_token_is_called():
    """`token_prefix` is the word before the id: `gezin-23`, `persoon-90`.

    Without it the tokenisation would have to guess a name from the column, and a
    guess here is worse than it sounds: the prefix is what the inbound
    re-translation looks the id up by, so a wrong one silently fails to resolve
    and the admin reads `gezin-23` where a name was promised.

    The prefix belongs to the ENTITY and not to the object, which is why more than
    one object shares one: 'Hoofdlid' and 'Adres' both point at a household, so the
    same row gives `gezin-23` twice — and that is exactly what the model should
    see.

    Broken to see it red: the prefix removed from `member_head_name` (the first
    assertion names it), and set to `"huishouden"` (the second — a prefix the
    re-translation has no lookup for would resolve to nothing, forever).
    """
    tokenised = [o for o in OBJECTS if o.ai_exposure is AiExposure.TOKENISED]
    assert len(tokenised) >= 5, (
        "deze poort draait over de getokeniseerde objecten; vindt ze er bijna "
        "geen, dan bewaakt ze niets (#678)"
    )

    zonder = [o.key for o in tokenised if not o.token_prefix]
    assert not zonder, f"deze objecten worden getokeniseerd zonder prefix: {zonder}"

    onbekend = {o.key: o.token_prefix for o in tokenised
                if o.token_prefix not in KNOWN_PREFIXES}
    assert not onbekend, (
        "deze prefixen kent de terugvertaling niet, dus hun token wordt op het "
        f"scherm nooit een naam: {onbekend}. Voeg de opzoeking toe in "
        "`assistant._LABEL_SQL`, of gebruik een bestaande prefix."
    )


def test_an_object_that_is_not_tokenised_carries_no_prefix():
    """A prefix on a plain object is a leftover, and leftovers get believed.

    It would read as "this is tokenised" to the next person, while the value goes
    out as itself — the most expensive kind of wrong documentation, because it is
    in the code.
    """
    fout = {o.key: o.token_prefix for o in OBJECTS
            if o.token_prefix and o.ai_exposure is not AiExposure.TOKENISED}
    assert not fout, f"prefix zonder tokenisatie: {fout}"

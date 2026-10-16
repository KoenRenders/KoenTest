"""The public bot exports exactly the fields it declares (CR-07 §5.1).

A tool result travels to Mistral in full. So the question "which fields leave the
building?" must have an answer that is written down rather than reconstructed by
reading three serialisers — and the answer must be kept honest by something other
than attention. `PUBLIC_FIELD_CONTRACT` is the declaration; this gate compares it
with what the tools actually emit, in both directions:

- **a key the tools emit but the contract does not name** is a new export to a
  third party, added by someone who was changing a serialiser and thinking about
  something else;
- **a key the contract names but no scenario emits** is a contract rotting in
  place — the entry that stays behind after a field is removed quietly re-permits
  it the day the name returns.

Both directions need the scenarios to actually cover the branches, so the
scenarios are run against seeded data and their count is asserted (#678): a
fixture that stops seeding would otherwise make this gate scan an empty result
and go green.

Broken on purpose, each restored after:
  - `"phone": None` added to the activity serialiser → the emitted-but-undeclared
    half fails, naming `get_activities` and `activities[].phone`;
  - `"location"` removed from the contract → same half, naming that key;
  - `"info_text"` removed from the `components[]` serialiser → the declared-but-
    never-emitted half fails, so a field cannot disappear from the code while its
    permission stays behind.
"""

import json
from datetime import date, time, timedelta

from app.domains.activities.api import Activity, ActivityDate
from app.domains.activities.models import ActivityProduct, ActivitySubRegistration
from app.domains.chatbot.tools import (
    PUBLIC_FIELD_CONTRACT,
    STRUCTURAL_NAMES,
    STRUCTURE,
    declared_fields,
    execute_tool,
)


def _seeded_activity(db):
    """One activity that exercises every branch of the detail serialiser."""
    a = Activity(
        name="Buurtfeest",
        location="De Zaal",
        members_only=False,
        # #1028: hier stond `notes`, en dat veld ging integraal naar het model —
        # precies wat deze gate moest vangen en waarvoor de kolom verdwenen is.
        # De publieke omschrijving is wat de bezoeker wél mag lezen.
        description="Een feest voor de hele buurt, met taart.",
    )
    db.add(a)
    db.flush()
    db.add(
        ActivityDate(
            activity_id=a.id,
            start_date=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=7),
            start_time=time(14, 0),
            end_time=time(18, 0),
        )
    )
    component = ActivitySubRegistration(
        activity_id=a.id,
        name="Deelname",
        description="Voor alle leeftijden.",
        price=5,
        member_price=3,
        is_free=False,
    )
    db.add(component)
    db.flush()
    db.add(
        ActivityProduct(
            component_id=component.id,
            name="Pannenkoek",
            price=2,
            member_price=1,
            is_free=False,
        )
    )
    db.flush()
    return a


def _keys_by_path(value, path: str, out: dict[str, set[str]]) -> None:
    """Collect, per path, the keys a result carries. ``"" `` is the root."""
    if isinstance(value, dict):
        out.setdefault(path, set()).update(value.keys())
        for key, child in value.items():
            _keys_by_path(child, f"{path}.{key}" if path else key, out)
    elif isinstance(value, list):
        for item in value:
            _keys_by_path(item, f"{path}[]", out)


def _scenarios(db):
    """One call per branch the serialisers can take."""
    activity = _seeded_activity(db)
    return [
        ("get_activities", {}),
        ("get_activities", {"when": "past"}),
        ("get_activity_detail", {"activity_id": activity.id}),
        ("get_activity_detail", {"activity_id": 999_999}),  # de weigering
        ("submit_idea", {"name": "T", "content": "c", "email": "t@example.org"}),
        ("submit_idea", {"name": "", "content": "c", "email": ""}),  # de foutvorm
    ]


def _emitted(db) -> dict[str, dict[str, set[str]]]:
    scenarios = _scenarios(db)
    assert len(scenarios) >= 6, (
        "deze gate draait alle tool-takken af; met minder scenario's dekt ze niet "
        "elke serialiser en staat ze groen op wat ze niet zag (#678)"
    )
    emitted: dict[str, dict[str, set[str]]] = {}
    for tool, arguments in scenarios:
        result = json.loads(execute_tool(tool, arguments, db))
        _keys_by_path(result, "", emitted.setdefault(tool, {}))
    return emitted


def test_no_tool_emits_a_field_the_contract_does_not_declare(db_session):
    emitted = _emitted(db_session)
    assert set(emitted) == set(PUBLIC_FIELD_CONTRACT), (
        "het contract en de gedraaide tools gaan over verschillende tools: "
        f"contract {sorted(PUBLIC_FIELD_CONTRACT)}, gedraaid {sorted(emitted)}"
    )

    undeclared = []
    for tool, paths in emitted.items():
        for path, keys in paths.items():
            allowed = declared_fields(tool, path)
            for key in sorted(keys - allowed):
                undeclared.append(f"{tool}: {path or '(wortel)'}.{key}")

    assert not undeclared, (
        "deze velden verlaten het gebouw zonder in PUBLIC_FIELD_CONTRACT te staan:\n  "
        + "\n  ".join(undeclared)
        + "\n\nEen tool-resultaat gaat integraal naar Mistral (CR-07 §5.1). Voeg het "
        "veld toe aan het contract als het er hoort — en als het een persoonsgegeven "
        "draagt, hoort het er niet."
    )


def test_the_contract_declares_no_field_that_is_never_emitted(db_session):
    emitted = _emitted(db_session)
    stale = []
    for tool, paths in PUBLIC_FIELD_CONTRACT.items():
        for path in paths:
            keys = declared_fields(tool, path)
            seen = emitted.get(tool, {}).get(path, set())
            for key in sorted(keys - seen):
                stale.append(f"{tool}: {path or '(wortel)'}.{key}")

    assert not stale, (
        "het contract geeft toestemming voor velden die geen enkele tool-tak nog "
        "uitstuurt:\n  "
        + "\n  ".join(stale)
        + "\n\nHaal ze weg. Een achtergebleven regel is geen documentatie maar een "
        "openstaande deur voor de dag dat iemand de naam hergebruikt."
    )


def _unexplained_structure(contract) -> list[str]:
    """The fields declared `STRUCTURE` whose name is no structural name: a way round the register."""
    return [
        f"{tool}: {path or '(root)'}.{name}"
        for tool, paths in contract.items()
        for path, fields in paths.items()
        for name, keys in fields.items()
        if not keys and name not in STRUCTURAL_NAMES
    ]


def _non_public_keys(contract) -> list[str]:
    """The register keys a contract names that are unknown or not `publiek`, with the field."""
    from app.domains.registry import load_all_models
    from app.kernel.attributes import AiExposure, attribute

    load_all_models()
    problems = []
    for tool, paths in contract.items():
        for path, fields in paths.items():
            for name, keys in fields.items():
                for key in keys:
                    try:
                        level = attribute(key).ai_exposure
                    except LookupError:
                        problems.append(
                            f"{tool}: {path or '(root)'}.{name} names {key}, which is not in the register"
                        )
                        continue
                    if level is not AiExposure.PUBLIC:
                        problems.append(
                            f"{tool}: {path or '(root)'}.{name} comes from {key}, which the register "
                            f"classifies {level.value}"
                        )
    return problems


def test_every_field_of_the_contract_comes_from_a_public_register_entry():
    """One list, not two: the register decides what may travel, the contract names where each
    field of an answer comes from (CR-33 phase 2, review of #2053). A field that comes from a
    datum the register does not call public cannot be declared until the register says so."""
    assert not _non_public_keys(PUBLIC_FIELD_CONTRACT), "\n  ".join(
        ["the public bot would send what the register does not call public:"]
        + _non_public_keys(PUBLIC_FIELD_CONTRACT)
    )
    named = [
        k for paths in PUBLIC_FIELD_CONTRACT.values() for f in paths.values() for k in f.values()
    ]
    assert sum(1 for keys in named if keys is not STRUCTURE and keys) >= 15, (
        "the contract names too few register keys — is it still read?"
    )


def test_a_contract_field_from_a_datum_that_is_not_public_is_named():
    """The gate can go red, additively: a field `street` that comes from the household's street
    (internal) and one from a key nobody registered."""
    added = {
        "get_activities": {
            "activities[]": {
                "street": ("mdm.address.street",),
                "ghost": ("activities.activity.no_such_column",),
            }
        }
    }
    found = _non_public_keys(added)
    assert any("street" in line and "internal" in line for line in found), found
    assert any("ghost" in line and "not in the register" in line for line in found), found


def test_a_field_cannot_skip_the_register_by_calling_itself_structure():
    """The contract's own fields use `STRUCTURE` only under the closed set of structural names, and
    the gate can go red: an additive `organiser: STRUCTURE`."""
    assert not _unexplained_structure(PUBLIC_FIELD_CONTRACT), _unexplained_structure(
        PUBLIC_FIELD_CONTRACT
    )
    added = {"get_activity_detail": {"": {"organiser": STRUCTURE, "id": STRUCTURE}}}
    assert _unexplained_structure(added) == ["get_activity_detail: (root).organiser"]

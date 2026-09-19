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
from app.domains.chatbot.tools import PUBLIC_FIELD_CONTRACT, execute_tool


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
            component_id=component.id, name="Pannenkoek", price=2, member_price=1,
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
        ("get_activity_detail", {"activity_id": 999_999}),          # de weigering
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
            allowed = PUBLIC_FIELD_CONTRACT[tool].get(path, set())
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
        for path, keys in paths.items():
            seen = emitted.get(tool, {}).get(path, set())
            for key in sorted(keys - seen):
                stale.append(f"{tool}: {path or '(wortel)'}.{key}")

    assert not stale, (
        "het contract geeft toestemming voor velden die geen enkele tool-tak nog "
        "uitstuurt:\n  " + "\n  ".join(stale)
        + "\n\nHaal ze weg. Een achtergebleven regel is geen documentatie maar een "
        "openstaande deur voor de dag dat iemand de naam hergebruikt."
    )

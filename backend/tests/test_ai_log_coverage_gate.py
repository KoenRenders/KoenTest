"""Gate: no AI call leaves without a row in the AI log (#978).

A cost read from `ai.ai_call_log` is only as right as every path that writes
into it. A new provider or a new surface must not fall silently outside the
total. Three rules, read from the source:

1. **Every chat provider is wrapped, with a sink.** A call to `get_provider(…)`
   outside the factory is the first argument of `GuardedProvider(…)`, and that
   call passes `sink_for(…)`. The seam writes the row; without the sink it
   writes nothing.
2. **Every dictation provider is logged by its route.** A module that calls
   `get_stt_provider(…)` also calls `sink_for(…)`.
3. **A module that talks to an AI vendor directly is known.** Any file that
   names a vendor host or SDK is listed in `DIRECT`, with the rule that covers
   it. A new one fails here until someone has decided how it is logged.

The behaviour itself — that the row really appears — is tested per path in
`test_ai_call_log_cost.py`; this gate makes sure there is no path that test
does not know about.

Broken to see it red (measured): `sink_for(actor)` removed from the
`GuardedProvider(…)` in `newsletter/drafting.py` → rule 1 fails naming that
file; the `sink_for` call removed from the STT route → rule 2 fails; a file
with "api.mistral.ai" in it added under `app/` → rule 3 fails.
"""
import ast
from pathlib import Path

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

VENDOR_MARKERS = ("api.mistral.ai", "mistralai", "api.bfl.ai")

# Files that reach a vendor themselves, and what makes their calls land in the log.
DIRECT = {
    "domains/chatbot/providers/mistral.py": "rule 1 — only built by get_provider",
    "domains/stt/providers/voxtral.py": "rule 2 — only built by get_stt_provider",
    "domains/media/extraction.py": "logs each OCR call itself (_log_ocr)",
}

FACTORIES = {"domains/chatbot/providers/factory.py", "domains/stt/providers/factory.py"}


def _python():
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/",
                     minstens=100)


def _rel(pad: Path) -> str:
    return pad.relative_to(APP).as_posix()


def _naam(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    return f.attr if isinstance(f, ast.Attribute) else ""


def _calls(tree, naam):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _naam(n) == naam]


def test_every_chat_provider_is_wrapped_with_a_sink():
    fouten, gezien = [], 0
    for pad in _python():
        if _rel(pad) in FACTORIES:
            continue
        tree = ast.parse(pad.read_text(encoding="utf-8"))
        gewikkeld = set()
        for g in _calls(tree, "GuardedProvider"):
            args = list(g.args) + [k.value for k in g.keywords]
            eerste = g.args[0] if g.args else None
            if isinstance(eerste, ast.Call) and _naam(eerste) == "get_provider" and any(
                    isinstance(a, ast.Call) and _naam(a) == "sink_for" for a in args):
                gewikkeld.add(id(eerste))
        for call in _calls(tree, "get_provider"):
            gezien += 1
            if id(call) not in gewikkeld:
                fouten.append(f"{_rel(pad)}:{call.lineno}")
    assert gezien >= 4, f"only {gezien} get_provider calls found — is the gate looking?"
    assert not fouten, (
        "A chat provider must be built as GuardedProvider(get_provider(…), rules, "
        "sink_for(…)) — otherwise its calls are missing from the AI log:\n  "
        + "\n  ".join(fouten))


def test_every_dictation_provider_is_logged_by_its_route():
    fouten, gezien = [], 0
    for pad in _python():
        if _rel(pad) in FACTORIES:
            continue
        tree = ast.parse(pad.read_text(encoding="utf-8"))
        if _calls(tree, "get_stt_provider"):
            gezien += 1
            if not _calls(tree, "sink_for"):
                fouten.append(_rel(pad))
    assert gezien >= 1, "no get_stt_provider call found — is the gate looking?"
    assert not fouten, "A dictation route must write the AI log:\n  " + "\n  ".join(fouten)


def test_a_module_that_reaches_a_vendor_is_known():
    gevonden = {
        _rel(pad) for pad in _python()
        if _rel(pad) != "config.py"
        and any(m in pad.read_text(encoding="utf-8") for m in VENDOR_MARKERS)
    }
    assert gevonden - set(DIRECT) == set(), (
        "New code reaches an AI vendor. Decide how its calls reach the AI log, "
        "test it in test_ai_call_log_cost.py, and add it to DIRECT: "
        f"{sorted(gevonden - set(DIRECT))}")
    assert set(DIRECT) - gevonden == set(), (
        f"DIRECT names files that no longer reach a vendor: {sorted(set(DIRECT) - gevonden)}")


def test_the_ocr_function_writes_the_log_itself():
    tree = ast.parse((APP / "domains/media/extraction.py").read_text(encoding="utf-8"))
    ocr = next(n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_ocr_via_mistral")
    assert _calls(ocr, "_log_ocr"), "_ocr_via_mistral no longer writes the AI log"

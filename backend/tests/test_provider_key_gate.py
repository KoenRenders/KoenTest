"""Refuses a module that reads a model vendor's key or names its address outside the place that vendor owns · hard · since #2007.

CR-33 C4.6, F12: "one port" is a measured fact only when no second door exists. Two vendors
reach a model from this application, and each has ONE place where its key is read and its address
stands (review of #2053, 16 October 2026: the second vendor was named in a docstring and checked
by a string that was still in a file, which gates nothing):

| vendor | what | key | address | where |
|---|---|---|---|---|
| Mistral | text, OCR, dictation | `mistral_api_key` | `api.mistral.ai` | `config.py` and `domains/chatbot/` |
| Black Forest Labs (EU endpoint) | design images | `bfl_api_key` | `bfl.ai` | `config.py` and `domains/designstudio/imaging.py` |

Until phase 2 of CR-33 the document reader posted to the OCR address itself, with the key,
outside the seam: it is a provider method now (`LLMProvider.ocr`) and this gate keeps the next one
from being written. The image vendor's calls are logged by the design studio's job handler and
checked by `test_ai_log_coverage_gate.py` (rule 5); its prompt is the administrator's scene text,
which the pattern guard scans whatever its language (`imaging.translate_scene`).

Proven red with an ADDITIVE violation (16 October 2026): a line `KEY = settings.mistral_api_key`
added to `media/extraction.py` fails the Mistral key test naming that file; `settings.bfl_api_key`
added to `designstudio/service.py` fails the BFL key test; a string `"https://api.eu.bfl.ai/x"`
added to `designstudio/handlers.py` fails the BFL address test. The search is case-insensitive:
`os.environ["BFL_API_KEY"]` is found as well as `settings.bfl_api_key`.
"""

from pathlib import Path

import pytest

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

#: vendor → (what stands only in its place, the places that may hold it, the file that must).
VENDORS = {
    "mistral": {
        "needles": ("mistral_api_key", "api.mistral.ai"),
        "places": ("config.py", "domains/chatbot/"),
        "must_hold": "domains/chatbot/providers/mistral.py",
    },
    "bfl": {
        "needles": ("bfl_api_key", "bfl.ai"),
        "places": ("config.py", "domains/designstudio/imaging.py"),
        "must_hold": "domains/designstudio/imaging.py",
    },
}


def _python():
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/", minstens=100)


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _in(rel: str, places: tuple[str, ...]) -> bool:
    return any(rel == place or (place.endswith("/") and rel.startswith(place)) for place in places)


def outside(needles: tuple[str, ...], places: tuple[str, ...]) -> set[str]:
    """The files that hold one of the needles without being one of the vendor's places."""
    return {
        _rel(p)
        for p in _python()
        if not _in(_rel(p), places)
        and any(n in p.read_text(encoding="utf-8").lower() for n in needles)
    }


@pytest.mark.parametrize("vendor", sorted(VENDORS))
def test_a_vendors_key_and_address_stand_only_in_its_place(vendor):
    spec = VENDORS[vendor]
    found = outside(spec["needles"], spec["places"])
    assert not found, (
        f"the key or the address of {vendor} stands outside {spec['places']}; a call to a model "
        "goes through `GuardedProvider` or a provider method (CR-33 F12):\n  "
        + "\n  ".join(sorted(found))
    )


@pytest.mark.parametrize("vendor", sorted(VENDORS))
def test_the_gate_looks_at_the_vendors_place(vendor):
    """It can go red: the place really holds the needles (a moved file would make the gate green
    on nothing), and each needle of each vendor is read from the file that owns it."""
    spec = VENDORS[vendor]
    text = (APP / spec["must_hold"]).read_text(encoding="utf-8")
    for needle in spec["needles"]:
        held = needle in text.lower() or any(
            needle in p.read_text(encoding="utf-8").lower()
            for p in _python()
            if _in(_rel(p), spec["places"])
        )
        assert held, f"{needle} stands nowhere in {spec['places']} — is the gate still looking?"


def test_the_gate_sees_a_second_reader_of_the_bfl_key():
    """The additive proof as a test: a file outside the place that names the key is found."""
    found = outside(("bfl_api_key", "bfl.ai"), ("config.py",))
    assert "domains/designstudio/imaging.py" in found, "imaging.py holds the BFL key and address"

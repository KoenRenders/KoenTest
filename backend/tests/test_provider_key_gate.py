"""Refuses a module that reads the language-model provider's key or names its address outside the chatbot's provider folder · hard · since #2007.

CR-33 C4.6, F12: "one port" is a measured fact only when no second door exists. The key of
the provider (`settings.mistral_api_key`) is read in `config.py` and inside the chatbot
domain (the chat provider, the dictation provider and the factories that choose between
them), and the address of a model (`api.mistral.ai`) stands only in those files. Until
phase 2 of CR-33 the document reader posted to the OCR address itself, with the key,
outside the seam: it is a provider method now (`LLMProvider.ocr`) and this gate keeps the
next one from being written.

What stays outside, named and not hidden: the image generator of the design studio
(`api.eu.bfl.ai`, its own key and its own budget gate, prompts only — the scene is translated
through the seam first); it is a vendor of images and not of text, and has its row in
`test_ai_log_coverage_gate.py`.

Proven red with an ADDITIVE violation (15 October 2026): a line `KEY = settings.mistral_api_key`
added to `media/extraction.py` fails `test_the_key_is_read_only_in_the_chatbots_provider_folder`
naming that file; a string `"https://api.mistral.ai/v1/ocr"` added to it fails the address test.
"""

from pathlib import Path

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

#: Where the key and the address of the text/OCR provider may stand.
ALLOWED = ("config.py", "domains/chatbot/")
#: The one other vendor, named: the design studio's image generator.
NAMED_OUTSIDE = {"domains/designstudio/imaging.py": "api.eu.bfl.ai"}

KEY = "mistral_api_key"
MODEL_HOSTS = ("api.mistral.ai",)


def _python():
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/", minstens=100)


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _allowed(rel: str) -> bool:
    return rel == "config.py" or rel.startswith("domains/chatbot/")


def test_the_key_is_read_only_in_the_chatbots_provider_folder():
    found = {
        _rel(p) for p in _python() if KEY in p.read_text(encoding="utf-8") and not _allowed(_rel(p))
    }
    assert not found, (
        "the provider key is read outside the chatbot's provider folder; a call to a model "
        "goes through `GuardedProvider` or a provider method (CR-33 F12):\n  "
        + "\n  ".join(sorted(found))
    )


def test_the_model_address_stands_only_in_the_chatbots_provider_folder():
    found = {
        _rel(p)
        for p in _python()
        if any(host in p.read_text(encoding="utf-8") for host in MODEL_HOSTS)
        and not _allowed(_rel(p))
    }
    assert not found, (
        "the address of a language model stands outside the chatbot's provider folder:\n  "
        + "\n  ".join(sorted(found))
    )


def test_the_gate_looks_at_the_providers_and_knows_its_one_named_outsider():
    inside = [
        _rel(p)
        for p in _python()
        if _allowed(_rel(p)) and (KEY in p.read_text() or MODEL_HOSTS[0] in p.read_text())
    ]
    assert "domains/chatbot/providers/mistral.py" in inside, inside
    for rel, host in NAMED_OUTSIDE.items():
        assert host in (APP / rel).read_text(encoding="utf-8"), f"{rel} no longer names {host}"

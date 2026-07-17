"""Stijl-guardrails (#486) — houdt de merkkleur automatisch consistent.

Het merkblauw is Ocean Blue = `blue-700` (#0051a4). De app was ooit afgedreven
naar het te donkere `blue-800` (#02407c) in koppen/headers. Deze test vangt zulke
drift in CI (net als de laaggrens-tests uit #396), zodat consistentie een
structureel gegeven is en niet pas op HDEV opvalt. Dof-blauw als *hover*-tint
(`hover:bg-blue-800`) blijft toegestaan — enkel rust-koppen/-achtergronden niet.
"""
import re
from pathlib import Path

_TEMPLATES = sorted((Path(__file__).resolve().parent.parent / "app").rglob("templates/**/*.html"))


def test_er_zijn_templates_gevonden():
    assert _TEMPLATES, "geen templates gevonden — is het pad verhuisd?"


def test_koppen_gebruiken_geen_text_blue_800():
    """Koppen/tekst horen de Ocean-token `text-blue-700` te gebruiken."""
    overtreders = [str(p.relative_to(p.parents[3]))
                   for p in _TEMPLATES if "text-blue-800" in p.read_text(encoding="utf-8")]
    assert not overtreders, (
        "Gebruik de Ocean-token 'text-blue-700' (#0051a4) i.p.v. 'text-blue-800'. "
        "Overtreders: " + ", ".join(overtreders))


def test_bg_blue_800_enkel_als_variant():
    """Een rust-achtergrond hoort `bg-blue-700`; `bg-blue-800` mag enkel als
    variant (hover:/focus:/…), d.w.z. voorafgegaan door ':'."""
    overtreders = []
    for p in _TEMPLATES:
        txt = p.read_text(encoding="utf-8")
        for m in re.finditer(r"bg-blue-800", txt):
            if m.start() == 0 or txt[m.start() - 1] != ":":
                overtreders.append(str(p.relative_to(p.parents[3])))
                break
    assert not overtreders, (
        "bg-blue-800 mag enkel als hover/focus-variant; een rust-achtergrond hoort "
        "bg-blue-700 (Ocean). Overtreders: " + ", ".join(overtreders))

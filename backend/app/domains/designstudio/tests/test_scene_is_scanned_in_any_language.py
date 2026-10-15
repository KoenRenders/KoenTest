"""The scene goes to the image vendor as typed: the pattern guard reads it whatever its language.

Review of #2053 (16 October 2026): `translate_scene` returned an English scene as it was, so a text
that was not Dutch reached the vendor without the guard; only a Dutch one was scanned, by the
translation call. Broken on purpose: the `refusal(...)` call taken out of `translate_scene` → the
English case below goes green on a refusal that never happens, and the first test fails.
"""

import pytest

from app.domains.designstudio import imaging


@pytest.mark.parametrize(
    "scene",
    [
        "A summer fair; write to jan.peeters@example.org for the lantern",  # English
        "Een zomerfeest, mail jan.peeters@example.org voor de lantaarn",  # Dutch
    ],
    ids=["english", "dutch"],
)
def test_a_scene_with_an_address_in_it_is_refused_whatever_its_language(scene):
    with pytest.raises(imaging.ImagingError):
        imaging.translate_scene(scene, actor="test")


def test_an_ordinary_english_scene_passes_unchanged():
    assert imaging.translate_scene("A summer fair with lanterns", actor="test") == (
        "A summer fair with lanterns",
        False,
    )

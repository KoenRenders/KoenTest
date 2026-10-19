"""`ui.field(kind="upload")` takes `multiple` (#2130) — and without it renders
byte for byte what it rendered before.

The media library's upload form takes several files at once. The kit's upload
field knew one: the form passed `multiple` through `attrs`, and the field then
named only the first file chosen. `multiple=True` puts the attribute on the input
and says how many files were chosen. Every other screen leaves it out, and for
them nothing may change: each argument shape of the six calls in the templates
is rendered and compared with the output of `master`'s macro before #2130
(`snapshots/upload_field_2130.json`, written once from that macro; rewrite it
only on purpose, with `SNAPSHOT_UPDATE=1`).

Proven red (put back): one space added inside the field's `<input` line → every
shape differs from its snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).parent / "snapshots" / "upload_field_2130.json"

#: The argument shapes of the calls in the templates (design system, media upload,
#: product attachments twice, the activity's poster and a component's info).
SHAPES = {
    "design_system_edit": dict(
        name="kit_poster1", label="Affiche", kind="upload", edit=True, current_url="/x"
    ),
    "design_system_read": dict(
        name="kit_poster2", label="Affiche", kind="upload", edit=False, current_url="/x"
    ),
    "media_upload": dict(
        name="files",
        label="Bestanden (afbeeldingen)",
        kind="upload",
        id="me-files",
        required=True,
        accept="image/*",
        attrs='multiple aria-describedby="me-files-hint"',
    ),
    "product_photo": dict(
        name="file", label="Foto toevoegen", kind="upload", id="foto-file", accept="image/*"
    ),
    "activity_poster": dict(
        name="file",
        label="Affiche",
        kind="upload",
        id="upl-file",
        edit=True,
        current_url="/y",
        delete_name="drop_poster",
    ),
    "component_info": dict(
        name="c.1.file",
        label="Info-bijlage",
        kind="upload",
        id="c-1-file",
        delete_attrs='hx-post="/z"',
        delete_confirm="Weg?",
        current_url="/z",
    ),
}


def _render(shape: dict) -> str:
    from app.ui import templates

    field = templates.env.get_template("_macros.html").module.field
    return str(field(**shape))


def test_without_multiple_every_shape_renders_as_before():
    if os.environ.get("SNAPSHOT_UPDATE") == "1":
        SNAPSHOT.write_text(
            json.dumps({k: _render(v) for k, v in SHAPES.items()}, indent=1, ensure_ascii=False)
            + "\n"
        )
    recorded = json.loads(SNAPSHOT.read_text())
    assert set(recorded) == set(SHAPES), "a shape without its snapshot"
    for key, shape in SHAPES.items():
        assert _render(shape) == recorded[key], f"{key}: the upload field changed"


@pytest.mark.parametrize("multiple", [True])
def test_multiple_takes_several_files_and_counts_them(multiple):
    html = _render(dict(name="files", label="Bestanden", kind="upload", multiple=multiple))
    assert '<input type="file" accept="image/*,application/pdf" multiple ' in html
    assert "bestanden gekozen" in html
    plain = _render(dict(name="files", label="Bestanden", kind="upload"))
    assert " multiple " not in plain and "bestanden gekozen" not in plain

"""CR-15 C6 test 12 and §C7 — the storage seam, and no copies (#1473). Hard.

1. No module outside `media` writes a picture's address (`/api/v1/media/…`) by
   hand; it asks `media.api.media_url`. One exception: the CMS scan for "where
   used", which READS that address out of page HTML and builds none.
2. No module outside `media` reads a picture's bytes (`.data` on an asset); it
   asks `media.api.asset_bytes`. Checked on the syntax tree, not on a name: every
   `.data` outside media is refused unless `NOT_A_MEDIA_ASSET` says what it is,
   so a picture held in a variable called `m` or `record` is caught as well.
3. No module anywhere creates a `MediaAsset` from the bytes of an existing one
   — reuse is a reference, never a copy (§C4.1). Zero today, zero after.

So storing bytes elsewhere (architecture R8) stays a change inside media.

Proven by violation, additively (CLAUDE.md): a line
`url = f"/api/v1/media/{x}"` added to `meetings/admin_ui.py` → part 1 red,
naming the file; `b = m.data` and `c = media_asset.data` added there → part 2
red, naming both lines (the old line pattern saw only the second);
`MediaAsset(kind=k, data=source.data)` added to `media/service.py` → part 3 red.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MEDIA = APP / "domains" / "media"

# A reader, not a builder: it finds `/api/v1/media/<id>` in stored page HTML.
READS_THE_ADDRESS = {"domains/cms/service.py": "scans page HTML for the pictures it shows (#1471)"}

_ADDRESS = re.compile(r"/api/v1/media/")

# Every `.data` outside media that is NOT a MediaAsset, per file and expression,
# with what it is. A new `.data` must be added here with its reason — or ask
# media.api.asset_bytes.
NOT_A_MEDIA_ASSET = {
    ("domains/designstudio/blocks.py", "image.data"): "ImageBytes, the bytes asset_bytes returned",
    ("domains/meetings/admin_ui.py", "record.data"): "MeetingFile, a meeting's own file",
    ("domains/meetings/service.py", "record.data"): "MeetingFile, a meeting's own file",
}


def _files(*suffixes: str) -> list[Path]:
    found = [
        p
        for p in APP.rglob("*")
        if p.suffix in suffixes and "tests" not in p.parts and "__pycache__" not in p.parts
    ]
    assert len(found) > 200, f"only {len(found)} files under app/ — did the walk break?"
    return found


def _outside_media(paths: list[Path]) -> list[Path]:
    return [p for p in paths if MEDIA not in p.parents]


def _rel(path: Path) -> str:
    return str(path.relative_to(APP))


def test_no_module_outside_media_writes_a_media_address():
    wrong = [
        f"{_rel(p)}:{n}"
        for p in _outside_media(_files(".py", ".html"))
        if _rel(p) not in READS_THE_ADDRESS
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _ADDRESS.search(line)
    ]
    assert not wrong, "ask media.api.media_url instead of writing the address:\n" + "\n".join(wrong)


def test_the_one_reader_still_reads():
    """The exception must still be needed — a stale one is a hole."""
    for path, reason in READS_THE_ADDRESS.items():
        assert _ADDRESS.search((APP / path).read_text(encoding="utf-8")), (path, reason)


def _data_reads() -> list[tuple[str, str, int]]:
    """Every `<expr>.data` outside media: (file, expression, line)."""
    return [
        (_rel(path), ast.unparse(node), node.lineno)
        for path in _outside_media(_files(".py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Attribute) and node.attr == "data"
    ]


def test_no_module_outside_media_reads_a_pictures_bytes():
    reads = _data_reads()
    assert reads, "no `.data` found at all — did the walk break?"
    wrong = [f"{f}:{n} {expr}" for f, expr, n in reads if (f, expr) not in NOT_A_MEDIA_ASSET]
    assert not wrong, (
        "ask media.api.asset_bytes instead (or, when it is not a MediaAsset, say what it"
        " is in NOT_A_MEDIA_ASSET):\n" + "\n".join(wrong)
    )


def test_every_exemption_is_still_there():
    """A stale exemption is a hole: a MediaAsset could take its place unseen."""
    seen = {(f, expr) for f, expr, _n in _data_reads()}
    assert not set(NOT_A_MEDIA_ASSET) - seen, set(NOT_A_MEDIA_ASSET) - seen


def _reads_data(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == "data" for n in ast.walk(node))


def test_no_module_makes_a_media_asset_from_another_ones_bytes():
    copies = []
    for path in _files(".py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "MediaAsset"):
                continue
            data = next((k.value for k in node.keywords if k.arg == "data"), None)
            if data is not None and _reads_data(data):
                copies.append(f"{_rel(path)}:{node.lineno}")
    assert not copies, "a picture is reused by reference, never copied:\n" + "\n".join(copies)

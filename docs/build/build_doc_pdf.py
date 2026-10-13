#!/usr/bin/env python3
"""Turn any document under docs/ into a printable A4 PDF.

Grew out of a one-off builder for an architecture document that never landed
(branch `claude/react-python-htmx-decision-w4674d`, 7 September 2026). Koen kept
the capability and dropped the content, so this takes a Markdown file as an
argument instead of naming one.

Pipeline (no application code involved):
  1. every ```mermaid fence is rendered to SVG with mermaid-cli (mmdc), cached by
     content hash so an unchanged diagram is never redrawn — that is why Node is
     only needed when you actually edit a diagram;
  2. the Markdown becomes HTML (python-markdown) with each fence replaced by a
     <figure><img>, so GitHub keeps rendering the live Mermaid source while the
     PDF embeds the static image — one source, two renderings;
  3. WeasyPrint lays it out on A4 with a title page, a table of contents carrying
     page numbers, running headers and page numbers (docs/build/doc.css).

Figure options ride in an HTML comment on the line above the fence, so GitHub
still sees a plain fence:

    <!-- figure: name=components caption=The_components wide=1 -->

`wide=1` puts that one figure on its own landscape page.

Front matter is optional; the first block between `---` lines carries `title`,
`subtitle`, `brand` and any other line you want on the title page. `statustags: 1`
turns `[PROD]`/`[HDEV]`/`[PARTIAL]`/`[ROADMAP]` into coloured labels — off by
default, because in a document that never meant them as labels they would rewrite
ordinary text.

Two more lines, each alone on its line and outside a code fence, are replaced
before anything else (#1953) — one place per fact, so the document quotes the
code instead of copying it:

    <!-- include: backend/app/domains/mdm/CONTRACT.md -->

puts that file there, its headings one level lower (the file's `#` becomes `##`
under the heading the line stands under), its relative links rewritten so they
still point at the same file, its figure lines untouched; and

    <!-- gates-table -->

puts the table of the gates of the test suite there — file · refuses · hard or
ratchet · since — built from the first docstring sentence of every file in
`GATE_BESTANDEN` (`backend/tests/test_gate_niet_leeg.py`), in the shape
`GATE_SENTENCE` of `backend/tests/test_gate_docstring_gate.py` holds. The build
fails, naming the file, on an include that does not exist and on a gate without
its sentence: never a silently empty section or table.

Run it through scripts/build-doc-pdf.sh, which installs the tooling into .cache/.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
BUILD = DOCS / "build"
CSS = BUILD / "doc.css"
MERMAID_CFG = BUILD / "mermaid-config.json"

FENCE = re.compile(r"(?:<!--[ \t]*figure:([^>]*?)-->[ \t]*\n)?```mermaid[ \t]*\n(.*?)```", re.S)
TAG = re.compile(r"\[(PROD|HDEV|PARTIAL|ROADMAP)\]")
TAG_LABEL = {
    "PROD": "in production",
    "HDEV": "on HDEV",
    "PARTIAL": "designed / partial",
    "ROADMAP": "roadmap",
}


INCLUDE = re.compile(r"<!--[ \t]*include:[ \t]*(\S+)[ \t]*-->")
GATES_TABLE = re.compile(r"<!--[ \t]*gates-table[ \t]*-->")
HEADING = re.compile(r"#{1,6}[ \t]")
LINK = re.compile(r"(\]\()([^)\s]+)")
NOT_RELATIVE = ("http://", "https://", "mailto:", "#", "/")


class BuildError(Exception):
    """The document cannot be built as written; the message names the file."""


def _outside_fences(text: str):
    """Every line of a Markdown text with whether it stands outside a code fence."""
    fenced = False
    for line in text.split("\n"):
        marker = line.lstrip().startswith("```")
        yield line, not fenced and not marker
        if marker:
            fenced = not fenced


def include_file(name: str, root: Path, docs: Path) -> str:
    """The text of an included file as it stands in the document: headings one
    level lower, relative links pointing at the same file from `docs/`."""
    path = (root / name).resolve()
    if root.resolve() not in path.parents:
        raise BuildError(f"include: {name} lies outside the repository")
    if not path.is_file():
        raise BuildError(f"include: {name} does not exist")

    def relink(match: "re.Match[str]") -> str:
        target = match.group(2)
        if target.startswith(NOT_RELATIVE):
            return match.group(0)
        file, hash_, anchor = target.partition("#")
        moved = os.path.relpath(path.parent / file, docs)
        return f"{match.group(1)}{Path(moved).as_posix()}{hash_}{anchor}"

    out = []
    for line, outside in _outside_fences(path.read_text(encoding="utf-8").rstrip("\n")):
        if outside:
            line = LINK.sub(relink, line)
            if HEADING.match(line):
                line = "#" + line
        out.append(line)
    return "\n".join(out)


def gates_table(gates: Sequence[str] | None = None, backend: Path | None = None) -> str:
    """The table of part C2: one row per gate file, from its first docstring line.

    The list and the shape of the sentence are the test suite's own
    (`GATE_BESTANDEN`, `GATE_SENTENCE`); `gates` and `backend` exist for the test
    of this function, which proves the two refusals on a list of its own."""
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from tests.test_gate_docstring_gate import GATE_SENTENCE, first_line
        from tests.test_gate_niet_leeg import BACKEND, GATE_BESTANDEN
    finally:
        sys.path.pop(0)
    gates = GATE_BESTANDEN if gates is None else gates
    backend = BACKEND if backend is None else backend
    if not gates:
        raise BuildError("gates-table: the list of gates is empty")
    rows = ["| File | Refuses | Hard or ratchet | Since |", "|---|---|---|---|"]
    for name in gates:
        path = backend / name
        if not path.is_file():
            raise BuildError(f"gates-table: {name} is in the list of gates and does not exist")
        line = first_line(path)
        match = GATE_SENTENCE.match(line or "")
        if match is None:
            raise BuildError(
                f"gates-table: {name} does not open with its sentence "
                "(Refuses <what> · <hard|ratchet> · since #<issue>.)"
            )
        refuses = match["refuses"].replace("|", "\\|")
        rows.append(f"| `{name}` | {refuses} | {match['kind']} | #{match['issue']} |")
    return "\n".join(rows)


def expand(md: str, root: Path = ROOT, docs: Path = DOCS) -> str:
    """Replace every include line and every gates-table line (#1953)."""
    out = []
    for line, outside in _outside_fences(md):
        included = INCLUDE.fullmatch(line.strip()) if outside else None
        if included:
            out.append(include_file(included.group(1), root, docs))
        elif outside and GATES_TABLE.fullmatch(line.strip()):
            out.append(gates_table())
        else:
            out.append(line)
    return "\n".join(out)


def render_mermaid(source: str, name: str, figures: Path) -> Path:
    """Render one diagram to <figures>/<name>.svg, cached by content hash.

    The hash lives beside the SVG as `.<name>.sha1`. Unchanged source means the
    file is returned untouched and mermaid-cli is never started — that is the
    whole reason a normal build needs no Node.
    """
    figures.mkdir(parents=True, exist_ok=True)
    out = figures / f"{name}.svg"
    digest = hashlib.sha1(source.encode()).hexdigest()[:12]
    stamp = figures / f".{name}.sha1"
    if out.exists() and stamp.exists() and stamp.read_text().strip() == digest:
        return out
    mmdc = os.environ.get("MMDC", "mmdc")
    src = figures / f".{name}.mmd"
    src.write_text(source)
    cmd = [mmdc, "-i", str(src), "-o", str(out), "-c", str(MERMAID_CFG), "-b", "white"]
    cfg = os.environ.get("PUPPETEER_CONFIG")
    if cfg:
        cmd += ["-p", cfg]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    except FileNotFoundError:
        raise SystemExit(
            f"mermaid-cli niet gevonden ({mmdc}). Draai via scripts/build-doc-pdf.sh,\n"
            "die het eenmalig in .cache/ installeert — of zet MMDC naar een eigen mmdc."
        )
    src.unlink()
    stamp.write_text(digest)
    return out


def replace_fences(md: str, figures: Path) -> str:
    counter = 0

    def sub(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        opts = dict(kv.split("=", 1) for kv in (m.group(1) or "").split() if "=" in kv)
        name = opts.get("name", f"diagram-{counter:02d}")
        caption = opts.get("caption", "").replace("_", " ")
        cls = "figure wide" if opts.get("wide") == "1" else "figure"
        svg = render_mermaid(m.group(2), name, figures)
        cap = (
            f"<figcaption>Figuur {counter}. {html.escape(caption)}</figcaption>" if caption else ""
        )
        return (
            f'\n<figure class="{cls}" markdown="0">'
            f'<img src="{svg.relative_to(DOCS).as_posix()}" '
            f'alt="{html.escape(caption or name)}">{cap}</figure>\n'
        )

    return FENCE.sub(sub, md)


def status_tags(text: str) -> str:
    return TAG.sub(
        lambda m: f'<span class="tag tag-{m.group(1).lower()}">{TAG_LABEL[m.group(1)]}</span>', text
    )


def build_toc(body_html: str) -> str:
    items = []
    for level, hid, title in re.findall(
        r'<h([12])(?: class="[^"]*")? id="([^"]+)">(.*?)</h[12]>', body_html, re.S
    ):
        if hid in ("title", "toc"):
            continue
        items.append((int(level), hid, re.sub(r"<[^>]+>", "", title)))
    out = ['<nav class="toc"><h1 id="toc">Inhoud</h1><ul>']
    depth = 1
    for level, hid, title in items:
        while depth < level:
            out.append("<ul>")
            depth += 1
        while depth > level:
            out.append("</ul>")
            depth -= 1
        out.append(f'<li><a href="#{hid}">{html.escape(title)}</a></li>')
    while depth > 1:
        out.append("</ul>")
        depth -= 1
    out.append("</ul></nav>")
    return "\n".join(out)


def build(src: Path, out_pdf: Path) -> None:
    md_text = src.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    if md_text.startswith("---"):
        head, _, md_text = md_text[3:].partition("\n---")
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()

    # Diagrams live per document, so two documents never overwrite each other's
    # figures — and the folder is named after the document you can see.
    figures = BUILD / "figuren" / src.stem
    md_text = replace_fences(expand(md_text), figures)

    import markdown  # late import, as weasyprint below: `expand` needs neither

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "attr_list", "toc", "md_in_html", "sane_lists"],
        extension_configs={"toc": {"permalink": False, "toc_depth": "1-3"}},
    )
    if meta.get("statustags") == "1":
        body = status_tags(body)

    # A small table stays on one page; a long one may break, or it would leave
    # half a page empty before it.
    def _keep(m: "re.Match[str]") -> str:
        tbl = m.group(0)
        return tbl.replace("<table>", '<table class="keep">', 1) if tbl.count("<tr>") <= 9 else tbl

    body = re.sub(r"<table>.*?</table>", _keep, body, flags=re.S)
    # Every H1 after the first starts a new page.
    body = re.sub(r'<h1 id="([^"]+)">', lambda m: f'<h1 class="section" id="{m.group(1)}">', body)

    # The title falls back to the file name rather than to a hard-coded word: a
    # document without front matter still gets a title page that says what it is.
    title = html.escape(meta.get("title", src.stem.replace("-", " ").replace("_", " ")))
    subtitle = html.escape(meta.get("subtitle", ""))
    brand = html.escape(meta.get("brand", ""))
    skip = ("title", "subtitle", "brand", "statustags")
    metas = "".join(f"<div>{html.escape(v)}</div>" for k, v in meta.items() if k not in skip)
    doc = f"""<!doctype html><html lang="nl"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="{CSS.as_posix()}"></head><body>
<div class="titlepage"><div class="brand">{brand}</div>
<h1 id="title">{title}</h1><div class="subtitle">{subtitle}</div><div class="meta">{metas}</div></div>
{build_toc(body)}
{body}
</body></html>"""
    (BUILD / f"{src.stem}.html").write_text(doc, encoding="utf-8")

    from weasyprint import HTML  # late import: the HTML above is written either way

    HTML(string=doc, base_url=str(DOCS)).write_pdf(str(out_pdf))
    print(f"geschreven: {out_pdf.relative_to(ROOT)} ({out_pdf.stat().st_size // 1024} KB)")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("gebruik: build_doc_pdf.py <docs/bestand.md>", file=sys.stderr)
        return 2
    src = Path(argv[0])
    if not src.is_absolute():
        src = (ROOT / src).resolve()
    if not src.is_file():
        print(f"bestaat niet: {src}", file=sys.stderr)
        return 1
    if DOCS not in src.parents:
        print(f"alleen documenten onder docs/: {src}", file=sys.stderr)
        return 1
    try:
        build(src, src.with_suffix(".pdf"))
    except BuildError as fault:
        print(f"FOUT: {fault}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

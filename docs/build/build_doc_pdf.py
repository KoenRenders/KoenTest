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

Run it through scripts/build-doc-pdf.sh, which installs the tooling into .cache/.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
BUILD = DOCS / "build"
CSS = BUILD / "doc.css"
MERMAID_CFG = BUILD / "mermaid-config.json"

FENCE = re.compile(r"(?:<!--[ \t]*figure:([^>]*?)-->[ \t]*\n)?```mermaid[ \t]*\n(.*?)```", re.S)
TAG = re.compile(r"\[(PROD|HDEV|PARTIAL|ROADMAP)\]")
TAG_LABEL = {"PROD": "in production", "HDEV": "on HDEV",
             "PARTIAL": "designed / partial", "ROADMAP": "roadmap"}


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
        cap = (f"<figcaption>Figuur {counter}. {html.escape(caption)}</figcaption>"
               if caption else "")
        return (f'\n<figure class="{cls}" markdown="0">'
                f'<img src="{svg.relative_to(DOCS).as_posix()}" '
                f'alt="{html.escape(caption or name)}">{cap}</figure>\n')

    return FENCE.sub(sub, md)


def status_tags(text: str) -> str:
    return TAG.sub(lambda m: f'<span class="tag tag-{m.group(1).lower()}">'
                             f'{TAG_LABEL[m.group(1)]}</span>', text)


def build_toc(body_html: str) -> str:
    items = []
    for level, hid, title in re.findall(
            r'<h([12])(?: class="[^"]*")? id="([^"]+)">(.*?)</h[12]>', body_html, re.S):
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
    md_text = replace_fences(md_text, figures)
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
    build(src, src.with_suffix(".pdf"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

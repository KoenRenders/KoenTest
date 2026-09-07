#!/usr/bin/env python3
"""Build docs/architecture.pdf from docs/architecture.md.

Pipeline (no application code involved):
  1. every ```mermaid fence in the Markdown is rendered to SVG with mermaid-cli
     (mmdc) using the project theme in docs/build/mermaid-config.json; figure
     options live in an HTML comment on the line above the fence,
     `<!-- figure: name=x caption=Some_caption wide=1 -->`, so GitHub still
     renders the plain fence;
  2. the Markdown is converted to HTML (python-markdown) with the fences replaced by
     <figure><img></figure>, so GitHub keeps rendering the live Mermaid source while
     the PDF embeds static images;
  3. WeasyPrint lays it out on A4 with a title page, a table of contents with page
     numbers, running headers and page numbers (docs/build/architecture.css).

Run via scripts/build-architecture-pdf.sh, which installs the tooling in a cache.
Environment: MMDC (path to the mmdc binary), PUPPETEER_CONFIG (json with the Chromium
executablePath), both set by the wrapper script.
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
SRC = ROOT / "docs" / "architecture.md"
OUT_PDF = ROOT / "docs" / "architecture.pdf"
OUT_HTML = ROOT / "docs" / "build" / "architecture.html"
DIAGRAMS = ROOT / "docs" / "architecture"
CSS = ROOT / "docs" / "build" / "architecture.css"
MERMAID_CFG = ROOT / "docs" / "build" / "mermaid-config.json"

FENCE = re.compile(r"(?:<!--[ \t]*figure:([^>]*?)-->[ \t]*\n)?```mermaid[ \t]*\n(.*?)```", re.S)
TAG = re.compile(r"\[(PROD|HDEV|PARTIAL|ROADMAP)\]")
TAG_LABEL = {"PROD": "in production", "HDEV": "v2.0.0 · HDEV", "PARTIAL": "designed / partial", "ROADMAP": "roadmap"}


def render_mermaid(source: str, name: str) -> Path:
    """Render one diagram to docs/architecture/<name>.svg (cached by content hash)."""
    DIAGRAMS.mkdir(parents=True, exist_ok=True)
    out = DIAGRAMS / f"{name}.svg"
    digest = hashlib.sha1(source.encode()).hexdigest()[:12]
    stamp = DIAGRAMS / f".{name}.sha1"
    if out.exists() and stamp.exists() and stamp.read_text().strip() == digest:
        return out
    mmdc = os.environ.get("MMDC", "mmdc")
    src = DIAGRAMS / f".{name}.mmd"
    src.write_text(source)
    cmd = [mmdc, "-i", str(src), "-o", str(out), "-c", str(MERMAID_CFG), "-b", "white"]
    cfg = os.environ.get("PUPPETEER_CONFIG")
    if cfg:
        cmd += ["-p", cfg]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    src.unlink()
    stamp.write_text(digest)
    return out


def replace_fences(md: str) -> str:
    counter = 0

    def sub(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        opts = dict(kv.split("=", 1) for kv in (m.group(1) or "").split() if "=" in kv)
        name = opts.get("name", f"diagram-{counter:02d}")
        caption = opts.get("caption", "").replace("_", " ")
        cls = "figure wide" if opts.get("wide") == "1" else "figure"
        svg = render_mermaid(m.group(2), name)
        cap = f"<figcaption>Figure {counter}. {html.escape(caption)}</figcaption>" if caption else ""
        return (f'\n<figure class="{cls}" markdown="0"><img src="{svg.relative_to(ROOT / "docs").as_posix()}" '
                f'alt="{html.escape(caption or name)}">{cap}</figure>\n')

    return FENCE.sub(sub, md)


def status_tags(text: str) -> str:
    return TAG.sub(lambda m: f'<span class="tag tag-{m.group(1).lower()}">{TAG_LABEL[m.group(1)]}</span>', text)


def build_toc(body_html: str) -> str:
    items = []
    for level, hid, title in re.findall(r'<h([12])(?: class="[^"]*")? id="([^"]+)">(.*?)</h[12]>', body_html, re.S):
        if hid in ("title", "toc") or 'class="onepager' in title:
            continue
        clean = re.sub(r"<[^>]+>", "", title)
        items.append((int(level), hid, clean))
    out = ['<nav class="toc"><h1 id="toc">Contents</h1><ul>']
    depth = 1
    for level, hid, title in items:
        while depth < level:
            out.append("<ul>"); depth += 1
        while depth > level:
            out.append("</ul>"); depth -= 1
        out.append(f'<li><a href="#{hid}">{html.escape(title)}</a></li>')
    while depth > 1:
        out.append("</ul>"); depth -= 1
    out.append("</ul></nav>")
    return "\n".join(out)


def main() -> int:
    md_text = SRC.read_text(encoding="utf-8")
    # Front matter: first block between --- lines carries title/subtitle/meta.
    meta: dict[str, str] = {}
    if md_text.startswith("---"):
        head, _, md_text = md_text[3:].partition("\n---")
        for line in head.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    md_text = replace_fences(md_text)
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "attr_list", "toc", "md_in_html", "sane_lists"],
        extension_configs={"toc": {"permalink": False, "toc_depth": "1-3"}},
    )
    body = status_tags(body)
    # small tables stay on one page (the CSS gives table.keep page-break-inside: avoid)
    def _keep(m: "re.Match[str]") -> str:
        tbl = m.group(0)
        return tbl.replace("<table>", '<table class="keep">', 1) if tbl.count("<tr>") <= 9 else tbl
    body = re.sub(r"<table>.*?</table>", _keep, body, flags=re.S)
    # Every H1 after the first starts a new page.
    body = re.sub(r'<h1 id="([^"]+)">', lambda m: f'<h1 class="section" id="{m.group(1)}">', body)
    title = html.escape(meta.get("title", "Architecture"))
    subtitle = html.escape(meta.get("subtitle", ""))
    metas = "".join(f"<div>{html.escape(v)}</div>" for k, v in meta.items() if k not in ("title", "subtitle"))
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="{CSS.as_posix()}"></head><body>
<div class="titlepage"><div class="brand">I-X IT Solutions · reference architecture</div>
<h1 id="title">{title}</h1><div class="subtitle">{subtitle}</div><div class="meta">{metas}</div></div>
{build_toc(body)}
{body}
</body></html>"""
    OUT_HTML.write_text(doc, encoding="utf-8")
    from weasyprint import HTML  # imported late so `--html-only` works without it

    HTML(string=doc, base_url=str(ROOT / "docs")).write_pdf(str(OUT_PDF))
    print(f"wrote {OUT_PDF.relative_to(ROOT)} ({OUT_PDF.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

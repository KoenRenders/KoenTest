"""The documentation build quotes the code: an include line and a gates-table line (#1953).

`docs/build/build_doc_pdf.py` replaces two lines before it lays a document out:
`<!-- include: <file> -->` by that file, and `<!-- gates-table -->` by the table
of the gates of the test suite. This file runs both on small example documents —
the Markdown the build goes on with, not the PDF: a wrong section or an empty
table is decided there.

Broken on purpose (13 October 2026, each put back):
- `include_file`: the line that lowers a heading out → "not lowered: # membership
  — componentcontract …", and the scratch contract's `## proef` is missed;
- `include_file`: the check on a missing file out → a `FileNotFoundError` instead
  of the build's own refusal, and `pytest.raises(BuildError)` says so;
- `gates_table`: the refusal of a first line that is not the sentence out → a
  `TypeError` on the scratch gate instead of the refusal that names it;
- `expand`: the fence check out → "an include line shown as an example was
  replaced".
"""

import importlib.util
from pathlib import Path

import pytest

from tests.test_gate_niet_leeg import BACKEND, GATE_BESTANDEN

ROOT = BACKEND.parent
CONTRACT = "backend/app/domains/membership/CONTRACT.md"


def _build():
    spec = importlib.util.spec_from_file_location(
        "build_doc_pdf", ROOT / "docs" / "build" / "build_doc_pdf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _build()


# ── the include line ─────────────────────────────────────────────────────────


def test_an_include_puts_the_contract_there_one_level_lower():
    doc = f"# Part B\n\n## B3. membership\n\n<!-- include: {CONTRACT} -->\n\nAfter.\n"
    out = build.expand(doc)
    lines = out.split("\n")
    source = (ROOT / CONTRACT).read_text(encoding="utf-8").rstrip("\n").split("\n")
    headings = [line for line in source if line.startswith("#")]
    assert len(headings) >= 10, "the contract has its title and the nine headings"
    for heading in headings:
        assert "#" + heading in lines, f"not lowered: {heading}"
        assert heading not in lines, f"the contract's own level is still there: {heading}"
    title = "#" + source[0]
    assert title.startswith("## ") and lines.index(title) > lines.index("## B3. membership"), (
        "the contract's title stands at the level of the document's own"
    )
    assert "### Purpose and process" in lines
    assert "<!-- include" not in out
    # Nothing but the level of a heading changed, and the document goes on.
    assert [line.lstrip("#") for line in source] == [
        line.lstrip("#") for line in lines[lines.index(title) : lines.index(title) + len(source)]
    ]
    assert lines[-2:] == ["After.", ""]


def test_an_include_that_does_not_exist_fails_the_build_with_its_name():
    with pytest.raises(build.BuildError, match=r"backend/app/domains/nergens/CONTRACT\.md"):
        build.expand("<!-- include: backend/app/domains/nergens/CONTRACT.md -->\n")


def test_an_include_outside_the_repository_is_refused():
    with pytest.raises(build.BuildError, match="outside the repository"):
        build.expand("<!-- include: ../elders.md -->\n")


def test_an_include_line_inside_a_code_fence_is_an_example():
    doc = f"Write:\n\n```\n<!-- include: {CONTRACT} -->\n<!-- gates-table -->\n```\n"
    assert build.expand(doc) == doc, "an include line shown as an example was replaced"


def test_links_and_figure_lines_of_an_included_file_still_work(tmp_path):
    """A relative link points at the same file from `docs/`; a heading inside a
    code fence is code; a figure line stays on the line above its fence."""
    module = tmp_path / "backend" / "app" / "domains" / "proef"
    module.mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (module / "CONTRACT.md").write_text(
        "# proef\n\n"
        "See [the model](models.py), [the rule](../../kernel/rules.py#home),\n"
        "[elsewhere](https://example.org/x) and [below](#owns).\n\n"
        "## Owns\n\n"
        "<!-- figure: name=lc-proef caption=A_lifecycle -->\n"
        "```mermaid\nstateDiagram-v2\n  [*] --> draft\n```\n\n"
        "```python\n# a comment, not a heading\n```\n",
        encoding="utf-8",
    )
    out = build.expand(
        "## B1\n\n<!-- include: backend/app/domains/proef/CONTRACT.md -->\n",
        root=tmp_path,
        docs=tmp_path / "docs",
    )
    assert "[the model](../backend/app/domains/proef/models.py)" in out
    assert "[the rule](../backend/app/kernel/rules.py#home)" in out
    assert "[elsewhere](https://example.org/x)" in out and "[below](#owns)" in out
    lines = out.split("\n")
    assert "## proef" in lines and "### Owns" in lines
    assert "# a comment, not a heading" in lines
    figure = lines.index("<!-- figure: name=lc-proef caption=A_lifecycle -->")
    assert lines[figure + 1] == "```mermaid"
    # The build's own reader of figures finds the fence with its options.
    assert build.FENCE.search(out).group(1).strip() == "name=lc-proef caption=A_lifecycle"


# ── the gates table ──────────────────────────────────────────────────────────


def _rows(table: str) -> list[list[str]]:
    return [[cell.strip() for cell in row.strip("|").split("|")] for row in table.split("\n")]


def test_the_gates_table_has_one_row_per_gate():
    rows = _rows(build.gates_table())
    assert rows[0] == ["File", "Refuses", "Hard or ratchet", "Since"]
    body = rows[2:]
    assert len(body) == len(GATE_BESTANDEN) >= 58
    assert [row[0] for row in body] == [f"`{name}`" for name in GATE_BESTANDEN]
    assert all(len(row) == 4 and row[1] for row in body), "a row without what it refuses"
    assert {row[2] for row in body} == {"hard", "ratchet"}
    own = next(row for row in body if row[0] == "`tests/test_gate_docstring_gate.py`")
    assert own[1].startswith("a gate file whose docstring does not open with")
    assert own[2:] == ["hard", "#1952"]


def _scratch_gate(tmp_path: Path, name: str, docstring: str) -> None:
    (tmp_path / name).write_text(f'"""{docstring}"""\n', encoding="utf-8")


def test_a_gate_without_its_sentence_fails_the_build_with_its_name(tmp_path):
    _scratch_gate(tmp_path, "test_good_gate.py", "Refuses a thing · hard · since #1.")
    _scratch_gate(tmp_path, "test_plain_gate.py", "Checks a thing.")
    (tmp_path / "test_silent_gate.py").write_text("x = 1\n", encoding="utf-8")
    good = _rows(build.gates_table(["test_good_gate.py"], tmp_path))
    assert good[2] == ["`test_good_gate.py`", "a thing", "hard", "#1"]
    for name in ("test_plain_gate.py", "test_silent_gate.py"):
        with pytest.raises(build.BuildError, match=name) as refused:
            build.gates_table(["test_good_gate.py", name], tmp_path)
        assert "does not open with its sentence" in str(refused.value)


def test_a_gate_of_the_list_that_is_missing_fails_the_build_with_its_name(tmp_path):
    with pytest.raises(build.BuildError, match="test_gone_gate.py") as refused:
        build.gates_table(["test_gone_gate.py"], tmp_path)
    assert "does not exist" in str(refused.value)


def test_an_empty_list_of_gates_is_never_an_empty_table(tmp_path):
    with pytest.raises(build.BuildError, match="empty"):
        build.gates_table([], tmp_path)


def test_a_bar_in_a_sentence_does_not_split_its_cell(tmp_path):
    _scratch_gate(
        tmp_path, "test_bar_gate.py", "Refuses `a | b` in a template · ratchet · since #2."
    )
    assert "`a \\| b` in a template" in build.gates_table(["test_bar_gate.py"], tmp_path)


# ── both, in one example document ────────────────────────────────────────────


def test_an_example_document_builds_with_a_contract_and_the_gates_table():
    doc = (
        "# Part B — Per module\n\n## B3. membership\n\n"
        f"<!-- include: {CONTRACT} -->\n\n"
        "# Part C — The harness\n\n## C2. The gates\n\n<!-- gates-table -->\n\nThe end.\n"
    )
    out = build.expand(doc)
    assert "<!--" not in out
    lines = out.split("\n")
    assert lines.index("### Evolutions") < lines.index("# Part C — The harness")
    head = lines.index("| File | Refuses | Hard or ratchet | Since |")
    assert lines.index("## C2. The gates") < head
    end = lines.index("The end.")
    table = [line for line in lines[head:end] if line.startswith("|")]
    assert len(table) == len(GATE_BESTANDEN) + 2

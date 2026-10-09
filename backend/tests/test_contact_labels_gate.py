"""The screens say "Mobiel" and "E-mail" (#1719) — one word per contact field,
on every screen, in every mail and in the changes list.

Three rules over the application's templates and Python (tests left out,
comments and docstrings not read):

- **nothing a person reads says "gsm"**: not "Gsm", "GSM" or "gsm-nummer". The
  word is matched as a word — "bevestigingsmail" carries the three letters and
  is not a hit, and neither is an id like `reg-gsm-12`;
- **no label is "Mobiel nummer"**: the field is "Mobiel". A sentence keeps the
  noun ("Vul een mobiel nummer in.");
- **no field label is "E-mailadres"**: the field is "E-mail". Every compound
  label and every sentence keeps the noun ("Ander e-mailadres", "+ E-mailadres",
  "Vul een geldig e-mailadres in.").

What may stay stands in `ALLOWED`, per file with its exact number and its
reason: the member import's own column name `gsm` (the board's file, not our
copy), the label of the button that adds an address, and the form builder's
code label, which a migration writes and a migration would have to change.
The numbers are exact on purpose: they also prove that the scan finds what it
looks for — a scan that sees nothing would be red on them, not green.

Proven red, each with an ADDITIVE violation (run, restored from HEAD):
- `{{ _("Gsm") }}` added to `home.html` → "gsm: 1 found, 0 allowed";
- `x = "Mobiel nummer"` added to `mdm/ui.py` → "Mobiel nummer: 1 found";
- `{{ ui.label(_("E-mailadres"), "x") }}` added to `home.html` → "E-mailadres:
  1 found, 0 allowed".
"""

from __future__ import annotations

import ast
import pathlib
import re
from collections import Counter

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# "gsm" as a word: not inside a longer word ("bevestigingsmail") and not as a
# part of an identifier written with hyphens ("reg-gsm-12").
GSM = re.compile(r"(?<![\w-])gsm(?!\w)", re.IGNORECASE)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
QUOTED = re.compile(r"""(["'])((?:(?!\1).)*)\1""")

MOBILE_LABELS = {"Mobiel nummer", "Mobiel nummer:"}
EMAIL_LABELS = {"E-mailadres", "E-mailadres:"}

# file (relative to app/) → exact number, per rule.
ALLOWED: dict[str, dict[str, int]] = {
    "gsm": {
        # The member import reads the board's own file; "gsm" is its column.
        "domains/mdm/ledenrapport.py": 4,
        "domains/mdm/import_service.py": 2,
    },
    "Mobiel nummer": {},
    "E-mailadres": {
        # The button that adds an address: "+ E-mailadres" (a compound label).
        "domains/membership/templates/_household_rows.html": 1,
        "ui/templates/design_system.html": 1,
        # The form builder's code label: stored by a migration.
        "domains/forms/codes.py": 1,
    },
}


def gsm_hits(text: str) -> int:
    """How often `text` says "gsm" as a word."""
    return len(GSM.findall(text))


def _python_strings(source: str) -> list[str]:
    """Every string constant of a module, its docstrings left out."""
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def copy_of(path: pathlib.Path) -> tuple[str, list[str]]:
    """What a file can show a person: the text to search for a word, and the
    quoted strings a label can be."""
    source = path.read_text()
    if path.suffix == ".py":
        strings = _python_strings(source)
        return "\n".join(strings), strings
    text = JINJA_COMMENT.sub("", source)
    return text, [match.group(2) for match in QUOTED.finditer(text)]


def _files() -> list[pathlib.Path]:
    return sorted(
        path
        for suffix in ("*.html", "*.py")
        for path in APP.rglob(suffix)
        if "tests" not in path.relative_to(APP).parts
    )


def _found() -> dict[str, Counter[str]]:
    found: dict[str, Counter[str]] = {rule: Counter() for rule in ALLOWED}
    for path in _files():
        name = path.relative_to(APP).as_posix()
        text, strings = copy_of(path)
        found["gsm"][name] += gsm_hits(text)
        found["Mobiel nummer"][name] += sum(1 for s in strings if s.strip() in MOBILE_LABELS)
        found["E-mailadres"][name] += sum(1 for s in strings if s.strip() in EMAIL_LABELS)
    return found


def _check(rule: str) -> None:
    found = {name: count for name, count in _found()[rule].items() if count}
    allowed = ALLOWED[rule]
    wrong = [
        f"{name}: {found.get(name, 0)} found, {allowed.get(name, 0)} allowed"
        for name in sorted(set(found) | set(allowed))
        if found.get(name, 0) != allowed.get(name, 0)
    ]
    assert not wrong, f"{rule}: " + "; ".join(wrong)


def test_the_scan_reads_the_application():
    """The gate looks somewhere: templates and modules, and the new words on
    the screens it guards."""
    files = _files()
    assert sum(1 for p in files if p.suffix == ".html") > 100
    assert sum(1 for p in files if p.suffix == ".py") > 100
    for name, label in (
        ("domains/membership/templates/_household_rows.html", "Mobiel"),
        ("domains/membership/templates/_household_rows.html", "E-mail"),
        ("domains/activities/templates/_inschrijf_velden.html", "Mobiel"),
        ("ui/templates/_macros.html", "Mobiel"),
        ("domains/reporting/changes.py", "mobiel"),
    ):
        assert label in copy_of(APP / name)[1], f"{name} does not carry the label {label!r}"


def test_gsm_is_matched_as_a_word():
    assert gsm_hits("Gsm") == gsm_hits("GSM:") == gsm_hits("het gsm-nummer") == 1
    assert gsm_hits("Je krijgt een bevestigingsmail.") == 0  # the false hit
    assert gsm_hits('id="reg-gsm-12"') == 0
    assert gsm_hits("gsmnummer") == 0


def test_nothing_a_person_reads_says_gsm():
    _check("gsm")


def test_no_label_is_mobiel_nummer():
    _check("Mobiel nummer")


def test_no_field_label_is_e_mailadres():
    _check("E-mailadres")

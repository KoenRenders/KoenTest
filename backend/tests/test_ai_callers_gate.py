"""Refuses a module that sends a stored value to a model without the register, or reads a `none` datum without a named exception · hard · since #2007.

CR-33 phase 2 (F7, T12): a module that talks to a model hands the stored values it sends as
`fields` — `(attribute key, value)` — and the port classifies and renders them
(`chatbot/fields.py`). What it must not do is what it did before: read a datum the register
keeps from a model and write it into a prompt itself, where no classification looks at it.

**The rule is derived from the register, not from a list of words** (review of #2053, 16 October
2026: a gate that looks for the label `Naam:` finds `f"Naam: {x}"` and nothing else — not
`f"Straat: {a.street}"`, not `"Adres:\\n" + a.line`, not a join). A *caller* is a file outside the
chatbot that imports from it and calls a model (`complete`, `run_chat`, `run_public_chat`,
`json_answer`, `ocr`, `GuardedProvider(…)`); a module that is handed a provider as a parameter is
seen as well, because the import and the call decide, not the construction. In a caller:

1. **An attribute whose name the register keeps from a model may not be read.** The names are
   the column names of the register's entries (the last part of the key): every column that is
   `none` or `tokenised` somewhere and `public` or `internal` nowhere, and every column of the
   `mdm` package (people, households, addresses) that is not public anywhere. `street`,
   `house_number`, `line`, `board_notes`, `notes_document`, `email`, `iban` are among them. The
   attribute may be read by a caller only with a reason in `ALLOWED_READS` (a comparison, a
   count, a link — never a prompt), and the one named exception may read its own column in its own
   reader.
2. **No dynamic access.** `getattr(x, <not a constant>)`, `vars(…)`, `.__dict__`, `.model_dump(`,
   `asdict(`, `.__table__` and `.columns` read an attribute whose name stands nowhere in the file,
   so rule 1 cannot see it; they are refused in a caller. A join over values that came from such
   a read is therefore refused where it reads, not where it joins.
3. The two idioms that were written before the register (`f"Naam: {…}"`, `f"- {id}: {name}"`) stay
   refused as well.

The limit is stated: a value that reaches a caller already formatted — from another domain's
facade — is that facade's to classify (it is a caller of the port itself if it talks to a model, or
its data is public), and free text a person wrote has no key and keeps the pattern guard.

**The one named exception** (Koen, 15 October 2026, Q&A nr. 12, "a"): the newsletter's writer reads
the minutes, which are `nooit` in the register, with the names removed. It stands in
`chatbot.fields.NAMED_EXCEPTIONS` with its reader and its reason; `use_named_exception` refuses a
caller that is not the reader (it reads the call stack, not only its argument), and this gate keeps
the list honest: every exception names a datum that IS `none`, a reader that says so where it
reads, and nobody else may read that column — rule 1 is what stops a second module.

**What stays outside the register** is a list too (`OUTSIDE_THE_REGISTER`): dictation audio and the
design studio's image prompt, each with its reason; this gate checks that each place exists and that
nothing else reaches the dictation provider.

Proven red with ADDITIVE violations (16 October 2026), each as a test of this file: `f"Straat: …"`,
`"Adres:\\n" + a.line`, a join over `getattr(a, k)`, a `.notes_document` read in a second module, and
the old `f"Naam: …"`. And on the real tree: `x = a.street` added to `activities/proposer.py` fails
`test_no_ai_caller_reads_what_the_register_keeps_from_a_model` naming the file and the line.
"""

import ast
import re
from pathlib import Path

import pytest

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

LABEL = re.compile(r"^\s*(Naam|Locatie|Omschrijving|Datums|Onderdeel|Activiteit|Product):\s*$")

#: What a caller of the model calls.
MODEL_CALLS = {"complete", "run_chat", "run_public_chat", "json_answer", "ocr"}
MODEL_NAMES = {"GuardedProvider", "run_chat", "run_public_chat", "json_answer"}
#: Reads of an attribute whose name stands nowhere in the file.
DYNAMIC_ATTRIBUTES = {"__dict__", "__table__", "columns", "model_dump"}
DYNAMIC_CALLS = {"vars", "asdict"}

#: A caller may read an attribute of the forbidden kind when it is no prompt: file → name → why.
ALLOWED_READS: dict[str, dict[str, str]] = {
    "domains/reporting/admin_ui.py": {
        "owner_email": "compares the owner of a saved report with the signed-in address; never in a prompt",
        "columns": "the columns of a report's result table, shown on the screen; no ORM metadata",
        "link": "the link a blocked call offers on the screen (`SeamBlocked.link`); no stored datum",
    },
}


#: Names too common to say anything: the datum behind `.id`, `.kind`, `.source` or `.value` is
#: classified by its entity, and an attribute of that name is read all over a caller for
#: reasons that are no prompt. The limit is stated; the entity's own columns stay forbidden.
GENERIC_NAMES = {"id", "kind", "source", "value", "key", "status", "type", "code", "label", "role"}

#: A caller that reads attributes by a name held in a variable, and why that is safe: file → why.
ALLOWED_DYNAMIC: dict[str, str] = {
    "domains/activities/proposer.py": (
        "reads the date and time columns of a row by their names (`start_date`, `end_date`, "
        "`start_time`, `end_time`), all public (`activities.activity_date.*`)"
    ),
}


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _python():
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/", minstens=100)


def _is_caller(source: str) -> bool:
    tree = ast.parse(source)
    imports_chatbot = any(
        isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.domains.chatbot")
        for n in ast.walk(tree)
    )
    calls_model = any(
        (isinstance(n, ast.Attribute) and n.attr in MODEL_CALLS)
        or (isinstance(n, ast.Name) and n.id in MODEL_NAMES)
        for n in ast.walk(tree)
    )
    return imports_chatbot and calls_model


def ai_callers() -> list[Path]:
    """The files outside the chatbot that send something to a model."""
    return [
        p
        for p in _python()
        if not _rel(p).startswith("domains/chatbot/") and _is_caller(p.read_text(encoding="utf-8"))
    ]


def forbidden_attributes() -> set[str]:
    """The names a caller may not read, from the register (rule 1)."""
    from app.domains.registry import load_all_models
    from app.kernel.attributes import AiExposure, registry

    load_all_models()
    entries = registry()
    assert len(entries) > 300, f"only {len(entries)} register entries read — is the gate looking?"

    def column(key: str) -> str:
        return key.rsplit(".", 1)[1]

    kept_back = {
        column(k)
        for k, a in entries.items()
        if a.ai_exposure in (AiExposure.NONE, AiExposure.TOKENISED)
    }
    open_somewhere = {
        column(k)
        for k, a in entries.items()
        if a.ai_exposure in (AiExposure.PUBLIC, AiExposure.INTERNAL)
    }
    public_somewhere = {column(k) for k, a in entries.items() if a.ai_exposure is AiExposure.PUBLIC}
    people = {
        column(k)
        for k, a in entries.items()
        if k.startswith("mdm.") and a.ai_exposure is not AiExposure.PUBLIC
    }
    return ((kept_back - open_somewhere) | (people - public_somewhere)) - GENERIC_NAMES


def reads(source: str, rel: str, forbidden: set[str]) -> list[tuple[int, str]]:
    """What a caller's source reads that the register keeps from a model, or reads dynamically."""
    from app.domains.chatbot.api import NAMED_EXCEPTIONS

    own = {
        key.rsplit(".", 1)[1]
        for key, exception in NAMED_EXCEPTIONS.items()
        if rel == "domains/" + exception.by.replace(".", "/") + ".py"
    }
    allowed = set(ALLOWED_READS.get(rel, {})) | own
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            if node.attr in forbidden and node.attr not in allowed:
                found.append(
                    (node.lineno, f"reads `.{node.attr}`, which the register keeps from a model")
                )
            if node.attr in DYNAMIC_ATTRIBUTES and node.attr not in allowed:
                found.append(
                    (node.lineno, f"reads `.{node.attr}`: an attribute by a name nobody can see")
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DYNAMIC_CALLS:
                found.append(
                    (node.lineno, f"`{node.func.id}(…)` reads attributes by a name nobody can see")
                )
            if node.func.id == "getattr" and len(node.args) >= 2:
                name = node.args[1]
                if not isinstance(name, ast.Constant):
                    if rel not in ALLOWED_DYNAMIC:
                        found.append((node.lineno, "`getattr(…)` with a name that is no constant"))
                elif name.value in forbidden and name.value not in allowed:
                    found.append(
                        (
                            node.lineno,
                            f"reads `{name.value}` by `getattr`, which the register keeps from a model",
                        )
                    )
    return found


def idioms(source: str) -> list[tuple[int, str]]:
    """The lines of `source` that format a stored value into text the two old ways."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts = node.values
        first = parts[0] if parts else None
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and LABEL.match(first.value)
            and len(parts) > 1
            and isinstance(parts[1], ast.FormattedValue)
        ):
            found.append((node.lineno, f"a label and a value: {first.value.strip()}"))
        if (
            len(parts) == 4
            and isinstance(parts[0], ast.Constant)
            and parts[0].value == "- "
            and isinstance(parts[1], ast.FormattedValue)
            and isinstance(parts[2], ast.Constant)
            and str(parts[2].value).startswith(":")
            and isinstance(parts[3], ast.FormattedValue)
        ):
            found.append((node.lineno, "a line `- {id}: {name}`"))
    return found


def test_the_gate_finds_the_ai_callers():
    callers = {_rel(p) for p in ai_callers()}
    assert {
        "domains/activities/proposer.py",
        "domains/newsletter/drafting.py",
        "domains/media/extraction.py",
        "domains/designstudio/imaging.py",
        "domains/reporting/admin_ui.py",
    } <= callers, sorted(callers)


def test_the_gate_knows_what_the_register_keeps_from_a_model():
    forbidden = forbidden_attributes()
    assert {"street", "house_number", "line", "board_notes", "notes_document", "email"} <= forbidden
    assert not {"name", "description", "location"} & forbidden, (
        "a public datum is no forbidden read"
    )


def test_no_ai_caller_reads_what_the_register_keeps_from_a_model():
    forbidden = forbidden_attributes()
    problems = [
        f"{_rel(p)}:{line}: {what}"
        for p in ai_callers()
        for line, what in reads(p.read_text(encoding="utf-8"), _rel(p), forbidden)
    ]
    assert not problems, (
        "a caller of a model reads a datum the register keeps from it, or reads by a hidden name; "
        "hand it as a field of the register (`chatbot.api.Field`) and let the port classify it, "
        "or — when the read is no prompt — give it a reason in ALLOWED_READS:\n  "
        + "\n  ".join(problems)
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('prompt = f"Straat: {a.street}"', "street"),
        ('prompt = "Adres:\\n" + a.line', "line"),
        ('prompt = "\\n".join(f"{k}: {getattr(a, k)}" for k in names)', "no constant"),
        ('prompt = "{}: {}".format("Nota", item.notes_document)', "notes_document"),
        ("prompt = str(vars(person))", "vars"),
        ('prompt = f"Huisnummer {a.house_number}"', "house_number"),
    ],
    ids=["street-fstring", "address-concat", "join-getattr", "format-notes", "vars", "number"],
)
def test_the_rule_goes_red_on_the_shapes_the_old_gate_missed(source, expected):
    """The additive proofs: each of these was invisible to the label-word gate."""
    found = reads(source, "domains/somewhere/new_caller.py", forbidden_attributes())
    assert found, f"{source!r} was not refused"
    assert any(expected in what for _line, what in found), found


def test_a_public_datum_and_an_allowed_read_pass():
    forbidden = forbidden_attributes()
    assert reads('x = f"{a.name} {a.location}"', "domains/somewhere/c.py", forbidden) == []
    assert reads("x = r.owner_email == mine", "domains/reporting/admin_ui.py", forbidden) == [], (
        "an allowed read, with its reason, passes"
    )
    assert reads("x = r.owner_email == mine", "domains/other/c.py", forbidden), (
        "the same read in another file is no exception"
    )


def test_only_the_named_reader_may_read_the_exceptions_column():
    forbidden = forbidden_attributes()
    source = "x = item.notes_document"
    assert reads(source, "domains/newsletter/drafting.py", forbidden) == []
    assert reads(source, "domains/media/extraction.py", forbidden), (
        "a second reader of the minutes is no exception, it is a second door"
    )


def test_no_ai_caller_formats_a_stored_value_into_its_prompt():
    problems = [
        f"{_rel(p)}:{line}: {what}"
        for p in ai_callers()
        for line, what in idioms(p.read_text(encoding="utf-8"))
    ]
    assert not problems, (
        "a stored value is formatted into a prompt; hand it as a field of the register "
        "(`chatbot.api.Field`) and let the port render it:\n  " + "\n  ".join(problems)
    )


def test_the_idioms_are_recognised():
    """The gate can go red: the two shapes, written the old way."""
    old = 'a = f"Naam: {x.name}"\nb = f"- {s.activity.id}: {s.activity.name}"\nc = f"Naam is {x}"\n'
    assert [what for _line, what in idioms(old)] == [
        "a label and a value: Naam:",
        "a line `- {id}: {name}`",
    ]


def test_every_named_exception_is_honest():
    from app.domains.chatbot.api import NAMED_EXCEPTIONS
    from app.domains.registry import load_all_models
    from app.kernel.attributes import AiExposure, attribute

    load_all_models()
    assert NAMED_EXCEPTIONS, "no exception named — is the list still read?"
    for key, exception in NAMED_EXCEPTIONS.items():
        assert attribute(key).ai_exposure is AiExposure.NONE, (
            f"{key} is no longer `none`: the exception is an exception to nothing"
        )
        reader = APP / ("domains/" + exception.by.replace(".", "/") + ".py")
        assert f'use_named_exception("{key}", by="{exception.by}")' in reader.read_text(
            encoding="utf-8"
        ), f"{exception.by} does not say, where it reads, that it is the exception for {key}"
        others = [
            _rel(p)
            for p in _python()
            if _rel(p) != _rel(reader)
            and not _rel(p).startswith("domains/chatbot/")
            and f'use_named_exception("{key}"' in p.read_text(encoding="utf-8")
        ]
        assert not others, f"{key} is read as an exception by more than its named reader: {others}"


def test_a_reader_cannot_borrow_the_name_of_the_named_reader():
    """`use_named_exception` reads the call stack: this test module is not the newsletter's drafting,
    whatever `by=` says."""
    from app.domains.chatbot.api import use_named_exception

    with pytest.raises(LookupError):
        use_named_exception("meetings.meeting_item.notes_document", by="newsletter.drafting")


def test_what_stays_outside_the_register_is_named_and_exists():
    from app.domains.chatbot.api import OUTSIDE_THE_REGISTER

    assert OUTSIDE_THE_REGISTER, "nothing named outside the register — is the list still read?"
    for place, reason in OUTSIDE_THE_REGISTER.items():
        assert (APP / "domains" / place).exists(), f"{place} no longer exists"
        assert len(reason) > 80, f"{place} has no real reason"
    outside_stt = [
        _rel(p)
        for p in _python()
        if "get_stt_provider" in p.read_text(encoding="utf-8")
        and not _rel(p).startswith("domains/chatbot/")
    ]
    assert not outside_stt, (
        f"the dictation provider is reached from outside its place: {outside_stt}"
    )

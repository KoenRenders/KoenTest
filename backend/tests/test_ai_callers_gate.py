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

The names are the PHYSICAL columns of each entry (`columns=`) and the register's own word, so the
contact values (`mdm.contact_detail.email`, stored in `ContactDetail.value`) are caught as `.value`.
The rules are also read in the modules of the caller's own domain that it imports, one level deep
(`own_domain_helpers`): a long prompt builder split into two files is read as one. `attrgetter`
and `_mapping` are read like `getattr`.

**The limits, stated and not hidden:** (1) the layer modules of a domain — `models`, `service`,
`api`, `ui`, `admin_ui`, `viewmodels`, `handlers`, `schema` — are not followed: they hold and move
stored data for every reader, and a prompt composed inside one is not seen here; (2) a name that is
public in one entry and kept back in another (`name`, `start_date`, `end_date`, `data`,
`is_active`, `sort_order`) is not forbidden, nor are `id`, `kind`, `source`, `key`, `status`,
`type`, `code`, `label`, `role`; (3) raw SQL text (`text("select street …")`) and a read two modules away are not seen; (4) a value that reaches a caller already formatted — from another domain's
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
DYNAMIC_ATTRIBUTES = {"__dict__", "__table__", "columns", "model_dump", "_mapping"}
DYNAMIC_CALLS = {"vars", "asdict"}
#: Layers that hold and move stored data and build no prompt: a caller's import of one of these is
#: not followed (a stated limit, below); any other module of the caller's own domain it imports is.
LAYER_MODULES = {"models", "service", "api", "ui", "admin_ui", "viewmodels", "handlers", "schema"}

#: A caller may read an attribute of the forbidden kind when it is no prompt: file → name → why.
ALLOWED_READS: dict[str, dict[str, str]] = {
    "domains/reporting/admin_ui.py": {
        "owner_email": "compares the owner of a saved report with the signed-in address; never in a prompt",
        "columns": "the columns of a report's result table, shown on the screen; no ORM metadata",
        "value": "the `.value` of an enum member (an operator, a format, a module code) on a report screen",
        "link": "the link a blocked call offers on the screen (`SeamBlocked.link`); no stored datum",
    },
    "domains/reporting/assistant.py": {
        "columns": "the columns of a report's result table; no ORM metadata",
    },
    "domains/reporting/assistant_answer.py": {
        "columns": "the columns of a report's result table; no ORM metadata",
    },
    "domains/newsletter/drafting.py": {
        "subject": (
            "the letter's own subject line, which the author typed: internal in the register, "
            "kept as free text under the pattern guard and the name scrub; the register's `none` "
            "subject is the mail log's"
        ),
    },
}


#: Names too common to say anything: the datum behind `.id`, `.kind` or `.source` is
#: classified by its entity, and an attribute of that name is read all over a caller for
#: reasons that are no prompt. The limit is stated; the entity's own columns stay forbidden.
GENERIC_NAMES = {"id", "kind", "source", "key", "status", "type", "code", "label", "role"}

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
        (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.domains.chatbot"))
        or (
            isinstance(n, ast.Import)
            and any(a.name.startswith("app.domains.chatbot") for a in n.names)
        )
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
    """The names a caller may not read, from the register (rule 1).

    The names are the PHYSICAL columns an entry covers (`columns=`), not the last part of its key:
    the register calls a contact value `mdm.contact_detail.email`, but the attribute a model reads
    is `ContactDetail.value` (review of #2053, dev4). An entry with no column of its own (a
    composite) is named by its key. Every kept-back name must be an attribute of some mapped class,
    except the columns of the reporting views, which are no model: a name that maps to nothing
    would be a gate that guards a word nobody writes."""
    from app.database import Base
    from app.domains.registry import load_all_models
    from app.kernel.attributes import AiExposure, registry

    load_all_models()
    entries = registry()
    assert len(entries) > 300, f"only {len(entries)} register entries read — is the gate looking?"

    def columns_of(entry) -> set[str]:
        return {c.rsplit(".", 1)[1] for c in entry.columns}

    def names(key: str, entry) -> set[str]:
        """What a model can read for this entry: its columns, and the word the register uses."""
        return columns_of(entry) | {key.rsplit(".", 1)[1]}

    kept_back: set[str] = set()
    people: set[str] = set()
    public: set[str] = set()
    for key, entry in entries.items():
        if entry.ai_exposure is AiExposure.PUBLIC:
            public |= names(key, entry)
        if entry.ai_exposure in (AiExposure.NONE, AiExposure.TOKENISED):
            kept_back |= names(key, entry)
        if key.startswith("mdm.") and entry.ai_exposure is not AiExposure.PUBLIC:
            people |= names(key, entry)
    forbidden = ((kept_back | people) - public) - GENERIC_NAMES
    mapped = {attr.key for mapper in Base.registry.mappers for attr in mapper.attrs}
    views = {
        n
        for k, e in entries.items()
        if k.startswith("reporting.") or not e.columns
        for n in names(k, e)
    }
    physical = {
        n
        for k, e in entries.items()
        if not k.startswith("reporting.") and e.ai_exposure is not AiExposure.PUBLIC
        for n in columns_of(e)
    }
    unmapped = sorted(n for n in forbidden & physical if n not in mapped and n not in views)
    assert not unmapped, f"kept-back names that no mapped class carries: {unmapped}"
    return forbidden


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
        if isinstance(node, ast.Call):
            callee = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if callee in DYNAMIC_CALLS:
                found.append(
                    (node.lineno, f"`{callee}(…)` reads attributes by a name nobody can see")
                )
            if callee in ("getattr", "attrgetter"):
                names_read = node.args[1:2] if callee == "getattr" else node.args
                for name in names_read:
                    if not isinstance(name, ast.Constant):
                        if rel not in ALLOWED_DYNAMIC:
                            found.append(
                                (node.lineno, f"`{callee}(…)` with a name that is no constant")
                            )
                    elif isinstance(name.value, str):
                        for part in name.value.split("."):
                            if part in forbidden and part not in allowed:
                                found.append(
                                    (
                                        node.lineno,
                                        f"reads `{part}` by `{callee}`, which the register keeps from a model",
                                    )
                                )
    return found


def own_domain_helpers(rel: str, source: str) -> list[str]:
    """The modules of the caller's own domain it imports (absolute or relative), minus the layers
    that only hold and move data: one level, the shape a long prompt builder is split into."""
    parts = rel.split("/")
    if parts[0] != "domains" or len(parts) < 3:
        return []
    domain = parts[1]
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if node.level:
            base = parts[: len(parts) - node.level]
            target = base + (module.split(".") if module else [])
        elif module.startswith(f"app.domains.{domain}"):
            target = ["domains", *module.split(".")[2:]]
        else:
            continue
        candidates = [target] + [target + [a.name] for a in node.names]
        for candidate in candidates:
            path = "/".join(candidate) + ".py"
            if (
                (APP / path).exists()
                and path != rel
                and candidate[-1] not in LAYER_MODULES
                and path not in found
            ):
                found.append(path)
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


def test_no_helper_of_an_ai_caller_reads_what_the_register_keeps_from_a_model():
    """A long prompt builder is split into two files: the second is read like the first (review of
    #2053, dev4). One level, the caller's own domain, the layers that only hold data excluded."""
    forbidden = forbidden_attributes()
    problems, followed = [], 0
    for p in ai_callers():
        for helper in own_domain_helpers(_rel(p), p.read_text(encoding="utf-8")):
            followed += 1
            source = (APP / helper).read_text(encoding="utf-8")
            problems += [
                f"{helper}:{line}: {what}" for line, what in reads(source, helper, forbidden)
            ]
    assert followed >= 1, "no helper of any caller was followed — is the gate looking?"
    assert not problems, "a helper of an AI caller:\n  " + "\n  ".join(problems)


def test_the_helpers_of_a_caller_are_followed_and_the_layers_are_not(tmp_path):
    """The shape, on the real tree: `proposer.py` imports from its own domain; a helper module is
    followed and `models` is not."""
    source = (APP / "domains/activities/proposer.py").read_text(encoding="utf-8")
    followed = own_domain_helpers("domains/activities/proposer.py", source)
    assert not any(h.endswith("/models.py") for h in followed), followed
    synthetic = "from .prompt_context import build\nfrom .models import Activity\n"
    names = own_domain_helpers("domains/activities/proposer.py", synthetic)
    assert names == [] or all(n.endswith("prompt_context.py") for n in names), names


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
        ('prompt = f"Contact {cd.value}"', "value"),
        ('get = attrgetter("board_notes")', "board_notes"),
        ("get = operator.attrgetter(field)", "no constant"),
        ('prompt = row._mapping["street"]', "_mapping"),
    ],
    ids=[
        "street-fstring",
        "address-concat",
        "join-getattr",
        "format-notes",
        "vars",
        "number",
        "contact-value",
        "attrgetter",
        "attrgetter-dynamic",
        "mapping",
    ],
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

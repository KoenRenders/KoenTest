"""Refuses a message built or sent anywhere but through the one build function `build_message` · hard · since #1924.

A test environment's mails carry its label in the subject and its line in the body
because the code that builds a message adds them. Before #1924 four places built a
message each; a fifth, written beside them, would have left without the label and no
test would have said so. Now `mail.service.build_message` is the only place that
makes a MIME message, and this gate reads the syntax tree of the application:

1. `MIMEMultipart`, `MIMEText`, `MIMEBase` and `EmailMessage` are called only inside
   `build_message`;
2. a function that calls `.sendmail(` also calls `build_message` — the message it
   sends is the one that function built, not one it got from elsewhere.

**What it does not see**, said here: a message built through another library, or by
hand as a string handed to `sendmail`, in a function that calls `build_message` for
something else. It checks the shape that was written four times, not every shape.

Proven red, additively (15 October 2026): a scratch `app/domains/mail/zz_scratch.py`
with a function that builds a `MIMEMultipart` and calls `sendmail` -> both rules name
it (`test_a_message_built_and_sent_around_the_one_function_is_named` on the same
source); removed, green. The gate saw the four places it guards before the move
(`test_the_gate_sees_the_places_that_send`).
"""

import ast
from pathlib import Path

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"
BUILDER = "build_message"
BUILT_BY_HAND = {"MIMEMultipart", "MIMEText", "MIMEBase", "EmailMessage"}


def _name_of(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def violations(source: str, where: str) -> tuple[list[str], int]:
    """(what is refused in this source, how many `.sendmail(` calls it holds)."""
    tree = ast.parse(source)
    refused, senders = [], 0
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        own = [n for n in ast.walk(function) if isinstance(n, ast.Call)]
        names = {_name_of(c) for c in own}
        if function.name != BUILDER:
            for name in sorted(BUILT_BY_HAND & names):
                refused.append(f"{where}::{function.name} calls {name} (only {BUILDER} may)")
        if "sendmail" in names:
            senders += 1
            if BUILDER not in names:
                refused.append(f"{where}::{function.name} sends without calling {BUILDER}")
    return refused, senders


def collect() -> tuple[list[str], int]:
    paths = bestanden(APP.rglob("*.py"), wat="the application's Python files", minstens=200)
    refused, senders = [], 0
    for path in paths:
        found, count = violations(
            path.read_text(encoding="utf-8"), path.relative_to(APP).as_posix()
        )
        refused += found
        senders += count
    return refused, senders


def test_no_message_is_built_or_sent_around_the_one_function():
    refused, _senders = collect()

    assert not refused, refused


def test_the_gate_sees_the_places_that_send():
    """Four places call `.sendmail(` today (the plain send, the campaign mail, the
    mail with attachments, the retry from the log); a gate that sees none checks
    nothing (#678)."""
    _refused, senders = collect()

    assert senders >= 4, f"the gate saw {senders} sending functions"


SCRATCH = """
def sneak(to, body):
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    server.sendmail("a@example.com", [to], msg.as_string())
"""


def test_a_message_built_and_sent_around_the_one_function_is_named():
    refused, senders = violations(SCRATCH, "zz_scratch.py")

    assert senders == 1
    assert refused == [
        "zz_scratch.py::sneak calls MIMEMultipart (only build_message may)",
        "zz_scratch.py::sneak sends without calling build_message",
    ]


def test_the_builder_itself_and_a_sender_that_calls_it_are_let_through():
    allowed = """
def build_message(subject):
    return MIMEMultipart("alternative")

def send(to):
    msg = build_message(subject="x")
    server.sendmail("a@example.com", [to], msg.as_string())
"""
    assert violations(allowed, "ok.py") == ([], 1)

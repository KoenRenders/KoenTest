"""Refuses a browser test that types after it looked at a refusal's banner without waiting with `refusal_shown` · hard · since #1910.

The kit shows a refused save in two steps: the banner with the answer's swap, and
one settle later the reason at the refused field with the focus moved to it. A
test that waits for the banner and types at once can cross that move and type into
the wrong field (9 of 80 walks of the booking record's refund test, 12 October
2026). `tests_e2e/schermen.py::refusal_shown` waits for the second step.

**The rule, read from the syntax tree.** In a function of `tests_e2e/`, a string
that names the banner (`data-save-refusal`) followed — on a later line of the same
function — by a call that types (`fill`, `type`, `press`, `press_sequentially`,
`select_option`, `check`, `set_input_files`) is refused unless the function calls
`refusal_shown`. The helper may stand anywhere in the function: the gate does not
know in which order the steps happen, so it is not a proof of every order.

**What it does not see**, said here and not hidden: a banner looked at in a helper
function the test calls (`_measure` in the builder tests), a banner reached by
another selector, and typing that happens in a function the test calls afterwards.
It is a check on the shape that went wrong, not on every shape.

Proven red, additively (14 October 2026): `refusal_shown` taken out of a scratch
copy of a real test (a function that looks at the banner and types) -> named by
`test_a_banner_followed_by_typing_without_the_helper_is_named`; the same on the
real tree is a scratch `tests_e2e/test_zz_scratch.py` with such a function, put in
and taken out again.
"""

import ast
from pathlib import Path

from tests._bestanden import bestanden

BACKEND = Path(__file__).resolve().parents[1]
BROWSER_TESTS = BACKEND / "tests_e2e"

BANNER = "data-save-refusal"
TYPING = {
    "fill",
    "type",
    "press",
    "press_sequentially",
    "select_option",
    "check",
    "set_input_files",
}
HELPER = "refusal_shown"


def _called(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
    return None


def banner_functions(source: str) -> list[tuple[str, bool]]:
    """Per function that names the banner: its name, and whether it types after it
    without calling the helper (True = refused)."""
    found = []
    for function in ast.parse(source).body + [
        m for c in ast.parse(source).body if isinstance(c, ast.ClassDef) for m in c.body
    ]:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = list(ast.walk(function))
        banner_lines = [
            n.lineno
            for n in nodes
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and BANNER in n.value
        ]
        if not banner_lines:
            continue
        waits = any(_called(n) == HELPER for n in nodes)
        typing_after = any(
            _called(n) in TYPING and n.lineno > min(banner_lines)
            for n in nodes
            if isinstance(n, ast.Call)
        )
        found.append((function.name, typing_after and not waits))
    return found


def collect() -> tuple[int, list[str]]:
    """(how many functions name the banner, the refused ones as `file::function`)."""
    paths = bestanden(
        BROWSER_TESTS.rglob("test_*.py"), wat="the browser tests of tests_e2e/", minstens=40
    )
    named, refused = 0, []
    for path in paths:
        for name, bad in banner_functions(path.read_text(encoding="utf-8")):
            named += 1
            if bad:
                refused.append(f"{path.relative_to(BACKEND).as_posix()}::{name}")
    return named, refused


def test_no_browser_test_types_after_a_banner_without_the_helper():
    named, refused = collect()

    assert named >= 15, f"the gate saw only {named} functions that name the banner (#678)"
    assert not refused, (
        "these tests look at a refusal's banner and then type, without waiting with "
        "`schermen.refusal_shown` (it waits for the reason at the field and the focus, "
        f"#1910): {refused}"
    )


SCRATCH = """
def test_types_after_the_banner(page):
    page.click("[data-form-save]")
    banner = page.locator("[data-save-refusal]")
    banner.wait_for()
    page.fill("#name", "x")
"""


def test_a_banner_followed_by_typing_without_the_helper_is_named():
    assert banner_functions(SCRATCH) == [("test_types_after_the_banner", True)]


def test_the_helper_or_no_typing_after_the_banner_is_let_through():
    waits = SCRATCH.replace("banner.wait_for()", "refusal_shown(page)")
    typed_before = SCRATCH.replace('    page.fill("#name", "x")\n', "").replace(
        '    page.click("[data-form-save]")',
        '    page.fill("#name", "x")\n    page.click("[data-form-save]")',
    )
    assert banner_functions(waits) == [("test_types_after_the_banner", False)]
    assert banner_functions(typed_before) == [("test_types_after_the_banner", False)]

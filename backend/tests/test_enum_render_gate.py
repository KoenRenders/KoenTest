"""The twelfth gate of CR-12: no enum member ever reaches a template's output.

**Why this gate exists, and it is not a hypothesis.** Three times in this
change request a member ended up in an HTML attribute:

| Where | What rendered | What broke |
|---|---|---|
| the subscriber filter | `SubscriberStatus.CONFIRMED` in `<option value=…>` | the filter matched nothing |
| the newsletter audience radio | `Audience.MEMBERS` in `<input value=…>` | the chosen audience never came back |
| the attendance button | `Attendance.PRESENT` in `<input name="current">` | every click stayed grey |

None of the eleven gates can see that. The template gate looks for a
*comparison* with a literal; the loose-string gate looks for a comparison in
Python. A member that is **rendered** is neither. Two of the three were found
by hand and the third by an e2e golden flow — which covers four flows, not
every admin screen. So without this the next one is a coincidence.

**It is a guard, not a sample.** `install_enum_guard` hooks Jinja's
`finalize`, which runs for every `{{ ... }}` in every template of both
environments. Every render test in the suite is therefore a detector, and the
"which screens did you check?" question disappears. Filters run first, so
`{{ x | code_label("...") }}` hands the guard a string.

## Proof that this can go red

The method of the css gate (#652), on 26 September 2026:

| Violation | Fired |
|---|---|
| `attendance=attendance_of(db, meeting)` straight through, so `{{ state }}` is a member | yes — `EnumRendered: a template rendered Attendance.PRESENT, the enum member.` |
| the guard's `strict` forced to `False` in `app/ui/__init__.py` | yes — `test_the_guard_is_installed_and_strict_on_both_environments` |
| the `install_enum_guard(...)` call commented out altogether | yes — the same test |

The last two matter more than the first, and the second one is why that test
asks the environment to **raise** rather than merely checking that something
is attached: with `strict=False` the guard is installed, logs, repairs — and
finds nothing anybody reads. A guard that is off finds nothing and says
nothing, which is the failure mode of #678 in its purest form. Hence also the
second number in the ratchet table: how many values it actually inspected.
"""
from enum import Enum

import pytest
from jinja2 import Environment, DictLoader

from app.kernel import codes as kernel_codes
from app.kernel.codes import EnumRendered, install_enum_guard
from app.ui import templates


class SampleStatus(Enum):
    OPEN = "open"


def _environment(*, strict: bool) -> Environment:
    env = Environment(loader=DictLoader({"t.html": '<input value="{{ x }}">'}),
                      autoescape=True)
    install_enum_guard(env, strict=strict)
    return env


# ── The guard itself ─────────────────────────────────────────────────────────

def test_a_member_in_the_output_is_refused():
    """The exact shape of all three real cases: a member into `value=`."""
    with pytest.raises(EnumRendered, match=r"SampleStatus\.OPEN"):
        _environment(strict=True).get_template("t.html").render(x=SampleStatus.OPEN)


def test_the_code_passes_untouched():
    """What a view-model is supposed to hand over."""
    output = _environment(strict=True).get_template("t.html").render(x="open")
    assert output == '<input value="open">'


def test_outside_dev_and_test_it_repairs_instead_of_raising():
    """UAT and PROD render the code and log, the way `StrictUndefined` does.

    A repair and not a silence: the code is what the attribute should have
    carried anyway, so the screen keeps working while the log says what
    happened. A visitor never meets a 500 over a rendering detail.
    """
    output = _environment(strict=False).get_template("t.html").render(x=SampleStatus.OPEN)
    assert output == '<input value="open">'


def test_a_label_filter_still_renders_its_word(db_session):
    """The guard sits after the filters, so the one allowed way through works."""
    from app.kernel.codes import reset_label_cache

    reset_label_cache()
    env = Environment(loader=DictLoader({"t.html": '{{ x | code_label("meeting_status") }}'}),
                      autoescape=True)
    from app.kernel.codes import install_jinja_codes

    install_jinja_codes(env)
    install_enum_guard(env, strict=True)
    from app.domains.meetings.api import MeetingStatus

    assert env.get_template("t.html").render(x=MeetingStatus.AGENDA) == "Agenda"
    reset_label_cache()


# ── That it is attached, and that it sees something (#678) ───────────────────

def test_the_guard_is_installed_and_strict_on_both_environments():
    """A guard nobody attached finds nothing and says nothing.

    Both Jinja environments of this codebase: the shared one behind every
    screen, and the poster environment of the design studio. And not just
    *attached* — it has to **raise** here, because a guard that logs in the
    test environment turns a red test into a line nobody reads.
    """
    from app.domains.designstudio import render

    for name, env in (("the shared template environment", templates.env),
                      ("the poster environment", render._env())):
        template = env.from_string('<input value="{{ x }}">')
        with pytest.raises(EnumRendered):
            template.render(x=SampleStatus.OPEN)
        assert template.render(x="open") == '<input value="open">', name


def test_the_guard_actually_saw_values_in_this_run():
    """`0` would mean the guard ran nowhere, which reads exactly like `0` found.

    Rendering one template here is enough to make the counter non-zero on its
    own, so this is a floor and not a coverage claim; the number in the
    ratchet table is where the real coverage shows.
    """
    before = kernel_codes.rendered_under_the_guard
    _environment(strict=True).get_template("t.html").render(x="open")
    assert kernel_codes.rendered_under_the_guard > before

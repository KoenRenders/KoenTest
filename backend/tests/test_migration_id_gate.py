"""#1315 — a migration's `revision` id is the one its file name carries.

A migration came out of `alembic revision` as `168_…` because the head was 167.
After a rebase onto a branch that added its own 168, the file name and
`down_revision` were moved to 169 by hand and the id stayed `168_2026_09_29_090415`.
Alembic ran it — the timestamp is unique — but `alembic heads`, the deploy summary
and every later `down_revision` would have shown "168_…" beside the real 168: the
confusion CLAUDE.md warns of at *Alembic migrations*. The chain gate
(`test_migratieketen_gate.py`) cannot see it; it asks only for one head.

So: the file name's leading part — the number, and for the generated ids the
timestamp after it — must be the `revision` id. The message names the file, the id
and what it should be.

`EXEMPT` holds the fourteen migrations from the transition to generated ids
(#951, 16–20 September 2026): a timestamp id in a file that still has the old
short name. They are merged and frozen — CLAUDE.md forbids touching a merged
migration, and its file name is part of it — so they stay listed. The list may
only shrink: an entry that no longer disagrees fails the gate until it is removed.

Proven red (29 September 2026), additively: a file `170_2026_09_29_120000_zz.py`
with `revision = "169_2026_09_29_120000"` added to `alembic/versions` → the gate
named it, its id and the expected `170_2026_09_29_120000`. And `001_initial_schema.py`,
which agrees, added to `EXEMPT` → "no longer disagree … remove them".
"""

from __future__ import annotations

import re

from tests._migratieketen import Migratie, lees_migraties

# Transition migrations (#951): generated timestamp id, old short file name. Frozen.
EXEMPT: dict[str, str] = {
    name: "transition to generated ids (#951): timestamp id, old short file name; frozen"
    for name in (
        "129_newsletter_module.py",
        "130_ai_call_log_provider_and_cost.py",
        "131_newsletter_draft_reports.py",
        "132_home_intro_contact_button.py",
        "133_activity_organisers.py",
        "134_media_design_kinds.py",
        "135_activity_description.py",
        "136_designstudio_schema.py",
        "137_designstudio_two_presets.py",
        "138_activity_board_notes.py",
        "139_organiser_show_flags.py",
        "140_designstudio_round3.py",
        "141_home_intro_membership_band.py",
        "142_newsletter_preview_text.py",
    )
}

_ID_IN_NAME = re.compile(r"^(\d+(?:_\d{4}_\d{2}_\d{2}_\d{6})?)(?:_|\.py$)")


def expected_id(migration: Migratie) -> str | None:
    """The id the file name carries: `170` or `170_2026_09_29_094628`."""
    found = _ID_IN_NAME.match(migration.naam)
    return found.group(1) if found else None


def mismatches(migrations: list[Migratie]) -> dict[str, str]:
    """File name → message, for every migration whose id is not its name's."""
    out = {}
    for m in migrations:
        expected = expected_id(m)
        if m.revision != expected:
            out[m.naam] = f"{m.naam}: revision = {m.revision!r}, the file name says {expected!r}"
    return out


def test_every_revision_id_is_the_one_its_file_name_carries():
    migrations = lees_migraties()  # fails on too few files (#678)
    wrong = {name: msg for name, msg in mismatches(migrations).items() if name not in EXEMPT}
    assert not wrong, (
        f"{len(wrong)} of {len(migrations)} migrations carry another id than their file "
        "name — regenerate with `alembic revision` or put the id right:\n"
        + "\n".join(wrong.values())
    )


def test_the_exemptions_only_shrink():
    still = mismatches(lees_migraties())
    stale = sorted(name for name in EXEMPT if name not in still)
    assert not stale, f"these no longer disagree (or are gone) — remove them from EXEMPT: {stale}"

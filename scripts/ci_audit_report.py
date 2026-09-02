#!/usr/bin/env python3
"""Turn a pip-audit JSON report into a CI signal that cannot be missed (#574).

Why this exists. The `audit` job in `backend-tests.yml` is deliberately
*reporting*, not blocking: a vulnerability in a code path we never touch should
not hold up a release, and there is no ignore-list mechanism yet (architecture
doc §19.1). The cost of that choice was that the job stayed green with 33 known
vulnerabilities behind it — nobody looked, because a green tick says "nothing to
see here" (#571).

So the job stays green, but it stops being silent. For every affected package
this script emits:

- a `::warning::` workflow command, which GitHub renders in the Annotations box
  at the top of the run page (one per package, not per advisory — GitHub caps
  annotations at 10 per step, and 33 advisories would blow straight past that);
- a Markdown table in the job summary, which is the full detail;
- the same table on stdout, so the job log is readable on its own.

A clean audit also writes its summary — "no findings" must be something you can
*see*, not something you infer from the absence of a warning.

Fix versions come straight from the advisory and are per-advisory: the version
that fixes advisory A may still carry advisory B. #571 hit exactly that (pypdf
6.14.0 was the advertised fix and still had 12 open). Hence "first candidate",
never "safe version" — always re-audit the version you land on.

Usage: ci_audit_report.py <audit.json>
Always exits 0: whether findings block anything is the caller's decision.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_packages(raw: object) -> list[dict]:
    """Normalise the two pip-audit JSON shapes to a list of package dicts.

    Modern pip-audit wraps the list in ``{"dependencies": [...]}``; older
    releases emitted the bare list. Accept both so a pip-audit upgrade cannot
    quietly turn this report into "no findings".
    """
    if isinstance(raw, dict):
        raw = raw.get("dependencies", [])
    if not isinstance(raw, list):
        raise ValueError(f"unexpected pip-audit JSON: {type(raw).__name__}")
    return [p for p in raw if isinstance(p, dict)]


def first_candidate(vulns: list[dict]) -> str:
    """Highest fix version mentioned across the advisories, as a starting point.

    Not a promise that this version is clean — see the module docstring.
    """
    fixes = {v for vuln in vulns for v in (vuln.get("fix_versions") or [])}
    if not fixes:
        return "geen fix beschikbaar"

    def key(version: str) -> tuple:
        return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))

    return sorted(fixes, key=key)[-1]


def render(packages: list[dict]) -> tuple[str, list[str]]:
    """Return (markdown report, warning lines) for the affected packages."""
    affected = [p for p in packages if p.get("vulns")]
    if not affected:
        return ("### pip-audit — geen bekende kwetsbaarheden ✅\n\n"
                f"{len(packages)} vastgepinde pakketten gecontroleerd.\n"), []

    total = sum(len(p["vulns"]) for p in affected)
    lines = [
        f"### pip-audit — {total} bevinding(en) in {len(affected)} pakket(ten) ⚠️",
        "",
        "Niet-blokkerend: de release gaat door, jij beslist of dit moet wachten.",
        "",
        "| Pakket | Gepind | Eerste kandidaat-fix | # | Advisories |",
        "|---|---|---|---|---|",
    ]
    warnings = []
    for pkg in sorted(affected, key=lambda p: -len(p["vulns"])):
        name = pkg.get("name", "?")
        version = pkg.get("version", "?")
        vulns = pkg["vulns"]
        ids = sorted(str(v.get("id", "?")) for v in vulns)
        shown = ", ".join(f"`{i}`" for i in ids[:6])
        if len(ids) > 6:
            shown += f" … (+{len(ids) - 6})"
        candidate = first_candidate(vulns)
        lines.append(f"| `{name}` | {version} | {candidate} | {len(vulns)} | {shown} |")
        warnings.append(
            f"pip-audit: {name}=={version} heeft {len(vulns)} bekende "
            f"kwetsbaarheid(en) — eerste kandidaat-fix: {candidate}. "
            f"Controleer die versie opnieuw: een fixversie kan zelf nog "
            f"advisories hebben (#571)."
        )
    lines += [
        "",
        "> De kandidaat-fix komt uit de advisory zelf en is per advisory. Audit "
        "de versie waarop je landt altijd opnieuw voor je hem pint.",
        "",
    ]
    return "\n".join(lines) + "\n", warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: ci_audit_report.py <audit.json>", file=sys.stderr)
        return 0  # never break the build on our own reporting

    path = Path(argv[1])
    try:
        packages = load_packages(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        # pip-audit itself failed (network, bad JSON). Silence is the one thing
        # we are not allowed to produce, so shout about the missing report.
        print(f"::warning::pip-audit-rapport onleesbaar ({exc}) — "
              f"de scan heeft NIET gedraaid, behandel dit als onbekend risico")
        _append_summary("### pip-audit — rapport onleesbaar ⚠️\n\n"
                        f"`{path}`: {exc}\n\nDe scan is niet gedraaid.\n")
        return 0

    report, warnings = render(packages)
    for warning in warnings:
        print(f"::warning::{warning}")
    print(report)
    _append_summary(report)
    return 0


def _append_summary(text: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

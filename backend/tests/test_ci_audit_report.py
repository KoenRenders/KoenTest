"""The pip-audit report must never be silent (#574).

The `audit` job is deliberately non-blocking, so its only job is to be *seen*.
That makes the reporting itself the thing worth testing: if this script emits
nothing, CI goes green and 33 vulnerabilities sit behind a tick again — exactly
what happened in #571. Each test below pins one way that silence could return.

The script is driven as a subprocess, like `test_deploy_script_imports.py` does
for the deploy scripts: it runs in CI as a standalone stdlib program, so that is
how it should be exercised.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_audit_report.py"

FINDINGS = {
    "dependencies": [
        {"name": "pillow", "version": "12.2.0", "vulns": [
            {"id": f"GHSA-{i:04d}", "fix_versions": ["12.3.0"]} for i in range(26)
        ]},
        {"name": "markdown", "version": "3.7", "vulns": [
            {"id": "PYSEC-2026-89", "fix_versions": ["3.8.1"]},
            {"id": "GHSA-5wmx", "fix_versions": ["3.8.1"]},
        ]},
        {"name": "fastapi", "version": "0.137.1", "vulns": []},
    ]
}


def run(tmp_path, payload, *, write=True):
    report = tmp_path / "audit.json"
    if write:
        report.write_text(json.dumps(payload))
    summary = tmp_path / "summary.md"
    summary.write_text("")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(report)],
        capture_output=True, text=True,
        # De echte omgeving erven (CI draait een eigen Python-installatie), maar
        # GITHUB_STEP_SUMMARY naar een wegwerpbestand wijzen — anders schrijft
        # deze test in de summary van de draaiende CI-run.
        env={**os.environ, "GITHUB_STEP_SUMMARY": str(summary)},
    )
    return proc, summary.read_text()


def test_findings_produce_one_annotation_per_package(tmp_path):
    """GitHub caps annotations at 10 per step, so 33 advisories must collapse to
    one warning per package — otherwise the tail is dropped and the report lies
    about its own completeness."""
    proc, _ = run(tmp_path, FINDINGS)
    warnings = [ln for ln in proc.stdout.splitlines() if ln.startswith("::warning::")]
    assert len(warnings) == 2  # pillow + markdown; fastapi has no vulns
    assert any("pillow==12.2.0" in w and "26" in w for w in warnings)


def test_findings_land_in_the_job_summary(tmp_path):
    """The annotation is the alarm; the summary is the detail. Both, always."""
    _, summary = run(tmp_path, FINDINGS)
    assert "28 bevinding(en) in 2 pakket(ten)" in summary
    assert "`pillow`" in summary and "12.3.0" in summary
    assert "PYSEC-2026-89" in summary


def test_reporting_never_blocks(tmp_path):
    """Exit 0 even with findings — the job stays green on purpose; whether a
    finding holds up a release is Koen's call, not the scanner's."""
    proc, _ = run(tmp_path, FINDINGS)
    assert proc.returncode == 0


def test_a_clean_audit_still_writes_a_summary(tmp_path):
    """'Clean' has to be visible. Inferring it from the absence of a warning is
    the same trap as reading a green tick as 'nothing to see here'."""
    proc, summary = run(tmp_path, {"dependencies": [
        {"name": "fastapi", "version": "0.137.1", "vulns": []},
    ]})
    assert "::warning::" not in proc.stdout
    assert "geen bekende kwetsbaarheden" in summary
    assert proc.returncode == 0


def test_a_missing_report_warns_that_the_scan_did_not_run(tmp_path):
    """If pip-audit itself dies, the dangerous outcome is a green job with no
    output at all. Absence of a report must read as unknown risk, not as safe."""
    proc, summary = run(tmp_path, None, write=False)
    assert "::warning::" in proc.stdout
    assert "NIET gedraaid" in proc.stdout
    assert "onleesbaar" in summary
    assert proc.returncode == 0


def test_the_fix_version_is_labelled_a_candidate(tmp_path):
    """#571's lesson: fix versions are per advisory, and pypdf 6.14.0 — the
    advertised fix — still carried 12 open advisories. The report must not
    present one as a safe version."""
    _, summary = run(tmp_path, {"dependencies": [
        {"name": "pypdf", "version": "6.13.3", "vulns": [
            {"id": "A", "fix_versions": ["6.14.0"]},
            {"id": "B", "fix_versions": ["6.9.1"]},
        ]},
    ]})
    assert "kandidaat" in summary.lower()
    # Hoogste van de genoemde fixversies, numeriek — niet lexicaal (6.9.1 > 6.14.0
    # als je strings vergelijkt).
    assert "6.14.0" in summary


@pytest.mark.parametrize("payload", [
    {"dependencies": [{"name": "pillow", "version": "12.2.0",
                       "vulns": [{"id": "X", "fix_versions": ["12.3.0"]}]}]},
    [{"name": "pillow", "version": "12.2.0",
      "vulns": [{"id": "X", "fix_versions": ["12.3.0"]}]}],
])
def test_both_pip_audit_json_shapes_are_read(tmp_path, payload):
    """Modern pip-audit wraps the list in {"dependencies": …}; older releases
    emit the bare list. A pip-audit upgrade must not silently turn every report
    into 'no findings'."""
    proc, summary = run(tmp_path, payload)
    assert "::warning::" in proc.stdout
    assert "1 bevinding(en)" in summary


def test_no_fix_available_is_reported_as_such(tmp_path):
    _, summary = run(tmp_path, {"dependencies": [
        {"name": "odfpy", "version": "1.4.1", "vulns": [{"id": "X", "fix_versions": []}]},
    ]})
    assert "geen fix beschikbaar" in summary

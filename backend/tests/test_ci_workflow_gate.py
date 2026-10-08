"""The gate of CR-29 (a shorter CI, C7) — the workflow file keeps its promises.

The CI run is as long as its longest job, and four things keep it short without
making it test less: every job has a time limit, pytest runs in several processes,
one commit starts one run, and a commit that changes only documents no test reads
starts none. The workflow file is edited by Koen or the master CLI only; this gate
is the one place that keeps it from drifting away from the rule.

Each rule is a function that takes the PARSED workflow and returns its findings,
so the proofs below hand it a changed copy and never touch the real file.

Broken to check that each rule can go red — the proofs are tests of their own,
at the bottom, so nobody has to think them up again:
  * a seventh job without `timeout-minutes` added → rule 1 names it;
  * the pytest step without `-n` → rule 2;
  * `feature/**` added to the push trigger → rule 3;
  * `cancel-in-progress: true`, which would cancel a master run → rule 3;
  * the group `ci-${{ github.ref }}`, which all master commits share, so a
    waiting master run is cancelled by the next commit → rule 3;
  * `docs/reporting-universe.md` added to `paths-ignore` → rule 4 names the test
    that reads it, while a document named in a docstring only passes;
  * a filter entry that matches no file → rule 4.
"""

import ast
import copy
import functools
import re
from pathlib import Path

import pytest
import yaml

# One worker for the file (CR-29 R7): rule 4 parses every test module, once per
# process (`_test_module_strings`) — spread over four workers that was four times.
pytestmark = [pytest.mark.ui_agnostisch, pytest.mark.xdist_group("ci_workflow_gate")]

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
WORKFLOW = REPO / ".github" / "workflows" / "backend-tests.yml"
MAX_MINUTES = 30
# Where a test module, or a helper a test imports, can live (CR-13 R15).
TEST_ROOTS = ("tests", "tests_e2e", "app/domains/*/tests")


def load_workflow(path: Path = WORKFLOW) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as the boolean True.
    if True in data:
        data["on"] = data.pop(True)
    return data


# ── Rule 1: every job ends by itself ─────────────────────────────────────────


def jobs_without_time_limit(workflow: dict) -> list[str]:
    jobs = workflow["jobs"]
    assert jobs, "the workflow has no jobs — the gate would look at nothing"
    return [
        f"CI job `{name}` has no time limit of at most {MAX_MINUTES} minutes — CR-29"
        for name, job in jobs.items()
        if not isinstance(job.get("timeout-minutes"), int)
        or not 0 < job["timeout-minutes"] <= MAX_MINUTES
    ]


# ── Rule 2: pytest runs in several processes ─────────────────────────────────


def pytest_step_findings(workflow: dict) -> list[str]:
    runs = [
        step["run"]
        for step in workflow["jobs"].get("pytest", {}).get("steps", [])
        if "-m pytest" in step.get("run", "")
    ]
    assert len(runs) == 1, f"expected one pytest step in the `pytest` job, found {len(runs)}"
    findings = []
    if not re.search(r"(^|\s)-n\s+(\d+|auto)(\s|$)", runs[0]):
        findings.append("pytest runs in one process — CR-29")
    # A test that must not run beside its neighbour is marked `xdist_group`, and
    # that mark is ignored without this option: it would stop holding in silence.
    if "--dist loadgroup" not in runs[0]:
        findings.append(
            "pytest runs without `--dist loadgroup`: `xdist_group` marks are ignored — CR-29"
        )
    return findings


# ── Rule 3: one run per commit, and a master run finishes ────────────────────


def trigger_findings(workflow: dict) -> list[str]:
    message = "one run per commit, and a master run finishes — CR-29"
    findings = []
    for event in ("push", "pull_request"):
        branches = (workflow["on"].get(event) or {}).get("branches")
        if branches != ["master"]:
            findings.append(f"{message}: `on.{event}.branches` is {branches}, not ['master']")
    concurrency = workflow.get("concurrency")
    if not isinstance(concurrency, dict):
        return [*findings, f"{message}: no `concurrency` block"]
    group = str(concurrency.get("group", ""))
    if "github.ref" not in group:
        findings.append(f"{message}: the concurrency group does not separate by `github.ref`")
    # One group for the whole of master makes a master run WAIT behind the running
    # one, and GitHub cancels a waiting run as soon as a newer commit arrives —
    # `cancel-in-progress: false` spares only the run that already runs (8 October
    # 2026: a master commit lost its run that way, the day the rule came in). So a
    # push gets a group per commit, and only a pull request shares one per branch.
    if not ("github.event_name == 'pull_request' && github.ref" in group and "github.sha" in group):
        findings.append(
            f"{message}: the concurrency group is {group!r}; a push must get a group "
            "per commit (`github.sha`), or master commits queue behind each other "
            "and the waiting run is cancelled"
        )
    cancel = concurrency.get("cancel-in-progress")
    spares_master = isinstance(cancel, str) and (
        "github.event_name == 'pull_request'" in cancel
        or "github.ref != 'refs/heads/master'" in cancel
    )
    if not spares_master:
        findings.append(
            f"{message}: `cancel-in-progress` is {cancel!r}; it must cancel a pull "
            "request's stale run only, never the run of a master commit"
        )
    return findings


# ── Rule 4: the docs filter skips nothing a test reads ───────────────────────


def _string_constants_outside_docstrings(tree: ast.AST) -> list[str]:
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


@functools.cache
def _test_module_strings() -> dict[str, list[str]]:
    """Every string a test module could open a file by, per module — parsed once."""
    modules = sorted({path for root in TEST_ROOTS for path in BACKEND.glob(f"{root}/**/*.py")})
    assert len(modules) > 500, f"only {len(modules)} test modules found — a root has moved"
    return {
        str(path.relative_to(REPO)): _string_constants_outside_docstrings(
            ast.parse(path.read_text(encoding="utf-8"))
        )
        for path in modules
    }


def docs_filter_findings(workflow: dict, strings: dict[str, list[str]] | None = None) -> list[str]:
    filters = {
        event: (workflow["on"].get(event) or {}).get("paths-ignore") or []
        for event in ("push", "pull_request")
    }
    if filters["push"] != filters["pull_request"]:
        return ["`paths-ignore` differs between `push` and `pull_request` — CR-29"]
    strings = _test_module_strings() if strings is None else strings
    findings = []
    for entry in filters["push"]:
        files = [path for path in REPO.glob(entry) if path.is_file()]
        if not files:
            findings.append(f"the docs filter entry `{entry}` matches no file — CR-29")
        for path in files:
            readers = sorted(
                module
                for module, constants in strings.items()
                if any(path.name in constant for constant in constants)
            )
            findings.extend(
                f"a test reads `{path.relative_to(REPO)}` ({module}); "
                "the docs filter would skip it — CR-29"
                for module in readers
            )
    return findings


# ── The workflow as it stands ────────────────────────────────────────────────


def test_every_job_has_a_time_limit():
    assert jobs_without_time_limit(load_workflow()) == []


def test_pytest_runs_in_several_processes():
    assert pytest_step_findings(load_workflow()) == []


def test_one_run_per_commit_and_a_master_run_finishes():
    assert trigger_findings(load_workflow()) == []


def test_the_docs_filter_skips_nothing_a_test_reads():
    workflow = load_workflow()
    assert workflow["on"]["push"].get("paths-ignore"), (
        "no `paths-ignore` on the push trigger — this test would look at nothing"
    )
    assert docs_filter_findings(workflow) == []


# ── The proofs: each rule goes red on a changed copy ─────────────────────────


@pytest.fixture
def changed():
    return copy.deepcopy(load_workflow())


def test_proof_a_job_without_a_limit_is_named(changed):
    changed["jobs"]["seventh"] = {"runs-on": "ubuntu-latest", "steps": []}
    assert jobs_without_time_limit(changed) == [
        "CI job `seventh` has no time limit of at most 30 minutes — CR-29"
    ]
    changed["jobs"]["seventh"]["timeout-minutes"] = 45
    assert len(jobs_without_time_limit(changed)) == 1, "a limit above 30 minutes passed"


def test_proof_pytest_in_one_process_is_refused(changed):
    for step in changed["jobs"]["pytest"]["steps"]:
        if "-m pytest" in step.get("run", ""):
            step["run"] = "python -m pytest -v --tb=short --cov=app --cov-fail-under=85"
    findings = pytest_step_findings(changed)
    assert "pytest runs in one process — CR-29" in findings
    assert any("loadgroup" in finding for finding in findings)


def test_proof_a_second_branch_pattern_is_refused(changed):
    changed["on"]["push"]["branches"].append("feature/**")
    findings = trigger_findings(changed)
    assert len(findings) == 1 and "on.push.branches" in findings[0], findings


@pytest.mark.parametrize(
    "group",
    [
        "ci-${{ github.ref }}",  # what phase 1 shipped: one group for all of master
        "ci-${{ github.sha }}",  # a group per commit for a pull request too: nothing is cancelled
    ],
)
def test_proof_a_group_that_master_commits_share_is_refused(changed, group):
    changed["concurrency"]["group"] = group
    findings = trigger_findings(changed)
    assert findings, f"the group {group!r} passed"
    assert all("concurrency group" in finding for finding in findings), findings


@pytest.mark.parametrize("cancel", [True, False, "true", None])
def test_proof_a_cancel_that_does_not_spare_master_is_refused(changed, cancel):
    changed["concurrency"]["cancel-in-progress"] = cancel
    findings = trigger_findings(changed)
    assert len(findings) == 1 and "cancel-in-progress" in findings[0], findings


def test_proof_a_filter_entry_a_test_reads_is_refused(changed):
    for event in ("push", "pull_request"):
        changed["on"][event]["paths-ignore"].append("docs/reporting-universe.md")
    findings = docs_filter_findings(changed)
    assert findings, "a document a test compares with its render passed the filter"
    assert all("docs/reporting-universe.md" in finding for finding in findings), findings
    assert any("test_reporting_universe_gate.py" in finding for finding in findings), findings


def test_proof_a_docstring_mention_is_not_a_read():
    """The rules gate names its change request in its docstring and opens no such file."""
    strings = _test_module_strings()["backend/tests/test_rules_gate.py"]
    source = (BACKEND / "tests" / "test_rules_gate.py").read_text(encoding="utf-8")
    # Read from that docstring and not written here: a constant naming the
    # document in THIS module would be a read by rule 4's own measure.
    named = re.search(r"docs/(change_request_\w+\.md)", ast.get_docstring(ast.parse(source)))
    assert named, "the rules gate no longer names its change request in its docstring"
    assert (REPO / "docs" / named.group(1)).is_file()
    assert not any(named.group(1) in constant for constant in strings)


def test_proof_a_filter_entry_that_matches_nothing_is_refused(changed):
    for event in ("push", "pull_request"):
        changed["on"][event]["paths-ignore"].append("docs/no_such_document_*.md")
    assert docs_filter_findings(changed) == [
        "the docs filter entry `docs/no_such_document_*.md` matches no file — CR-29"
    ]


def test_proof_a_filter_on_one_trigger_only_is_refused(changed):
    changed["on"]["push"]["paths-ignore"].append("docs/reporting-universe.md")
    assert docs_filter_findings(changed) == [
        "`paths-ignore` differs between `push` and `pull_request` — CR-29"
    ]

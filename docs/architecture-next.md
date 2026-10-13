---
title: Architecture — the Raak platform
---

**Version:** 2.0 — in restructuring (13 October 2026)
**As-is:** `master` @ cf80ccde, 13 October 2026; the last GitHub Release is v2.16.0 (what PROD runs is measured at the close-out of the next release)
**Scope:** every claim is traceable to code (Appendix B); planned work stands in part E

> **While this document is being restructured** it grows part by part on the
> architecture branch, each part measured against `master` in the commit that
> adds it: parts C and E first, then A, B and D (`docs/architecture-skeleton.md`
> holds the plan and Koen's decisions of 11 and 13 October 2026). Until the
> restructuring is complete, `docs/architecture.md` remains the document the
> PDF build reads; this file replaces it when every part stands.

# Part C — The harness

The rules and the gates that give predictable development without drift. This
part is the counterpart of B7 (rules of the solution) and C7 (gates) of the
change request template: what a change request writes per change, this part
holds for the whole platform.

A harness has four layers, and the order matters: a rule is written once in
its home (C1); a mechanical rule is held by a gate that runs on every push
(C2) inside a CI whose jobs block the merge (C3); what a regex cannot decide
is judged by a person or a read-only agent at a fixed moment (C4); and the
process itself has gates that stop a release where a wrong step is expensive
(C5). C6 lists what the gates caught, because every gate here exists for a
failure that happened.

## C1. The rules and where each lives

Every rule has exactly one home. The home is where the rule is *written*; a
gate *holds* it. A rule found in two places is a bug of the same kind as a fact
stored twice (`AGENTS.md`, *Twee keer dezelfde reparatie*), so the table below
is the index, not a copy.

| Rule | Home | Held by |
|---|---|---|
| The process: who may change what, issue first, branches and merges, releases, reviews, builders outside the Claude series, data operations through the app, Europe first, keep it simple, first time right | `AGENTS.md` | the process gates of C5; `backend/tests/test_ci_workflow_gate.py` holds the CI's promises |
| All new code and documentation in English; Dutch identifiers only inside a baseline that may only shrink (#780) | `AGENTS.md` (*Code language*) | `backend/tests/test_rules_gate.py`, section 7, against `backend/tests/dutch_identifiers_baseline.py` (370 entries on 13 October 2026) |
| Formatting and linting | `pyproject.toml` (ruff, #781) | the `lint` job (C3); `backend/tests/test_ruff_migrations.py` for new migrations |
| A fixed vocabulary is a code table; `CodeEnum`, never `str, Enum` | `docs/code-style.md` (CR-12) | `backend/tests/test_codes_gate.py`, eleven checks, with `backend/tests/codes_baseline.py` for what is deliberately not a code |
| A rule has one home (validator, method, service, constraint) | `docs/code-style.md` (CR-13 §B9.1) | `backend/tests/test_rules_gate.py` (CR-13 phases 0a and 0c) |
| A copied model declares every column | `docs/code-style.md` (#1464) | `backend/tests/test_copy_plans_gate.py` |
| A gate names a right, never a role | `docs/code-style.md` (CR-24) | `backend/tests/test_rights_gate.py`; the role model itself in `backend/tests/test_role_model_gates.py` (#530) |
| Three validation layers: form in the router, meaning in the service, integrity at rest in the database; a screen builds a view-model and chooses a template, never touches `db` | `AGENTS.md` (*Validation layers*), `docs/design-system.md` §8.3 | `backend/tests/test_layer_gate.py` (#635), `backend/tests/test_template_variables_gate.py` (#643) |
| A domain is reached through its `api.py` facade; a port or an event where a facade would couple | `AGENTS.md` (*Backend architecture*), `docs/architecture.md` §3.2.1 (moves to part A) | `backend/tests/test_import_boundaries.py`, `backend/tests/test_port_gate.py` (#1251), `backend/tests/test_rules_gate.py::test_every_json_route_names_its_caller` |
| Every screen is drawn by the kit: tokens, macros, layouts, one shell per side | `docs/design-system.md` (norm since 9 September 2026), `docs/design-system-end-state.md` (CR-11) | `backend/tests/test_ui_conventions_gate.py` (#528) and the kit gates of CR-11: list page, list table, record form, record header, record tab, form field, repeating group, admin frame, public shell, public form page, assistant, read-mode grid; the ratchets `test_ui_ratchets.py`, `test_public_ratchets.py`, `test_actiebalk_ratchet.py` |
| User-facing text passes through `_()`; one word per contact field; the short date and the site name are written in one place | `docs/design-system.md` §6, `AGENTS.md` (*Documentation language*) | `test_i18n_gate.py` (#407), `test_contact_labels_gate.py` (#1719), `test_short_date_gate.py` (#1242), `test_site_name_gate.py` (#1546) |
| Money: the webhook body is never trusted; no hard delete in a domain that owns a payable; the payment-method choice stands once; FINANCE sees payments only | `AGENTS.md` (*Payment*), `docs/rollen-en-rechten.md` | `backend/app/domains/payment/tests/`, `test_payable_delete_gate.py` (#667), `test_payment_choice_gate.py` (#1748), `test_role_model_gates.py` |
| Reporting is a terminus; a detail may be shown, not grouped by; every shipped report runs | `docs/change_request_06_reporting.md`, `docs/change_request_07_raakje_backoffice.md` §6.6 | the four reporting gates in `backend/app/domains/reporting/tests/` and `backend/app/domains/activities/tests/test_reporting_schema_gate.py` |
| One linear migration chain; the tool writes the file; the id in the file is the id in the name; a merged migration is never modified | `AGENTS.md` (*Alembic migrations*) | `test_migratieketen_gate.py` (#951), `test_migration_id_gate.py` (#1315); the `boot` job runs the chain against an empty database |
| A test sits where its imports say; test data on the reserved example domains; a gate must be able to go red and must look somewhere | `AGENTS.md` (*Testen en test-evidence*), CR-13 R15 | `test_tests_placement_gate.py`, `test_test_email_domains_gate.py` (#1293), `test_gate_niet_leeg.py` (#678) |
| No AI call without a row in the AI log; the public assistant reaches no admin tool; a view transition is decided in one place | the issues that made them (#978, #1075) and CR-11 (#1591) | `test_ai_log_coverage_gate.py` (#978), `test_public_tool_boundary_gate.py` (#1075), `test_view_transition_gate.py` (#1591) |
| Every module router is guarded and every registry entry is real (modules per tenant) | CR-19 (tenant kinds) | `test_module_gate.py` |
| The import smoke test covers every package; the storage seam is the only way to a file | #583, CR-15 | `test_check_imports_gate.py`, `test_media_seam_gate.py` (#1473) |
| A change request is shaped, read against the code, built and closed out per the template; a review is asked and answered per the protocol | `docs/change_request_template.md`, `docs/review-protocol.md` | the judgment layer (C4): the build read before assignment, the review on request; no mechanical gate |
| Nothing secret, no real host, no personal data in the public repository; a Claude session takes no personal data from an environment | `AGENTS.md` (*This repository is PUBLIC*, *Europe First*) | the `publieke-repo-bewaker` agent (C4), on every diff and on request over the issues |

Two things this table makes visible. First, `AGENTS.md` is the home of the
process and of the conventions that predate the code-style document; a rule
that is about code moves to `docs/code-style.md` when it gets a gate, and the
table above is where that move is recorded. Second, three rules have no gate
and no plan for one — the change request process, the review protocol and the
public-repository rule — because what they guard is judgment; they are held by
C4 and C5 instead, and that is a choice, not a gap.

## C2. The gates

A gate is a test that holds a rule of the codebase rather than a behaviour of
the application: it reads source files, templates, migrations or the rendered
HTML of every admin page, and it fails when the rule is broken anywhere. On 13
October 2026 there are **53 gate files**: 48 in `backend/tests/` named
`test_*gate*.py` or `test_*ratchet*.py`, and 5 in the test folders of the
domains they belong to (`activities`, `reporting`), where CR-13's placement
rule put them. (A file glob on `*gate*` finds 54: `test_registration_aggregate.py`
matches on *aggregate* and is not a gate.)

### The table

The table of gates — file · what it refuses · hard or ratchet · since · what it
caught — is **generated by the PDF build from the first sentence of every gate
file's docstring** (Koen, 13 October 2026, Q&A of 11 October, question 3:
"akkoord"), so it cannot go stale: a gate that is added appears, a gate whose
sentence changes changes here. The build reads the same files the meta-gate
lists in its `GATE_BESTANDEN`. Two things are needed for that and are planned in part E: the
one-sentence docstring on every gate file in the form *refuses · hard or
ratchet · since #issue* (today 53 of 53 have a docstring, in two languages
and several shapes), and a gate that requires that sentence, proven red with one
file without it.

<!-- gates-table: generated from the docstrings; until the build does it, the
     count of 13 October 2026 by the design-documentation CLI stands here -->

### Hard gates and ratchets

A **hard gate** has no exceptions: the rule holds for every file it reads, and
a new violation is red the moment it is pushed. Most of the 53 are hard.

A **ratchet** holds a rule that was introduced while the code still broke it.
It freezes the violations that stood on the day the rule came (a *baseline*)
and allows the number only to fall: an entry that leaves the code must leave
the baseline, nothing may join it, and the gate is as red on room left
standing as on a new violation. A rule with a growing exemption list would be
dead; a baseline that can only shrink is the same rule with a date. The
baselines on 13 October 2026, each in a file of its own under
`backend/tests/`:

| Baseline | File | Rule | Size on 13 October 2026 |
|---|---|---|---|
| Dutch identifiers | `dutch_identifiers_baseline.py` | all new code is English (#780, 29 September 2026) | 370 names (437 when frozen) |
| The UI ratchets of CR-11 | `ui_baseline.py` | every screen on the kit: raw form elements, raw surfaces, header extras, sideways scrolls, shells extended directly, … (#1563, frozen 5 October 2026 when pilot A stood on the kit) | 165 template rows over eleven rules; the largest are `SHELL_EXTENDED_DIRECTLY` (52) and `RAW_SURFACES` (36) |
| The public ratchets | `public_baseline.py` | the public side on the kit: hand-written buttons, cards, activity parts (#1591) | 5 rows |
| The hand-drawn lists | inside `test_list_table_gate.py` | a back-office list is the kit's table (#1911, 12 October 2026) | 10 templates |
| What is deliberately not a code | `codes_baseline.py` | the code-list rule (CR-12): MIME types, labels that are not a vocabulary, foreign keys to lists that are not ours | an allow-list with a reason per line, not a ratchet: it may grow when a new external vocabulary arrives |

So the sentence of the former §6.2, "on master every ratchet list is empty but
two", no longer holds since CR-11: the kit roll-out carries a baseline of 165
rows that shrinks with every screen that moves onto a macro (the kit roll-out issues of
v2.17 take the next ones). The number is the measure of how far the roll-out
is; it belongs in the release tracker of every release that lowers it.

### The meta-gate

`backend/tests/test_gate_niet_leeg.py` (#678) guards the gates themselves: a
gate collects the files it reads through one helper that fails on an empty set
and on fewer files than the rule expects, every gate uses that helper, and no
gate scans the file system directly any more. It exists because fourteen gate
functions once scanned files without asserting they found any — a moved folder
or a changed glob would have made them green for good.

## C3. The CI

One workflow, `.github/workflows/backend-tests.yml`, runs on every push to
`master` and on every pull request against it, except when only the
documentation files listed in its `paths-ignore` change (the change requests,
this document, the review protocol). Since CR-29 (8 October 2026) a run is
one per commit: a newer push cancels a pull request's stale run, a `master`
run always finishes because HDEV and the release wait for it.
`backend/tests/test_ci_workflow_gate.py` holds these promises against the
workflow file.

Eight jobs, each with a thirty-minute limit:

| Job | What it does | Blocks the merge |
|---|---|---|
| `lint` | `ruff format --check` and `ruff check` on the whole tree (#781); a job of its own so a style finding is red within seconds | yes |
| `pytest` | `mypy`, then the suite with `pytest -n 4` against a PostgreSQL 16 service container, coverage of `app` at least 85 %; Inkscape is installed for the poster tests | yes |
| `audit` | `pip-audit` on the backend requirements, **reporting only** (#574): the findings go to the run's summary and to the release tracker, and Koen decides what blocks a release, not the scanner | no — but never silent |
| `e2e (part 1)`, `e2e (part 2)` | the Playwright suite in `backend/tests_e2e/` against a really started backend with seeded data, split in two parts by folder so the two run side by side | yes |
| `measure` | the measurement baseline of the pilot screens (#1605, `scripts/measure-run.sh`): positions and sizes read from the rendered DOM at 390 px and at the wider widths each screen declares, compared with the committed baseline, so a kit change that moves another screen is red before anyone looks | yes |
| `css` | rebuilds `backend/app/static/app.css` from the templates with the pinned Tailwind CLI and fails on a diff (#652): a template change whose CSS was not rebuilt is red | yes |
| `boot` | runs the real `startup.sh` — migrations, every seed, uvicorn — against an empty PostgreSQL 16 and probes the health route (#450); the import check runs the same way as the Docker build | yes |

The last green run on `master` before this part was written: run 38381461117
on 92791f8b (13 October 2026) — `pytest` 6 291 passed, 1 skipped; e2e 305 and
86 passed; `pip-audit` *No known vulnerabilities found*. Every closed issue
carries the run id, the test count and the audit outcome as evidence
(`AGENTS.md`, *Testen en test-evidence*), and the release tracker carries them
once more at step 4 of the release.

Three things the CI deliberately does **not** do. It does not deploy: HDEV is
deployed by the master CLI from `master` HEAD, UAT and PROD from a tag, by
hand and with a confirmation (C5). It does not tag: a release tag is created
on GitHub on a commit that HDEV has already run. And it does not read an
environment: the six verification lines after a deploy (`AGENTS.md`,
*Verifying a deploy*) are measured by the session that deploys.

## C4. The judgment layer

What a gate cannot express is judged at a fixed moment by a person or by a
read-only agent. Four moments:

**The merge gate on the rendered screen.** Before merging a pull request that
touches a screen, the master CLI looks at the rendered screen at 390 px — the
screens the pull request touches, rendered against a seeded local backend
(`backend/tests_e2e/screenshots.py`) — and a handover of a UI change without a
measurement taken from the rendered DOM goes back (Koen, 27 September 2026,
after six of twenty-four issues of v2.6.0 reached him broken with CI green).
The `measure` job of C3 holds the pilot screens mechanically; the eye holds
the rest.

**Two read-only agents**, defined in `.claude/agents/`, both on Sonnet, both
with read tools only, both producing a report and never a commit:
`design-conformiteit-bewaker` reads templates and UI modules against the
design system where the gate stops — patterns, and the layering of the Python
UI modules — and ranks its findings with `file:line` and a proposed issue
title; `publieke-repo-bewaker` screens a diff and, on request, the issues and
their comments for secrets, real hosts, credentials and personal data, because
the repository and its tracker are public.

**The build read of a change request** (Koen, 7 October 2026, after CR-22):
every change request, small or large, is laid against `master` by a dev CLI
before Koen assigns it, through the review door below. CR-22 was assigned
first, and the two dev CLIs then found twelve points where the document and
the code disagreed. What the read looks for stands in
`docs/change_request_template.md`.

**The review on request** (`docs/review-protocol.md`): one trigger — the
`ai-review` label and one sentence naming the scope and the reviewer — one
answer as one comment, findings grouped by weight with file and line, ending
with *take in · already decided · not taken*. Within the Claude series the
master CLI routes it; an outside reviewing agent is started by Koen. A review
is advisory: only CI blocks a merge, and Koen decides what is taken in. One
review is standing and needs no request: every pull request of a builder
outside the Claude series is read by a Claude dev CLI before a merge, the
first time and after every later commit (`AGENTS.md`, *A builder outside the
Claude series*).

## C5. The process gates

The process has gates of its own, written in `AGENTS.md` and held by the
master CLI, which is the only session that merges, tags and deploys.

- **Issue first.** Every deployable code change goes through a GitHub issue;
  no drive-by commits. The issue is the record of *why*; the commit references
  it; the release tracker ticks it off.
- **The release assignment is the merge approval, and only the master CLI
  merges.** A feature CLI readies a green pull request and hands it over; work
  not on a release never reaches that handover, not with green CI, not with an
  approved deliverable (Koen, 6 and 14 September 2026).
- **The fourteen steps of a release**, in `AGENTS.md` (*Running a release from
  the CLI — the order*): tracker (1), merge gate (2), the closing comment per
  issue at its merge with how to test it on HDEV (3), CI evidence (4), env vars
  by Koen (5), HDEV deploy (6), Koen validates on HDEV (7), the GitHub Release
  on the HDEV-tested commit (8), UAT (9), the shared Caddy when touched (10),
  PROD (11), the six verification lines (12), close the tracker (13), close out
  every change request the release built (14).
- **HDEV before the tag.** A release tag is created only on a commit that
  HDEV has run and Koen has validated; the tag is the single source of truth
  for what UAT and PROD run.
- **Three confirmations stop the pipeline, nothing else does:** the UAT
  deploy, a change to the shared proxy, the PROD deploy. Inside an assigned
  release the agent works autonomously.
- **The close-out at step 14** exists because CR-14 showed what happens
  without it: a change request that is not closed out keeps telling the next
  reader the design, not what runs. The architecture CLI edits the document,
  the master CLI closes the issue. From v2.17 on this step also updates this
  document (part B of the modules touched, part D for a new standard, part E's
  row and change log E3; see the change request template, C10).
- **Who may change the process.** `AGENTS.md`, `CLAUDE.md`, `.github/` and the
  process documents are changed by Koen or the master CLI at his explicit
  word; every other session proposes. A decision of Koen is written only with
  his own words, the date and the question they answered.
- **First time right** (Koen, 13 October 2026): an open question is answered
  before what depends on it is built; no workaround to get past one; a
  proposal says when it is not the final form.

## C6. What the gates caught

Every gate in C2 exists for a failure that happened, and the failure is
written in the gate's docstring so the next reader does not have to rediscover
it. The ones that shaped the harness:

- **The escaping class** (#622, `test_render_gate.py`). Three times an htmx
  attribute was HTML-escaped and a button silently did nothing while every
  endpoint test passed — 830 tests green while three buttons were dead. Answer:
  a gate over the *rendered* HTML of every admin page, plus browser flows on
  the admin screens.
- **Green by looking nowhere** (#678, `test_gate_niet_leeg.py`). Fourteen gate
  functions scanned files without asserting they found any. Answer: the
  meta-gate of C2, and the rule in `AGENTS.md` that a gate proves it looked.
- **Green while undeployable** (#450, the `boot` job). A renamed module passed
  CI and failed only in the Docker build; the backend crash-looped on HDEV with
  CI green. Answer: the real `startup.sh` boots in CI against an empty
  database, and the import check derives its module list from the package
  (#583, `test_check_imports_gate.py`).
- **The typo that rendered blank** (#643, `test_template_variables_gate.py`).
  Jinja rendered an unknown variable as an empty string. Answer:
  `StrictUndefined` outside production, typed view-models, and a gate that
  compares each template's variables with its view-model's fields; its first
  run found five real gaps, among them role checkboxes that had silently
  disappeared from a form.
- **CSS that drifted** (#652, the `css` job). `app.css` is generated and
  committed, and it silently fell behind the templates: the e-mail log on HDEV
  rendered with wrong margins and nothing failed. Answer: CI rebuilds it and
  fails on a diff.
- **Two migrations with one key** (#951, #1315). Hand-typed migration ids
  drifted from real timestamps to round hours until two branches chose the
  same key on 19 September 2026. Answer: the tool writes the file, a gate
  checks the chain has one head and that the id in the file is the id in the
  name.
- **Twenty-six Dutch function names** that review caught on 26 September 2026
  after CI had let them through. Answer: the English-identifier ratchet (#780)
  three days later.
- **The hidden read wrapper** (#913, `test_actiebalk_ratchet.py`). An action
  cluster stood inside a collapsed read wrapper and was unreachable. Answer: a
  ratchet that reads the templates.
- **Two list screens drawn as cards** (#1911, `test_list_table_gate.py`). On 12
  October 2026 Koen found two webshop lists hand-drawn while the same builder's
  third used the macro, after several reads: "Hebben we geen gate die bewaakt
  dat op lijst-schermen enkel nog via de macro mag gewerkt worden?". Nothing
  mechanical said it, so no review brought it back; now one does.
- **A cancelled run that nobody saw** (CR-29, `test_ci_workflow_gate.py`). With
  one concurrency group for all of `master`, GitHub cancelled a queued run as
  soon as a newer commit arrived (8 October 2026). Answer: one group per
  `master` commit, cancellation only for pull requests, and a gate on the
  workflow file.

The pattern is the same every time: a failure that CI let through becomes a
rule, the rule gets a gate on the day it is written, and the gate is proven red
once with one deliberate violation before it is trusted (`AGENTS.md`, *Testen
en test-evidence*). A gate that cannot go red is worse than none.

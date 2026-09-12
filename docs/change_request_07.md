# Change Request 07 — Raakje for the back office: conversational reporting

**Project:** Web Portal "Raak Millegem"
**Status:** Draft — brainstorm of 12 September 2026, not assigned to a release.
Decisions marked "confirmed by Koen" in §11 are settled; the open questions in
§12 are not.
**Apply to:** the `reporting` domain (new assistant seam + admin screen), a small
facade addition to the `chatbot` domain. No new schema; one new log table.

---

## Goal

The back office gets a **conversational entry point to the reporting universe**:
an admin asks a reporting question in Dutch — "hoeveel volk was er op de
kerstmarkt?", "in welke straat wonen de meeste leden?", "welke gezinnen haken
volgend jaar waarschijnlijk af?" — and Raakje answers **in text** (bullets
allowed, no charts), asking a clarifying question first when the question is
ambiguous.

The assistant is not a second reporting system. It is a second *driver* of the
one that exists: the LLM composes a `Selection` — the same datastructure the
query panel saves — and the existing engine executes it. Everything CR-06 built
is inherited, not reimplemented: the universe as the single vocabulary, the
tenant filter on every statement, the small-cell threshold, symbolic values,
named refusals.

Three constraints, stated up front:

- **No personal data leaves the system.** Mistral sees pseudonymous ids
  (`gezin-23`), never names, addresses, birth dates, phone numbers or e-mail
  addresses. The translation back to names happens server-side, in the rendered
  answer, after the LLM is done.
- **No free SQL, ever — inherited, not re-promised.** The LLM's only path to
  data is `build_query` over the universe. A question the query panel cannot
  express, the assistant cannot express either.
- **The public Raakje is untouched.** Separate tool list, separate entry point,
  separate budget. There is no code path from the public widget to a reporting
  tool.

## 1. Current state (measured, 12 September 2026)

| | measured |
|---|---|
| Semantic layer | `reporting/universe.py`: 8 facts, 10 dimensions, ~70 objects, each with a one-sentence description; `docs/reporting-universe.md` generated from it, drift is a red build |
| Query engine | `build_query` is pure (no session), refuses with named `SelectionError`s, applies tenant filter and small-cell merge unconditionally |
| Value lookup | `service.dimension_values` already answers "which values exist for this object" |
| LLM plumbing | `chatbot/providers/` — `LLMProvider.complete()` seam, Mistral via bare httpx, mock provider for tests |
| Conversation loop | `chatbot/service.run_chat` — tool-loop with allowlist dispatch, bounded rounds, forced grounding |
| Admin chat surface | none — `/raakje` is public-only, grounded on 3 public tools |
| Row identity in results | `ReportResult.drill_aliases` carries the row's entity id per column — the hook pseudonymisation needs |

## 2. Principles

1. **The universe is the contract — also for the machine.** The "descriptive
   API" the assistant needs is the universe declaration itself. A second
   renderer next to `docs.py` produces a compact catalogue for the system
   prompt: key, kind, format, description, per class, from the same tuples.
   One source; the human document and the machine catalogue cannot drift apart.
2. **The LLM composes, the engine decides.** The model produces selections and
   prose; every refusal, cap, filter and merge is the engine's. A prompt is
   never a security mechanism (the public bot's `execute_tool` allowlist set
   that precedent; the same pattern applies here).
3. **Refusals are feedback.** `SelectionError` messages name the object and the
   rule. They go back to the model as tool results, so a wrong selection
   corrects itself within the round budget instead of surfacing as an error.
4. **Identity out, measurement in.** The same masking rule the project applies
   to public text applies to the LLM boundary: strip who, keep how much. Ids
   stay, names go, and the answer the admin reads has the names back.
5. **Honest about prediction.** v1 predicts by *cohort reasoning* — composing
   selections over years and reasoning about the behaviour of pseudonymous
   households. It presents indicators with reasons ("high risk: member every
   year since 2019, not renewed, no registrations this year"), never invented
   probabilities. A calibrated model is a separate, later change request.

## 3. The test set — questions the assistant must answer

From the brainstorm of 12 September 2026. Questions 1–6 are expressible in the
universe today; 7–8 are cohort reasoning (§8).

| # | Question | Universe path |
|---|---|---|
| 1 | How many people attended activity X? | registrations fact, activity dimension |
| 2 | Which activities draw the most participants? | registrations × activity, sorted |
| 3 | What is the revenue per activity? | payments × activity |
| 4 | In which street do most members live? | memberships × address street |
| 5 | Which board member has the most members? | memberships × board member |
| 6 | What is the age-group distribution? | membership persons × age group |
| 7 | Which members will probably not renew next year? | cohort reasoning over membership years (§8) |
| 8 | Who is likely to attend activity X? | cohort reasoning over past registrations (§8) |

Ambiguity is part of the test set: "wat zijn de leeftijdscategorieën?" must
yield a clarifying answer that *names the buckets the universe declares* and
asks which cut the user wants — driven by `list_values`, not by guessing.

## 4. Architecture

### 4.1 Placement

The assistant lives **inside the reporting domain** (`reporting/assistant.py` +
an `admin_ui` route + template). Reporting already is the domain that reads from
everywhere and is imported by nobody; that invariant stands. The `chatbot`
facade grows one export: the provider seam (`LLMProvider`, `get_provider`), so
reporting imports chatbot — never the reverse.

### 4.2 The tool surface (the whole of it)

Two tools, in their own allowlist with their own dispatch — the public
`TOOL_SPECS` is not touched:

| Tool | Does | Backed by |
|---|---|---|
| `run_report(selection)` | Validate + execute one selection; return columns, rows (pseudonymised, capped), totals, and the refusal text on failure | `selection_from_dict` → `resolve_selection` → `run_selection` |
| `list_values(object_key)` | The existing values a dimension holds, for clarification and for filter construction | `dimension_values` |

The universe catalogue is **system prompt, not a tool**: it is small, static per
release, and the model needs it before its first move.

Caps: rows per tool result (start: 50, with an explicit "refine your filter"
marker when cut), tool rounds (start: 6 — selections need more retries than the
public bot's lookups), an admin-side daily budget next to the public one
(`limits.py` pattern), and the engine's own `MAX_ROWS`/statement limits beneath
everything.

### 4.3 The conversation loop

`run_chat` generalises: it takes the tool specs + dispatcher as parameters
instead of importing the public ones (one loop, two configurations — public and
admin). The admin screen mirrors `/raakje`: htmx question/answer,
server-side complete, no SSE. History capped like the public bot.

### 4.4 Model choice

Provider stays Mistral (EU — Europe First holds; nothing new is added).
Composing valid selections is harder than the public bot's lookups, so the
assistant gets its own model setting (start: `mistral-medium-latest`,
measured against the test set in phase 1) — the public bot stays on Small.
The mock provider grows canned selection-composing turns so the loop, the
pseudonymisation and the screen are testable without a key.

## 5. Pseudonymisation — the privacy boundary

The one genuinely new mechanism. Placement: **between `run_selection` and the
tool result** — the engine and the panel are untouched.

1. **A `pii` flag on universe objects.** Set on the objects whose value
   identifies a person: head-of-household name, partner name, address line,
   house number, bus, and the label of the household/person dimensions. Not on
   street, municipality, postal code, age group, household size — those are the
   aggregates the assistant exists for. The flag is declared in the universe,
   so it appears in the generated documentation and is gated like every other
   universe property.
2. **Outbound: value → token.** In a tool result, every pii-flagged column's
   value is replaced by a stable token built from the row's entity id, which
   `drill_aliases` already carries: `gezin-23`, `persoon-90`. Same entity, same
   token, within and across turns of one conversation — the model can reason
   about recurrence.
3. **Inbound: token → value, at render time.** Tokens occurring in the final
   answer are replaced server-side by the real label (one lookup, tenant-scoped,
   at most once per token). The admin reads "het gezin Renders"; Mistral only
   ever saw `gezin-23`. Tokens the model never mentions cost nothing.
4. **What never enters the universe needs no masking.** Phone numbers, e-mail
   addresses and exact birth dates are not universe objects and stay out
   (CR-06 §7.3 attitude: the fence is declared before the first object needs
   it). Age group exists; birth date does not need to.
5. **The small-cell threshold keeps applying.** Same engine, same merge. It
   protects grouped results; the pii tokens protect row-level ones. Together
   they cover both shapes an answer takes.

Gate-style test (the CLAUDE.md "bewijs het" norm): a test composes a selection
containing every pii-flagged object, captures the exact payload handed to the
provider (mock), and asserts no value from a seeded name/address set appears in
it — then breaks the masking deliberately and asserts the test goes red.

## 6. Security invariants

1. **Admin-only.** The screen and its route sit behind `require_admin_ui` —
   the same door as the reports panel. All admin roles are equal here
   (confirmed by Koen, 12 September 2026: no ADMIN/FINANCE/OPERATOR
   distinction), consistent with the universe's declared-not-enforced roles.
   The day per-object role enforcement is built (CR-06 §7.2), the assistant
   inherits it through the engine — by construction, not by extra work.
2. **Public and admin surfaces share no tool list.** Two allowlists, two
   dispatchers, two entry points. The generalised loop takes them as
   parameters; a test asserts the public dispatcher refuses `run_report` by
   name.
3. **Tenant fence unchanged.** The engine requires `tenant_id` on every
   statement; the assistant passes the session's tenant. Enabling is
   per-tenant (a tenant setting — Raak Millegem on, platform off) under a
   global kill-switch (`admin_chat_enabled`, default off, next to
   `chat_enabled`).
4. **Every outbound call is logged.** One row per `run_report` execution:
   actor, question text, the selection, row count, timestamp — a new
   `ai_question_log` table in the reporting schema, append-only like
   `export_log`, and for the same reason: rows handed to Mistral are data
   leaving the system.
5. **CSRF and session semantics** as on every admin htmx screen.

## 7. Answer form

Text only, Dutch, bullets allowed; no charts, no tables-as-images. Numbers in
an answer come from tool results — the system prompt forbids arithmetic beyond
what a returned row states, and the totals row is returned precisely so the
model does not add up pages. Every answer carries a one-line provenance footer
("op basis van: inschrijvingen × activiteit, filter jaar = 2026") rendered from
the executed selection — the admin sees what was actually asked, which is also
the debugging handle when an answer looks off.

## 8. Cohort reasoning — prediction without a model

Questions 7–8 of the test set. The mechanism: the model composes selections
over membership years and registration history — the measures new / renewed /
lapsed and the per-household registration counts exist today — and reasons over
the pseudonymous result. The answer names indicators and reasons, never
percentages: "hoog risico: elk jaar lid sinds 2019, dit jaar niet vernieuwd,
geen inschrijvingen" reads as what it is — a pattern, explainable and
checkable. The prompt explicitly forbids invented probabilities.

What this deliberately is not: a trained churn model with calibrated scores.
If the cohort answers prove useful and Koen wants real scores, that is its own
change request, with its own evaluation question ("calibrated against which
seasons?") — not a prompt tweak.

## 9. Phasing (each phase shippable)

1. **Aggregates.** Catalogue renderer, the two tools, generalised loop, admin
   screen, kill-switch + tenant flag, question log, caps. Test set 1–6 green.
   Pii flag already declared; person-naming objects simply refused in the
   assistant's selections this phase (named refusal, so the model routes
   around them).
2. **Person level.** Outbound tokenisation + inbound re-translation replace
   the phase-1 refusal; the masking gate test. Answers may now list
   households by name (rendered server-side).
3. **Cohorts.** Prompt work + evaluation of questions 7–8 against known
   history; the indicator convention.

## 10. Non-goals

- Saving reports from the conversation (confirmed by Koen, 12 September 2026:
  answering is enough).
- Charts or any visual output.
- The public Raakje answering any of this, now or later.
- A trained prediction model (§8).
- Streaming/SSE — server-side complete answers, like the public htmx screen.
- Cross-tenant or platform-level questions.

## 11. Decisions taken (confirmed by Koen, 12 September 2026)

| Decision | Choice |
|---|---|
| Audience | Back office only, behind `require_admin_ui` |
| Role distinction within admin | None — all admin roles equal |
| Tenant scope | Per-tenant flag; Raak Millegem only for now |
| PII to the LLM | Never; pseudonymous ids allowed; names re-translated server-side in the rendered answer |
| Prediction in v1 | Cohort reasoning, indicator language, no invented probabilities |
| Saving reports | Out of scope — answering is enough |
| Answer form | Text with bullets, no charts |

Defaults taken in this draft, to be challenged: a **separate admin screen**
rather than a panel inside `/admin/rapporten` (different interaction model, and
the reports screen is dense); `mistral-medium-latest` as the starting model;
row cap 50, round cap 6.

## 12. Open questions for Koen

1. Where does the screen live — own menu entry, or reachable from the reports
   screen (button "Vraag het Raakje")?
2. May a conversation reference *earlier answers'* data ("en per maand?"), i.e.
   history kept within the browser session — or is each question standalone?
3. Does the question log need a screen of its own, or is the table enough for
   now?

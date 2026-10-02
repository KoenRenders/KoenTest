# Review protocol

> One trigger, one answer, one place: a review is asked for with the **`ai-review`** label plus one sentence on the PR or the tracking issue, and it is answered as a comment on that PR or issue. It is *advisory*: nothing blocks a merge but CI, and the platform owner decides what is taken in. Any reviewer — an AI tool or a human — gets the same scope. Never automatic: a review starts only when asked.

**The request.** On the PR that carries the change request document, or on a code PR: add the label `ai-review`; comment: *review please, <scope> — **@<reviewer>*** — "the document" for a change request, "the diff against CR-<NN>" for a PR. The label marks the request; the @-mention names the addressee, and without it nobody is expected to act.

**The answer.** One comment, headed **"Review — <date>, <scope>"**, findings grouped by weight, each with file and line or section; ending with the verdict list (*take in* · *already decided* · *not taken, with the reason*).

**Checklist — a change request.** 1. Premises measured: every "as X already does" claim carries file and line in C1. 2. Exceptions named once (B4). 3. Screens shown or waived (C9). 4. The user's words in A3; no components in Part A. 5. The shape holds: deliberate Won'ts, walkable ACs, the reading budget, no old decision lingering against a new one. 6. The tests could go red.

**Checklist — a PR with code.** 1. The description states its claim (CR, modules, evidence). 2. Scope: the diff stays inside its CR. 3. Conventions hold (`AGENTS.md`, `docs/code-style.md`, the domain's `CONTRACT.md`). 4. Every new test could go red. 5. No copy-paste of a fact the codebase keeps in one place.

**Sources.** Every item points at `docs/change_request_template.md` (the five rules), `AGENTS.md`, `docs/code-style.md`, the contracts, and the CR the PR implements; a convention found nowhere in those is an observation, not a finding.

# Code style

What a formatter cannot decide. One screen, and it points elsewhere rather than
repeating what is already written down.

> **Note on this file, 26 September 2026.** `CLAUDE.md` describes this guide as
> created by #781, together with a ruff configuration that CI blocks on. Neither
> exists on `master`: there is no `[tool.ruff]` section in
> `backend/pyproject.toml` and `.github/workflows/backend-tests.yml` runs mypy
> but not ruff. The file is created here because CR-12 phase 0 has to write its
> rule down somewhere and this is the place `CLAUDE.md` names for it. It holds
> that one rule. The rest of what #781 promised — language, where a rule belongs,
> layer boundaries, exceptions, typing, docstrings, tests — is still #781's work,
> and so is the formatter.

## A fixed vocabulary is a code table

> A fixed vocabulary is a code table in the schema of the domain that owns it —
> in `mdm` when it is master data or used by more than one domain, in `auth`
> when it is security vocabulary — with a foreign key from every column that
> stores it, a label table per language, and a plain `Enum` in the owning domain
> wherever Python branches on the value. Labels come from `code_label()` and
> nowhere else; templates never compare a code. An external party's vocabulary
> gets an `Enum` in its adapter and a mapping to ours — never a code table: it
> is not our list.

The design and the reasoning are in
[`change_request_12_codes_and_enums.md`](change_request_12_codes_and_enums.md);
this paragraph is the rule, not a summary of the document.

Six steps for a new list, and the gate
(`backend/tests/test_codes_gate.py`) fails on whichever one was forgotten,
naming it: (1) a `_codes` table, (2) a `_labels` table with an `nl` and an `en`
row, (3) a foreign key from each storing column, (4) a `CodeList` declaration in
the domain's `codes.py`, (5) an `Enum` when the code branches, (6)
`code_label()` on every screen and export. The entry points are covered from
both sides, so whichever of the six you start with, the other five are demanded.

Three things that are deliberately *not* code lists: an external party's
vocabulary (Mollie's statuses), design and brand data with a payload (icons,
colour duos), and numbers that are not codes (a 1–5 rating scale is copy, so it
goes through `_()`). An `Enum` that is none of ours carries `TechnicalEnum` or
`ExternalVocabulary` with its reason in the docstring.

**Member names are English; values are the codes as stored.**
`RelationType.PRIMARY_MEMBER = "HOOFDLID"` — the value is data and stays, the
name is an identifier and follows the English rule.

**Plain `Enum`, never `str, Enum`.** With a `str` subclass, `status == "paid"`
stays a valid comparison that happens to be true, so a stale literal survives
unnoticed. Plain, that comparison is silently *false* — which is why the
loose-string gate is an AST walk and not a mypy rule: the models use the legacy
`Column()` style, so mypy types every column attribute as `Any` and `Any ==
"paid"` is never an error.

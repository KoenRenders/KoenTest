# Migrations

One linear chain. Read the current head from the code, never from a document:

```bash
ls alembic/versions/ | sort | tail -1     # from a checkout
alembic heads                              # in a running backend container
```

## Writing a new one

```bash
alembic revision -m "what it is about"
```

That fills in `script.py.mako` and generates the revision id. Do not type the id
by hand — the form is the point (see below), and a convention you have to
remember is one you will eventually forget.

## Why the id is a timestamp (#951)

Until 15 September 2026 the id **was** the sequence number (`revision = "124"`).
Three CLIs work on branches in parallel and each picks "the next number", so they
pick the same one. That day it happened for real, between #945 and #939 — both
`124`.

The telling part: **neither branch is broken.** Each one on its own has a green
CI, one head, a chain that runs. The collision exists only in the *combination*,
and that does not exist until the merge. A check on the branch can therefore never
find it.

So a new migration gets an id that cannot collide:

```
revision = "126_2026_09_15_143012"
            │   └── UTC timestamp, to the second
            └────── sequence number, for reading and sorting
```

Two heads can still appear — two branches forking from the same point — but the
repair is then **one line**: what do I hang under? No rename, no references to
chase.

**Existing migrations are not renumbered.** Alembic does not care about file
names; a mixed series (`001` next to `126_2026_09_15_…`) runs fine, and
`tests/test_migratieketen_gate.py` pins that. A bulk rename would break every open
branch and buy nothing.

## Sync before you hand over

Pull master in just before handing the PR over. Your migration then hangs under
the head that is actually current, and it cannot collide. The same habit fixes the
`app.css` conflicts — one cause there too: a branch that goes stale before it is
handed over.

It does not cover master moving *during* a CI run of a few minutes. That is what
the timestamp id is for.

## When the chain is wrong

The suite does not run the migrations before saying so. `conftest` reads the chain
first and stops with a message naming the two heads, which one is the youngest,
and the line to change:

```
De migratieketen klopt niet (#951). Dit is géén kapotte suite — het is een tak
die onder een verouderde head hangt:

De keten heeft 2 heads in plaats van één:
    125_meeting_guests.py (revision='125')
    126_organization_lists.py (revision='126_2026_09_15_143012')
  De jongste is 126_organization_lists.py. Zet daarin down_revision = '125'.
```

Before #951 the whole suite collapsed on `MultipleHeads`, which reads as
"everything is broken" while it is one line.

## House rules that have not changed

- Never modify a migration already merged to master — it is a snapshot, and
  someone has already run it.
- Make them idempotent where you can (check before you create).
- Does `downgrade()` restore the **data** as well, or only the schema? Say so out
  loud in the docstring. A half reversal presenting itself as a whole one is worse
  than one that is honest about what it leaves behind.
- Copying data and then dropping the old column? **Count in between**, and let a
  mismatch fail the migration. Postgres runs DDL transactionally, so a failing
  count rolls the whole thing back and the column is still there. Migration
  `124_organization_lists.py` is the worked example; #945 has the reasoning.

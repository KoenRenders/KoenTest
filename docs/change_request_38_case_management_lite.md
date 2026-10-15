# Change Request 38 — Case Management Lite: follow a case from intake to close

**Project:** Web Portal "Raak Millegem"
**Status:** shaped with Koen on 15 October 2026 · not assigned to a release · the data model and the domain boundaries of B3 are a proposal for the architecture CLI to confirm
**Tracking issue:** #2030
**Applies to:** the workbench (`workflow`), the form engine (`forms`), a new domain `cases`, the party model (CR-26), the shop (CR-21) and activities for the sale step; the back-office menu and the public site
**Reading:** A 1 500 words · B 2 444 · C 1 526 — measured per part; A ≤ 1 500, B ≤ 2 500

---

# Part A — The business

## A1. Reason to act — the trigger

Koen, 15 October 2026: a tenant should be able to follow a **case** of any type from beginning to end, with its own workflow, without a developer. Two types are in his head and are the first two to build: a **complaint** (a claim) and an **opportunity** in a sales context; they serve a business and an association alike. Today the portal can take a message and put one task on the workbench; it cannot follow a matter through several steps, with questions per step, a decision in the middle, and a clear end.

## A2. As-is process — how it works today, and where it hurts

As far as I understand it (Koen to confirm): a complaint or an interest arrives as a *message*; one person gets one task *"Bericht behartigen"*; the rest happens outside the portal.

```mermaid
flowchart LR
  subgraph client["Client"]
    c1[Send a complaint or an interest]:::hand
  end
  subgraph board["Board member"]
    b1[Handle the message task]:::tool
    b2[Judge it by hand]:::hand
    b3[Follow up by mail and by memory]:::hand
    s([Matter ends nowhere visible]):::done
  end
  c1 -.-> b1
  b1 --> b2 --> b3 --> s
  classDef hand fill:#ffffff,stroke:#52607a
  classDef tool fill:#e8f0ff,stroke:#0051a4
  classDef done fill:#ffffff,stroke:#52607a
```

*What to see:* after the first task the matter leaves the portal.

| Step | Pain |
|---|---|
| Handle the message task | one task, one comment, no structured questions |
| Judge, follow up | nothing records whether a complaint was admissible, who handled it, or how it ended |
| The end | no closed state and no reason; nobody can say how many offers were won |

## A3. To-be process — how it should work afterwards

The **case** is the umbrella over the tasks. The workbench stays what it is, the one place where tasks are done; a case is the matter the tasks belong to, with its request, its steps and its end.

```mermaid
flowchart TB
  subgraph client["Client"]
    c1[Fill in the intake form]:::hand
  end
  subgraph board["Board member"]
    b1[Judge: admissible?]:::tool
    g1{Admissible?}
    b2[Handle the complaint]:::tool
    e1([Closed: handled]):::done
    e2([Closed: not admissible]):::done
  end
  c1 -.-> b1
  b1 --> g1
  g1 -->|yes| b2 --> e1
  g1 -->|no| e2
  classDef hand fill:#ffffff,stroke:#52607a
  classDef tool fill:#e8f0ff,stroke:#0051a4
  classDef done fill:#ffffff,stroke:#52607a
```

*What to see (the complaint):* the intake form starts the case; each step is a task with its own form; a decision on a field sends the case on; the end says why it closed.

The opportunity, drawn the same way:

```mermaid
flowchart TB
  subgraph client["Client"]
    c1[Register an interest]:::hand
    c2[Answer the offer]:::hand
  end
  subgraph sales["Sales"]
    s1[Judge: admissible?]:::tool
    g1{Admissible?}
    s2[Make the offer]:::hand
    s3[Wait for the answer]:::tool
    g2{Won?}
    s4[Register the sale]:::tool
    e1([Closed: won]):::done
    e2([Closed: lost]):::done
    e3([Closed: not admissible]):::done
  end
  c1 -.-> s1
  s1 --> g1
  g1 -->|yes| s2 --> s3
  g1 -->|no| e3
  s3 -.-> c2
  c2 -.-> g2
  g2 -->|yes| s4 --> e1
  g2 -->|no| e2
  classDef hand fill:#ffffff,stroke:#52607a
  classDef tool fill:#e8f0ff,stroke:#0051a4
  classDef done fill:#ffffff,stroke:#52607a
```

*What to see (the opportunity):* the offer is made outside the portal, but followed in it; registering the sale closes the case by itself.

What it says on the screen (Dutch), decided here:
- the umbrella is called **Zaak** (plural *Zaken*); the menu item in the back office is **Zaken**
- a case has a **status**: *Open* (registered, nobody has worked on it yet), *In behandeling* (being worked on), *Gesloten* (an end is reached); a closed case has a **reden**: *Behandeld*, *Niet ontvankelijk*, *Gewonnen*, *Verloren*
- on the workbench: a button **Nieuwe zaak** listing the case types with a form
- one menu item, *Zaken*; on its list a button **Instellingen** opens **Soorten zaken**, the list of case types (new, rename, intake form, export, import), and per type **Proces**, a screen that lists the steps, as the form engine does: **Stap toevoegen** and four step types, **Taak met formulier**, **Beslissing**, **Verkoop registreren** and **Einde**
- on a case: the request, a tab per step with its answers, the process drawn with the current step, and the party

## A4. Benefits — what the change earns

- Every complaint and opportunity is registered and followed to a visible end (no figure; the count of open matters is the first the board lacks).
- A tenant sets up its own case types: one generic tool instead of a screen per matter.
- Questions per step are structured, so afterwards the board can count: admissible or not, won or lost.

## A5. Supplied material — and what it taught us

Koen's dictation of 15 October 2026. It taught us that the blocks exist: the workbench, the form engine and its form export and import, and the form-to-task link of the contact message. Reporting need: R13.

## A6. Business requirements — what the board asks, with MoSCoW

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | A tenant defines its own case types; each starts with a form | Must | Koen, 15 Oct 2026 | "elke tenant zet zijn case types op" |
| R2 | A case starts when its intake form comes in, from the public site or from the back office | Must | Koen, 15 Oct 2026 | signed in or not |
| R3 | A case is about a person, and optionally about an organisation the person acts for | Must | Koen, 15 Oct 2026 | needs the party model (CR-26) |
| R4 | A case follows a process of steps; each step is a task for a role, chosen per step in the process | Must | Koen, 15 Oct 2026 | "Aan een taak moet je natuurlijk ook rollen kunnen toekennen." |
| R5 | A step may have a form; what is filled in is kept with the step | Must | Koen, 15 Oct 2026 | |
| R6 | A decision after a step, on a field of a form, sends the case on one way or another | Must | Koen, 15 Oct 2026 | admissible or not; won or lost |
| R7 | A case has a status from a list: Open, In behandeling, Gesloten, and a closing reason | Must | Koen, 15 Oct 2026 | "een codelijst" |
| R8 | A closed step cannot be changed | Must | Koen, 15 Oct 2026 | "niet meer wijzigbaar" |
| R9 | A step can trigger a system action: registering a sale for the party; when the sale is registered, the case closes by itself as won | Must | Koen, 15 Oct 2026 | an activity registration or a shop order |
| R10 | A screen per case: the request, a tab per step, the process drawn with the current step | Must | Koen, 15 Oct 2026 | |
| R11 | A process, with its forms, can be exported and imported between environments | Must | Koen, 15 Oct 2026 | as forms can today |
| R12 | The process is stored in BPMN | Should | Koen, 15 Oct 2026 | rendered by a good renderer or as a Mermaid diagram |
| R13 | A menu item *Zaken* with the cases listed by status (open, in progress, closed), filterable by type and reason, and searchable | Must | Koen, 15 Oct 2026 | "Uiteraard moet je ook kunnen zoeken op die cases." Search: number, party name and e-mail, intake text (my proposal) |
| R14 | Dropdowns in the intake form that point at articles or activities | Won't | Koen, 15 Oct 2026 | "op termijn", not now |
| R16 | A process drawn on a canvas by dragging shapes | Won't | my proposal; B1 | the list screen is the editor; the diagram is a picture of the result |
| R17 | A due date on a task | Won't | Koen, 15 Oct 2026 | "Due dates buiten de scope." |
| R18 | A history of the status of a case, and of who completed which task when | Won't | Koen, 15 Oct 2026 | "Oké, dat gaat het misschien automatisch hebben, maar dat nemen we allemaal buiten scope." A task keeps its own done-by and done-at |
| R15 | A screen to model a process from start to end, in the way of the form engine: choose steps, order them, choose a step type, say what a decision does with the status and which task follows | Must | Koen, 15 Oct 2026 | "een scherm om die processen van startpunt tot eindpunt te kunnen modelleren"; textual or visual |

## A7. Non-functional requirements — security, privacy, house style, tenants

| Concern | This change |
|---|---|
| **Security** | a public intake form is a new input from outside: the form engine's own rules and limits apply; a case and its answers are seen only by the roles that handle it; a task goes to a role, not to a person |
| **Privacy** | a complaint holds personal data and often sensitive text; it is kept as long as the case lives and its retention is Q3; the register of CR-33 gets the case's attributes |
| **House style** | screens from the kit, 390 px first; the case screen follows the workbench's norms |
| **Multi-tenant** | case types, forms and processes are per tenant; the platform ships the two first types as examples a tenant imports |

## A8. Acceptance criteria — what the business signs off on HDEV

| # | Criterion | Requirement | Walkthrough steps |
|---|---|---|---|
| AC1 | Filling in the public complaint form starts a case with a first task | R1, R2 | fill it in signed out, then signed in |
| AC2 | Signed in, the case shows the person (and the organisation chosen) | R3 | fill it in for an organisation |
| AC3 | *Niet ontvankelijk* closes the case at once, with that reason | R6, R7 | fill the first step, pick no |
| AC4 | *Ontvankelijk* gives the handling task; closing it closes the case as *Behandeld* | R4–R7 | pick yes, handle, close |
| AC5 | A finished step shows its answers and cannot be changed | R8 | open a done step |
| AC6 | The opportunity runs to *Gewonnen* by registering a sale, to *Verloren* by a lost answer | R6, R9 | walk both |
| AC7 | A new case can be started from the workbench for a chosen party | R2 | *Nieuwe zaak* |
| AC11 | *Instellingen* on the *Zaken* list opens the case types; a type is made, given its form and its process there | R1, R15 | open it |
| AC8a | *Zaken* lists the cases with their status, and a search finds a case by number, name or a word of the intake answers | R13 | open the menu, search |
| AC8 | The case screen draws the process with the current step | R10 | open a running case |
| AC9 | A process exported from one environment imports into another with its forms | R11 | export, import |
| AC10 | A new process is made in the screen: steps, types, order, a decision with its routes and statuses; it runs, and the drawing matches | R15 | build the complaint process in the screen and run it |

---

# Part B — The solution, for whoever approves it

## B1. Solution outline — the solution and the decisions that shape it

**A case is the umbrella over a process.** Three new things, all data, none code per type:
1. **Case type**: a name, an intake form, and a **process**.
2. **Process**: a BPMN 2.0 diagram, stored as such, in a small agreed subset: a start (the intake form), tasks (a role, an optional form), exclusive gateways (a choice on a field of an earlier form), a system action (register a sale), and ends (each with a closing reason). The workbench draws it; Mermaid is the fallback of the diagram (Q1, C8).
3. **Case**: one running process, about a party, with a status from a code list (*open*, *in progress*, *closed*) and, when closed, a reason from a second list.

**The workbench stays the place where tasks are done.** A step of a case is an ordinary workbench task, with the same buttons; what changes is that it can carry a form and that closing it moves the case on. A case screen shows the whole matter.

Five decisions:
- **Status**: *open* = registered and no step done yet, so nobody has worked on it; *in progress* = at least one step done, so it is being worked on; *closed* = an end reached, with a reason. The tasks define it (Koen: "dat zijn eigenlijk de taken die definiëren"); a task has no "started" state, so "worked on" means a step is done (Q6). Both lists are code lists (Koen, 15 Oct 2026).
- **A step with a form is filled in, then closed; after closing it is fixed.** The answers are stored as an attached submission of the form engine, judged by the form's own rules.
- **A decision is a rule on one field**: an option of a choice question equals a value. Nothing more in this version.
- **The sale step is a task with a button** that opens the existing screen for an activity registration or a shop order with the party filled in; registering the sale closes the step and the case, as *won*. I read "triggert een systeemactie" this way (Q2).
- **A process screen, as a list** (R15): the steps in order, each with a type; the screen writes the BPMN, so the stored process is always standard BPMN (the layout of the drawing is generated, not dragged). The first two case types are delivered ready-made. B1a analyses the options.

### B1a. The process screen — the options

| Option | How it works | For | Against |
|---|---|---|---|
| A. A list of steps (recommended) | like the form engine: add a step, pick its type, pick where it goes next; a decision step has a list of rules | the same way of working as the forms; fits a phone; no library; the BPMN is generated | no free drawing: loops and parallel paths are limited to what the list can say |
| B. A canvas (bpmn.io modeler) | drag shapes and arrows | the real BPMN modeller; any shape | a large library, a licence with a required logo (unverified), poor on a phone, a tenant can draw what the engine does not run |
| C. Text (BPMN XML or Mermaid) | the author types it | cheapest; exact | not for a board member |

**Step types in option A**, each a row in the list:
- **Taak met formulier**: a title, a role, an optional form (the answers are fixed when the task is done), and *next step*.
- **Beslissing** (automatic, no person): rules *if the field F of form X is option O, then go to step N and optionally set the status to S*, and one *otherwise* route. This is what Koen calls the automatic step. It is a BPMN exclusive gateway.
- **Verkoop registreren**: a task with a button to register an activity registration or a shop order for the party; when the sale is registered the step is done by itself.
- **Einde**: the status *closed* and a reason from the list (*Behandeld*, *Niet ontvankelijk*, *Gewonnen*, *Verloren*, or the tenant's own).

The screen refuses a process with no start step, a step that nothing leads to, a step with no way on, or no end. A loop back (rework) is allowed. A status set on a route comes from the status list; if none is set, the status follows the rule of C4.2.

*Not the final form:* B3 puts the cases in a new domain; the architecture CLI may place them in `workflow`. The rest does not change with that choice.

## B2. Fit with the process and the requirements — for the business

Covers R1–R13. Use, the complaint: the public page *Klacht indienen* → intake form → case *Open*, first task *Beoordeel ontvankelijkheid* (form: *Ontvankelijk? ja/nee* and a motivation) on the workbench of the board → *ja*: task *Behandel de klacht* (form: what was done, the outcome) → closed *Behandeld*; *nee*: closed *Niet ontvankelijk*. The opportunity: *Interesse tonen* (a dropdown of what the interest is about, remarks) → *Beoordeel* → *Maak een offerte* (by hand, a short comment) → *Wacht op antwoord klant* (form: *Gewonnen? ja/nee*) → *ja*: *Registreer verkoop* → closed *Gewonnen* the moment the sale is registered; *nee*: closed *Verloren*.

## B3. The whole across the modules — for the architect

A proposal for the architecture CLI to confirm.
- **`cases` (new domain)** owns the case type, the case (party, type, status, reason, started, closed), the case's steps (a link to the workbench task and to the attached submission) and the process (BPMN text, per tenant). It consumes `workflow.api` (tasks), `forms` (intake submission, attached answers), `mdm` (the party, CR-26) and publishes `CaseClosed`.
- **`workflow`** keeps the task and the workbench. It gains a task *form* (the slug) and a way to hand a finished task to `cases` instead of walking its own step list. Its linear step list (`WorkflowDefinition.steps`, used by the contact message) is replaced by a one-step BPMN process in the last phase, so there is one engine; until then both exist and that is said.
- **`forms`**: a form can be linked to a case type (*when this form comes in, start this case*). It already offers the intake event and the attached answers; the link is one field.
- **`activities` and `sales` (CR-21)** publish an event when a registration or an order is made from a case's screen, carrying the case's number as an opaque value; they import nothing from `cases`.
- **Party (CR-26)**: a case holds a person and optionally an organisation (a person acting for it). A visitor who is not signed in gives name and address in the form; such a person is not a party (as for a guest buyer in CR-34).

## B3a. Standards the model follows — and where it deviates, on purpose

Checked on 15 October 2026 (Koen: "laten we het warm water niet opnieuw uitvinden"):

- **BPMN 2.0 (OMG)** for the process: start and end events, user and service tasks, exclusive gateways, sequence flows. Our additions (role, form, action, closing reason, status) are extension attributes in our own namespace, as the standard allows. It fits: the two first processes are sequences with decisions.
- **CMMN (OMG Case Management Model and Notation)** is the standard for cases, but for flexible knowledge work: plan items that become available, enabled and active under *sentries*, discretionary tasks a person adds while working, *milestones*, a case file. Its case lifecycle ends in *completed* and *closed*. We **borrow its words, not its model**: the status list (*open*, *in progress*, *closed*) and the closing reason are CMMN's idea of a case with an outcome, and a milestone is what *in progress* marks. The flexibility of CMMN (a person adds tasks as the case unfolds) is not asked for, and tooling for it is thin; found in the Camunda 7 and CIB seven documentation, which support a subset and no planning. A later need for ad-hoc tasks is a reason to look at CMMN again.
- **DMN (OMG decision tables)** is the standard for the rules of a decision. Our rule is one field equal to one option, which a decision table would only dress up; if rules grow, DMN is the shape to take, and the *Beslissing* step is where it would plug in.
- **UBL 2.1 / EN 16931** describe documents (invoice, order), not cases or processes; to my knowledge nothing in them applies here. The party in a case is CR-26's party as it stands.

## B4. Rules this change needs an exception from — decided once, here

| Rule (where) | What the design does instead | Mechanism | Temporary until … / the new rule | Decided |
|---|---|---|---|---|
| `workflow.SubjectType` is a closed list a definition cannot extend (`workflow/models.py:41`) | a case is a new subject, `case` | one code row and one enum member | permanent: a subject type is code, a case type is data | proposal, not yet put to Koen |
| One engine (the duplication rule in `AGENTS.md`) | the step list of `bericht` and the BPMN engine exist side by side until the last phase | phase 5 replaces the step list | until phase 5 | proposal, not yet put to Koen |

## B5. Cost — investment and running cost, and what operations must know

About 28 days (my estimate, to be set by the build read), with the list screen for processes and without CR-26's own work. Running cost: rows per case, per step and per answer; a renderer for the diagram (Q1). Operations: the two first processes are imported on each environment; an import never overwrites a type that has running cases.

## B6. Phasing — shippable phases, and what changes on the failure paths

| Phase | Content | Days |
|---|---|---|
| 0 | case type, case, status and reason lists, the intake from a form (public and back office), the first task, the party, the case list and screen without the diagram | 6 |
| 1 | the steps: a form per task, fixed after closing, gateways on a field, ends with a reason; the complaint runs end to end | 6 |
| 2 | the diagram on the case screen; export and import of a process with its forms | 4 |
| 3 | the process screen: the list, the four step types, the rules, the checks, the BPMN written and read back | 6 |
| 4 | the sale step for both kinds of sale, the opportunity runs end to end | 3 |
| 5 | the contact message moves to the one engine | 3 |

Failure paths: a gateway with no matching rule and no default stops the case and puts a task on the workbench for ADMIN ("cannot continue"); a sale made from a case's screen but never registered leaves the step open; an import that refers to a form the environment lacks is refused whole.

## B7. Rule and gatekeeper — what this fixes for all future work

A matter the portal follows over several steps is a case of a type, not a new table and a new screen. A gate: a task of a case that has a form cannot be closed without a valid submission, and a closed step's answers cannot be updated (a test that tries both).

## B8. Open decisions — what the approver still decides

| # | Question | Recommendation | What the answer changes |
|---|---|---|---|
| Q1 | How is the process drawn: a BPMN viewer in the browser (bpmn.io; its licence requires its logo on the diagram, unverified), or a Mermaid diagram made from the BPMN on the server? | prototype both in C8; Mermaid if the viewer's logo is unacceptable, because Mermaid is already used for the documents | the renderer and a library |
| Q2 | Does registering a sale happen from a button on the task that opens the existing screen (my reading), or does the portal register the sale itself? | the button: a sale needs an article or an activity and an amount, which a person chooses | the size of phase 4 |
| Q3 | How long is a closed case kept? | a number of years as a tenant setting; the legal period for a complaint is unverified | one setting and a purge |
| Q4 | Which role handles a complaint? Today the roles are ADMIN, FINANCE, OPERATOR and ACCOUNT_ADMIN, and the shop adds Verkoop (CR-21) | ADMIN for the complaint; Verkoop for the opportunity | the role in two processes |
| Q5 | Is the case's number visible to the client, so a client can ask about it? | yes, a number on the confirmation mail | a field and a mail line |
| Q6 | Is a case *in progress* from the first step done, or from the moment a person opens its task? | the first step done: a task has no started state and the workbench would need one | a started state on a task, or nothing |

## B9. Decisions log — dated answers

| Date | Decision | By |
|---|---|---|
| 15 Oct 2026 | Requirements R1–R14 as written in A6 (dictation, not an answer to a question) | Koen |
| 15 Oct 2026 | The statuses of a case are a code list: *open*, *in progress*, *closed* | Koen: "Misschien moeten we de statussen die een case heeft vastleggen, dat dat een codelijst is. Open, in progress, closed." |
| 15 Oct 2026 | The workbench stays a view on tasks; the case is the umbrella above it | Koen: "Dus de werkbank blijft een visualisatie van de taken, maar daar zit dus een koepel boven en dat is de case." |
| 15 Oct 2026 | A screen to model a process from start to end is part of this change, in the way of the form engine, with step types and decisions that set the status and say which task follows; the earlier proposal to deliver the first types ready-made without an editor is withdrawn | Koen: "Ik weet dus dat ja, de formulieren die al manueel kunnen gemaakt worden, dat er dus ook een scherm is om die processen van startpunt tot eindpunt te kunnen modelleren. Dat mag visueel gewoon in het scherm zijn, in een textueel scherm zoals de Form Engine […] Dus analyseer dan maar eens een keer dat die verschillende opties mogelijk zijn in een scherm" |
| 15 Oct 2026 | Standards: look at CMMN and others before inventing; the analysis stands in B3a | Koen: "laten we dan het warm water niet opnieuw uitvinden" |
| 15 Oct 2026 | Every task of a process is given a role; due dates are out of the scope | Koen: "Aan een taak moet je natuurlijk ook rollen kunnen toekennen. Dat ben ik juist vergeten te zeggen. [...] Due dates buiten de scope." |
| 15 Oct 2026 | A history of the status and of who completed which task when is out of the scope | Koen: "Ook buiten scope is historiek op status meten van wie welke taak wanneer voltooid heeft. Oké, dat gaat het misschien automatisch hebben, maar dat nemen we allemaal buiten scope." |
| 15 Oct 2026 | The case types are managed through a button *Instellingen* on the *Zaken* list, so there is one menu item, not two | Koen, who left the choice open ("kies maar"): "Ik denk bij cases is het voor mij goed dat we misschien de knop instellingen voorzien op de cases menulijn. Dat we daar de processen kunnen definiëren." |

---

# Part C — The build, for the master CLI and the dev CLIs

## C1. Verified premises — measured before the handover

Measured on master @ `ef4b130c` on 15 October 2026 (CR-21 and CR-26 are not on master; read from their branches); a build read is still to come, and the table is to be re-measured at the handover.

| Concept or claim | Kind | Measurement | Verdict | Consequence |
|---|---|---|---|---|
| A workflow definition is a linear list of steps in JSON; `advance` goes to the next step | changes | `workflow/models.py:140–158`, `api.py:285` | must change | gateways need a graph; phase 5 retires the list |
| A task has a role, a title, a subject, a free-text `decision`, no form | changes | `workflow/models.py:86–135` | must change | a form slug on the task |
| `SubjectType` is a closed list of four | changes | `workflow/models.py:41` | must change | add `case` (B4) |
| `complete_task` closes the task and advances the instance in one commit | relies on | `workflow/api.py:301` | holds | a case step completes through it |
| A contact submission starts the `bericht` definition by event | relies on | `SubmissionCreated`, `workflow/handlers.py` | holds | the generic start reads a form → case-type link instead |
| The form engine stores answers of another record as an attached submission under the form's own rules, and updates them | relies on | `SubmitAttached`, `UpdateAttached` in `forms/CONTRACT.md` | holds | fixing a closed step = refusing `UpdateAttached` for it |
| A form definition exports and imports as JSON | relies on | `forms/admin_ui.py:723, 907`; `forms/service.py:1102, 1517` | holds | the process export bundles it |
| The board can register for an activity | relies on | `board_register_for_activity` (activities) | to verify | the case screen links to it with a case number |
| The shop's back-office order and the role Verkoop | relies on | CR-21 on `cr21/webshop` | not on master | phase 4 waits for CR-21 |
| The party model: person, household, organisation; an account's *Mijn organisatie* | relies on | CR-26 on `claude/cr-26-party-model` | not on master | phases 0 and later wait for CR-26 phase 2 |
| Roles are ADMIN, FINANCE, OPERATOR, ACCOUNT_ADMIN | relies on | `auth/models.py:28–31` | to verify with CR-24 (roles as bundles) | Q4 |

## C2. Per module: what must happen

- **cases (new)**: tables `case_types`, `cases`, `case_steps`, `processes` (BPMN text per type, versioned), code lists `case_status` (*open*, *in_progress*, *closed*) and `case_close_reason` (*handled*, *not_admissible*, *won*, *lost*; a tenant's process may name its own, as codes in the BPMN end event); an engine that reads the BPMN subset (start, user task, exclusive gateway with a rule on one field, service task `register_sale`, end event with a reason); a facade `start_case`, `case_of`, `list_cases` (filters and a search term); events `CaseStarted`, `CaseClosed`; the case screens and the *Zaken* menu; export and import of a process with its forms; the process screen (C4.6).
- **workflow**: a `form_slug` on a task; the hand-over of a finished task to `cases`; `SubjectType.CASE`; phase 5 replaces the step list.
- **forms**: the link *form → case type*; the intake handler; a refusal to update the answers of a fixed step.
- **activities, sales**: an event on a registration or an order made from a case's screen, with the case number as an opaque value.
- **mdm**: reads only (the party), after CR-26.

## C3. Cross-cutting impact — the checklist of what gets forgotten

- Every reader of `SubjectType` and of the workbench's `subject_url` (the workbench must find the way to a case).
- The seeded `bericht` definition of each tenant and `can_handle_messages`.
- CR-33 register: the case, the steps and the answers are personal data; the retention (Q4).
- CR-24 rights: a right per case type or one right for cases; `docs/rollen-en-rechten.md`.
- CONTRACT.md of `cases`, `workflow`, `forms`; `docs/architecture.md` (a domain, two figures).
- The public intake form's limits and spam brake, as the contact form has.
- Alembic: one migration per phase; head counted before the push.

## C4. Detailed decisions — one subsection each, with the reasons

**C4.1 The BPMN subset.** `startEvent`, `userTask`, `serviceTask`, `exclusiveGateway`, `sequenceFlow` with an optional rule, `endEvent`. Extension attributes (namespace `raak`): `role`, `form`, `action`, `when="<field>=<option>"`, `reason`. Anything else is refused at import with the element named.

**C4.2 Status.** `open` at start; `in_progress` when the first step is done; `closed` at an end event with its reason. Closing is one transaction with the last step.

**C4.3 The sale step.** A `serviceTask` with `action="register_sale"` creates a workbench task with a button. The screens of both kinds of sale accept a case number and the party; their event carries both; `cases` records the link and completes the step, which reaches the end event *won*.

**C4.4 Start from the workbench.** *Nieuwe zaak* lists the case types that have an intake form; it opens the form in the back office on behalf of a chosen party or contact details.

**C4.6 The process screen.** One page per case type, `/admin/zaken/instellingen/<type>/proces`, a list of steps like the form builder's (htmx, kit macros). The screen holds a small model (steps, type, role, form, routes with rules and status) and writes BPMN with generated layout; opening it reads the stored BPMN back into the same model, and a BPMN that the screen cannot read (an import with elements outside the subset) is refused at import, so the two never disagree. Saving runs the checks of B1a and is refused with the step named. A process with running cases is saved as a new version; running cases keep theirs.

**C4.5 Fixing.** A step's submission is updatable until its task is done; after that `UpdateAttached` is refused.

## C5. Privacy and security — the mechanics behind A7

A public intake form takes free text from outside: the form engine's validation and brake; the case is visible to the role of its tasks and to ADMIN of the tenant; the case's answers are never put in a mail beyond the confirmation. Import is allowed to ADMIN only and never overwrites a type with running cases.

## C6. Tests — what the build must prove

| # | Test |
|---|---|
| T1 | an intake form linked to a type starts a case with the first task, signed in and signed out |
| T2 | the gateway sends on by a field's option; an unmatched value with no default stops the case with a task |
| T3 | a task with a form cannot be closed without a valid submission |
| T4 | a closed step's answers cannot be updated |
| T5 | status goes open → in progress → closed; the reason is set at the end only |
| T6 | registering a sale from a case's screen completes the step and closes the case as won |
| T7 | a sale made elsewhere for the same party does not close the case |
| T8 | export then import of a process and its forms into an empty tenant gives the same process; an import with a missing form is refused whole |
| T9 | an import is refused for a type with running cases |
| T10 | a BPMN element outside the subset is refused with its name |
| T11 | the contact message still starts its task (before and after phase 5) |
| T12 | a task of another tenant's case is not visible |
| T17 | *Zaken* filters by status, type and reason, and finds a case by number, party name, e-mail and a word of the intake answers |
| T13 | a process made in the screen is written as BPMN and read back to the same list (round trip) |
| T14 | the screen refuses a process with no end, a step nothing leads to, or a step with no way on, naming the step |
| T15 | saving a process with running cases makes a new version; the running case keeps its own |
| T16 | a route that sets a status moves the case to it; a route that sets none follows the derived rule |

## C7. The gate — what refuses a deviation from now on

A gate that every `userTask` of a seeded process names a role that exists and a form that exists, proved with an additive violation (a task naming a role that is not there).

## C8. Prototype findings — what was measured before the build

Not yet taken: draw the two first processes with bpmn.io's viewer and as Mermaid, and look at both on a phone; check the viewer's licence text.

## C9. Screens before the build — the concepts the approver saw

Not yet made, at 390 px: the process screen (the list of steps, a decision with its rules), the *Zaken* list, the case screen (the request, the tabs, the diagram), *Nieuwe zaak* on the workbench, the task with its form, the public complaint form.

## C10. Close-out at the release

Status line, as-built notes folded in, tracking issue closed (`CLAUDE.md` step 14).

## Q&A log — asked once, answered here

| Q&A | Date | Question | Status |
|---|---|---|---|
| — | 15 Oct 2026 | Q1–Q6 of B8 go into a Q&A file for Koen | open |

## Non-goals — deliberately outside this change

Due dates on tasks; a history of statuses and of who did what when (beyond what a task already keeps); a canvas editor with dragging of shapes; dropdowns of articles or activities in an intake form; conditions other than a field equal to an option; parallel steps, timers, messages between cases and sub-processes; assigning a task to a person (a task goes to a role); a client portal showing the case to the client.

## Relationship to existing work — issues and change requests

Builds on the workbench (CR-05's sibling work in `workflow`, #403) and the form engine (CR-14). Needs CR-26 (party model) for the party and CR-21 (webshop) for the sale step. CR-24 (rights) and CR-25 (back office) shape the menu and the roles; CR-33 (attribute register) gets the entries.

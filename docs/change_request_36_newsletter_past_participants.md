# Change Request 36 — Newsletter to the people registered for earlier activities

**Project:** Web Portal "Raak Millegem"
**Status:** shaped with Koen on 15 October 2026 · not assigned to a release; open decisions in B8
**Tracking issue:** #2026 — the one place where what is open stands; this document is the design, the issue is the status
**Applies to:** the newsletter (audience choice, recipient list, send screen, Raakje's sources), the activities facade (a read of registration addresses), the unsubscribe page
**Reading:** A 758 words · B 1 155 · C 1 460 — measured per part; A ≤ 1 500, B ≤ 2 500

---

# Part A — The business

## A1. Reason to act — the trigger

Koen, 15 October 2026: the newsletter should be able to address a *specific audience*: the people who were registered for one or two activities in the past years. His example: last year there was an activity; when it comes back, the people who came get a mail "we organise it again, nice that you were there last year on that date". More targeted communication, built on who registered for similar activities before. The audience is chosen by hand in the audience choice that exists today; Raakje drafts the letter as it does today. A suggestion of a fitting past activity is outside this change (Koen, 15 October 2026).

## A2. As-is process — how it works today, and where it hurts

Today the audience of a letter is *Leden*, *Abonnees* or *Allebei*. There is no way to say "the people who came to last year's activity". My reading, to be confirmed by Koen: an author who wants that sends a mail by hand outside the portal, with the addresses copied from the registrations.

```mermaid
flowchart LR
  subgraph author["Board member (author)"]
    a1[Decide to invite last year's participants]:::hand
    a2[Look up the registrations of the activity]:::tool
    a3[Copy the addresses]:::hand
    a4[Write and send a mail in the own mail program]:::hand
    s([Mail sent]):::done
  end
  a1 --> a2 --> a3 --> a4 --> s
  classDef hand fill:#ffffff,stroke:#52607a
  classDef tool fill:#e8f0ff,stroke:#0051a4
  classDef done fill:#ffffff,stroke:#52607a
```

*What to see:* three of four steps are by hand and the mail leaves the portal.

| Step | Pain |
|---|---|
| Copy the addresses | slow, error-prone, one activity at a time |
| Send from the own mail program | no unsubscribe link, no archive, no queue, no help from Raakje, shares the mailbox limit with everything else |

## A3. To-be process — how it should work afterwards

```mermaid
flowchart LR
  subgraph author["Board member (author)"]
    b1[Write the letter with Raakje]:::tool
    b2[Choose the audience: registered for earlier activities]:::tool
    b3[Tick one or more past activities]:::tool
    b4[Check who it goes to and send]:::tool
    s([Letter queued]):::done
  end
  subgraph reg["Person registered earlier"]
    r1[Receives the letter]:::hand
    r2([Unsubscribes]):::done
  end
  b1 --> b2 --> b3 --> b4 --> s
  b4 -.-> r1 --> r2
  classDef hand fill:#ffffff,stroke:#52607a
  classDef tool fill:#e8f0ff,stroke:#0051a4
  classDef done fill:#ffffff,stroke:#52607a
```

*What to see:* the three by-hand steps are gone; the letter keeps its queue, archive and unsubscribe link.

What it says on the screen (Dutch):
- audience choice, a fourth option: **Eerdere deelnemers**
- under it a list: **Kies één of meer activiteiten**, past activities newest first, each with its date and the number of addresses
- the send screen says in words who gets it: "*N adressen van mensen die waren ingeschreven op <activiteit>*", and how many of them already get the letter as member

## A4. Benefits — what the change earns

- Targeted mail to people who showed interest in the same kind of activity: higher turnout for a returning activity (no figure; to be seen after the first use).
- The by-hand route disappears: the minutes of copying addresses per mail, and the mails without unsubscribe link.

## A5. Supplied material — and what it taught us

Koen's dictation of 15 October 2026 only. Reporting need: the archive of a sent letter names its audience and the activities chosen (A6 R6).

## A6. Business requirements — what the board asks, with MoSCoW

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | Choose, per letter, one or more past activities as the audience | Must | Koen, 15 Oct 2026 | "de ingeschrevenen op 1 of 2 gelijkaardige activiteiten vorig jaar" |
| R2 | The choice sits in the audience choice that exists | Must | Koen, 15 Oct 2026 | a drop-down by hand |
| R3 | Anyone can unsubscribe from such a letter, and is not mailed again | Must | my reading of CR-05 §3.4; Q1 | |
| R4 | The letter can name the activity and its date | Should | Koen, 15 Oct 2026 | "tof dat je vorig jaar er was op die datum" |
| R5 | Raakje suggests a past activity that fits the letter | Won't | Koen, 15 Oct 2026 | taken out of the scope: a later change if wanted |
| R6 | The archive shows which activities a letter went to | Should | my proposal | |
| R7 | Choosing people by presence, payment or age | Won't | — | not asked |

## A7. Non-functional requirements — security, privacy, house style, tenants

| Concern | This change |
|---|---|
| **Security** | only the board that may send a newsletter chooses the audience; no new public input except the unsubscribe link, which exists |
| **Privacy** | the address of a registration is used for a new purpose, a newsletter; whether that needs consent is Q1; every such letter carries a working unsubscribe link; Raakje never sees addresses |
| **House style** | the audience choice and send screen follow the kit; 390 px first |
| **Multi-tenant** | registrations and activities of the own tenant only |

## A8. Acceptance criteria — what the business signs off on HDEV

| # | Criterion | Requirement | Walkthrough steps |
|---|---|---|---|
| AC1 | Choosing *Eerdere deelnemers* shows the list of past activities with their counts | R1, R2 | open a draft, choose it |
| AC2 | The send screen says in words who gets the letter and how many | R1 | tick two activities, read the sentence |
| AC3 | A person registered twice, or for both activities, gets one mail | R1 | check the recipient count |
| AC4 | The mail has an unsubscribe link; after using it the person gets nothing from a later letter of this kind | R3 | unsubscribe, send a second letter |
| AC5 | The archive shows the activities chosen | R6 | open the sent letter |

---

# Part B — The solution, for whoever approves it

## B1. Solution outline — the solution and the decisions that shape it

A fourth audience, *Eerdere deelnemers*, next to Leden, Abonnees and Allebei. With it the letter keeps a list of the activities chosen. The recipients are the contact addresses of the registrations on those activities, deduplicated by address, fixed when sending starts like every audience. Four rules decide the rest:

1. **One rule for everybody: someone who is on a list already is not mailed twice.** Order of precedence: a household with a membership for the working year gets it as a member (as in CR-05 §3.3, no unsubscribe line); a confirmed subscriber as a subscriber; everyone else as a *participant*.
2. **An address that objected is never mailed through this audience**: it unsubscribed as a subscriber (CR-05 §3.6), or the person used the unsubscribe link of a participant letter. The second is kept as an address-only objection and never as a subscriber, so nobody becomes a subscriber by having registered; the check is made again at the moment each mail leaves, because a send takes days.
3. **"Attended" means registered.** The portal does not record presence. A registration that was deleted, or an activity that was cancelled, counts for nobody; a registration whose payment never completed counts (the person showed interest).
4. **Addresses are compared in one spelling**: trimmed and lower-case, checked as everywhere in the newsletter. An address that does not pass is skipped and counted on the send screen.

*Raakje* gets the chosen activities as the source "voorbije activiteiten" of the letter, with name and date, so the letter can say it. Raakje does not suggest an activity (R5): the author ticks it. Only the *old* activities are chosen as audience; the activity the letter advertises is put in the text with the existing insert helper, and the portal links the two nowhere. Someone already registered for the new activity still gets the letter (B9).

## B2. Fit with the process and the requirements — for the business

Covers R1–R4 and R6. An example of use: *Nieuwsbrief*, step *Doelgroep* → the new option → tick last year's activity → *Naar versturen* → "212 adressen van mensen die waren ingeschreven op …, waarvan 140 al als lid de brief krijgen"; send.

## B3. The whole across the modules — for the architect

- `activities` gives two reads through its facade: the past activities that may be offered, and the raw addresses of the registrations on a set of activities, per tenant. `newsletter` never reads `Registration` itself and normalises the addresses itself.
- `newsletter` owns the audience, the list of chosen activities (a soft reference across the schema line, with the activity's name and date copied when the send starts, so the archive survives a later deletion), the delivery kind `participant`, one `token` per delivery, and an address-only table of objections.
- No new module and no new edge: `newsletter` already consumes `activities.api`.

## B4. Rules this change needs an exception from — decided once, here

None.

## B5. Cost — investment and running cost, and what operations must know

About 6 days (my estimate; the build read of 15 October added a re-check at send, normalised addresses and the delivery token). No running cost. Operations: letters to this audience count against the same daily cap; one letter to a large past activity can take days, as *Allebei* does.

## B6. Phasing — shippable phases, and what changes on the failure paths

| Phase (the only one) | Content | Days |
|---|---|---|
| 1 | audience, list of activities, recipient rule with the re-check at send, participant unsubscribe and resubscribe, send screen words, archive | 6 |

Failure paths: an activity chosen and then deleted before sending is dropped from the list and the screen says so; a letter whose audience becomes empty cannot be sent.

## B7. Rule and gatekeeper — what this fixes for all future work

A letter's recipients are always a derived list with one precedence rule and one opt-out check; a new audience is one more entry in that function, never a second path. A test names the precedence order so a new audience must choose its place.

## B8. Open decisions — what the approver still decides

| # | Question | Recommendation | What the answer changes |
|---|---|---|---|
| Q1 | May the association mail people who registered for an activity, without their consent, if the letter carries an unsubscribe link? (a) yes, on the existing relationship as for the imported list; (b) only people who ticked agreement on the registration form | a, after the accountant or a privacy adviser agrees; legal facts here are unverified | b needs an answer on both ways in (the public form and the board's registration for someone, where nobody ticks: those count as not agreed) and leaves last year's people out |
| Q2 | May two chosen activities be combined, so a person of either gets the letter? | yes: union, one mail | a letter naming "last year" must then speak generally |
| Q3 | Which activities are offered: those of the last three working years? | yes | the list length |
| Q4 | "Je moet ook een nieuwsbriefje kunnen maken om dat te versnellen": does that mean Raakje drafts the letter for this audience (as it does now)? | yes, it does with R4's sources | nothing to build beyond B1 |

## B9. Decisions log — dated answers

| Date | Decision | By |
|---|---|---|
| 15 Oct 2026 | Requirement R1, R2, R4 as written in A6 (dictation, not an answer to a question) | Koen |
| 15 Oct 2026 | R5 (Raakje suggests a past activity) leaves the scope: one phase | Koen: "haal die fase 2 op basis van een activiteit voorstellen, haal dat maar uit de scope, zodanig dat het een eenfasige change request wordt" |
| 15 Oct 2026 | People already registered for the activity the letter advertises stay on the recipient list; no exclusion | Koen, to "moeten mensen die al voor de nieuwe activiteit ingeschreven zijn uit de ontvangerslijst vallen?": "Nee, dat is geen probleem. Als die mensen die nog een mail krijgen, ook al zijn ze al ingeschreven, dat is geen probleem." |
| 15 Oct 2026 | The portal makes no link between the old activities of the audience and the activity the letter advertises; the author does that in the letter, with the insert helper that exists | Koen, to my explanation of the two kinds of activity: "Ik ben het ook met die redenering eens. [...] Het feit dat er geen link is tussen oud en nieuw, dat is helemaal aan de gebruiker om dat te doen." |
| 15 Oct 2026 | The new audience is called *Eerdere deelnemers* on the screen | Koen, to the question which word the audience carries (a *Eerdere deelnemers*, b *Ingeschreven op eerdere activiteiten*, c *Aangemeld voor eerdere activiteiten*): "eerdere deelnemers op vraag 1 is een goed voorstel" (my reading: he meant that question) |
| 15 Oct 2026 | Erasure of an address from the archives (the right to be forgotten) is not built in this change; see the known gap under Non-goals | Koen, to my question whether erasure by address should be part of this change: "Het recht om vergeten te worden gaan we voorlopig even laten liggen." |

---

# Part C — The build, for the master CLI and the dev CLIs

## C1. Verified premises — measured before the handover

Measured on master @ `ef4b130c` on 15 October 2026 (the build read of dev2 on #2026 re-measured it the same day); to be re-measured at the handover.

| Concept or claim | Kind | Measurement | Verdict | Consequence |
|---|---|---|---|---|
| `Audience` has three values with code table and labels (*Leden*, *Abonnees*, *Allebei*) | changes | `newsletter/models.py:72`, `codes.py:67–80` | must change | one code, one label row, one migration row |
| Readers of `Audience` | changes | `admin_ui.py:161, 537–568, 632, 687, 881–893`; `service.py:1608`; `drafting.py:285–291, 1056`; `_nb_versturen.html:5`; `admin_nieuwsbrief.html:152` | must change (C2, C3) | each reader is walked in the build |
| `recipients_for`, `audience_summary`, `_audience_said`, `audience_counts` take only the audience; `start_sending` calls `recipients_for` | changes | `service.py:429, 484, 509, 1700`; `admin_ui.py:1001` | must change | they take the letter, because the participants need its chosen activities |
| `send_batch` re-checks only a subscriber delivery | changes | `service.py:1853–1862` | must change | a participant delivery gets its own re-check (C4.2) |
| A registration keeps its address as given; members are lower-cased; subscribers go through `normalize_email`; deliveries are unique on (letter, address) | changes | `activities/models.py:470`; `mdm/service.py:1613`; `service.py:75` | must change | C4.3 |
| The unsubscribe page shows on GET and acts on POST; the resubscribe form finds a subscriber by token | relies on / changes | `ui.py:118–147`; `_nb_publiek.html:54`; `subscriber_by_unsubscribe_token` | holds for subscribers; a participant needs its own path | C4.2 |
| `list_subscribers` and `subscriber_counts` return every subscriber row | relies on | `service.py:96, 107` | holds | an objection is no subscriber row, so the *Uitgeschreven* count does not grow with people who never joined |
| The test mail and the preview each decide the delivery kind from the audience | changes | `service.py:1608`; `admin_ui.py:886–893` | must change | one function (C4.5) |
| `copy_newsletter` and `delete_draft` | changes | `service.py:807, 819` | must change | clear, respectively delete, the chosen activities |
| An activity has `is_cancelled`, a draft/published status and soft-deletable dates | relies on | `activities/models.py:234`, `ActivityDate` | holds | C4.6 |
| The registration form carries no newsletter wording; the board registers for someone | relies on | `board_register_for_activity` | holds | the cost of Q1 (b) |
| No presence is recorded | relies on | no field in `activities/models.py` | holds | "attended" = registered |
| `newsletter` has four data tables with `tenant_id` | relies on | `newsletter/CONTRACT.md` | holds | the new tables carry `tenant_id` |

## C2. Per module: what must happen

- **activities**: `past_activities(db, since_year)` (id, name, last non-deleted date; published, not cancelled, a non-deleted date, all dates before today) and `registration_addresses(db, activity_ids)` (the raw distinct addresses of the non-deleted registrations). Tenant-scoped.
- **newsletter**:
  - models: `Audience.PARTICIPANTS`, `DeliveryKind.PARTICIPANT`, `deliveries.token` (nullable, unique, random), `newsletter_audience_activities` (tenant, letter, activity, name and date filled at `start_sending`), `address_objections` (tenant, normalised address, date; unique on tenant and address);
  - service: `recipients_of(db, letter)` replaces the call at `service.py:1700`; the summary, the sentence and the counts take the letter; the sentence uses the union of the chosen activities, not a sum; `send_batch` re-checks a participant delivery (C4.2); `copy_newsletter` clears the chosen activities, `delete_draft` deletes them;
  - routes: the public unsubscribe page resolves a subscriber token, then a delivery token; for a delivery token POST writes the objection, and the resubscribe route deletes it (the person stays a participant, not a subscriber);
  - screens: the audience choice with the list (htmx fragment, kit macros), offered only when the `activities` module is on for the tenant; the send screen sentence with the count of skipped addresses; the archive line.
- **drafting**: the chosen activities go to `set_draft_sources`; Raakje's examples of earlier letters (`drafting.py:285–291`) are looked at per audience: a participant letter about another activity is a weak example, the build decides whether to leave it out.

## C3. Cross-cutting impact — the checklist of what gets forgotten

- The readers of C1, one by one; the test-mail snapshot test `test_newsletter_test_mail_unchanged_1251.py` covers two audiences only and stays unchanged.
- CR-33 attribute register: the purpose list of a registration's `contact_email` gains "newsletter, to earlier participants"; the token and the objection table get entries (the register's gate is not on master yet; the merge order decides who carries it).
- CONTRACT.md of `newsletter` and `activities`; the architecture document where it names three audiences.
- Privacy statement of the registration form (Q1).
- Alembic: one migration; head counted before the push.

## C4. Detailed decisions — one subsection each, with the reasons

**C4.1 Recipient rule.** `recipients_of` builds members, then subscribers, then participants (each `setdefault` on the normalised address), then drops every participant address that has an objection or an unsubscribed subscriber row. A member address is never dropped (CR-05 §3.4).

**C4.2 The participant's link and the check at send.** A participant delivery gets a random `token`; the unsubscribe link is `/nieuwsbrief/uitschrijven/<token>`, GET shows, POST writes the objection , one-click POST likewise. *Toch opnieuw* deletes the objection and nothing more: no `consented_at`, no subscriber, so "source = proof of consent" stays true. `send_batch` checks, at the moment each participant mail leaves, the objection table and the subscriber rows, and skips with "uitgeschreven tijdens het versturen", as for a subscriber.

**C4.3 One spelling.** `registration_addresses` returns raw addresses; `newsletter` runs each through `normalize_email`, an address it refuses is skipped and counted, and the delivery row stores the normalised form (so (letter, address) stays unique per person).

**C4.4 Erasure.** Not part of this change (B9, Non-goals): the existing `erase` of a subscriber is untouched. The objection row holds the address only.

**C4.5 One mapping.** A function audience → delivery kind of a sample mail serves `render_test` and the preview; the new audience is one entry.

**C4.6 Which activities are offered.** Published, not cancelled, with at least one non-deleted date, all non-deleted dates before today, within the last three working years (Q3); newest first; label = name, last date, number of addresses.

## C5. Privacy and security — the mechanics behind A7

The registration address is used for a second purpose; Q1 decides the basis and the form text. The token is random, 32 bytes, unique; the public page answers the same for an unknown token (no oracle). The unsubscribe page has no per-IP limit today and gets none now. Erasure of an address from the archives: C4.4.

## C6. Tests — what the build must prove

| # | Test |
|---|---|
| T1 | two activities, one person on both: one delivery |
| T2 | a deleted registration and a cancelled activity add nobody; an unpaid registration counts |
| T3 | a member address gets the member kind, no unsubscribe line |
| T4 | a subscriber address gets the subscriber kind |
| T5 | an unsubscribed subscriber and an objection are absent, unless the address is a member's |
| T6 | the participant link, called once and by one-click POST, writes the objection; a second letter skips the address |
| T7 | another tenant's registrations never appear |
| T8 | copy clears audience and activities; deleting a draft deletes them |
| T9 | the audience-said sentence counts the union, not the sum |
| T10 | the test mail of a participant letter carries the unsubscribe line |
| T11 | a participant who objects during a running send is skipped (red when the re-check is removed) |
| T12 | a mixed-case registration against a lower-case objection is not mailed |
| T13 | an address that fails the check is skipped and counted |
| T15 | *Toch opnieuw* removes the objection and creates no subscriber |
| T16 | the subscriber counts do not change when a participant objects |
| T17 | a tenant without the `activities` module is not offered the option |
| T18 | the archive keeps the activity's name after the activity is soft-deleted |

## C7. The gate — what refuses a deviation from now on

A test that every `Audience` value has a precedence entry in `recipients_of` and an entry in the audience → kind function (an additive violation proves it: a fourth fake value fails both).

## C8. Prototype findings — what was measured before the build

Not yet taken: count the addresses of three real past activities on a dev copy with made-up data; the numbers go here.

## C9. Screens before the build — the concepts the approver saw

Not yet made: audience choice with the drop-down, send screen, archive line, at 390 px.

## C10. Close-out at the release

Status line, as-built notes folded in, tracking issue closed (`CLAUDE.md` step 14).

## Q&A log — asked once, answered here

| Q&A | Date | Question | Status |
|---|---|---|---|
| — | 15 Oct 2026 | Q1–Q4 of B8 go into a Q&A file for Koen; the build read of dev2 (#2026, 15 Oct 2026) is taken in | open |

## Non-goals — deliberately outside this change

A suggestion by Raakje of a fitting past activity; segments by age, payment or presence; a saved audience; mail to the registrants of an activity about that activity (CR-05 §3.14, a separate change).

**Known gap, to be taken up later:** removing an address from the archives of sent letters. Today it works for a subscriber (the *Verwijderen* action anonymises his deliveries); a member's delivery and, with this change, a participant's has no such action, so the address stays in the archive. The build read found it for members already. It is left out for now; it is not decided that it stays out.

## Relationship to existing work — issues and change requests

CR-05 (newsletter) is the base; CR-37 (anonymous opens and clicks, #2027) is independent and takes nothing from this change; CR-26 (party model) may later make "who registered" a party question, not needed now.

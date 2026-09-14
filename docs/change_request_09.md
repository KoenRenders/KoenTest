# Change Request 09 — Meetings in the portal, newsletters out of them

**Project:** Web Portal "Raak Millegem"
**Status:** Draft in progress — being shaped with Koen (started 14 September
2026, handover on #258). Scope decisions §3 are settled; the numbered open
questions in §10 are not. Not assigned to a release.
**Apply to:** a new `meetings` domain (backend + admin screens), the
`communication` domain CR-05 already designed (built here for the first time),
a drafting capability pack on the CR-07 conversation kernel. No public-facing
screens.

---

## Goal

The board runs the association through a monthly meeting: an **agenda** goes
out the day before, gets filled in during the meeting, and returns as the
**report** the day after. Out of that same material flow two newsletters: a
monthly one to the members and a half-yearly one to a mailing list of ~800
addresses. Today every step lives outside the portal — Google Docs for the
document, Gmail for all three mails, the mailing list implicit in a Bcc field.

This change request moves the chain into the portal:

1. **Meetings are composed in the portal** — the agenda pre-filled from the
   activities that already exist there, the report the same document filled in.
2. **The portal sends the meeting mails** — agenda and report as PDF to the
   board, with ad-hoc extra attachments.
3. **The mailing list becomes data** — the ~800 addresses imported as
   `Subscriber` rows (CR-05's entity) with a working opt-out.
4. **The LLM drafts newsletter concepts** from meeting and activity data — the
   first *acting* capability pack on the CR-07 kernel, under the three rules
   CR-07 §4.1 fixed for it. A person edits and sends; nothing auto-sends.

This CR is the meeting-and-content layer **on top of CR-05, not a revision of
it**: the subscription/consent model, the `Subscriber` entity, the EU-ESP
adapter and the phase order were decided on 17 June 2026 and stand.

## 1. The source material (measured, 14 September 2026)

Read from real examples (meeting cycle of 3 September 2026; member newsletters
of June and September 2026; half-yearly mailing of July 2026). The examples
hold personal data and stay in Koen's Nextcloud project folder — none of it
enters this repository.

**The meeting document.** Agenda and report are one document. Fixed structure:
a header (date, present, excused) and five sections — *evaluation of past
activities*, *upcoming activities*, *members* (new members with their
neighbourhood steward), *programme ideas*, *miscellaneous*. Activities appear
as one line (name | date time location) with nested bullets: evaluation notes,
counts ("172 tickets sold", "4 walkers"), and action items with a first name
on them ("X books the room"). The agenda is the same list with the bullets
still empty, plus whatever carried over. Sent the evening before; the report
the evening after; ~28 board recipients, from a personal Gmail account.

**The monthly member newsletter.** Recognisably derived from the report:
an intro around the next headline activity, an "in de kijker" block, a
two-month calendar, a further outlook, external events. Sent from a personal
Gmail account to the member list. The September edition was visibly drafted
with AI help already — the links carry `utm_source=gemini`.

**The half-yearly mailing.** Same source material, wider audience (~800
addresses), promotional tone, public activities only, activity flyers as PDF
attachments. Sent from the association's Gmail address **to itself with the
audience in Bcc, without an unsubscribe link and without any consent
record** — the list exists only inside Gmail. This is the GDPR exposure CR-05
was written for, now measured rather than presumed.

## 2. What exists to build on

| | measured |
|---|---|
| Activities | the `activities` domain holds name, date, location, price, registration link and occupancy — the agenda's "upcoming activities" section is a query, not typing |
| Subscription model | CR-05: `Subscriber`, double opt-in, unsubscribe tokens, `EmailCampaignProvider` adapter — designed, nothing built |
| Transactional mail | `mail` domain + Gmail SMTP — fine for ~28 board recipients, wrong for campaigns |
| LLM plumbing | CR-07's conversation kernel and capability-pack architecture; the drafting pack was already named there as the first acting capability |
| Attachments | the `media` domain stores uploaded files |
| STT | a `stt` domain exists but is **out of scope** — decided 14 September 2026: the report is typed, never transcribed |

## 3. Decisions

Taken by Koen on 14 September 2026, in the CR-shaping conversation:

1. **The ~800 mailing addresses are imported into the portal as `Subscriber`
   rows with opt-out.** Double opt-in (CR-05, 17 June 2026) governs *new*
   signups through the public form; the import of the existing list rests on
   the existing relationship (legitimate interest), provided every mail
   carries a working unsubscribe link and the first mailing after import says
   where the address came from. Every imported row records its provenance
   (`source = "import_2026"`, import date) so it stays traceable how anyone
   got on the list.
2. **Agenda and report are composed in the portal** — one document that grows
   from agenda into report, as the board already works, with the activities
   sections pre-filled from the `activities` domain. Detailed 14 September
   2026 — the agenda is *prepared deterministically*, section by section:
   - **evaluation**: the activities between the previous meeting and this
     one, from the platform — plus manual additions for something that was
     not on the portal's calendar;
   - **upcoming**: the activities of the coming months, same source;
   - **members**: the new members since the previous meeting, with their
     steward assignment;
   - **ideas**: textual, carried over between meetings (the brainstorm);
   - **miscellaneous**: free — anyone can raise something.
   No LLM anywhere in this preparation: it is queries and carry-over. The
   newsletter concept (§6) is the only AI goal in this CR.
3. **The meeting module is board-only.** Back-office, **desktop-only** — no
   public side, no plan whatsoever toward a member-facing view. Refined
   14 September 2026: the meeting circle is wider than "the board" — it
   includes fixed participants who are not called board members and the
   branch supporter from Raak national, **who is not even a member**. The
   recipient list is therefore its own maintained list, not a query over
   membership or roles.
4. **The portal sends the meeting mails itself**: agenda mail and report mail
   to the ~28 board members, the document rendered as PDF attachment, plus
   freely added extra attachments (a working-group report, a municipal
   document, …).
5. **The report's source is what an admin types during the meeting.** Not
   an uploaded document, not speech — no STT anywhere in this chain; the
   `stt` domain stays untouched.
6. **Single editor.** One person types during the meeting (the secretary
   model) — no concurrent editing, which keeps M1 well clear of A17's
   simultaneous-edit machinery.
7. **The meeting module is built separately and first; the newsletter chain
   follows.** The newsletter draws its input from what the meeting track
   produces: the agenda's activity data, media, positive evaluation notes
   from the report, and items the report explicitly marks as newsletter
   material — so meetings must exist before drafting can.

Inherited, not reopened:

- **CR-05 (17 June 2026):** consent model, `Subscriber`, double opt-in for
  public signups, EU ESP behind an `EmailCampaignProvider` adapter, Gmail SMTP
  stays transactional-only, phases 0–4.
- **CR-07 §4.1 (13 September 2026):** drafting is an acting capability pack on
  the conversation kernel. Three rules fixed: **drafting is not sending** (a
  person confirms anything outward), **one write path** (the pack reuses the
  owning domain's write path), **injection weighs heavier with acting tools**
  (the confirmation step is the brake). A capability pack holds no business
  logic; when something is missing, the owning domain's facade grows.
- **#785 triage A17:** the AI-per-module contract — read / propose / execute
  separated, verifiable confirmation.

## 4. The chain, end to end

```
activities domain ──► agenda (pre-filled) ──► meeting (typed notes) ──► report
                                                        │
                                                        ▼
                                        drafting pack (LLM, concepts only)
                                                        │
                                              ┌─────────┴─────────┐
                                              ▼                   ▼
                                     monthly member NL     half-yearly NL
                                              │                   │
                                              ▼                   ▼
                                   communication domain: audience + send (ESP)
```

Two mail paths, deliberately different:

| Mail | Audience | Path | Why |
|---|---|---|---|
| Agenda / report mail | ~28 board members | `mail` domain (Gmail SMTP), PDF + extra attachments | one-to-few, operational, attachment-heavy — transactional in nature |
| Newsletters | members (auto) and/or subscribers | `communication` domain via the ESP adapter | campaigns need unsubscribe headers, bounce handling, deliverability — CR-05's whole argument |

## 5. Data model (sketch — to be settled with the open questions)

New domain `meetings`:

- `Meeting` — `id`, `meeting_date`, `status` (`agenda` → `report` → `sent`),
  `location`, attendance (present / excused, referencing meeting
  participants), timestamps for the agenda mail and report mail.
- `MeetingItem` — `id`, `meeting_id`, `section` (evaluation / upcoming /
  members / ideas / misc), `position`, optional `activity_id` FK, `title`
  (free for non-activity items), `notes` (the bullets, rich-ish text),
  `carried_over_from` (optional self-reference: an ideas/misc item that moves
  to the next meeting), and a **newsletter marker** — during the meeting an
  item (or a note) can be flagged "for the newsletter", the portal form of
  what the board already does in prose ("X adds the choir call to the
  newsletter").
- `MeetingAttachment` — link to a `media` file, per meeting, flagged
  agenda-mail / report-mail / both.
- `MeetingParticipant` — the meeting circle (~28 people): name, e-mail,
  active flag, optional soft link to `Person`. Its own list because the
  circle includes non-members (decision §3.3); it drives both the mail
  recipients and the present/excused picker.

`communication` domain: exactly CR-05's model (`Subscriber` with status,
tokens, consent fields), plus the import provenance of decision §3.1. Nothing
is redesigned here.

The **report is data, not a blob**: sections and items are rows, so the
drafting pack can receive structured, maskable input and the next agenda can
be generated (upcoming activities + carried-over items) instead of copied.

## 6. The drafting pack and the PII boundary

The pack's job: produce a Dutch (nl-BE) newsletter concept from structured
meeting + activity data — the monthly member edition and the half-yearly
public edition are two prompts over the same source, differing in audience,
tone and which activities qualify (the half-yearly takes public activities
only).

Its input, named by Koen (14 September 2026): the agenda's activity data
(upcoming, with date/price/location/registration link), media (flyers,
photos), positive evaluation notes from the report, and the items flagged
"for the newsletter" (§5). **The flag is also the PII gate**: unflagged
report content — attendance, action items, internal discussion — never
enters an LLM payload; what is flagged is written to be public and passes a
human editor anyway.

The boundary CR-05 and CR-07 both draw: **the LLM never sees the subscriber
list, recipient PII, or member data.** New and specific to this CR: the
meeting notes themselves contain first names — guides, helpers, action-item
owners ("Herman guides the walk", "X books the room"). Names of volunteers in
a newsletter are sometimes *wanted* (thanking helpers is part of the genre),
but the default at the LLM boundary follows the standing masking rule:
**identity out, measurement in**. How wanted names re-enter the draft is open
question §10.4.

Structured fields win over free text (the chatbot's grounding rule); the
model may not invent facts, prices or dates. The draft lands in an editor —
never in an outbox.

## 7. Phasing (each phase shippable)

The order interleaves this CR with CR-05's phases — CR-05 phase 0/1/2 are
built here, unchanged, as steps of this chain:

| Phase | Scope | Builds on | AI? |
|---|---|---|---|
| **M1 — Meeting module** | `meetings` domain: compose agenda (pre-filled from activities), fill in during meeting, report; PDF render; board mail with attachments via `mail` domain | activities, mail, media | No |
| **S0 — Subscriber core** | CR-05 phase 0: `Subscriber` + double opt-in + unsubscribe pages **+ the one-off import of the ~800 with provenance** | CR-05 as decided | No |
| **S1 — ESP adapter** | CR-05 phase 1: `EmailCampaignProvider` + provider choice (§10.6: ListMonk vs Brevo) | S0 | No |
| **S2 — Compose & send** | CR-05 phase 2: admin compose, audience build (members auto + subscribers), send, archive | S1 | No |
| **D1 — Drafting pack** | LLM concept button on the compose screen, sourced from meeting + activity data, per §6 | M1 + S2 + CR-07 kernel | Yes |

M1 and S0 are independent and can run in either order or in parallel; D1 is
deliberately last — it needs both a source (M1) and a destination (S2) to be
more than a demo.

## 8. Test set — what the build must reproduce

From the real examples of §1, anonymised:

1. **Generate the agenda of a monthly meeting** from the activities in the
   portal and the previous meeting's carried-over items — structurally equal
   to the real September agenda (same sections, same activity lines).
2. **Fill in the report during a meeting** — attendance, notes per item,
   action items — and send it the same evening with the PDF plus one extra
   attachment (the working-group scenario).
3. **Draft the monthly member newsletter** from that report: intro around the
   next headline activity, "in de kijker", two-month calendar, outlook,
   external events — recognisably the September edition's shape, with every
   date/price/link coming from structured data.
4. **Draft the half-yearly edition** from the same source: public activities
   only, promotional tone — the July edition's shape.
5. **Unsubscribe works end to end** on an imported address: link in the mail,
   token page, status flip, excluded from the next audience build.

## 9. GDPR / compliance (additions to CR-05's checklist)

- [ ] Import with provenance: `source`, import date, and the lawful-basis note
      recorded per imported row.
- [ ] First mailing after import names where the address comes from, next to
      the unsubscribe link.
- [ ] Every campaign mail: unsubscribe link + `List-Unsubscribe` header (ESP).
- [ ] Board mail path stays out of the campaign machinery — no unsubscribe on
      operational board mail, per CR-05's transactional/marketing distinction.
- [ ] Meeting reports contain personal data (names, attendance) — board-only
      access, and they stay out of every LLM payload per §6.
- [ ] No subscriber list, recipient PII or member data to the LLM — inherited,
      re-stated because this CR is where it first becomes load-bearing.

## 10. Open questions

1. ~~Live editing during the meeting~~ — **settled 14 September 2026: one
   person types** (decision §3.6).
2. **Action items.** Keep them as text in the notes (as today), or structure
   them (owner + text + open/done, carried to the next agenda automatically)?
   Structured is more build and more value — the agenda could open with
   outstanding actions.
3. **Attendance.** Free text (as today) or picked from the
   `MeetingParticipant` list (§5)? Picking gives S2/D1 nothing (attendance
   never leaves the board), so this is purely a meeting-module ergonomics
   question.
4. **Names in newsletter drafts.** The masking default strips volunteer names
   from LLM input. Is a newsletter that thanks helpers by name a case the
   board wants — and if so, does the person's name enter during human editing
   (simplest, compliant), or does the pack need a whitelisted "public names"
   field per item?
5. **The monthly member newsletter's sending path.** CR-05 auto-subscribes
   members with per-member opt-out. Confirm that from S2 on, the member
   edition also goes through the ESP (not Gmail), so the opt-out is real.
6. **ESP choice: ListMonk (self-hosted, EU infra) vs Brevo (FR, SaaS).**
   The exploratory cloud session "ListMonk voor nieuwsbriefmodule" exists;
   Europe First requires the trade-off to be made explicitly. The adapter
   makes it reversible; S1 is where it must be decided.
7. **Import mechanics.** The ~800 live in Gmail (contacts / historical Bcc
   lists, duplicates and dead addresses included). One-off CSV export cleaned
   by hand, or a small import screen with dedup? And who owns the cleaning?
8. **The half-yearly audience vs the member list.** Are members part of the
   ~800, or disjoint? This decides whether the audience builder needs
   segments (member edition / public edition) or two simple lists with dedup
   at send time.
9. **PDF rendering.** The meeting PDF replaces a Google-Docs export the board
   is used to. Is a clean, portal-styled PDF acceptable from day one, or must
   it resemble the current template (logo header, table layout)?
10. **Steward assignment for new members.** The members section lists new
    members with their steward ("wijkmeester"). `Member` already carries a
    `board_member_id`. Does the meeting screen only *show* the assignment
    (read-only, link to the member screen), or is the meeting the place where
    it is *made*? The latter is a write into the membership domain from the
    meeting module — possible through the facade, but it must be deliberate.

## Non-goals

- No speech-to-text anywhere in the chain (decision §3.5).
- No member-facing meeting screens (decision §3.3).
- No revision of CR-05's consent model, entity or phase content.
- No auto-sending: every outward mail is confirmed by a person (CR-07 rule).
- No general document management; attachments are per-meeting files.

## Relationship to existing work

- **Builds** CR-05 phases 0–2 as steps S0–S2, unchanged in content.
- **First acting capability pack** on the CR-07 kernel (§4.1's three rules).
- **Reads** the `activities` domain through its facade; the meeting module
  never duplicates activity data, it references it.
- **Uses** the `mail` domain for board mail and the `media` domain for
  attachments; the `stt` domain is explicitly not involved.

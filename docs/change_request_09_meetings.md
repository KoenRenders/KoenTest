# Change Request 09 — Meetings in the portal

**Project:** Web Portal "Raak Millegem"
**Status:** Shaped with Koen on 14 September 2026 (handover on #258). All
scope decisions are settled; no open questions remain on the meeting side.
Not assigned to a release.
**Apply to:** a new `meetings` domain (backend + admin screens). Board mail
goes through the existing `mail` domain; attachments through `media`.
**Split note (14 September 2026):** this CR covers the **meeting module
only**. The newsletter — which consumes meeting output as *one* of its
inputs, next to activities and media — lives in
[`change_request_05_newsletter.md`](change_request_05_newsletter.md), updated
the same day. The original draft covered both as one chain; Koen split them.

---

## Goal

The board runs the association through a monthly meeting: an **agenda** goes
out the day before, gets filled in during the meeting, and returns as the
**report** the day after. Today that lives in Google Docs and Gmail. This
change request moves it into the portal:

1. **Meetings are composed in the portal** — the agenda prepared
   deterministically from data the portal already holds, the report the same
   document filled in during the meeting.
2. **The portal sends the meeting mails** — agenda and report as PDF to the
   meeting circle, with ad-hoc extra attachments.
3. **The newsletter composer reads the report afterwards** and picks what
   goes to the newsletter in the compose screen (CR-05) — the meeting module
   itself carries no newsletter machinery. Nothing of the report leaves this
   module except what that person selects there.

## 1. The source material (measured, 14 September 2026)

Read from the real meeting cycle of 3 September 2026 (agenda and report; the
examples hold personal data and stay in Koen's Nextcloud project folder —
none of it enters this repository).

Agenda and report are **one document**. Fixed structure: a header (date,
present, excused) and five sections — *evaluation of past activities*,
*upcoming activities*, *members* (new members with their neighbourhood
steward), *programme ideas*, *miscellaneous*. Activities appear as one line
(name | date time location) with nested bullets: evaluation notes, counts
("172 tickets sold", "4 walkers"), and action items with a first name on
them ("X books the room"). The agenda is the same list with the bullets
still empty, plus whatever carried over. Sent the evening before; the report
the evening after; ~28 recipients, from a personal Gmail account.

## 2. What exists to build on

| | measured |
|---|---|
| Activities | the `activities` domain holds name, date, location, price, registration link and occupancy — the agenda's activity sections are a query, not typing |
| Board mail | `mail` domain + Gmail SMTP — one-to-few operational mail with attachments is exactly what it is for |
| Attachments | the `media` domain stores uploaded files |
| New members | the membership data knows who joined since a given date, and `Member` carries the steward (`board_member_id`) |
| Organisation | `Organization` exists in MDM (#924); a person↔organisation relation does not yet — this CR adds it (decision §3.11) |
| STT | a `stt` domain exists but is **out of scope** — decided 14 September 2026: the report is typed, never transcribed |

## 3. Decisions

Taken by Koen on 14 September 2026, in the CR-shaping conversation:

1. **Agenda and report are composed in the portal** — one document that
   grows from agenda into report, as the board already works. The agenda is
   *prepared deterministically*, section by section:
   - **evaluation**: the activities between the previous meeting and this
     one, from the platform — plus manual additions for something that was
     not on the portal's calendar;
   - **upcoming**: **all** planned future activities, however far ahead,
     same source (decision §3.14);
   - **members**: the new members since the previous meeting, with their
     steward assignment;
   - **ideas**: textual, carried over between meetings (the brainstorm);
   - **miscellaneous**: free — anyone can raise something.
   No LLM anywhere in this preparation: it is queries and carry-over.
   Drafting AI exists only on the newsletter side (CR-05).
2. **The meeting module is board-only.** Back-office, **desktop-only** — no
   public side, no plan whatsoever toward a member-facing view. The meeting
   circle is wider than "the board": it includes fixed participants who are
   not called board members and the branch supporter from Raak national,
   **who is not even a member**. The circle is therefore never a query over
   membership or roles — it is modelled as **persons in relation to the
   organisation** (decision §3.11).
3. **The portal sends the meeting mails itself**: agenda mail and report
   mail to the ~28-person circle, the document rendered as PDF attachment,
   plus freely added extra attachments (a working-group report, a municipal
   document, …).
4. **The report's source is what an admin types during the meeting.** Not an
   uploaded document, not speech — no STT anywhere in this chain; the `stt`
   domain stays untouched.
5. **Single editor.** One person types during the meeting (the secretary
   model) — no concurrent editing.
6. **Action items stay free text inside the notes**, as today — no
   structured owner/status tracking. Only ideas/misc items carry over
   between meetings (§4); everything else is retyped or dropped by the
   person preparing the agenda.
7. **Attendance is ticked off from the participant list** (present /
   excused), not typed.
8. **The meeting PDF is a clean portal-styled document** (logo, header with
   date and attendance) — no mimicry of the current Google-Docs template.
9. **Steward assignment is only noted in the report.** The actual change is
   made in Raak national's administration programme and comes back through
   the existing MDM import. The portal changes nothing itself.
10. **The meeting module is built separately and first; the newsletter chain
    follows** (CR-05). The newsletter draws on what this module produces —
    flagged report items next to activity data and media — so meetings must
    exist before newsletter drafting can.

Decided later the same day (14 September 2026), while PR #932 ran:

11. **The meeting circle is a person↔organisation relation in MDM**, not a
    standalone list. A new generic link following the `MemberPerson`
    pattern — person, organisation, relation-type code, begin/end date —
    with `BOARD_MEETING` as its first code (English identifier, Dutch
    label, per the #779 pattern). The circle is the persons with an active
    `BOARD_MEETING` relation to Raak Millegem; their e-mail address comes
    from `ContactDetail`. The branch supporter is created once as a
    `Person` without membership. First fill: link the ~28 people (most
    already exist as members), each with an e-mail contact detail. One
    place per fact: persons and their contact details already live in MDM;
    only the relation was missing.
12. **A human reads, then sends.** The agenda mail and the report mail
    (with their attachments) never leave automatically: someone reviews
    the document — PDF preview and attachment list next to the send
    button — and sends deliberately. The same brake as "drafting is not
    sending", here without any AI involved.
13. **One mail, the whole circle in the To line.** The circle knows each
    other and replies-all (the report mail is a reply to the agenda mail
    today). Deliberately the opposite of the newsletter's per-recipient
    campaign path; no Bcc, no unsubscribe machinery.
14. **"Upcoming activities" has no time window.** It lists everything
    planned, however far out — booking a venue a year ahead is a normal
    agenda point. Evaluation covers what *started* since the previous
    meeting, running activities included (the photo hunt sat under
    evaluation while it ran). The secretary curates: manual additions for
    off-portal items, and far-out items with nothing to discuss can be
    left off this month's agenda.

Added after the first mockup round (14 September 2026, Koen's review):

15. **Loose one-off e-mail addresses on a meeting mail.** A guest speaker
    who comes once is not created as a `Person`: their address is added to
    that mail only (in the To line like everyone else), stored with the
    meeting so the report mail can reuse it, and gone afterwards. The fixed
    circle stays the organisation relation of §3.11.
16. **No PDF preview pane — a download is the control step.** Before
    sending, the secretary downloads the generated PDF and checks it; the
    PDF is regenerated at send time so what is checked is what goes out.
    This sharpens §3.12: the human review happens on the real artefact.
17. **Sections are per meeting, extensible.** Besides the five standard
    sections, the secretary can add a named section block ("Jaarplanning
    2027") to agenda a big topic and notulate its discussion. Standard
    sections keep their generation and carry-over semantics; a custom
    section holds free items only. **Miscellaneous is always the last
    section** — a custom section inserts before it (refined 14 September
    2026). Adding sections — like adding items and attachments — works
    identically while preparing the agenda and while taking minutes:
    agenda and report are one document in two statuses.

18. **No newsletter flag during the meeting** (revises §3.10's flag idea,
    same day). Selecting what reaches the newsletter is the newsletter
    composer's call, made afterwards in the compose screen — not the
    secretary's call mid-meeting. The privacy gate moves with it and holds:
    only what the composer explicitly selects from a report can enter an
    LLM payload (CR-05); everything unselected never leaves the meeting
    module.
19. **Chronological insertion.** In the activity sections, items order by
    activity date — a point added during the meeting slides into its
    chronological place, also in between existing points. Free items
    without a date go at the end and can be repositioned by hand.

Inherited, not reopened: **#785 triage A17** — the AI-per-module contract
(read / propose / execute separated). This module has no AI at all, which is
the simplest way to honour it.

## 4. Data model (sketch)

New domain `meetings`:

- `Meeting` — `id`, `meeting_date`, `status` (`agenda` → `report` → `sent`),
  `location`, attendance (present / excused, referencing meeting
  participants), timestamps for the agenda mail and report mail.
- `MeetingSection` — the sections of one meeting: the five standard kinds
  (evaluation / upcoming / members / ideas / misc) seeded at agenda
  generation, plus manually added named sections (decision §3.17). Carries
  `kind` (standard code or `custom`), `title`, `position`.
- `MeetingItem` — `id`, `meeting_id`, `section_id` (FK to
  `MeetingSection`), `position`, optional `activity_id` FK, `title`
  (free for non-activity items), `notes` (the bullets, rich-ish text),
  `carried_over_from` (optional self-reference: an ideas/misc item that
  moves to the next meeting). No newsletter marker (decision §3.18): the
  newsletter side reads the report through the facade and the composer
  selects there.
- `MeetingAttachment` — link to a `media` file, per meeting, flagged
  agenda-mail / report-mail / both.
- Extra recipients (decision §3.15): per meeting, plain e-mail strings for
  one-off guests — no `Person`, no relation.
- The meeting circle lives in **MDM, not here** (decision §3.11): a new
  generic person↔organisation relation (person, organisation, relation-type
  code — first code `BOARD_MEETING` — begin/end date), following the
  `MemberPerson` pattern. The circle is the persons with an active
  `BOARD_MEETING` relation; e-mail from `ContactDetail`; ending a relation
  end-dates it, so the attendance history of old reports stays intact.
  Attendance on `Meeting` references `Person`. The `meetings` domain reads
  the circle through the MDM facade.

The **report is data, not a blob**: sections and items are rows, so the next
agenda can be generated (upcoming activities + carried-over items) instead
of copied, and the newsletter flag can select items instead of prose.

## 5. Privacy

Meeting reports are personal data: attendance, first names in notes, who
does what. Board-only access, desktop screens behind the existing admin
auth. **No LLM sees report content** — the only thing that leaves this
module is what a human explicitly flagged for the newsletter, and the
masking rules for that live where the LLM lives: CR-05.

The board mail path stays out of any campaign machinery: operational mail to
a known circle, no unsubscribe link — per CR-05's transactional/marketing
distinction.

## 6. Phasing

One phase, shippable on its own: the `meetings` domain with agenda
preparation, report editing, PDF render, and the two mails with attachments —
plus the small MDM addition it stands on: the person↔organisation relation
and its `BOARD_MEETING` code (decision §3.11), one migration.
(In the original combined draft this was "M1"; the newsletter phases live in
CR-05.)

Before building: none of this blocks on CR-05, and nothing in CR-05 blocks
on anything here except the newsletter flag existing.

## 7. Test set — what the build must reproduce

From the real September 2026 cycle, anonymised:

1. **Generate the agenda of a monthly meeting** from the activities in the
   portal and the previous meeting's carried-over items — structurally equal
   to the real September agenda (same sections, same activity lines),
   including one manually added activity that was not on the portal's
   calendar.
2. **Fill in the report during a meeting** — attendance ticked from the
   participant list, notes per item, one activity added mid-meeting that
   slots in chronologically — and send it the same evening — one mail, the whole circle in the To
   line — with the PDF plus one extra attachment (the working-group
   scenario).
3. **The next agenda carries over** the ideas/misc items of this one.

## Non-goals

- No speech-to-text anywhere (decision §3.4).
- No member-facing meeting screens (decision §3.2).
- No AI in the meeting module — drafting lives in CR-05.
- No structured action-item tracking (decision §3.6).
- No writes into the membership domain (decision §3.9).
- No general document management; attachments are per-meeting files.

## Relationship to existing work

- **Feeds** [`change_request_05_newsletter.md`](change_request_05_newsletter.md):
  the newsletter compose screen reads reports through this domain's facade;
  the composer selects there (decision §3.18).
- **Reads** the `activities` domain through its facade; the meeting module
  never duplicates activity data, it references it.
- **Uses** the `mail` domain for the meeting mails and the `media` domain
  for attachments; the `stt` domain is explicitly not involved.

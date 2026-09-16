# Change Request 05 — Newsletter

**Project:** Web Portal "Raak Millegem"
**Status:** Being shaped with Koen. First decided 17 June 2026 (consent model,
`Subscriber`, provider adapter); reshaped on 14, 15 and 16 September 2026
alongside the meeting module (CR-09). **Not assigned to a release** — Koen
expects v2.6 but has not decided (16 September 2026). Two questions are still
open, see §8.
**Apply to:** a new `newsletter` domain (backend, admin screens, public signup
pages). Mail goes through the existing `mail` domain; the member audience comes
from `membership` and `mdm` through their `api.py`.
**History:** this document was rewritten on 16 September 2026 into one
consistent text. Until then a dated update layer sat on top of the June text
and contradicted it in three places: whether members can unsubscribe, which
service sends, and which blocks the compose screen has. Where a decision
reverses an earlier one, the earlier one is named at the decision itself.

---

## Goal

Raak Millegem sends two kinds of newsletter today, both by hand from a personal
Gmail account:

- a **monthly letter to the members**;
- a **half-yearly letter to a mailing list of about 800 non-members**.

Both are plain text written in Gmail and sent in Bcc. This change request moves
that into the portal:

1. **The newsletter is written and sent from the portal**, one mail per
   recipient, so an unsubscribe link can work and a To/Bcc mistake can no
   longer happen.
2. **The mailing list lives in the portal**, with a public signup form for new
   people and a working opt-out.
3. **Later, an LLM drafts a concept** from activity data and meeting output.
   A human edits and sends; the model never sees who receives the letter.

---

## 1. The source material (measured)

In `koentest/vergader-nieuwsbrief/input/` in Nextcloud, never in the repo:

| Example | What it shows |
|---|---|
| monthly member letter (June 2026; September 2026) | Running text: an intro, then the activities of the coming weeks, each with a date and a link. Sent from a personal Gmail account. |
| half-yearly letter (*Deze zomer in Millegem*) | The same form, longer, aimed at people who are not members. |
| *Het najaar van Raak* (Raak nationaal, Mailchimp) | One column, a logo, then nine cards: thumbnail, title, two sentences, a *"Schrijf je in!"* button. The footer has the organisation's address and an unsubscribe/preferences link. |

Koen on the third example (16 September 2026): *"was als voorbeeld van wat het
ooit kan worden, momenteel sturen we simpelweg een tekstuele via gmail."* It
shows a **direction**, not the scope of the first release (§3.10).

## 2. What exists to build on

- **The mail transport** (`mail` domain): Gmail SMTP, one log row per recipient
  in `email_log`, a `log_only` mode for demo tenants. It has **no daily quota**
  and no queue yet.
- **The WYSIWYG editor** (Trix) and its sanitiser (`cms/render.py`), in use in
  the meeting notes. It already supports bold, italic, headings, lists, quotes
  and links, and blocks file uploads.
- **The membership rule**: `membership.api.members_with_membership_for_year`
  answers which households hold a membership covering a given year. The
  member count in the meeting report already uses it.
- **Person e-mail addresses** in `mdm` (contact details), used by the meeting
  circle.
- **Tenant settings** (`kernel_tenant_settings`) for per-association values,
  such as the meeting mail signature.
- **Background jobs** (`JOBS_ENABLED`) to run a sending queue.

---

## 3. Decisions

### Audience and consent

1. **Subscription and sending are one system; drafting is another** (17 June
   2026). Subscribers, consent, recipient lists and sending are deterministic
   and contain no AI. The LLM drafting of phase C produces text only: it never
   sees a recipient list or recipient data, and it never sends.
2. **The audience is chosen per letter** (15 September 2026). There are three
   choices at compose time, and **none is pre-selected**, so the choice is
   made rather than inherited:
   - *leden* (members);
   - *niet-leden* (non-members);
   - *allebei* (both), merged and **deduplicated by e-mail address**.

   The two lists overlap: someone on the mailing list who becomes a member
   stays on it. The content differs as well as the audience. A member letter
   mentions things a non-member does not get, such as the member discount, so
   *allebei* is for a letter written for both, never a convenient default.
3. **The member audience is every person with an e-mail address in a household
   whose membership covers the current working year** (16 September 2026).
   Koen: *"ieder lid met een mailadres"* and *"lopende werkjaar, alle
   personen"*.
   - This means every person of the household, not only the main member and
     not only adults.
   - Two people sharing one address get one mail.
   - The working year is the calendar year. The rule is
     `members_with_membership_for_year` from the membership domain, the same
     one the meeting report counts with. The newsletter must not define "a
     member" a second time.
4. **Members cannot unsubscribe** (15 September 2026). This **reverses** the
   decision of 17 June 2026, which gave every newsletter a working
   unsubscribe link, members included. Koen's reasoning: they are members,
   the monthly letter is part of that, and that is how it works today. So a
   member letter has no link and no footer line at all.

   Two objections were put to him. They are recorded because overruling them
   does not make them go away:
   - (a) For direct **marketing**, the GDPR gives an absolute right to object.
     Whether an association's own programme sent to its own members counts as
     marketing is arguable either way, and was not settled here.
   - (b) Bulk mail without a `List-Unsubscribe` header is filtered to spam
     more often. So the risk is not legal but delivery: a member whose letter
     lands in spam does not read it.

   **For non-members nothing changes**: a real, working unsubscribe link is
   mandatory there.
5. **Non-members sign up through a public form with double opt-in** (17 June
   2026; in the first release since 16 September 2026).
   - The form asks for an **e-mail address and an optional first name**,
     nothing else.
   - A confirmation mail carries a link; only a confirmed address receives
     letters.
   - The form shows a *"word lid"* link for people who want more. Family
     details go through the membership flow, never through this form.
   - Every subscriber row stores what was agreed, when, and through which
     source.
6. **The existing list of about 800 addresses is imported, on PROD only**
   (14 and 16 September 2026).
   - The file is plain text with one address per line. Koen: *"het mag enkel
     in PROD geladen worden. Tot dan voorbeeldadressen."*
   - The import is therefore an **upload on an admin screen**, not a script
     or a seed. It shows a preview before it writes: how many addresses are
     new, already known, or invalid. Other environments get `example.org`
     addresses from the seed.
   - The import rests on the existing relationship (legitimate interest), not
     on double opt-in. It is allowed only because every letter to these
     addresses carries a working unsubscribe link, and because the **first
     letter after the import says where the address came from**.
   - Every imported row records its provenance (`source = "import"`, the
     import date).
   - **An import never resubscribes an address that unsubscribed.** Otherwise
     every re-import would undo opt-outs.
   - The two people who already opted out are marked as unsubscribed by hand
     on the subscriber screen after the import.
   - An admin can also add a single address by hand.

### Sending

7. **The portal sends one mail per recipient through Gmail SMTP, queued under
   a daily limit** (14 and 16 September 2026).
   - The account is a **free Gmail account** (Koen, 16 September 2026).
     Google publishes a limit of roughly 500 recipients a day for such an
     account. **Confirm the current figure against Google's documentation
     before building.**
   - **That limit is shared with every other mail the portal sends**:
     registration confirmations, payment instructions, login links, the
     meeting mails. A newsletter that uses the whole quota blocks a
     registration confirmation the same day. The newsletter therefore gets
     its own daily cap **below** the account limit, as a tenant setting with
     a safe default. The rest is headroom.
   - A letter to *allebei* (about 950 addresses) is spread over several days.
     The screen shows how far it has come and when it expects to finish.
   - The queue survives a backend restart and continues where it stopped.
   - Every mail to a non-member carries **its own unsubscribe token** and a
     one-click `List-Unsubscribe` header.
   - Gmail SMTP is the first implementation behind an
     `EmailCampaignProvider` adapter. A European campaign service (Brevo,
     France; or a self-hosted ListMonk) stays a **provider swap, deferred
     until one of these happens**: the daily limit starts to pinch;
     deliverability degrades; bounce handling by hand becomes a burden; or
     Google restricts the account for bulk sending. That last one is a real
     risk for a personal account, which is why it is named.
   - This reverses the 17 June 2026 plan to send newsletters through an ESP
     from the start.
8. **Sender address — open, see §8.1.**
9. **The mail is shown to a human before it goes out** (in line with the
   meeting mails, CR-09 §3.12).
   - The compose screen has a **"send a test to myself"** button, which
     sends the real mail to the signed-in admin.
   - Sending asks for confirmation and repeats the chosen audience and the
     number of addresses.
   - Nothing is ever sent automatically.

### Content

10. **The first release sends a formatted text letter, not a designed
    layout** (16 September 2026).
    - Scope: a subject line and one body in the WYSIWYG editor the meeting
      notes already use (bold, italic, headings, lists, links).
    - The mail gets a simple frame: the association logo at the top, the
      association name and, for non-members, the unsubscribe line at the
      bottom.
    - Koen: *"Als je al zaken nu simpel kan invoeren zonder het complexer te
      maken kan je dat nu zeker al doen."* So there are **two insert helpers**,
      and both only write text into the editor, which the author can then
      change freely:
      - **"Activiteit invoegen"**: a line with the name, date, place and a
        link to the registration page.
      - **"Kalender invoegen"**: the activities of the next two months as a
        list, generated from the same activity data as the agenda of CR-09.
    - The card layout of Raak nationaal (§1) is the direction for a later
      phase: a flyer as thumbnail and a registration button per activity.
    - This replaces the fixed blocks of the 14 September 2026 update: intro,
      *in de kijker*, calendar, outlook, external events.
11. **Meeting report as input — open, see §8.2.**
12. **A newsletter can be copied** (15 September 2026).
    - Subject and body come along. **The audience does not**: you copy
      precisely because you are writing to someone else, so the new draft
      asks again.
    - A sent letter stays exactly as it went out. A copy is a new object.
13. **Sent letters stay in an archive**, with their audience, the number of
    recipients, and per recipient whether and when the mail left. The
    `email_log` row per recipient remains the answer to "did this person get
    it?".

### Scope boundaries

14. **Mailing the people registered for an activity is not a newsletter** (15
    September 2026; timing decided 16 September 2026).
    - It is operational mail about an arrangement people made themselves:
      the departure time moved, bring boots, the payment is still open.
    - It therefore carries **no unsubscribe link**, needs no consent, and
      belongs **with the activity**, per component. The barbecue and the
      cornhole tournament have different participants, and it should also
      be possible to reach a whole activity.
    - It goes to the **contact address of the registration**, because that
      is who made the arrangement.
    - It shares the sending machinery with the newsletter (one mail per
      recipient, queued, logged), but it is **built later, as a separate
      change**, not in the first newsletter release.
15. **Drafting is the first acting capability pack on the CR-07 kernel**
    (14 September 2026; phase C).
    - The kernel's rules apply: drafting is not sending, there is one write
      path, and prompt injection weighs heavier once tools can act.
    - Its input is activity data (date, price, place, registration link),
      media (flyers), and meeting report items once §8.2 is settled.
    - **The model never detects activities in prose.** A meeting item
      carries the `activity_id` set when the agenda was generated, so the
      pack fetches the activity data fresh, and those structured fields win
      over whatever the note's text says. This is the same grounding rule the
      chatbot follows.
    - **No recipient data ever enters an LLM payload.**

---

## 4. Data model (sketch)

A new schema `newsletter`. Following the repo's rules: no cross-schema foreign
keys (soft references instead), `TenantMixin`, soft delete, English names.

`newsletter.subscribers`, for **non-members only** (members are derived, never
stored; decision §3.3):

- `email` (unique per tenant), `first_name` (optional)
- `status`: `pending` → `confirmed` → `unsubscribed`
- `source`: `public_form`, `import` or `admin`
- `consented_at`, `confirmed_at`, `unsubscribed_at`, `imported_at`
- `confirm_token`, `unsubscribe_token`
- `person_id`: an optional soft reference, set when the subscriber turns out
  to be a known person. It is not a foreign key, so it survives the person
  being deleted.

`newsletter.newsletters`, one per letter:

- `subject`, `body_html` (sanitised)
- `audience`: `members`, `non_members` or `both`. It is empty in a draft and
  required to send.
- `status`: `draft` → `sending` → `sent`
- `copied_from_id`; `created_by`; `sent_started_at`; `sent_finished_at`

`newsletter.deliveries`, the queue and the archive in one table, one row per
recipient, written when sending starts:

- `newsletter_id`, `email`
- `kind`: `member` or `subscriber`. It decides whether an unsubscribe link is
  added.
- `subscriber_id` (only for `subscriber`)
- `status`: `queued` → `sent` / `failed` / `skipped`; `sent_at`, `error`

The recipient list is fixed when sending starts. Someone who joins or
unsubscribes during a multi-day send is handled at the moment their own mail
leaves: an address that unsubscribed in the meantime is `skipped`.

## 5. Privacy / GDPR checklist

- [ ] Lawful basis written down per audience: members = membership (decision
      §3.4, with its objections); imported non-members = legitimate interest
      with a working opt-out; new non-members = consent through double
      opt-in.
- [ ] Double opt-in for the public form, with the consent record stored.
- [ ] Unsubscribe link plus one-click `List-Unsubscribe` header on every mail
      to a non-member.
- [ ] The first letter after the import says where the address came from.
- [ ] An import never resubscribes an unsubscribed address.
- [ ] Data minimisation: an e-mail address and an optional first name; no
      family data.
- [ ] Right to erasure: deleting a subscriber removes the row and anonymises
      its deliveries.
- [ ] The import file never reaches the repo or any environment other than
      PROD.
- [ ] Privacy statement updated (newsletter, import, retention).
- [ ] No recipient data in any LLM payload (phase C).

## 6. Phasing

| Phase | Scope | AI? |
|---|---|---|
| **A** (first release) | Subscribers, public signup with double opt-in, unsubscribe page, import upload, manual add; compose (editor plus the two insert helpers), test mail, send per recipient in a queue under the daily cap; copy; archive. | No |
| **B** | Mail to the registrants of an activity or component (decision §3.14), on the same sending machinery. | No |
| **C** | Drafting with an LLM on the CR-07 kernel (decision §3.15). | Yes |
| **D** | Card layout following Raak nationaal: flyer, title, teaser, registration button. | No |
| **E** | Provider swap to an EU campaign service, only when a trigger from §3.7 fires. | No |

## 7. Test set — what phase A must prove

1. The member audience is exactly the people with an address in households
   with a membership for the current year. A household whose membership
   covers only last year is left out, a child with its own address is
   included, and a shared address appears once.
2. *allebei* deduplicates across members and subscribers.
3. A letter cannot be sent without an explicitly chosen audience, and a copy
   comes without one.
4. A mail to a subscriber carries its own unsubscribe token and a
   `List-Unsubscribe` header; a member mail carries neither.
5. The unsubscribe link works end to end on an imported address, without a
   login.
6. Double opt-in: an unconfirmed address receives nothing; the confirmation
   link confirms exactly one row.
7. The import skips invalid lines, reports duplicates, and never
   resubscribes an unsubscribed address.
8. A send of about 950 recipients with a daily cap below that spreads over
   several days, resumes after a restart without sending anyone a second
   time, and never goes above the cap.
9. An address that unsubscribes during a running send is skipped.
10. The test mail goes only to the signed-in admin and does not change the
    letter's status.

---

## 8. Open questions

1. **Which account sends the newsletter?** Today Koen sends from a personal
   Gmail account. The portal already sends everything else through the
   Gmail account configured for the association, with Reply-To set to the
   admin who sends (CR-09 §3.24).
   **Recommendation:** use that same association account for the newsletter,
   not a personal account. A personal password in the portal ties the
   association to one person, and a Google block on that account would also
   hit that personal mailbox. If the association account is also a free Gmail
   account, the limit and risk of §3.7 apply to it.
2. **Does the compose screen offer items from the meeting report?** The
   14 September 2026 update planned a panel in which the author picks report
   items to include. With a plain text letter, the author can already copy
   whatever is needed from the report. The selection matters most as a privacy
   gate for the LLM, which is phase C.
   **Recommendation:** move this panel to phase C instead of building it in
   phase A.

---

## Non-goals

- No family data at newsletter signup; that is the membership flow.
- No mail to a non-member without an unsubscribe link.
- No LLM access to recipient lists or recipient data.
- No self-hosted mail server.
- No general CRM; this stays a newsletter tool.
- No segmentation or profiling of members.

## Relationship to existing work

- **CR-09 (meetings):** a meeting item carries its `activity_id`, which
  grounds the drafting of phase C. The sending pattern (a human reads first,
  Reply-To the sender) is the same.
- **CR-07 (AI kernel):** phase C is its first acting capability pack.
- **`mail` domain:** the transport, the log, and the `log_only` mode. The
  queue and the daily cap are new and belong there, because the registrant
  mail of phase B needs them too.
- **`membership` / `mdm`:** the member audience, through their `api.py`.

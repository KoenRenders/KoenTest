# Change Request 05 — Newsletter

**Project:** Web Portal "Raak Millegem"
**Status:** Being shaped with Koen. First decided 17 June 2026 (consent model,
`Subscriber`, provider adapter); reshaped on 14, 15 and 16 September 2026
alongside the meeting module (CR-09). **Not assigned to a release** — Koen
expects v2.6 but has not decided (16 September 2026). No question is open:
all were answered on 16 and 17 September 2026 (§8). The document is ready to
build once the newsletter is assigned to a release.
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
3. **Raakje drafts the letter.** From the activities and meeting points the
   author picks, the back-office assistant writes a proposal in seconds. A
   human edits and sends; the model never sees who receives the letter. This
   is the point of the whole change, not an extra (Koen, 16 September 2026).

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
- **The public Raakje's activity tools** (`chatbot/tools.py`):
  `get_activities` and `get_activity_detail` return public activity data,
  including dates, prices and the flyer text with its AI addition
  (`ChatbotInfo.effective_text`). A field contract already limits what those
  results may carry to the model.
- **Photo albums per activity** at `/activiteiten/{key}/fotos` (`media`).
- **Raakje in the back office** (CR-07, `reporting/assistant.py`) on the AI
  kernel in `chatbot/`: the Mistral provider (EU), budgets, a payload log, and
  the **seam guard** (`chatbot/seam.py`). That guard refuses any outbound
  payload that contains a known person name, an e-mail address, a phone number
  or an IBAN. Today Raakje only answers reporting questions; drafting is its
  first *acting* capability (CR-07 §4.1). `reporting/assistant.py` already
  has the **name scrubber** that replaces a typed name with a token before
  anything leaves.
- **The editor exists in four templates, without a shared macro**: the page
  editor (`admin_pagina.html`, `_cp_detail.html`) and the meeting notes
  (`admin_vergadering.html`, `_vg_punt.html`).

---

## 3. Decisions

### Audience and consent

1. **Subscription and sending are one system; drafting is another** (17 June
   2026). Subscribers, consent, recipient lists and sending are deterministic
   and contain no AI. Raakje's drafting (§3.15) produces text only: it never
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
     **The exact limit is uncertain, and this design does not depend on
     it.** What we know:
     - Google's published figures for free accounts are in the order of 500
       a day, but they differ between the web interface and SMTP, and
       between counting messages and counting recipients.
     - The half-yearly letter used to leave from this account **in one day,
       as 4 mails with all ~800 addresses in Bcc** (Koen). So roughly 800
       recipients in one day was accepted, through the web interface.
     - One mail per recipient is 800 *messages* instead of 4. If Google
       counts messages, that is a different load from what was accepted
       before.
     - Therefore: the cap is a tenant setting with a conservative default,
       and **the queue reads Gmail's own answer**. On the "daily sending
       quota exceeded" error it stops, marks nothing as failed, and resumes
       the next day. A wrong estimate then costs a day, not a pile of failed
       deliveries. The first real send tells us the actual figure, and the
       cap is adjusted to it.
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
8. **The newsletter leaves the way a registration confirmation does** (Koen,
   16 September 2026). Technically it goes through the Gmail account the
   portal logs in with (`gmail_user`, today Koen's own free account); the
   recipient sees the association's address as sender (`gmail_from`). No new
   account, no new setting.

   **Replies go to the association by default, and the sender may choose**
   (Koen, 16 September 2026). The send dialog offers *antwoorden naar de
   vereniging* (pre-selected) or *antwoorden naar mezelf*. The association
   address is the sender address from the tenant configuration
   (`gmail_from`; Koen, 16 September 2026), so *antwoorden naar de
   vereniging* simply means replies go to the address the mail came from.
   No new setting. (The organisation also carries an e-mail contact on
   `/admin/organisaties`; the newsletter does not read it.) This differs from the meeting mails, whose
   replies go to the secretary (CR-09 §3.24): a board mail is a conversation
   between people, a newsletter speaks for the association.
   Consequence, accepted with the choice: the daily limit of §3.7 is that
   account's limit, shared with every other portal mail, and a Google
   restriction for bulk sending would also hit that personal mailbox. That is
   one of the named triggers for the provider swap.
9. **The mail is shown to a human before it goes out** (in line with the
   meeting mails, CR-09 §3.12).
   - The compose screen has a **"send a test to myself"** button, which
     sends the real mail to the signed-in admin.
   - Sending asks for confirmation. The dialog repeats the chosen audience
     and the number of addresses, and holds the choice of reply address
     (§3.8).
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
    - **One editor macro first** (Koen, 16 September 2026). The newsletter
      would be the fifth copy of the editor markup, so the build starts with a
      shared `ui.rich_text` macro, with its demo on the design-system page,
      and moves the page editor and the meeting notes onto it. The insert
      helpers use Trix's own insert function; the snippet itself is rendered
      by the server.
    - **The newsletter is not signed with the meeting signature** (Koen, 16
      September 2026: *"We gaan daar wel niet onderzetten 'Tot binnenkort!
      Mon, Steven en Koen'."*). The meeting mail signature of CR-09 §3.26
      stays a board-mail setting. A newsletter closes **without personal
      names**, with the association as sender (*"Het bestuur van Raak
      Millegem"*), built from the organisation's name rather than typed in
      (§8.4).
    - This replaces the fixed blocks of the 14 September 2026 update: intro,
      *in de kijker*, calendar, outlook, external events.
11. **The compose screen offers the points of recent meeting reports** (14
    September 2026; kept in the first release on 16 September 2026, because
    the drafting is in it). The author ticks the points that should come
    along. That selection is the **input gate** for Raakje: a point that is
    not ticked never reaches the model.
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
15. **Raakje drafts the letter, in the first release** (14 September 2026;
    moved into the first release by Koen on 16 September 2026: *"dat is net
    het deel van het opzet. De AI die helpt om snel een nieuwsbrief te
    maken."*).

    **How the author works with it.**
    - The compose screen has a **Raakje panel**: a conversation next to the
      editor. The author picks activities (the same picker as the insert
      helper), ticks meeting points (§3.11), and says what the letter should
      do.
    - The first answer is **the whole letter as a proposal**: subject, a
      short intro, a paragraph per chosen activity or meeting point, and the
      closing of §3.10 (§8.2).
    - After that the conversation works on **pieces** (Koen: *"je moet dus
      stukken kunnen vervangen of stukken invoegen op basis van het
      gesprek"*). "Maak de intro korter", "zet de BBQ er ook bij", or a
      selected passage with "herschrijf dit" produce a proposal to replace,
      insert or remove one piece.
    - **Nothing lands in the editor without a click.** Every proposal is
      shown first, with *Toepassen*; applying goes through the editor's own
      functions, so the editor's undo still works. This is the confirmation
      step the kernel requires for an acting capability.
    - To target pieces, the server hands the model the current text as
      numbered paragraphs, and the model answers with operations on those
      numbers (replace, insert after, remove). A selection in the editor
      becomes the target of the next operation.
    - The conversation is kept with the draft, so the author can continue
      the next day, and is removed when the letter is sent: the sent letter
      is the record, and the payload log already holds what left.

    **What Raakje knows.**
    - **All activities**, through the public Raakje's read tools: dates,
      places, prices, and the flyer text with its AI addition. So the author
      can say "zet de BBQ er ook bij" without picking it first.
    - **The photo album of an activity**, when there is one: Raakje may add a
      link to it ("de foto's van het Comedy Festival staan online").
    - **The ticked meeting points**, including the evaluation of past
      activities. Positive feedback from the meeting may be used to say
      something ("het Comedy Festival was uitverkocht").
    - **The house style** (§8.3) and the last two letters to the same
      audience.

    **Fixed rules.**
    - **Raakje never sends, never sees a recipient list, and never picks the
      audience.** The draft is text in an editor, nothing more. The kernel's
      rules apply: drafting is not sending; there is one write path; prompt
      injection weighs heavier once a tool can act.
    - **The model never writes a date, a time, a place, a registration link or
      a photo link.** It places a marker, and the server replaces the marker
      with a line built from the activity data (the same line the insert
      helper produces). A wrong date or an invented link becomes impossible,
      not merely unlikely.
    - **Every amount in a proposal is checked.** Prices may appear in prose
      ("leden betalen minder"), so they cannot all be markers. The server
      compares every amount in a proposal with the prices of the activities
      involved, and marks an amount it cannot find before the author applies
      the proposal.
    - **The model never detects activities in prose.** A meeting point
      carries the `activity_id` set when the agenda was generated (CR-09 §4);
      a free point without one contributes only its text.
    - **Individual organisers are never thanked, and people from our
      administration are never named** (Koen, 16 September 2026: *"We
      bedanken NOOIT individuele organisatoren."*). This is a rule of the
      association, and the design makes it structural:
      - Names in ticked meeting points, in the typed instruction and in the
        example letters are replaced by the name scrubber before anything
        leaves. The replacement is a neutral placeholder, and **it is never
        turned back into the name**.
      - The house-style prompt states the rule.
      - A proposal that still contains a known person name is marked before
        it can be applied.
      - The seam guard stays on as the last check.
      This replaces the earlier plan of this document to put the names back
      after the model was done.
    - **It uses the same switch as Raakje in the back office**
      (`admin_chat_enabled` plus `ADMIN_CHAT_ENABLED`). With the switch off,
      the panel is not shown and the letter is written by hand; nothing else
      changes. The calls count against the same budgets and land in the same
      payload log.
    - **Provider:** Mistral (EU), as for the rest of Raakje. The mock provider
      gets canned drafts and canned operations, so the whole chain is
      testable without a model.

16. **Raakje invents no facts** (Koen, 16 September 2026: *"hij mag niets
    verzinnen wat hij niet in de data vindt. Wel proza, mooie enthousiaste
    taal. Maar geen feiten bijverzinnen."*).

    **Why a rule in the prompt is not enough.** The public Raakje already has
    one (`chatbot/context.py`: *"verzin NOOIT iets"*) and still invented
    facts in testing: extra games at Brood & Spelen, and a function for a
    board member that the person did not hold (#309). A newsletter goes to
    hundreds of people, so the protection has to be in the design and not in
    the model's goodwill.

    **The division of labour.** Raakje writes the *language*: the
    enthusiasm, the transitions, the order. The *facts* come from the
    sources and nowhere else. The sources are, and are only:
    - the activity data (name, dates, places, prices, components);
    - the flyer text with its AI addition;
    - whether a photo album exists;
    - the ticked meeting points;
    - the instruction the author typed.

    The example letters of §8.3 are **style only**: a fact that appears only
    in an old letter (last year's price, last year's programme) counts as
    invented.

    **Five layers, each catching what the previous one misses.**
    1. **Facts as markers.** Dates, times, places, prices of a named
       component, registration links and photo links are never written by
       the model. It places a marker; the server fills it in from the data
       (§3.15).
    2. **Few sources, stated per call.** The model receives only the sources
       above for the activities and points in play, not the whole calendar
       in one go. The prompt states the rule, and adds that leaving something
       out is always better than filling a gap.
    3. **Deterministic checks on the proposal.** Checks that need no model:
       - every number, amount, time and date word must occur in a source;
       - every function word (voorzitter, secretaris, penningmeester,
         wijkmeester, bestuurslid, organisator, …) must occur in a source;
       - no known person name may appear (§3.15).
       Anything that fails is marked.
    4. **A verification pass.** A second, separate model call receives the
       proposal and the sources, and lists every factual claim with the
       source passage that supports it. A claim without support is marked.
       This is the layer that catches an invented game: *zaklopen* is an
       ordinary Dutch word, so no word list would find it, but it has no
       supporting passage in the flyer text. The verifier is a model too and
       can miss something; that is why it is not the only layer.
    5. **The author decides, per mark.** A marked passage is shown with its
       reason ("staat niet in de flyer", "€ 12 is geen prijs van de BBQ").
       **On *Toepassen*, a marked passage is left out** unless the author
       ticked "klopt, behouden" for it (Koen, 17 September 2026). The safe
       choice costs nothing; keeping an unsupported claim is always a
       deliberate click. Koen called this *"een goed patroon, een
       dubbelcheck in de response van een AI"*: the model's answer is
       checked against the sources before it is used, and what cannot be
       checked does not pass by default.

    **Tested on the failures we know.** The test set keeps the known
    hallucinations as fixed cases with canned model answers: extra games at
    Brood & Spelen, a function attached to a board member, a price from last
    year's letter. Layers 3 and 4 must mark each of them. Before each
    release that touches the drafting, a live run against Mistral goes
    through the same cases, graded by a person, the way the CR-07
    evaluation harness works (`reporting/evaluation.py`).

    **Said plainly:** no mechanism makes free prose free of invented facts
    with certainty. These layers make an invented fact unlikely to get past
    unnoticed, and the author remains the last check before anything is
    applied.

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
- [ ] No recipient data in any LLM payload.
- [ ] Names in ticked meeting points, the typed instruction and the example
      letters are replaced before the payload leaves and never restored; the
      seam guard stays on.

## 6. Phasing

| Phase | Scope | AI? |
|---|---|---|
| **A** (first release) | The shared editor macro; subscribers, public signup with double opt-in, unsubscribe page, import upload, manual add; compose (editor, the two insert helpers, meeting points), **drafting by Raakje**, test mail, send per recipient in a queue under the daily cap; copy; archive. | Yes |
| **B** | Mail to the registrants of an activity or component (decision §3.14), on the same sending machinery. | No |
| **C** | Card layout following Raak nationaal: flyer, title, teaser, registration button. | No |
| **D** | Provider swap to an EU campaign service, only when a trigger from §3.7 fires. | No |

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
   time, and never goes above the cap. A "daily quota exceeded" answer from
   Gmail pauses the send until the next day and marks no delivery as
   failed.
9. An address that unsubscribes during a running send is skipped. Replies
   go to the tenant's sender address (`gmail_from`) unless the sender chose
   their own address.
10. The test mail goes only to the signed-in admin and does not change the
    letter's status.
11. A drafting payload contains no recipient address and no known person
    name: a ticked point "Kris regelt de bus" leaves without the name, and the
    name does not come back in the proposal.
12. An unticked meeting point never appears in a drafting payload.
13. A date, place or link in the proposal always comes from the activity
    data: a model answer that writes its own date for an activity does not
    reach the editor unchanged.
14. An amount, number, time or date word in a proposal that occurs in no
    source is marked before the proposal can be applied; so is a function
    word (voorzitter, penningmeester, …) that occurs in no source.
15. A proposal that contains a known person name is marked before it can be
    applied.
16. A piece operation (replace, insert, remove) changes exactly the paragraph
    it names, and nothing reaches the editor before *Toepassen*.
17. A photo link is only offered for an activity that has an album.
18. The known hallucinations are marked: a canned answer that adds games to
    Brood & Spelen that are not in its flyer text, one that attaches a
    function to a board member, and one that reuses a price found only in an
    example letter. Each must come out of layers 3 and 4 marked.
19. With the Raakje switch off, the panel is absent, and composing and
    sending still work.
20. The pages and the meeting notes still save their text after moving to the
    shared editor macro.

---

## 8. Answered questions (16 and 17 September 2026)

No shaping question is open. For the record, what was asked and answered:

1. **Which account sends?** The same way as a registration confirmation:
   technically through the portal's Gmail login, shown as the association's
   address (§3.8).
2. **What does Raakje write in one go?** The whole letter as a proposal, and
   then pieces, replaced or inserted following the conversation (§3.15).
3. **Where does Raakje learn the tone?** A short house-style text per
   association, as a tenant setting next to the meeting mail signature, plus
   the last two letters sent to the same audience once the archive holds any.
4. **How does a letter close?** Without personal names, with the association
   as sender, taken from the organisation's name (§3.10).

5. **What happens to a marked passage by default?** It is left out on
   *Toepassen*, unless the author ticks "klopt, behouden" for it (answered
   17 September 2026; §3.16, layer 5).

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
  grounds the drafting (§3.15). The sending pattern (a human reads first,
  Reply-To the sender) is the same.
- **CR-07 (AI kernel):** the drafting of §3.15 is its first acting capability
  pack. It reuses the name scrubber of `reporting/assistant.py` (with a
  replacement that is never restored) and the public Raakje's activity tools.
  The scrubber belongs in the kernel once a second capability uses it; moving
  it there is part of this build.
- **`mail` domain:** the transport, the log, and the `log_only` mode. The
  queue and the daily cap are new and belong there, because the registrant
  mail of phase B needs them too.
- **`membership` / `mdm`:** the member audience, through their `api.py`.

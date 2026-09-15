# Change Request 05 — Newsletter & Communication (subscriptions + LLM-assisted drafts)

**Project:** Web Portal "Raak Millegem"
**Status:** Decided 17 June 2026 (consent model, `Subscriber`, ESP adapter);
**updated 14 September 2026** in the CR-09 shaping conversation — see *Update
(14 September 2026)* below. Not scheduled. Phased, each phase independently
shippable.
**Apply to:** `backend/app/` (new `communication` domain; public signup and
admin compose are server-rendered screens — the `frontend/src/` mention
predates the React exit, #405).

---

## Update (14 September 2026)

Decided by Koen while shaping CR-09 (meetings). The 17 June 2026 decisions
below stand; this update refines the sending model, adds the import, and
plugs the drafting into the architecture that now exists.

1. **The existing mailing list (~800 addresses) is imported as `Subscriber`
   rows with opt-out.** Double opt-in stays the rule for *new* signups
   through the public form; the import rests on the existing relationship
   (legitimate interest), provided every mail carries a working unsubscribe
   link and the first mailing after import says where the address came from.
   Every imported row records provenance (`source = "import_2026"`, import
   date). The import comes from Koen's existing file; **two people already
   opted out** of the current mailing and are imported as `unsubscribed`
   from day one. Adding a subscriber by hand later must be possible (a small
   admin add on the subscriber screen). The members are **not** in the ~800.
2. **Newsletters are composed and sent from the portal — starting on the
   existing Gmail account.** The portal sends **one mail per recipient**
   through Gmail SMTP (the `mail` domain's transport), each with its own
   unsubscribe token and a `List-Unsubscribe` header, queued and batched
   under Gmail's daily limit (measure the actual limit before building).
   That ends the Bcc sends and the To/Bcc accident they invite, and makes
   the opt-out real. Gmail SMTP is the **first `EmailCampaignProvider`
   implementation**; the EU ESP below stays behind the same adapter as a
   later provider swap, **deferred with named triggers**: Gmail's daily cap
   starts to pinch, deliverability degrades, or manual bounce handling
   becomes a burden. The ListMonk-vs-Brevo trade-off (an exploratory cloud
   session exists) is decided only when a trigger fires.
3. **The compose screen carries the blocks the newsletters already have**
   (intro, "in de kijker", two-month calendar, outlook, external events),
   pre-filled from activities — and the composer browses the recent meeting
   report(s) there and **selects** which items come along (revised
   14 September 2026, mockup round: the earlier per-item "for the
   newsletter" flag set during the meeting is dropped; the newsletter maker
   decides, not the secretary). The monthly member edition also goes
   through the portal from then on.
4. **Drafting is the first acting capability pack on the CR-07 kernel**
   (CR-07 §4.1) — this supersedes the older "#205 swappable LLM layer"
   phrasing below; the seam guard, payload log and budgets inherit from the
   kernel. The three fixed rules apply: drafting is not sending, one write
   path, injection weighs heavier with acting tools. Its input: activity
   data (date/price/location/registration link), media (flyers, photos),
   and the report items the composer **selected in the compose screen**
   ([`change_request_09_meetings.md`](change_request_09_meetings.md), §3.18).
   **That selection is the PII gate**: unselected report content never
   enters an LLM payload; selected content may name volunteers — the human
   editor decides what survives into the sent newsletter. **And the LLM never detects
   activities in prose**: a selected meeting item carries the `activity_id`
   set when the agenda was generated (CR-09 §4), so the pack fetches the
   canonical activity data fresh from the activities domain and the
   structured fields win over whatever the note's free text says — the
   grounding rule the chatbot already has. A manually added item without a
   link contributes only its text; an item that should appear with a
   registration link gets one by first creating the activity in the portal
   and linking it, never by the model guessing.
5. **The audience is chosen per letter** (Koen, 15 September 2026 —
   replaces the earlier open question about the half-yearly edition). Three
   choices at compose time, **with no pre-selected value** so it is made
   rather than inherited: *leden*, *niet-leden*, or *allebei* (merged and
   **deduplicated by e-mail address** — the two lists will overlap, because
   someone from the mailing list who becomes a member stays on it). The
   content differs, not only the audience: a member letter names things a
   non-member does not get (the member discount, a refund), so "allebei" is
   for a letter written for both, never a convenient default.
6. **Members cannot unsubscribe from the newsletter** (Koen, 15 September
   2026 — **reverses** the decision of 17 June 2026, which gave every
   newsletter a working unsubscribe link for members too). His reasoning:
   they are members, the monthly newsletter is part of that, and that is how
   it works today. Nothing at all, deliberately: no link, no footer line.

   Recorded with the two objections that were put to him, because they do
   not disappear by being overruled: (a) for direct **marketing** the GDPR
   gives an absolute right to object — the crux is whether an association's
   own programme to its own members counts as marketing, which is arguable
   both ways and was not settled here; (b) bulk senders without a
   `List-Unsubscribe` header are filtered to spam more often, so the risk is
   not legal but delivery — and a member who lands in spam is a member who
   does not read it. **For non-members nothing changes**: a real, working
   unsubscribe link stays mandatory there.
7. **A newsletter can be copied.** Content, subject and blocks come along;
   the **audience does not** — you copy precisely because you are writing to
   someone else, so the new draft asks again. The original is untouched: a
   copy of a sent letter is a new object, and what was sent stays as it went
   out (the same rule as a sent meeting report).
8. **Mailing the people registered for an activity is NOT a newsletter**
   (Koen, 15 September 2026). It is operational mail about an arrangement
   they made themselves — the departure time moved, bring boots, mind the
   payment — so it carries **no unsubscribe link** and needs no consent,
   exactly like the board mail of CR-09. It therefore belongs **with the
   activity**, on the component (the barbecue and the cornhole tournament
   have different participants), with the option to reach a whole activity.
   What it shares with the newsletter is the *sending machinery*: one mail
   per recipient, queued under the daily limit, logged. The three audiences
   — members, subscribers, registrants — become three ways to build a
   recipient list on one engine, each with its own lawful basis. Open: which
   address (the registration's contact address is the obvious candidate,
   because that is who made the arrangement).

**Phasing after this update:** phase 0 (+ the import) → phase 2′ (compose &
send via the Gmail SMTP provider, per recipient, queued; personal
unsubscribe token + `List-Unsubscribe` header; campaign archive) → phase 3
(drafting, after CR-09's meeting module exists) → **ESP swap deferred with
the triggers above** (the old phase 1) → phase 4 unchanged, optional. Test
additions: an ~800-recipient campaign runs queued across the daily limit,
resumes cleanly after a backend restart, and every sent mail carried its own
unsubscribe token; unsubscribe works end to end on an imported address.

---

## Goal

Let members **and** non-members receive Raak Millegem communication, and help the
board produce that communication faster with an LLM that drafts concepts from
structured data. The non-members list also becomes a soft funnel toward
membership.

Two responsibilities are deliberately **kept separate** (see *Separation*):

- **(A) Subscription & sending** — a deterministic, GDPR-bound system. No AI.
- **(B) LLM-assisted drafting** — produces *concepts* a human edits and sends. The
  AI **never** sees the subscriber list or picks recipients.

---

## Separation of responsibilities (ties to CR-04)

The LLM is a *content* tool, not a *distribution* tool. It receives non-PII
structured data (an activity's name/date/price/location) and returns Dutch (nl-BE)
draft text. The subscriber list, consent state, recipient selection and actual
sending live in a separate communication domain that the LLM has no access to.
This keeps the GDPR surface small and mirrors CR-04's "isolated responsibilities".

---

## Audience & consent model (the part we must get right)

The decisive distinction is **transactional/contractual vs. marketing**:

| Communication type | Lawful basis | Members | Non-members | Unsubscribe |
|---|---|---|---|---|
| **Necessary member comms** (renewal reminder, payment/OGM, official convocations) | contract / legitimate interest | auto, always | n/a | **not** offered (necessary for membership) |
| **Newsletter / promotion** (activities, general blurbs) | legitimate interest (members) / consent (non-members) | **auto-subscribed** | **double opt-in** | **mandatory, every message** |

Decisions taken (Koen, 2026-06-17):

- **Members are auto-subscribed to the newsletter**, but every newsletter message
  carries an **unsubscribe link**. Unsubscribing removes them from the *newsletter*
  only — never from necessary member comms. (Right to object, GDPR art. 21 + the
  ePrivacy unsubscribe requirement, are non-negotiable.)
- **Non-members subscribe via double opt-in** (confirmation email with a link),
  with **minimal data: email (+ optional first name)**. Confirmable, unsubscribable.
- **No household/family data is collected at newsletter signup** (data
  minimisation). A non-member who wants to leave family details is starting a
  *membership*, which goes through the existing `POST /families` flow. The
  newsletter signup shows a "word lid" CTA for conversion — it does not hoard PII.
- **"Smart"/segmented mails** may use lawfully-held **member** data; for
  non-members only what they consented to.

**Always required:** consent record (timestamp + source + what was agreed),
unsubscribe token, one-click `List-Unsubscribe` header, privacy-policy update,
honouring erasure (unsubscribe + delete).

---

## Data model

New, **separate** entity in its own domain — deliberately not folded into the
member tables (different lawful basis, different lifecycle, minimal data):

`Subscriber`
- `id`
- `email` (unique, required)
- `first_name` (optional, for the greeting only)
- `status` — `pending` → `confirmed` → `unsubscribed`
- `source` — e.g. `public_form`, `member_auto`
- `consent_at`, `confirmed_at`, `unsubscribed_at`
- `confirm_token`, `unsubscribe_token`
- optional soft link to `Person`/`Member` (set when a subscriber becomes a member;
  no FK requirement — survives member deletion, like the analytics events)

Members are represented in the newsletter audience via `source = member_auto`
(either materialised rows or a union view), each with their own unsubscribe state
so an opt-out is recorded without touching their membership.

---

## Sending infrastructure

- **Newsletter → EU email service provider (ESP)** via API. **Recommended: Brevo
  (FR)**; alternative **MailerLite (LT)**. The ESP provides deliverability
  (SPF/DKIM/DMARC), built-in unsubscribe, bounce/complaint handling and
  `List-Unsubscribe` out of the box — exactly the tedious, compliance-critical work
  we should not reimplement. EU processor → DPA in place, no third-country transfer.
- **Transactional mail stays on Gmail SMTP** (registration confirmation, OGM/payment)
  — it is fine for low-volume one-to-one mail.
- **Provider behind an adapter** (`BaseProvider`-style, like the payment gateway and
  the planned LLM layer): `EmailCampaignProvider` interface with a `BrevoProvider`
  implementation, so the ESP can be swapped without touching callers. Do not
  hardcode the ESP.
- Volume context: ~150 members + ~150 non-members. The ESP free tiers cover this
  comfortably (≈ €0).

---

## LLM-assisted drafting

- Generates a **concept** for: activity announcement (first), renewal reminder,
  "almost full" notice, newsletter blurb — in nl-BE.
- **Human-in-the-loop:** the board edits and sends; nothing auto-sends.
- **Guardrails** (same as the chatbot #205): structured fields (date/price/location)
  always win over free text; the model may not invent facts.
- **Input = non-PII structured/aggregate data only.** Never the subscriber list,
  never recipient PII.
- Runs behind the **swappable LLM layer** of #205; the placement decision
  (Mistral/EU vs. local Ollama) is **deferred** — it sits behind the adapter.

---

## Architecture / layering

- New backend domain `backend/app/domains/communication/`:
  - `models.py` (`Subscriber`), Alembic migration.
  - `service.py` — subscribe / confirm / unsubscribe / build-audience / send-campaign.
  - `providers/` — `EmailCampaignProvider` (ABC) + `BrevoProvider`.
  - `schemas.py` — public signup + admin compose DTOs.
- LLM drafting is a **separate** concern (a `drafting` service reusing the #205
  LLM adapter), not part of the communication domain's data path.
- Frontend:
  - Public: newsletter signup form, confirm page, unsubscribe page (token-based, no
    login).
  - Admin: subscriber list, compose/send screen with a "draft with AI" button.

---

## GDPR / compliance checklist

- [ ] Lawful basis documented per communication type.
- [ ] Double opt-in for non-members; consent record stored.
- [ ] Mandatory unsubscribe link + `List-Unsubscribe` header on every newsletter.
- [ ] Members auto-subscribed **with** working unsubscribe (newsletter only).
- [ ] Data minimisation: email (+ optional name) at signup; no family data.
- [ ] Right to erasure honoured (unsubscribe + delete).
- [ ] EU ESP with signed DPA; privacy policy updated.
- [ ] No PII (and no recipient list) sent to the LLM.

---

## Phasing (each phase shippable)

| Phase | Scope | AI? | Risk |
|---|---|---|---|
| **0** | `Subscriber` model + double opt-in + unsubscribe (token pages). The compliant core. | No | Low |
| **1** | ESP integration via `EmailCampaignProvider` adapter; transactional/Gmail split. | No | Medium (deliverability) |
| **2** | Admin compose + send newsletter; build audience (members auto + confirmed non-members). | No | Medium |
| **3** | LLM "draft this" button (activity announcement first), behind the #205 adapter. | Yes | Low |
| **4** | Segmented / "smart" mails using lawful member data. | Optional | Medium (profiling consent) |

Recommended start: **Phase 0** — it is the compliant foundation and carries no AI
or deliverability risk.

---

## Non-goals

- No household/family data at newsletter signup (that is the membership flow).
- No marketing email without an unsubscribe link.
- No LLM access to recipient lists or PII.
- No self-hosted mail server (conflicts with the low-maintenance constraint).
- No general CRM build-out; this stays a newsletter/communication tool.

---

## Relationship to existing work

- **Reuses** the swappable LLM layer (#205) for drafting; **separate** from the
  ML/predictions track (#171).
- **Reuses** the existing `services/email.py` + `structured_communication` for
  transactional mail; the ESP is additive, for campaigns only.
- **Follows** CR-04's adapter/strategy and layered-isolation patterns.

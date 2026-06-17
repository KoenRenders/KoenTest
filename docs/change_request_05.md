# Change Request 05 — Newsletter & Communication (subscriptions + LLM-assisted drafts)

**Project:** Web Portal "Raak Millegem"
**Status:** Proposal / discussion — not scheduled. Phased, each phase independently shippable.
**Apply to:** `backend/app/` (new communication domain), `frontend/src/` (public signup + admin compose).

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

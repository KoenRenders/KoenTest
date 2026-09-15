# The tenant's own organisation: field inventory (#924)

> **Superseded in part by #945 (15 September 2026).** This document describes the
> three switchovers of #924 and the eleven columns they put on `Organization`. Of
> those, only `legal_form` is still a column. Identifications, bank accounts and
> contact details — including the social links — became **rows** in
> `mdm.organization_identifications`, `mdm.bank_accounts` and
> `mdm.contact_details`, in the shape UBL 2.1 / EN 16931 gives them, and the
> `display_name` setting is gone: the name comes from the organisation.
>
> The reasoning below still holds and is worth keeping — it is how the fields got
> off the settings screen in the first place. The *locations* are the part that
> moved. Left as written rather than rewritten, because a snapshot that pretends
> to be current is exactly the second source this document argues against.

Where each field lives **today**, where it goes, and — the part that is easiest to
lose — **what happens to the old source**. A field that keeps existing in two
places is the duplication this issue set out to remove: then it was moved, not
taken away.

Measured on the branch of 14 September 2026, not recalled. Line numbers are
pointers, not promises.

The entity's identifier is **not decided yet** (`Organization` is taken: it is the
tenant model itself, `org_type` ∈ ACCOUNT/UNIT/PLATFORM). This document says "the
own organisation" throughout, so the name can be filled in without rewriting it.

---

## The order is the safety, not a preference

1. **Payment instructions** — two fields, three readers, a fallback chain that is
   already there and already tested.
2. **Footer** — one CMS block, and the only step that meets free text a tenant may
   have edited.
3. **Contact / privacy** — the smallest, and it inherits whatever the first two
   settle about name and address.

Doing the footer first would mean deciding the address format while nothing yet
reads it.

---

## Wave 1 — payment instructions

| Field | Where it comes from today | Moves? | What happens to the old source |
|---|---|---|---|
| IBAN | tenant setting `payment_iban` → env `PAYMENT_IBAN` (`config.py:117`) | **yes** | disappears from the settings screen (`ui/tenants_ui.py:50`); stays as a **read** fallback |
| Beneficiary | tenant setting `payment_beneficiary` → env (`config.py:118`) | **yes** | idem (`ui/tenants_ui.py:51`) |
| Payment term (days) | tenant setting `payment_term_days` | **no** | stays — it is payment *policy*, not an attribute of the organisation |

**Readers to repoint** — all three read through `kernel/tenant_config.py:349-357`:

- `domains/mail/service.py:166-171` — the transfer instructions in the mail.
- `domains/membership/ui.py:186-192` — membership screen.
- `domains/membership/ui.py:315-321` — second screen, same pair.

Repoint `tenant_payment_iban()` / `tenant_payment_beneficiary()` themselves rather
than their three callers: then the reading order lives in one place and the callers
do not have to know the entity exists.

**Reading order becomes:** own organisation → tenant setting → env.

> **The tension worth naming.** The issue asks for the existing fallback to stay as
> a safety net, and that is right for the deploy. But the migration seeds the entity
> **from** those settings, so from the first deploy the setting level is dead
> weight: every environment has the entity. Keeping it editable in two places is
> exactly what this issue removes — hence removing it from the **screen** while
> keeping it as a **read** fallback. Once the environments are confirmed, dropping
> the setting level entirely is a small follow-up; it should not be assumed done
> here.

---

## Wave 2 — the footer

Today the footer is assembled in `ui/templates/site_base.html:177-224` from four
independent sources:

| Part | Source today | Moves? | What happens to the old source |
|---|---|---|---|
| Address / contact block | CMS page `site-footer`, published by migration 094, rendered via `ui/__init__.py:369-372` | **yes** | the CMS page stops being the carrier of these details |
| Sponsor logos | media items | **no** | unrelated to the organisation |
| Social links | settings `facebook_url`, `instagram_url`, `tiktok_url` (`ui/__init__.py:411-414`) | **no** | channels of the *site*, not identity |
| Privacy link + year + site name | setting `privacy_url`, `tenant_display_name` | **no** | see the name question below |

**The one thing that is not mechanical.** `site-footer` is a free CMS page: a tenant
may have put anything in it, and a migration cannot tell an address block from a
sentence somebody wrote. The proposal is therefore:

- the footer renders the organisation block **from the entity**;
- the CMS page keeps rendering **underneath** it if it still has content, so nothing
  a tenant wrote disappears on deploy;
- and the placeholder seed of 14 September becomes superfluous, which was the point.

Whether the CMS block is then retired for good is a decision **after** an
environment has been looked at — not a step this issue can take blind.

---

## Wave 3 — contact and privacy

| Field | Source today | Moves? | What happens to the old source |
|---|---|---|---|
| E-mail, phone, address on a contact page | free CMS content | **yes**, where a page uses them | the page keeps its text, the details come from the entity |
| `privacy_url` | tenant setting | **no** | a link to a document, not organisation data |

---

## What stays a tenant setting, and why

These describe the **site**, not the identity of the organisation behind it.
Recording it here is the point of the inventory: "why does this one stay" is the
question that comes back in six months.

`display_name`, `tagline`, `base_url`, the three social links, `privacy_url`,
`mail_mode`, `noindex`, `language`, the membership prices and dates,
`payment_term_days`, the Gmail keys, the Umami keys, the two limits and
`admin_chat_enabled`.

---

## Two questions the inventory cannot settle

**1. Brand name against legal name.** `display_name` is the brand and the sender
name ("Raak Millegem"); the entity carries the legal name, which for a *feitelijke
vereniging* may read differently. Both are legitimate and they are not the same
field. Which one the footer shows is Koen's call — and until it is made, the entity
gets its own `name` and `display_name` stays exactly where it is.

**2. The address is already modelled once.** `mdm.addresses` exists, hangs off a
**person**, and carries a partial unique index on `person_id` (migration 053). The
own organisation needs an address that does not hang off a person. Two roads: give
the entity its own address columns, or make the address table polymorphic. The first
is duplication of the address *shape*; the second touches a table that every member
screen reads. This one deserves a decision before the migration is written, not
during.

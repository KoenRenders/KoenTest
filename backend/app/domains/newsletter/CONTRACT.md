# newsletter — component contract (CR-05, #984)

**Purpose.** The newsletter to members and non-members: subscribers with a
recorded consent, a letter written in the portal with Raakje drafting alongside,
and a send of one mail per recipient in a queue under a daily cap.

## Facade (`api.py`) — the only door for other components and for this component's screens

- **Subscribers:** `subscribe_public`, `confirm`, `unsubscribe`, `resubscribe`,
  `add_by_admin`, `unsubscribe_by_admin`, `erase`, `list_subscribers`,
  `subscriber_counts`, `preview_import`, `run_import`.
- **Audiences:** `member_addresses`, `recipients_for`, `audience_counts`.
- **Letters:** `create_newsletter`, `update_draft`, `set_draft_sources`,
  `copy_newsletter`, `delete_draft`, `list_newsletters`, `get_newsletter`.
- **Content helpers:** `activity_facts`, `activity_line_html`, `calendar_html`,
  `closing_html`, `insertable_activities`.
- **Sending:** `send_test`, `start_sending`, `send_batch` (the job's work),
  `progress_of`, `expected_days`, `deliveries_of`.
- **Raakje:** `ask_raakje`, `apply_proposal`, `dismiss_proposal`,
  `display_proposal`, `record_turn`, `get_drafting_message`, `messages_of`.
- **Settings:** `save_settings` (house style, daily cap).
- **Models as types, for other domains' services only:** `Subscriber`,
  `Newsletter`, `Delivery`, `DraftingMessage`.

## What this component uses from others (only through their facade)

| Component | For |
|---|---|
| `membership.api` | `members_with_membership_for_year` — who is a member (CR-05 §3.3) |
| `mdm.api` | `email_addresses_of_members` (the member audience), `organization_address` (the mail footer), `person_name_parts` (the name list Raakje scrubs with, the guard's own) |
| `activities.api` | `activities_from`, `Activity` — the facts of an activity |
| `media.api` | `activity_photo_covers` (does an album exist), `tenant_logo` (the mail header) |
| `meetings.api` | `recent_report_points` — the points the composer may tick |
| `cms.api` | `sanitize_cms_html` — the letter's HTML |
| `mail.api` | `send_campaign_mail`, `send_newsletter_confirmation`, `SendingQuotaReached` |
| `chatbot.api` | `GuardedProvider`, `admin_rules`, `sink_for`, `get_provider`, `run_chat`, `read_tool_specs`, `execute_read_tool`, `admin_chat_char_budget`, `SeamBlocked`, `ChatTimeout` |

## What other components take from here

Today: nothing. The registrant mail of CR-05 §3.14 will reuse the sending
machinery when it is built.

## Invariants

- **Members are derived, never stored.** `subscribers` holds non-members only.
- **No audience, no send** — in the screen, in the service and as a database
  CHECK.
- **Only a subscriber's mail carries an unsubscribe link** and the one-click
  header; a member's never does (CR-05 §3.4).
- **An import never resubscribes an unsubscribed address.**
- **Erasure is real:** the subscriber row goes, its deliveries keep their
  counts with the address replaced.
- **The recipient list is fixed when sending starts;** an address that
  unsubscribes during a multi-day send is skipped when its row comes up.
- **The queue never exceeds the daily cap** and pauses on Gmail's quota answer
  without marking anything as failed; each delivery is committed right after
  its mail left.
- **Confirming and unsubscribing act on a POST,** never on opening the link —
  mail scanners open links.
- **Raakje proposes, never acts:** no tool sends, nothing reaches the editor
  without "Toepassen", nothing outbound carries a known name or a recipient
  address, and a marked sentence is left out unless the author keeps it.

## Where to start reading

`service.py` for the rules, `drafting.py` for Raakje, `handlers.py` for the job,
`docs/change_request_05_newsletter.md` for the why.

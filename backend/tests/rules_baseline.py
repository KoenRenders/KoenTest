"""The frozen offenders of the CR-13 gate (`tests/test_rules_gate.py`, §B9.3).

**A burn-down, not an exemption list** (§B9.4). Phase 0 froze today's offenders
per gate; every later phase removes the entries of the domains it migrates and
makes the gate hard for them; phase 4 deletes this file. An entry may only
disappear — the gate turns red on a new offender, and on an entry that no longer
occurs.

**Keys carry no line numbers:** they would shift on the first unrelated edit, and
a gate that turns red for the wrong reason gets switched off. Each key names the
thing it is about — `file::function`, `package:piece`, `METHOD path` — so the
commit that changes the type of that thing can find and settle its entries in
the same commit (§B9.3, the #1268 lesson).

Measured by the collectors themselves on `master` of 28 September 2026 (after
#781), not written by hand.
"""

# Every /api/v1 route (method × path) as of 28 September 2026: none is named
# under ## Callers in a CONTRACT.md yet. Phase 4 names each remaining route or removes
# it (R14), measured in the repository and in the PROD access log.
JSON_ROUTE_WITHOUT_CALLER: frozenset[str] = frozenset(
    {
        "DELETE /api/v1/auth/api-keys/{key_id}",
        "DELETE /api/v1/users/{user_id}",
        "GET /api/v1/auth/api-keys",
        "GET /api/v1/auth/me",
        "GET /api/v1/auth/member/me",
        "GET /api/v1/auth/verify-login",
        "GET /api/v1/users",
        "POST /api/v1/auth/api-keys",
        "POST /api/v1/auth/request-login",
        "POST /api/v1/auth/verify-otp",
        "POST /api/v1/users",
    }
)


# Writes to another domain's mapped classes as of 29 September 2026 (#1254), one key
# per function and class written: membership → mdm 22, audit → activities/mdm/
# membership/payment 13 (the history snapshots), mdm → auth 2, mdm → membership 1,
# media → chatbot 1, payment → membership 1. Phase 3 moves the household writes to
# mdm (B2.5); phase 2 turns `_activate_membership` into a membership handler.
FOREIGN_WRITES: frozenset[str] = frozenset(
    {
        "domains/media/extraction.py::update_media_extracted_text → chatbot.ChatbotInfo",
    }
)


# Functions another domain's service, handler or tool calls through `api.py` and that
# commit (§B9.3 (c)), 29 September 2026, followed three calls deep including late
# imports. A router or screen calling another domain's
# service is not here: that service is the request's door. Mail's `_log_email` is
# the phase 4 job enqueuer (§B4.1); media and designstudio meet in phase 4.
COMMIT_BEHIND_API: frozenset[str] = frozenset(
    {
        "forms.api.submit_bericht",
    }
)


# Calls into another domain's command outside a `@subscribe` function (§B4.9, R12),
# 29 September 2026, one key per calling function and command. A command is derived
# from the code: an `api.py` export that writes or commits (master CLI, 29 Sep). The
# audit snapshots (84 of these) become events or move with their writers; the rest
# are the couplings B4.9 names — mail, payment, workflow, media — and phase 3's
# household moves.
#
# Two entries were ADDED after the freeze, by decision (Koen, 29 September 2026): the
# synchronous commands of `activities` into `forms` (CR-14 §B4.2, §B4.7). When a call
# is an event, a port or a read — and when a port gets built instead of an entry
# here — is one rule, written once: `docs/architecture.md` §3.2.1.
COMMAND_CALLS: frozenset[str] = frozenset(
    {
        "domains/activities/router.py::create_registration → payment.api.create_payment_record",
        "domains/auth/login.py::start_login → mail.api.send_magic_link",
        "domains/auth/login.py::start_login → mail.api.send_member_contact_board_notice",
        "domains/chatbot/tools.py::submit_idea → forms.api.submit_bericht",
        "domains/forms/api.py::submit_bericht → mail.api.send_form_confirmation",
        "domains/forms/service.py::submit_form → mail.api.send_form_confirmation",
        "domains/mdm/ui.py::gezin_aanmaken → membership.api.create_family_by_admin",
        "domains/mdm/ui.py::lidmaatschap_toevoegen → membership.api.create_membership_for_family",
        "domains/mdm/ui.py::lidmaatschap_verwijderen → membership.api.delete_membership",
        "domains/meetings/admin_ui.py::circle_add → mdm.api.add_to_circle",
        "domains/meetings/admin_ui.py::circle_end → mdm.api.end_circle_relation",
        "domains/meetings/admin_ui.py::circle_new_person → mdm.api.create_person_for_circle",
        "domains/meetings/service.py::send_meeting_mail → mail.api.send_with_attachments",
        "domains/membership/portal_service.py::renew_membership → payment.api.create_payment_record",
        # CR-22 S7 (#1712): the delete of a person moved to master data — one
        # rule, `mdm.service.delete_person` — and its history calls with it;
        # membership's door calls that rule. Four entries left, four came.
        "domains/membership/signup_service.py::register_family → payment.api.create_payment_record",
        "domains/newsletter/service.py::send_batch → mail.api.send_campaign_mail",
        "domains/newsletter/service.py::send_test → mail.api.send_campaign_mail",
        "domains/newsletter/service.py::subscribe_public → mail.api.send_newsletter_confirmation",
    }
)


# Refusals decided at the door (§B9.3, *no rule in a router*), 29 September 2026, with
# a reason per entry, as the change request asks: a `rule` moves to its entity or
# service in the phase named; a `door` entry is the request's shape (a file's size or
# type, an empty upload, a parameter) and is the doorman's own — the phase that
# sweeps its domain decides whether the gate learns to except it or it stays named.
# Keys are `file::function::condition` — the condition text, not a line number.
RULE_IN_ROUTER: dict[str, str] = {
    "domains/auth/router.py::create_api_key::db.query(ApiKey).filter(ApiKey.name == name).first()": "rule: API key names are unique (ApiKey, with a UNIQUE constraint) — phase 4",
    "domains/auth/router.py::create_api_key::not name": "rule: an API key has a name (ApiKey) — phase 4",
}


# Writes to a mapped class in a router, UI module or `@subscribe` handler (§B9.3,
# *one entrance rule* (b)), 29 September 2026. The household router (phase 3) and the
# registration router (phase 1) are the ones the change request names.
WRITE_OUTSIDE_SERVICE: frozenset[str] = frozenset(
    {
        "domains/auth/router.py::create_api_key → auth.ApiKey",
        "domains/auth/router.py::revoke_api_key → auth.ApiKey",
        "domains/auth/router.py::verify_login → auth.LoginToken",
    }
)

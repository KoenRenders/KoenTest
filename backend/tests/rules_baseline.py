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

# Two helpers in activities/models.py that open a session through object_session to
# find an uploaded asset. Phase 1 moves them to the service (the Registration aggregate).
SESSION_ON_ENTITY: frozenset[str] = frozenset(
    {
        "domains/activities/models.py::ActivitySubRegistration._info_asset",
        "domains/activities/models.py::_single_asset",
    }
)


# Phase 0b gave every domain with a single-domain test its tests/; audit, designstudio
# and newsletter have none yet — their tests walk through other domains too, so they
# live in tests/integration/. audit, stt, cms, membership and reporting lack a further
# piece. Phase 4 decides audit and stt (give them the shape, or move them — §B4.5).
MODULE_SHAPE: frozenset[str] = frozenset(
    {
        "audit:CONTRACT.md",
        "audit:codes.py",
        "audit:models.py",
        "audit:tests/",
        "cms:codes.py",
        "designstudio:tests/",
        "membership:codes.py",
        "newsletter:tests/",
        "reporting:CONTRACT.md",
        "stt:CONTRACT.md",
        "stt:api.py",
        "stt:codes.py",
        "stt:models.py",
    }
)


# The one event handler that commits, through _dispatch → _send → _log_email.
# Phase 4 turns it into a job enqueuer (§B4.1). Any other handler that commits is red.
COMMIT_IN_HANDLER: frozenset[str] = frozenset(
    {
        "domains/mail/handlers.py::on_mail_requested",
    }
)


# The same handler, sending over SMTP inside the transaction. Phase 4.
NETWORK_IN_HANDLER: frozenset[str] = frozenset(
    {
        "domains/mail/handlers.py::on_mail_requested",
    }
)


# Every /api/v1 route (method × path) as of 28 September 2026: none is named
# under ## Callers in a CONTRACT.md yet. Phase 4 names each remaining route or removes
# it (R14), measured in the repository and in the PROD access log.
JSON_ROUTE_WITHOUT_CALLER: frozenset[str] = frozenset(
    {
        "DELETE /api/v1/activities/{activity_id}",
        "DELETE /api/v1/activities/{activity_id}/components/{component_id}",
        "DELETE /api/v1/activities/{activity_id}/components/{component_id}/products/{product_id}",
        "DELETE /api/v1/activities/{activity_id}/dates/{date_id}",
        "DELETE /api/v1/activities/{activity_id}/registrations/{registration_id}",
        "DELETE /api/v1/activities/{activity_id}/registrations/{registration_id}/items/{item_id}",
        "DELETE /api/v1/admin/activities/{activity_id}/poster",
        "DELETE /api/v1/admin/chatbot-info/{row_id}",
        "DELETE /api/v1/admin/components/{component_id}/info",
        "DELETE /api/v1/admin/email-log/{log_id}",
        "DELETE /api/v1/admin/media/{asset_id}",
        "DELETE /api/v1/auth/api-keys/{key_id}",
        "DELETE /api/v1/families/{family_id}",
        "DELETE /api/v1/forms/{form_id}",
        "DELETE /api/v1/forms/{form_id}/submissions/{submission_id}",
        "DELETE /api/v1/member/household/persons/{person_id}",
        "DELETE /api/v1/member/household/persons/{person_id}/emails/{contact_id}",
        "DELETE /api/v1/memberships/{membership_id}",
        "DELETE /api/v1/pages/{page_id}",
        "DELETE /api/v1/payment-status/records/{record_id}",
        "DELETE /api/v1/persons/{person_id}",
        "DELETE /api/v1/users/{user_id}",
        "GET /api/v1/activities",
        "GET /api/v1/activities/{activity_id}/components/{component_id}/export",
        "GET /api/v1/activities/{activity_id}/photos",
        "GET /api/v1/activities/{activity_id}/public-registrations",
        "GET /api/v1/activities/{activity_id}/registrations",
        "GET /api/v1/admin/changes",
        "GET /api/v1/admin/chatbot-info",
        "GET /api/v1/admin/email-log",
        "GET /api/v1/admin/media",
        "GET /api/v1/admin/member-changes",
        "GET /api/v1/admin/member-changes/export",
        "GET /api/v1/admin/pages",
        "GET /api/v1/admin/stats",
        "GET /api/v1/admin/system-info",
        "GET /api/v1/auth/api-keys",
        "GET /api/v1/auth/me",
        "GET /api/v1/auth/member/me",
        "GET /api/v1/auth/verify-login",
        "GET /api/v1/blocks/{slug}",
        "GET /api/v1/cms/placeholders",
        "GET /api/v1/families",
        "GET /api/v1/families/{family_id}",
        "GET /api/v1/forms",
        "GET /api/v1/forms/by-token/{share_token}",
        "GET /api/v1/forms/edit/{edit_token}",
        "GET /api/v1/forms/{form_id}",
        "GET /api/v1/forms/{form_id}/export",
        "GET /api/v1/forms/{form_id}/results",
        "GET /api/v1/forms/{form_id}/submissions",
        "GET /api/v1/media/activity-photos/availability",
        "GET /api/v1/media/activity-photos/covers",
        "GET /api/v1/media/{asset_id}",
        "GET /api/v1/media/{asset_id}/thumb",
        "GET /api/v1/member/household",
        "GET /api/v1/members",
        "GET /api/v1/members/{member_id}",
        "GET /api/v1/memberships",
        "GET /api/v1/pages",
        "GET /api/v1/pages/{slug}",
        "GET /api/v1/payment-status/records",
        "GET /api/v1/payment-status/records/export",
        "GET /api/v1/payment-status/records/{payable_type}/{payable_id}",
        "GET /api/v1/payment-status/registrations/{registration_id}/balance",
        "GET /api/v1/persons",
        "GET /api/v1/postal-codes",
        "GET /api/v1/sponsors",
        "GET /api/v1/users",
        "PATCH /api/v1/activities/{activity_id}/registrations/{registration_id}",
        "PATCH /api/v1/activities/{activity_id}/registrations/{registration_id}/items/{item_id}",
        "PATCH /api/v1/admin/chatbot-info/{row_id}",
        "PATCH /api/v1/admin/media/{asset_id}",
        "PATCH /api/v1/payment-status/records/{record_id}",
        "POST /api/v1/activities",
        "POST /api/v1/activities/{activity_id}/components",
        "POST /api/v1/activities/{activity_id}/components/{component_id}/products",
        "POST /api/v1/activities/{activity_id}/dates",
        "POST /api/v1/activities/{activity_id}/register",
        "POST /api/v1/activities/{activity_id}/registrations/{registration_id}/items",
        "POST /api/v1/admin/activities/{activity_id}/poster",
        "POST /api/v1/admin/chatbot-info/notes",
        "POST /api/v1/admin/components/{component_id}/info",
        "POST /api/v1/admin/media",
        "POST /api/v1/admin/media/{asset_id}/extract",
        "POST /api/v1/admin/member-import/commit",
        "POST /api/v1/admin/member-import/preview",
        "POST /api/v1/auth/api-keys",
        "POST /api/v1/auth/request-login",
        "POST /api/v1/auth/verify-otp",
        "POST /api/v1/chat",
        "POST /api/v1/families",
        "POST /api/v1/families/{family_id}/memberships",
        "POST /api/v1/families/{family_id}/persons",
        "POST /api/v1/forms",
        "POST /api/v1/forms/by-token/{share_token}/submit",
        "POST /api/v1/member/household/persons",
        "POST /api/v1/member/household/persons/{person_id}/emails",
        "POST /api/v1/member/household/persons/{person_id}/emails/rows",
        "POST /api/v1/member/household/persons/{person_id}/emails/{contact_id}/primary",
        "POST /api/v1/member/household/renew-membership",
        "POST /api/v1/members",
        "POST /api/v1/members/{member_id}/memberships",
        "POST /api/v1/pages",
        "POST /api/v1/payment-gateway/webhooks/mollie",
        "POST /api/v1/payment-gateway/webhooks/stub",
        "POST /api/v1/payment-status/records/{record_id}/refresh",
        "POST /api/v1/payment-status/records/{record_id}/refund",
        "POST /api/v1/users",
        "PUT /api/v1/activities/{activity_id}",
        "PUT /api/v1/activities/{activity_id}/components/{component_id}",
        "PUT /api/v1/activities/{activity_id}/components/{component_id}/products/{product_id}",
        "PUT /api/v1/activities/{activity_id}/dates/{date_id}",
        "PUT /api/v1/admin/chatbot-info/cms/{page_id}",
        "PUT /api/v1/admin/chatbot-info/media/{asset_id}",
        "PUT /api/v1/families/{family_id}/board-member",
        "PUT /api/v1/forms/edit/{edit_token}",
        "PUT /api/v1/forms/{form_id}",
        "PUT /api/v1/member/household/persons/{person_id}",
        "PUT /api/v1/pages/{page_id}",
        "PUT /api/v1/persons/{person_id}",
        "PUT /api/v1/persons/{person_id}/address",
        "PUT /api/v1/persons/{person_id}/contacts",
        "PUT /api/v1/users/{user_id}",
    }
)

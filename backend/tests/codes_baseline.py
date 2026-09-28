"""The permanent exemptions of the code gate (CR-12 §B9.3) — no ratchet left.

The #780 pattern held the violations of CR-12 here while their count was not
yet zero: a frozen list, a new offender red, a fixed one required to leave.
**Phase 5 (#1182) closed all five.** Four reached zero on 27 September 2026;
the last, `FK_MISSING`, held one column until Koen decided on 28 September
that `mdm.external_numbers.source` is a code list (migration 166). Every gate
in `test_codes_gate.py` is hard now, and the file name stays although no
baseline is left in it — a rename would only move the imports.

What stays are the exemption dicts (§B9.3). They are not ratchets: they are
values somebody else owns, they never reach zero, and each carries its reason
on its own line. `test_every_permanent_exception_still_has_a_target` removes an
entry whose target is gone.

**Why the keys carry no line numbers.** Line numbers shift on the first
unrelated edit above the entry, and a gate that goes red for the wrong reason
gets switched off. So every key is stable: a column name, a class name, or the
comparison itself. The gate's **message** names `file:line`.
"""


# ── Permanent exceptions: not a vocabulary of ours ───────────────────────────
#
# These do NOT belong to a ratchet, because a ratchet is a promise to reach
# zero and these never will. Each one carries its reason on its own line, the
# way `CLAUDE.md` asks a noqa comment to. The gate subtracts them before it
# judges and reports their number separately, so the two stay
# distinguishable: "not cleaned up yet" versus "not ours to clean".
#
# Adding an entry here is a decision, not a convenience. The question that
# settles it: *could this value ever be a row in a code table of ours?* An HTTP
# method and a MIME type could not — somebody else owns those lists.

_MIME_TYPE = "A MIME type: IANA's list, not ours (§B4.10)."

#: Columns that look like a vocabulary but get no code table (§B4.10).
FK_NOT_OUR_LIST: dict[str, str] = {
    "payment.gateway_payments.status": (
        "Mollie's own list. Mollie can add a value without our migration, and a "
        "foreign key would make the webhook fail at exactly the wrong moment. The "
        "adapter has an ExternalVocabulary enum and maps to our PaymentStatus."
    ),
    # CR-12 phase 4 residue (27 September 2026).
    "media.media_assets.content_type": _MIME_TYPE,
    "media.media_assets.thumb_content_type": _MIME_TYPE,
    "meetings.meeting_files.content_type": _MIME_TYPE,
    "designstudio.designs.duo_code": (
        "A colour duo is a brand asset with a payload — two house-style colours "
        "per code — and changes with the brand guide. It stays in `brand.py` "
        "(§B4.10, design and brand data)."
    ),
    "designstudio.design_highlights.icon_code": (
        "An icon code maps to an SVG path in `icons.py`: brand data with a "
        "payload, not a vocabulary (§B4.10)."
    ),
    "designstudio.design_renditions.size_code": (
        "A paper size is design data with a payload (dimensions) in `brand.py` (§B4.10)."
    ),
    "auth.login_tokens.otp_code": (
        "Not a vocabulary: the SHA-256 hash of a one-time login code (#395). The "
        "net matches on the `_code` suffix and cannot tell a code list from a "
        "secret."
    ),
}

#: `*_LABELS` dictionaries whose values are not labels at all (§B4.10). The
#: question that settles an entry here is the same one: *could a translator
#: ever own this text?* A file-name fragment and a brand asset's name could
#: not. Each phase moves its own domain's entries; phase 3 brought these three
#: out of the ratchet, so the count that is left really is work to do.
LABELS_NOT_A_VOCABULARY: dict[str, str] = {
    "app/domains/designstudio/admin_ui.py:DUO_LABELS": (
        "The colour duos are brand assets with a payload — two house-style "
        "colours per code — and change with the brand guide, not with a "
        "translator. They stay in `brand.py` (§B4.10)."
    ),
    "app/domains/designstudio/service.py:FILE_LAYOUT_LABELS": (
        "Not a label but a file-name fragment: `bowlen-v1-a3.pdf`. It is part "
        "of a download's name, which stays the same in every language."
    ),
    "app/domains/forms/models.py:RATING_LABELS": (
        "The 1-5 rating scale of a form is a Likert scale, not a vocabulary: "
        "numbers with their words, never stored as codes. §B4.10 keeps it as "
        "copy behind `_()`."
    ),
    "app/domains/designstudio/service.py:FILE_SIZE_LABELS": (
        "The same, for a size code: `feed` is called `portrait` in a file "
        "name. A translated file name would break the downloads folder."
    ),
    # Koen, 26 September 2026 (CR-12 note 6): the next two are exempt.
    "app/domains/cms/render.py:PLACEHOLDER_LABELS": (
        "The placeholders in CMS page text (`{{membership_price_full}}`) are "
        "stored inside the text, not in a column, and each one needs code that "
        "computes its value, so a new row in a table would do nothing. The "
        "words are help texts with an example, not labels."
    ),
    "app/domains/reporting/engine.py:SYMBOLIC_LABELS": (
        "The symbolic filter values (today, this year, the logged-in user) "
        "live in the JSON of a saved report, not in a column, and each one is "
        "resolved by its own code when the report runs. Their words go "
        "through `_()` (#1216), marked with `N_` in the table."
    ),
}

#: Template comparisons on a value that is not one of our stored codes. Added
#: with the Raakje proposals (26 September 2026) and proven both ways: an entry
#: whose comparison does not exist turned the target test red, and dropping
#: `kind==insert` from here turned the template ratchet red on that line.
TEMPLATE_COMPARISONS_NOT_A_CODE: dict[str, str] = {
    # Koen, 26 September 2026 (CR-12 note 6): Raakje's newsletter proposals.
    **{
        f"app/domains/newsletter/templates/_nb_raakje.html:{key}": (
            "A Raakje proposal is a JSON object on a chat message, written by the "
            "drafting code while the letter is being written; its `kind` and "
            "`status` are stored in no column, so there is nothing for a foreign "
            "key to guard and a code list would only add a table."
        )
        for key in (
            "kind==insert",
            "kind==letter",
            "kind==replace",
            "status==applied",
            "status==open",
        )
    },
}

#: Comparisons the vocabulary net catches that compare no code of ours.
LOOSE_STRINGS_NOT_A_CODE: dict[str, str] = {
    "app/domains/payment/ui.py:method==GET": (
        "`request.method` is the HTTP verb, not a payment method — the net matches "
        "on the attribute name and cannot tell the two apart."
    ),
    "app/domains/activities/models.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."
    ),
    "app/domains/designstudio/service.py:content_type==image/svg+xml": (
        "A MIME type: IANA's list, not ours."
    ),
    # CR-12 phase 4 residue (27 September 2026).
    "app/domains/media/service.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."
    ),
    "app/domains/chatbot/info_service.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."
    ),
    **{
        f"app/domains/media/{key}": (
            "A Pillow image mode (`RGB`, `RGBA`, `LA`, `P`): the imaging library's "
            "vocabulary, not ours (§B4.10)."
        )
        for key in (
            "images.py:mode in LA",
            "images.py:mode in RGBA",
            "images.py:mode!=RGB",
            "images.py:mode!=RGBA",
            "images.py:mode==P",
            "pdf.py:mode!=RGB",
        )
    },
    "app/domains/chatbot/router.py:role==user": (
        "The role of a chat message (`user`/`assistant`/`system`) is the "
        "chat-completions API's vocabulary, not ours (§B4.10)."
    ),
    "app/schemas/chat.py:role!=user": ("The same chat-message role, validated on the way in."),
}

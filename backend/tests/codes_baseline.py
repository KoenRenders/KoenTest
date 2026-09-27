"""The one ratchet left, and the permanent exemptions (CR-12 §B9.3).

The #780 pattern: while a count is not yet zero, the gate is a **ratchet**.
Today's offenders are listed here; a new one is red, and one that disappears
from the code must leave this file or the test is red. The list can only
shrink, and "not cleaned up yet" stays distinguishable from "allowed".

**Phase 5 (#1182) closed four of the five.** `ENUM_WITHOUT_LIST`,
`LABEL_DICTIONARIES`, `TEMPLATE_COMPARISONS` and `LOOSE_STRINGS` reached zero
and are hard gates now: their sets are gone from this file, and so is the code
that read them. Only `FK_MISSING` is still a ratchet, holding the one column
that waits for Koen's decision (`mdm.external_numbers.source`: a code list with
one code, or a provenance column exempt like history). When that is decided,
the set goes too and the last ratchet is a hard gate.

The exemption dicts below stay (§B9.3): they are not ratchets, they are
values somebody else owns, and they never reach zero.

**Why there are no line numbers here.** §B9.3 allows `file:line` or
`file:name`. Line numbers shift on the first unrelated edit above the offender,
and then the ratchet is red every day for a reason that has nothing to do with
codes — and a gate that goes red for the wrong reason gets switched off. So
every key here is stable: a column name, a class name, or the comparison
itself. The **message** does name `file:line`, because that is where the reader
has to go.
"""

#: Columns that store a vocabulary but carry no foreign key to a code table
#: yet. Key: `schema.table.column`. This is the heuristic net of §B9.3 —
#: explicitly a net and not a proof: a column called `categorie` escapes it
#: until someone registers it.
FK_MISSING: frozenset[str] = frozenset({
    'mdm.external_numbers.source',
})


# ── Permanent exceptions: not a vocabulary of ours ───────────────────────────
#
# These do NOT belong to a ratchet, because a ratchet is a promise to reach
# zero and these never will. Each one carries its reason on its own line, the
# way `CLAUDE.md` asks a `# noqa` to. The gate subtracts them before it
# ratchets and reports their number separately, so the two stay
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
        "adapter has an ExternalVocabulary enum and maps to our PaymentStatus."),
    # CR-12 phase 4 residue (27 September 2026).
    "media.media_assets.content_type": _MIME_TYPE,
    "media.media_assets.thumb_content_type": _MIME_TYPE,
    "meetings.meeting_files.content_type": _MIME_TYPE,
    "designstudio.designs.duo_code": (
        "A colour duo is a brand asset with a payload — two house-style colours "
        "per code — and changes with the brand guide. It stays in `brand.py` "
        "(§B4.10, design and brand data)."),
    "designstudio.design_highlights.icon_code": (
        "An icon code maps to an SVG path in `icons.py`: brand data with a "
        "payload, not a vocabulary (§B4.10)."),
    "designstudio.design_renditions.size_code": (
        "A paper size is design data with a payload (dimensions) in `brand.py` "
        "(§B4.10)."),
    "auth.login_tokens.otp_code": (
        "Not a vocabulary: the SHA-256 hash of a one-time login code (#395). The "
        "net matches on the `_code` suffix and cannot tell a code list from a "
        "secret."),
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
        "translator. They stay in `brand.py` (§B4.10)."),
    "app/domains/designstudio/service.py:FILE_LAYOUT_LABELS": (
        "Not a label but a file-name fragment: `bowlen-v1-a3.pdf`. It is part "
        "of a download's name, which stays the same in every language."),
    "app/domains/forms/models.py:RATING_LABELS": (
        "The 1-5 rating scale of a form is a Likert scale, not a vocabulary: "
        "numbers with their words, never stored as codes. §B4.10 keeps it as "
        "copy behind `_()`."),
    "app/domains/designstudio/service.py:FILE_SIZE_LABELS": (
        "The same, for a size code: `feed` is called `portrait` in a file "
        "name. A translated file name would break the downloads folder."),
    # Koen, 26 September 2026 (CR-12 note 6): the next two are exempt.
    "app/domains/cms/render.py:PLACEHOLDER_LABELS": (
        "The placeholders in CMS page text (`{{membership_price_full}}`) are "
        "stored inside the text, not in a column, and each one needs code that "
        "computes its value, so a new row in a table would do nothing. The "
        "words are help texts with an example, not labels."),
    "app/domains/reporting/engine.py:SYMBOLIC_LABELS": (
        "The symbolic filter values (today, this year, the logged-in user) "
        "live in the JSON of a saved report, not in a column, and each one is "
        "resolved by its own code when the report runs. Their words go "
        "through `_()` (#1216), marked with `N_` in the table."),
}

#: Template comparisons on a value that is not one of our stored codes. Added
#: with the Raakje proposals (26 September 2026) and proven both ways: an entry
#: whose comparison does not exist turned the target test red, and dropping
#: `kind==insert` from here turned the template ratchet red on that line.
TEMPLATE_COMPARISONS_NOT_A_CODE: dict[str, str] = {
    # Koen, 26 September 2026 (CR-12 note 6): Raakje's newsletter proposals.
    **{f"app/domains/newsletter/templates/_nb_raakje.html:{key}": (
        "A Raakje proposal is a JSON object on a chat message, written by the "
        "drafting code while the letter is being written; its `kind` and "
        "`status` are stored in no column, so there is nothing for a foreign "
        "key to guard and a code list would only add a table.")
       for key in ("kind==insert", "kind==letter", "kind==replace",
                   "status==applied", "status==open")},
}

#: Comparisons the vocabulary net catches that compare no code of ours.
LOOSE_STRINGS_NOT_A_CODE: dict[str, str] = {
    "app/domains/payment/ui.py:method==GET": (
        "`request.method` is the HTTP verb, not a payment method — the net matches "
        "on the attribute name and cannot tell the two apart."),
    "app/domains/activities/models.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."),
    "app/domains/designstudio/service.py:content_type==image/svg+xml": (
        "A MIME type: IANA's list, not ours."),
    # CR-12 phase 4 residue (27 September 2026).
    "app/domains/media/service.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."),
    "app/domains/chatbot/info_service.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."),
    **{f"app/domains/media/{key}": (
        "A Pillow image mode (`RGB`, `RGBA`, `LA`, `P`): the imaging library's "
        "vocabulary, not ours (§B4.10).")
       for key in ("images.py:mode in LA", "images.py:mode in RGBA",
                   "images.py:mode!=RGB", "images.py:mode!=RGBA",
                   "images.py:mode==P", "pdf.py:mode!=RGB")},
    "app/domains/chatbot/router.py:role==user": (
        "The role of a chat message (`user`/`assistant`/`system`) is the "
        "chat-completions API's vocabulary, not ours (§B4.10)."),
    "app/schemas/chat.py:role!=user": (
        "The same chat-message role, validated on the way in."),
}

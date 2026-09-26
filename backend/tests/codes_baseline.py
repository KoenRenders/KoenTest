"""Frozen lists of the violations that exist today (CR-12 §B9.3).

The #780 pattern: while a count is not yet zero, the gate is a **ratchet**.
Today's offenders are listed here; a new one is red, and one that disappears
from the code must leave this file or the test is red. The list can only
shrink, and "not cleaned up yet" stays distinguishable from "allowed".

Phase 5 of CR-12 deletes each of these sets together with the exemption logic
in the gate: a ratchet at zero becomes a hard gate.

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
    'activities.activity_sub_registrations.registration_type_code',
    'activities.registrations.registration_type',
    'ai.ai_call_log.provider',
    'ai.ai_call_log.status',
    'auth.login_tokens.otp_code',
    'designstudio.design_highlights.icon_code',
    'designstudio.design_renditions.layout_code',
    'designstudio.design_renditions.size_code',
    'designstudio.design_renditions.variant',
    'designstudio.designs.duo_code',
    'designstudio.designs.preset',
    'designstudio.designs.status',
    'designstudio.image_generations.status',
    'designstudio.image_generations.style',
    'form.form_fields.field_type',
    'form.forms.status',
    'mail.email_log.email_type',
    'mail.email_log.status',
    'mdm.external_numbers.source',
    'media.media_assets.content_type',
    'media.media_assets.kind',
    'media.media_assets.thumb_content_type',
    'meetings.meeting_attendances.status',
    'meetings.meeting_files.content_type',
    'meetings.meeting_files.purpose',
    'meetings.meeting_sections.kind',
    'newsletter.deliveries.kind',
    'newsletter.deliveries.status',
    'newsletter.drafting_messages.role',
    'newsletter.newsletters.audience',
    'newsletter.newsletters.reply_to_mode',
    'newsletter.newsletters.status',
    'newsletter.subscribers.source',
    'newsletter.subscribers.status',
    'public.kernel_jobs.status',
    'reporting.export_log.kind',
    'workflow.workflow_instances.definition_code',
    'workflow.workflow_instances.status',
    'workflow.workflow_instances.subject_type',
    'workflow.workflow_tasks.kind',
    'workflow.workflow_tasks.status',
    'workflow.workflow_tasks.subject_type',
})

#: `Enum` classes under `app/` that sit in no `CodeList` and carry no
#: `TechnicalEnum`/`ExternalVocabulary` marker either.
#: Key: `path/to/file.py:ClassName`.
ENUM_WITHOUT_LIST: frozenset[str] = frozenset({
    'app/domains/activities/service.py:RegistrationState',
    'app/domains/reporting/universe.py:Role',
})

#: Label dictionaries in Python — the shape this change request removes.
#: Key: `path/to/file.py:NAME`.
LABEL_DICTIONARIES: frozenset[str] = frozenset({
    'app/domains/audit/changes.py:_OPERATION_LABELS',
    'app/domains/chatbot/admin_ui.py:CAPABILITY_LABELS',
    'app/domains/chatbot/admin_ui.py:STATUS_LABELS',
    'app/domains/chatbot/admin_ui.py:SURFACE_LABELS',
    'app/domains/cms/render.py:PLACEHOLDER_LABELS',
    'app/domains/designstudio/admin_ui.py:CORNER_LABELS',
    'app/domains/designstudio/admin_ui.py:DUO_LABELS',
    'app/domains/designstudio/admin_ui.py:GENERATION_LABELS',
    'app/domains/designstudio/imaging.py:STYLE_LABELS',
    'app/domains/designstudio/service.py:FILE_LAYOUT_LABELS',
    'app/domains/designstudio/service.py:FILE_SIZE_LABELS',
    'app/domains/designstudio/service.py:LAYOUT_LABELS',
    'app/domains/designstudio/service.py:PRESET_LABELS',
    'app/domains/designstudio/service.py:STATUS_LABELS',
    'app/domains/forms/models.py:RATING_LABELS',
    'app/domains/mail/ui.py:_STATUS_LABELS',
    'app/domains/mail/ui.py:_TYPE_LABELS',
    'app/domains/meetings/service.py:SECTION_LABELS',
    'app/domains/newsletter/admin_ui.py:AUDIENCE_LABELS',
    'app/domains/newsletter/admin_ui.py:DELIVERY_LABELS',
    'app/domains/newsletter/admin_ui.py:LETTER_STATUS_LABELS',
    'app/domains/newsletter/admin_ui.py:SOURCE_LABELS',
    'app/domains/newsletter/admin_ui.py:SUBSCRIBER_LABELS',
    'app/domains/reporting/engine.py:SYMBOLIC_LABELS',
    'app/domains/workflow/ui.py:CAT_LABELS',
    'app/domains/workflow/ui.py:KIND_LABELS',
    'app/ui/organisaties_ui.py:SOORT_LABELS',
})

#: Templates comparing a code to a string literal.
#: Key: `path/to/template.html:attribute==value`.
TEMPLATE_COMPARISONS: frozenset[str] = frozenset({
    'app/domains/activities/templates/_aa_rail.html:registration_state==closed',
    'app/domains/activities/templates/_activiteiten_cards.html:registration_state==closed',
    'app/domains/activities/templates/_activiteiten_cards.html:registration_state==open',
    'app/domains/activities/templates/_activiteiten_cards.html:status!=Open',
    'app/domains/activities/templates/activiteit.html:registration_state==closed',
    'app/domains/activities/templates/activiteit.html:registration_state==open',
    'app/domains/activities/templates/activiteit.html:status!=Open',
    'app/domains/forms/templates/_fb_recordkop.html:status==closed',
    'app/domains/forms/templates/_fb_recordkop.html:status==open',
    'app/domains/forms/templates/_fb_resultaten.html:field_type==number',
    'app/domains/forms/templates/_fb_resultaten.html:field_type==rating',
    'app/domains/forms/templates/_formulier_veld.html:field_type==checkbox',
    'app/domains/forms/templates/_formulier_veld.html:field_type==email',
    'app/domains/forms/templates/_formulier_veld.html:field_type==info',
    'app/domains/forms/templates/_formulier_veld.html:field_type==number',
    'app/domains/forms/templates/_formulier_veld.html:field_type==phone',
    'app/domains/forms/templates/_formulier_veld.html:field_type==radio',
    'app/domains/forms/templates/_formulier_veld.html:field_type==rating',
    'app/domains/forms/templates/_formulier_veld.html:field_type==select',
    'app/domains/forms/templates/_formulier_veld.html:field_type==textarea',
    'app/domains/forms/templates/formulier_afdruk.html:field_type==info',
    'app/domains/forms/templates/formulier_afdruk.html:field_type==rating',
    'app/domains/forms/templates/formulier_afdruk.html:field_type==textarea',
    'app/domains/mail/templates/_email_log_lijst.html:status==failed',
    'app/domains/mail/templates/_email_log_lijst.html:status==sent',
    'app/domains/mdm/templates/_leden_persoon_velden.html:relation_type==HOOFDLID',
    'app/domains/media/templates/_me_lijst.html:kind==sponsor',
    'app/domains/meetings/templates/_vg_document.html:kind==CUSTOM',
    'app/domains/meetings/templates/_vg_document.html:kind==IDEAS',
    'app/domains/meetings/templates/_vg_document.html:kind==MEMBERS',
    'app/domains/meetings/templates/_vg_punt.html:kind==activity',
    'app/domains/meetings/templates/_vg_punt.html:kind==member',
    'app/domains/meetings/templates/meeting_pdf.html:kind!=MEMBERS',
    'app/domains/meetings/templates/meeting_pdf.html:kind==MEMBERS',
    'app/domains/membership/templates/gezin_portaal.html:relation_type==HOOFDLID',
    'app/domains/newsletter/templates/_nb_abonnees.html:status!=unsubscribed',
    'app/domains/newsletter/templates/_nb_raakje.html:kind==insert',
    'app/domains/newsletter/templates/_nb_raakje.html:kind==letter',
    'app/domains/newsletter/templates/_nb_raakje.html:kind==replace',
    'app/domains/newsletter/templates/_nb_raakje.html:role==author',
    'app/domains/newsletter/templates/_nb_raakje.html:status==applied',
    'app/domains/newsletter/templates/_nb_raakje.html:status==open',
    'app/domains/workflow/templates/_werkbank_detail.html:status==done',
    'app/domains/workflow/templates/_werkbank_lijst.html:status==done',
    'app/ui/templates/_org_kaarten.html:org_type==ACCOUNT',
    'app/ui/templates/_tn_kaarten.html:org_type==PLATFORM',
})

#: Loose string comparisons on a vocabulary attribute in `.py`.
#: Key: `path/to/file.py:attribute==value`.
LOOSE_STRINGS: frozenset[str] = frozenset({
    'app/domains/activities/admin_ui.py:status==Open',
    'app/domains/activities/models.py:kind==component_info',
    'app/domains/auth/router.py:contact_type_code in MOBILE',
    'app/domains/auth/router.py:contact_type_code in PHONE',
    'app/domains/auth/users.py:role_code==OPERATOR',
    'app/domains/chatbot/info_service.py:content_type==application/pdf',
    'app/domains/chatbot/info_service.py:kind==activity_poster',
    'app/domains/chatbot/info_service.py:kind==component_info',
    'app/domains/chatbot/router.py:role==user',
    'app/domains/designstudio/admin_ui.py:status==requested',
    'app/domains/designstudio/blocks.py:preset!=tekst',
    'app/domains/designstudio/blocks.py:preset==eenvoudig',
    'app/domains/designstudio/blocks.py:preset==tekst',
    'app/domains/designstudio/service.py:content_type==image/svg+xml',
    'app/domains/designstudio/service.py:status==fetched',
    'app/domains/forms/export.py:field_type!=info',
    'app/domains/forms/router.py:status!=open',
    'app/domains/forms/router.py:status==draft',
    'app/domains/forms/service.py:field_type in radio',
    'app/domains/forms/service.py:field_type in select',
    'app/domains/forms/service.py:field_type not in radio',
    'app/domains/forms/service.py:field_type not in select',
    'app/domains/forms/service.py:field_type==info',
    'app/domains/forms/service.py:status!=open',
    'app/domains/forms/ui.py:field_type in radio',
    'app/domains/forms/ui.py:field_type in select',
    'app/domains/forms/ui.py:field_type!=info',
    'app/domains/forms/ui.py:field_type==checkbox',
    'app/domains/forms/ui.py:field_type==info',
    'app/domains/forms/ui.py:field_type==number',
    'app/domains/forms/ui.py:field_type==rating',
    'app/domains/mail/handlers.py:status==sent',
    'app/domains/media/images.py:mode in LA',
    'app/domains/media/images.py:mode in RGBA',
    'app/domains/media/images.py:mode!=RGB',
    'app/domains/media/images.py:mode!=RGBA',
    'app/domains/media/images.py:mode==P',
    'app/domains/media/pdf.py:mode!=RGB',
    'app/domains/media/router.py:kind==activity_photo',
    'app/domains/media/router.py:kind==sponsor',
    'app/domains/media/service.py:content_type==application/pdf',
    'app/domains/media/service.py:kind==activity_photo',
    'app/domains/media/service.py:kind==activity_poster',
    'app/domains/media/service.py:kind==component_info',
    'app/domains/media/service.py:kind==tenant_logo',
    'app/domains/meetings/service.py:kind==member',
    'app/domains/newsletter/drafting.py:status!=draft',
    'app/domains/reporting/admin_ui.py:layout==pivot',
    'app/domains/reporting/chart.py:format==money',
    'app/domains/reporting/engine.py:layout==detail',
    'app/domains/reporting/exports.py:layout!=detail',
    'app/domains/reporting/pivot.py:layout!=pivot',
    'app/domains/workflow/api.py:status!=done',
    'app/domains/workflow/api.py:status==done',
    'app/domains/workflow/api.py:status==open',
    'app/domains/workflow/handlers.py:status==failed',
    'app/domains/workflow/handlers.py:status==sent',
    'app/domains/workflow/ui.py:subject_type==email_log',
    'app/domains/workflow/ui.py:subject_type==form_submission',
    'app/domains/workflow/ui.py:subject_type==kernel_job',
    'app/domains/workflow/ui.py:subject_type==payment_record',
    'app/kernel/jobs.py:status==pending',
    'app/schemas/chat.py:role!=user',
    'app/ui/__init__.py:kind==sponsor',
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

#: Columns that look like a vocabulary but get no code table (§B4.10).
FK_NOT_OUR_LIST: dict[str, str] = {
    "payment.gateway_payments.status": (
        "Mollie's own list. Mollie can add a value without our migration, and a "
        "foreign key would make the webhook fail at exactly the wrong moment. The "
        "adapter has an ExternalVocabulary enum and maps to our PaymentStatus."),
}

#: Comparisons the vocabulary net catches that compare no code of ours.
LOOSE_STRINGS_NOT_A_CODE: dict[str, str] = {
    "app/domains/payment/ui.py:method==GET": (
        "`request.method` is the HTTP verb, not a payment method — the net matches "
        "on the attribute name and cannot tell the two apart."),
    "app/domains/activities/models.py:content_type==application/pdf": (
        "A MIME type: IANA's list, not ours."),
}

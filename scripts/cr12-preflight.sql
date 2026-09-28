-- CR-12 preflight (generated): values that no code of their list covers.
-- READ-ONLY: SELECT statements only. Run with psql WITHOUT ON_ERROR_STOP, so a
-- column that does not exist on this environment reports an error and the rest
-- still runs. An empty result set for a column means: the key will go on.
-- Each row: the column, the stray value, how many rows hold it.
\pset footer off

-- ai.ai_call_log.capability → ai.ai_capability_codes (7 codes)
SELECT 'ai.ai_call_log.capability' AS column_name, "capability"::text AS stray_value, count(*) AS row_count
FROM ai.ai_call_log
WHERE "capability" IS NOT NULL
  AND "capability"::text NOT IN ('chat', 'dictation', 'image', 'newsletter_drafting', 'ocr', 'reporting', 'translate', '')
GROUP BY "capability" ORDER BY row_count DESC;

-- ai.ai_call_log.provider → ai.ai_provider_codes (3 codes)
SELECT 'ai.ai_call_log.provider' AS column_name, "provider"::text AS stray_value, count(*) AS row_count
FROM ai.ai_call_log
WHERE "provider" IS NOT NULL
  AND "provider"::text NOT IN ('bfl', 'mistral', 'mock', '')
GROUP BY "provider" ORDER BY row_count DESC;

-- ai.ai_call_log.status → ai.ai_status_codes (4 codes)
SELECT 'ai.ai_call_log.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM ai.ai_call_log
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('blocked', 'error', 'moderated', 'ok')
GROUP BY "status" ORDER BY row_count DESC;

-- ai.ai_call_log.surface → ai.ai_surface_codes (3 codes)
SELECT 'ai.ai_call_log.surface' AS column_name, "surface"::text AS stray_value, count(*) AS row_count
FROM ai.ai_call_log
WHERE "surface" IS NOT NULL
  AND "surface"::text NOT IN ('admin', 'designstudio', 'public')
GROUP BY "surface" ORDER BY row_count DESC;

-- meetings.meeting_attendances.status → meetings.attendance_codes (2 codes)
SELECT 'meetings.meeting_attendances.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM meetings.meeting_attendances
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('excused', 'present')
GROUP BY "status" ORDER BY row_count DESC;

-- newsletter.newsletters.audience → newsletter.audience_codes (3 codes)
SELECT 'newsletter.newsletters.audience' AS column_name, "audience"::text AS stray_value, count(*) AS row_count
FROM newsletter.newsletters
WHERE "audience" IS NOT NULL
  AND "audience"::text NOT IN ('both', 'members', 'non_members')
GROUP BY "audience" ORDER BY row_count DESC;

-- mdm.contact_details.contact_type_code → mdm.contact_type_codes (7 codes)
SELECT 'mdm.contact_details.contact_type_code' AS column_name, "contact_type_code"::text AS stray_value, count(*) AS row_count
FROM mdm.contact_details
WHERE "contact_type_code" IS NOT NULL
  AND "contact_type_code"::text NOT IN ('EMAIL', 'FACEBOOK', 'INSTAGRAM', 'MOBILE', 'PHONE', 'TIKTOK', 'WEBSITE')
  AND "contact_type_code"::text NOT IN (SELECT code::text FROM mdm.contact_type_codes)
GROUP BY "contact_type_code" ORDER BY row_count DESC;

-- newsletter.deliveries.kind → newsletter.delivery_kind_codes (2 codes)
SELECT 'newsletter.deliveries.kind' AS column_name, "kind"::text AS stray_value, count(*) AS row_count
FROM newsletter.deliveries
WHERE "kind" IS NOT NULL
  AND "kind"::text NOT IN ('member', 'subscriber')
GROUP BY "kind" ORDER BY row_count DESC;

-- newsletter.deliveries.status → newsletter.delivery_status_codes (4 codes)
SELECT 'newsletter.deliveries.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM newsletter.deliveries
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('failed', 'queued', 'sent', 'skipped')
GROUP BY "status" ORDER BY row_count DESC;

-- designstudio.designs.status → designstudio.design_status_codes (2 codes)
SELECT 'designstudio.designs.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM designstudio.designs
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('draft', 'final')
GROUP BY "status" ORDER BY row_count DESC;

-- designstudio.image_generations.style → designstudio.drawing_style_codes (3 codes)
SELECT 'designstudio.image_generations.style' AS column_name, "style"::text AS stray_value, count(*) AS row_count
FROM designstudio.image_generations
WHERE "style" IS NOT NULL
  AND "style"::text NOT IN ('kleur', 'lijn', 'lijnkleur')
GROUP BY "style" ORDER BY row_count DESC;

-- mail.email_log.email_type → mail.email_type_codes (11 codes)
SELECT 'mail.email_log.email_type' AS column_name, "email_type"::text AS stray_value, count(*) AS row_count
FROM mail.email_log
WHERE "email_type" IS NOT NULL
  AND "email_type"::text NOT IN ('activity_confirmation', 'form_confirmation', 'idea_ack', 'idea_board', 'magic_link', 'meeting', 'member_contact_notice', 'membership_confirmation', 'newsletter', 'newsletter_confirmation', 'other')
GROUP BY "email_type" ORDER BY row_count DESC;

-- reporting.export_log.kind → reporting.export_kind_codes (3 codes)
SELECT 'reporting.export_log.kind' AS column_name, "kind"::text AS stray_value, count(*) AS row_count
FROM reporting.export_log
WHERE "kind" IS NOT NULL
  AND "kind"::text NOT IN ('ad-hoc', 'dataset', 'report')
GROUP BY "kind" ORDER BY row_count DESC;

-- mdm.external_numbers.source → mdm.external_source_codes (1 codes)
SELECT 'mdm.external_numbers.source' AS column_name, "source"::text AS stray_value, count(*) AS row_count
FROM mdm.external_numbers
WHERE "source" IS NOT NULL
  AND "source"::text NOT IN ('ledenadministratie')
GROUP BY "source" ORDER BY row_count DESC;

-- form.form_fields.field_type → form.field_type_codes (10 codes)
SELECT 'form.form_fields.field_type' AS column_name, "field_type"::text AS stray_value, count(*) AS row_count
FROM form.form_fields
WHERE "field_type" IS NOT NULL
  AND "field_type"::text NOT IN ('checkbox', 'email', 'info', 'number', 'phone', 'radio', 'rating', 'select', 'text', 'textarea')
GROUP BY "field_type" ORDER BY row_count DESC;

-- meetings.meeting_files.purpose → meetings.file_purpose_codes (2 codes)
SELECT 'meetings.meeting_files.purpose' AS column_name, "purpose"::text AS stray_value, count(*) AS row_count
FROM meetings.meeting_files
WHERE "purpose" IS NOT NULL
  AND "purpose"::text NOT IN ('attachment', 'sent_pdf')
GROUP BY "purpose" ORDER BY row_count DESC;

-- form.forms.status → form.form_status_codes (3 codes)
SELECT 'form.forms.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM form.forms
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('closed', 'draft', 'open')
GROUP BY "status" ORDER BY row_count DESC;

-- mdm.persons.gender_code → mdm.gender_codes (4 codes)
SELECT 'mdm.persons.gender_code' AS column_name, "gender_code"::text AS stray_value, count(*) AS row_count
FROM mdm.persons
WHERE "gender_code" IS NOT NULL
  AND "gender_code"::text NOT IN ('F', 'M', 'U', 'X')
  AND "gender_code"::text NOT IN (SELECT code::text FROM mdm.gender_codes)
GROUP BY "gender_code" ORDER BY row_count DESC;

-- designstudio.image_generations.status → designstudio.generation_status_codes (6 codes)
SELECT 'designstudio.image_generations.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM designstudio.image_generations
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('discarded', 'failed', 'fetched', 'picked', 'refused', 'requested')
GROUP BY "status" ORDER BY row_count DESC;

-- mdm.organization_identifications.scheme → mdm.identification_scheme_codes (2 codes)
SELECT 'mdm.organization_identifications.scheme' AS column_name, "scheme"::text AS stray_value, count(*) AS row_count
FROM mdm.organization_identifications
WHERE "scheme" IS NOT NULL
  AND "scheme"::text NOT IN ('KBO', 'VAT')
  AND "scheme"::text NOT IN (SELECT code::text FROM mdm.identification_schemes)
GROUP BY "scheme" ORDER BY row_count DESC;

-- designstudio.designs.inset_corner → designstudio.inset_corner_codes (4 codes)
SELECT 'designstudio.designs.inset_corner' AS column_name, "inset_corner"::text AS stray_value, count(*) AS row_count
FROM designstudio.designs
WHERE "inset_corner" IS NOT NULL
  AND "inset_corner"::text NOT IN ('bottom_left', 'bottom_right', 'top_left', 'top_right')
GROUP BY "inset_corner" ORDER BY row_count DESC;

-- public.kernel_jobs.status → public.kernel_job_status_codes (4 codes)
SELECT 'public.kernel_jobs.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM public.kernel_jobs
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('done', 'failed', 'pending', 'running')
GROUP BY "status" ORDER BY row_count DESC;

-- designstudio.design_renditions.layout_code → designstudio.layout_codes (2 codes)
SELECT 'designstudio.design_renditions.layout_code' AS column_name, "layout_code"::text AS stray_value, count(*) AS row_count
FROM designstudio.design_renditions
WHERE "layout_code" IS NOT NULL
  AND "layout_code"::text NOT IN ('feed_portrait', 'print_a')
GROUP BY "layout_code" ORDER BY row_count DESC;

-- mdm.organizations.legal_form → mdm.legal_form_codes (3 codes)
SELECT 'mdm.organizations.legal_form' AS column_name, "legal_form"::text AS stray_value, count(*) AS row_count
FROM mdm.organizations
WHERE "legal_form" IS NOT NULL
  AND "legal_form"::text NOT IN ('BEDRIJF', 'FEITELIJKE_VERENIGING', 'VZW')
  AND "legal_form"::text NOT IN (SELECT code::text FROM mdm.legal_form_codes)
GROUP BY "legal_form" ORDER BY row_count DESC;

-- newsletter.newsletters.status → newsletter.letter_status_codes (3 codes)
SELECT 'newsletter.newsletters.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM newsletter.newsletters
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('draft', 'sending', 'sent')
GROUP BY "status" ORDER BY row_count DESC;

-- mail.email_log.status → mail.mail_status_codes (4 codes)
SELECT 'mail.email_log.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM mail.email_log
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('failed', 'logged', 'sent', 'skipped')
GROUP BY "status" ORDER BY row_count DESC;

-- media.media_assets.kind → media.media_kind_codes (9 codes)
SELECT 'media.media_assets.kind' AS column_name, "kind"::text AS stray_value, count(*) AS row_count
FROM media.media_assets
WHERE "kind" IS NOT NULL
  AND "kind"::text NOT IN ('activity_photo', 'activity_poster', 'component_info', 'design_image', 'design_render', 'newsletter_file', 'page_image', 'sponsor', 'tenant_logo')
GROUP BY "kind" ORDER BY row_count DESC;

-- meetings.meetings.status → meetings.meeting_status_codes (3 codes)
SELECT 'meetings.meetings.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM meetings.meetings
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('agenda', 'report', 'sent')
GROUP BY "status" ORDER BY row_count DESC;

-- newsletter.drafting_messages.role → newsletter.message_role_codes (2 codes)
SELECT 'newsletter.drafting_messages.role' AS column_name, "role"::text AS stray_value, count(*) AS row_count
FROM newsletter.drafting_messages
WHERE "role" IS NOT NULL
  AND "role"::text NOT IN ('author', 'raakje')
GROUP BY "role" ORDER BY row_count DESC;

-- mdm.organization_persons.relation_type → mdm.organization_relation_type_codes (1 codes)
SELECT 'mdm.organization_persons.relation_type' AS column_name, "relation_type"::text AS stray_value, count(*) AS row_count
FROM mdm.organization_persons
WHERE "relation_type" IS NOT NULL
  AND "relation_type"::text NOT IN ('BOARD_MEETING')
  AND "relation_type"::text NOT IN (SELECT code::text FROM mdm.organization_relation_types)
GROUP BY "relation_type" ORDER BY row_count DESC;

-- mdm.organizations.org_type → mdm.organization_type_codes (3 codes)
SELECT 'mdm.organizations.org_type' AS column_name, "org_type"::text AS stray_value, count(*) AS row_count
FROM mdm.organizations
WHERE "org_type" IS NOT NULL
  AND "org_type"::text NOT IN ('ACCOUNT', 'PLATFORM', 'UNIT')
GROUP BY "org_type" ORDER BY row_count DESC;

-- payment.payment_records.payable_type → payment.payable_type_codes (2 codes)
SELECT 'payment.payment_records.payable_type' AS column_name, "payable_type"::text AS stray_value, count(*) AS row_count
FROM payment.payment_records
WHERE "payable_type" IS NOT NULL
  AND "payable_type"::text NOT IN ('membership', 'registration')
GROUP BY "payable_type" ORDER BY row_count DESC;

-- payment.payment_records.method → mdm.payment_method_codes (3 codes)
SELECT 'payment.payment_records.method' AS column_name, "method"::text AS stray_value, count(*) AS row_count
FROM payment.payment_records
WHERE "method" IS NOT NULL
  AND "method"::text NOT IN ('cash', 'online', 'transfer')
GROUP BY "method" ORDER BY row_count DESC;

-- activities.registrations.payment_method → mdm.payment_method_codes (3 codes)
SELECT 'activities.registrations.payment_method' AS column_name, "payment_method"::text AS stray_value, count(*) AS row_count
FROM activities.registrations
WHERE "payment_method" IS NOT NULL
  AND "payment_method"::text NOT IN ('cash', 'online', 'transfer', 'ONLINE', 'OVERSCHRIJVING')
GROUP BY "payment_method" ORDER BY row_count DESC;

-- payment.gateway_payments.provider → payment.payment_provider_codes (1 codes)
SELECT 'payment.gateway_payments.provider' AS column_name, "provider"::text AS stray_value, count(*) AS row_count
FROM payment.gateway_payments
WHERE "provider" IS NOT NULL
  AND "provider"::text NOT IN ('mollie')
GROUP BY "provider" ORDER BY row_count DESC;

-- payment.payment_records.status → payment.payment_status_codes (4 codes)
SELECT 'payment.payment_records.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM payment.payment_records
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('cancelled', 'failed', 'paid', 'pending')
GROUP BY "status" ORDER BY row_count DESC;

-- payment.payment_records.type → payment.payment_type_codes (2 codes)
SELECT 'payment.payment_records.type' AS column_name, "type"::text AS stray_value, count(*) AS row_count
FROM payment.payment_records
WHERE "type" IS NOT NULL
  AND "type"::text NOT IN ('charge', 'refund')
GROUP BY "type" ORDER BY row_count DESC;

-- designstudio.designs.preset → designstudio.preset_codes (3 codes)
SELECT 'designstudio.designs.preset' AS column_name, "preset"::text AS stray_value, count(*) AS row_count
FROM designstudio.designs
WHERE "preset" IS NOT NULL
  AND "preset"::text NOT IN ('beeld', 'eenvoudig', 'tekst')
GROUP BY "preset" ORDER BY row_count DESC;

-- activities.registrations.registration_type → activities.registration_type_codes (2 codes)
SELECT 'activities.registrations.registration_type' AS column_name, "registration_type"::text AS stray_value, count(*) AS row_count
FROM activities.registrations
WHERE "registration_type" IS NOT NULL
  AND "registration_type"::text NOT IN ('FAMILY', 'INDIVIDUAL')
  AND "registration_type"::text NOT IN (SELECT code::text FROM public.registration_type_codes)
GROUP BY "registration_type" ORDER BY row_count DESC;

-- activities.activity_sub_registrations.registration_type_code → activities.registration_type_codes (2 codes)
SELECT 'activities.activity_sub_registrations.registration_type_code' AS column_name, "registration_type_code"::text AS stray_value, count(*) AS row_count
FROM activities.activity_sub_registrations
WHERE "registration_type_code" IS NOT NULL
  AND "registration_type_code"::text NOT IN ('FAMILY', 'INDIVIDUAL')
  AND "registration_type_code"::text NOT IN (SELECT code::text FROM public.registration_type_codes)
GROUP BY "registration_type_code" ORDER BY row_count DESC;

-- mdm.member_persons.relation_type → mdm.relation_type_codes (3 codes)
SELECT 'mdm.member_persons.relation_type' AS column_name, "relation_type"::text AS stray_value, count(*) AS row_count
FROM mdm.member_persons
WHERE "relation_type" IS NOT NULL
  AND "relation_type"::text NOT IN ('HOOFDLID', 'KIND', 'PARTNER')
  AND "relation_type"::text NOT IN (SELECT code::text FROM mdm.relation_type_codes)
GROUP BY "relation_type" ORDER BY row_count DESC;

-- designstudio.design_renditions.variant → designstudio.render_variant_codes (5 codes)
SELECT 'designstudio.design_renditions.variant' AS column_name, "variant"::text AS stray_value, count(*) AS row_count
FROM designstudio.design_renditions
WHERE "variant" IS NOT NULL
  AND "variant"::text NOT IN ('jpeg', 'pdf', 'png', 'svg', 'svg_edited')
GROUP BY "variant" ORDER BY row_count DESC;

-- newsletter.newsletters.reply_to_mode → newsletter.reply_to_mode_codes (2 codes)
SELECT 'newsletter.newsletters.reply_to_mode' AS column_name, "reply_to_mode"::text AS stray_value, count(*) AS row_count
FROM newsletter.newsletters
WHERE "reply_to_mode" IS NOT NULL
  AND "reply_to_mode"::text NOT IN ('association', 'sender')
GROUP BY "reply_to_mode" ORDER BY row_count DESC;

-- auth.user_roles.role_code → auth.role_codes (6 codes)
SELECT 'auth.user_roles.role_code' AS column_name, "role_code"::text AS stray_value, count(*) AS row_count
FROM auth.user_roles
WHERE "role_code" IS NOT NULL
  AND "role_code"::text NOT IN ('ACCOUNT_ADMIN', 'ADMIN', 'FINANCE', 'MEMBER', 'OPERATOR', 'USER')
  AND "role_code"::text NOT IN (SELECT code::text FROM public.role_codes)
GROUP BY "role_code" ORDER BY row_count DESC;

-- workflow.workflow_tasks.required_role → auth.role_codes (6 codes)
SELECT 'workflow.workflow_tasks.required_role' AS column_name, "required_role"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_tasks
WHERE "required_role" IS NOT NULL
  AND "required_role"::text NOT IN ('ACCOUNT_ADMIN', 'ADMIN', 'FINANCE', 'MEMBER', 'OPERATOR', 'USER')
  AND "required_role"::text NOT IN (SELECT code::text FROM public.role_codes)
GROUP BY "required_role" ORDER BY row_count DESC;

-- workflow.workflow_instances.status → workflow.run_status_codes (3 codes)
SELECT 'workflow.workflow_instances.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_instances
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('done', 'failed', 'running')
GROUP BY "status" ORDER BY row_count DESC;

-- meetings.meeting_sections.kind → meetings.section_kind_codes (6 codes)
SELECT 'meetings.meeting_sections.kind' AS column_name, "kind"::text AS stray_value, count(*) AS row_count
FROM meetings.meeting_sections
WHERE "kind" IS NOT NULL
  AND "kind"::text NOT IN ('CUSTOM', 'EVALUATION', 'IDEAS', 'MEMBERS', 'MISC', 'UPCOMING')
GROUP BY "kind" ORDER BY row_count DESC;

-- workflow.workflow_tasks.subject_type → workflow.subject_type_codes (4 codes)
SELECT 'workflow.workflow_tasks.subject_type' AS column_name, "subject_type"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_tasks
WHERE "subject_type" IS NOT NULL
  AND "subject_type"::text NOT IN ('email_log', 'form_submission', 'kernel_job', 'payment_record')
GROUP BY "subject_type" ORDER BY row_count DESC;

-- workflow.workflow_instances.subject_type → workflow.subject_type_codes (4 codes)
SELECT 'workflow.workflow_instances.subject_type' AS column_name, "subject_type"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_instances
WHERE "subject_type" IS NOT NULL
  AND "subject_type"::text NOT IN ('email_log', 'form_submission', 'kernel_job', 'payment_record')
GROUP BY "subject_type" ORDER BY row_count DESC;

-- newsletter.subscribers.source → newsletter.subscriber_source_codes (3 codes)
SELECT 'newsletter.subscribers.source' AS column_name, "source"::text AS stray_value, count(*) AS row_count
FROM newsletter.subscribers
WHERE "source" IS NOT NULL
  AND "source"::text NOT IN ('admin', 'import', 'public_form')
GROUP BY "source" ORDER BY row_count DESC;

-- newsletter.subscribers.status → newsletter.subscriber_status_codes (3 codes)
SELECT 'newsletter.subscribers.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM newsletter.subscribers
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('confirmed', 'pending', 'unsubscribed')
GROUP BY "status" ORDER BY row_count DESC;

-- workflow.workflow_tasks.kind → workflow.task_kind_codes (6 codes)
SELECT 'workflow.workflow_tasks.kind' AS column_name, "kind"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_tasks
WHERE "kind" IS NOT NULL
  AND "kind"::text NOT IN ('bericht.behartigen', 'kernel.job_gefaald', 'mail.definitief_gefaald', 'payment.refund_bevestigen', 'payment.webhook_mismatch', 'payment.wees_record')
GROUP BY "kind" ORDER BY row_count DESC;

-- workflow.workflow_tasks.status → workflow.task_status_codes (2 codes)
SELECT 'workflow.workflow_tasks.status' AS column_name, "status"::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_tasks
WHERE "status" IS NOT NULL
  AND "status"::text NOT IN ('done', 'open')
GROUP BY "status" ORDER BY row_count DESC;

-- workflow.workflow_instances.definition_code → workflow.workflow_definitions.code
-- (not a code list: the definitions table is its own target, migration 165)
SELECT 'workflow.workflow_instances.definition_code' AS column_name, definition_code::text AS stray_value, count(*) AS row_count
FROM workflow.workflow_instances
WHERE definition_code NOT IN (SELECT code FROM workflow.workflow_definitions)
GROUP BY definition_code ORDER BY row_count DESC;

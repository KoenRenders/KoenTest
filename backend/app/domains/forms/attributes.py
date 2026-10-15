"""The attributes of the `forms` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="forms.form.title",
        columns=("form.forms.title",),
        label=None,
        name_en="Title",
        help="The title of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form.slug",
        columns=("form.forms.slug",),
        label=None,
        name_en="Slug",
        help="The slug of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form.description",
        columns=("form.forms.description",),
        label=None,
        name_en="Description",
        help="The description of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form.share_token",
        columns=("form.forms.share_token",),
        label=None,
        name_en="Share token",
        help="The share token of the form.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="forms.form.status",
        columns=("form.forms.status",),
        label=None,
        name_en="Status",
        help="The status of the form, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="forms.form.requires_login",
        columns=("form.forms.requires_login",),
        label=None,
        name_en="Requires login",
        help="The requires login of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form.max_submissions",
        columns=("form.forms.max_submissions",),
        label=None,
        name_en="Max submissions",
        help="The max submissions of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form.send_confirmation",
        columns=("form.forms.send_confirmation",),
        label=None,
        name_en="Send confirmation",
        help="The send confirmation of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form.confirmation_message",
        columns=("form.forms.confirmation_message",),
        label=None,
        name_en="Confirmation message",
        help="The confirmation message of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="forms.form.allow_edit",
        columns=("form.forms.allow_edit",),
        label=None,
        name_en="Allow edit",
        help="The allow edit of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form.is_anonymous",
        columns=("form.forms.is_anonymous",),
        label=None,
        name_en="Is anonymous",
        help="The is anonymous of the form.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.field_type",
        columns=("form.form_fields.field_type",),
        label=None,
        name_en="Field type",
        help="The field type of the form field, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="forms.form_field.label",
        columns=("form.form_fields.label",),
        label=None,
        name_en="Label",
        help="The label of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field.help_text",
        columns=("form.form_fields.help_text",),
        label=None,
        name_en="Help text",
        help="The help text of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="forms.form_field.required",
        columns=("form.form_fields.required",),
        label=None,
        name_en="Required",
        help="The required of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.position",
        columns=("form.form_fields.position",),
        label=None,
        name_en="Position",
        help="The position of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.min_value",
        columns=("form.form_fields.min_value",),
        label=None,
        name_en="Min value",
        help="The min value of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.max_value",
        columns=("form.form_fields.max_value",),
        label=None,
        name_en="Max value",
        help="The max value of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.min_length",
        columns=("form.form_fields.min_length",),
        label=None,
        name_en="Min length",
        help="The min length of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.max_length",
        columns=("form.form_fields.max_length",),
        label=None,
        name_en="Max length",
        help="The max length of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.regex_pattern",
        columns=("form.form_fields.regex_pattern",),
        label=None,
        name_en="Regex pattern",
        help="The regex pattern of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field.rating_max",
        columns=("form.form_fields.rating_max",),
        label=None,
        name_en="Rating max",
        help="The rating max of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field.rating_low_label",
        columns=("form.form_fields.rating_low_label",),
        label=None,
        name_en="Rating low label",
        help="The rating low label of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field.rating_high_label",
        columns=("form.form_fields.rating_high_label",),
        label=None,
        name_en="Rating high label",
        help="The rating high label of the form field.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field_option.label",
        columns=("form.form_field_options.label",),
        label=None,
        name_en="Label",
        help="The label of the form field option.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field_option.value",
        columns=("form.form_field_options.value",),
        label=None,
        name_en="Value",
        help="The value of the form field option.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_field_option.position",
        columns=("form.form_field_options.position",),
        label=None,
        name_en="Position",
        help="The position of the form field option.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field_option.is_other",
        columns=("form.form_field_options.is_other",),
        label=None,
        name_en="Is other",
        help="The is other of the form field option.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_field_option.skip_to_end",
        columns=("form.form_field_options.skip_to_end",),
        label=None,
        name_en="Skip to end",
        help="The skip to end of the form field option.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_section.title",
        columns=("form.form_sections.title",),
        label=None,
        name_en="Title",
        help="The title of the form section.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_section.description",
        columns=("form.form_sections.description",),
        label=None,
        name_en="Description",
        help="The description of the form section.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="forms.form_section.position",
        columns=("form.form_sections.position",),
        label=None,
        name_en="Position",
        help="The position of the form section.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_section.next_is_end",
        columns=("form.form_sections.next_is_end",),
        label=None,
        name_en="Next is end",
        help="The next is end of the form section.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_submission.submitted_at",
        columns=("form.form_submissions.submitted_at",),
        label=None,
        name_en="Submitted at",
        help="The submitted at of the form submission.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_submission.submitter_name",
        columns=("form.form_submissions.submitter_name",),
        label=None,
        name_en="Submitter name",
        help="The submitter name of the form submission.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="forms.form_submission.submitter_email",
        columns=("form.form_submissions.submitter_email",),
        label=None,
        name_en="Submitter email",
        help="The submitter email of the form submission.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="forms.form_submission.edit_token",
        columns=("form.form_submissions.edit_token",),
        label=None,
        name_en="Edit token",
        help="The edit token of the form submission.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="forms.form_submission.attached",
        columns=("form.form_submissions.attached",),
        label=None,
        name_en="Attached",
        help="The attached of the form submission.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_submission_answer.value_text",
        columns=("form.form_submission_answers.value_text",),
        label=None,
        name_en="Value text",
        help="The value text of the form submission answer.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="forms.form_submission_answer.value_number",
        columns=("form.form_submission_answers.value_number",),
        label=None,
        name_en="Value number",
        help="The value number of the form submission answer.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="forms.form_submission_answer.value_rating",
        columns=("form.form_submission_answers.value_rating",),
        label=None,
        name_en="Value rating",
        help="The value rating of the form submission answer.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)

"""The attributes of the `workflow` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="workflow.workflow_definition.name",
        columns=("workflow.workflow_definitions.name",),
        label=None,
        name_en="Name",
        help="The name of the workflow definition.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_definition.steps",
        columns=("workflow.workflow_definitions.steps",),
        label=None,
        name_en="Steps",
        help="The steps of the workflow definition.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_instance.subject_type",
        columns=("workflow.workflow_instances.subject_type",),
        label=None,
        name_en="Subject type",
        help="The subject type of the workflow instance, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_instance.subject_id",
        columns=("workflow.workflow_instances.subject_id",),
        label=None,
        name_en="Subject id",
        help="The subject id of the workflow instance.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_instance.current_step",
        columns=("workflow.workflow_instances.current_step",),
        label=None,
        name_en="Current step",
        help="The current step of the workflow instance.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="workflow.workflow_instance.status",
        columns=("workflow.workflow_instances.status",),
        label=None,
        name_en="Status",
        help="The status of the workflow instance, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_instance.done_at",
        columns=("workflow.workflow_instances.done_at",),
        label=None,
        name_en="Done at",
        help="The done at of the workflow instance.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="workflow.workflow_task.kind",
        columns=("workflow.workflow_tasks.kind",),
        label="Soort",
        name_en="Kind",
        help="Wat voor taak het is: een terugbetaling bevestigen, een mislukte e-mail, een webhook die afwijkt, een mislukte achtergrondtaak.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_task.title",
        columns=("workflow.workflow_tasks.title",),
        label=None,
        name_en="Title",
        help="The title of the workflow task.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_task.subject_type",
        columns=("workflow.workflow_tasks.subject_type",),
        label=None,
        name_en="Subject type",
        help="The subject type of the workflow task, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_task.subject_id",
        columns=("workflow.workflow_tasks.subject_id",),
        label=None,
        name_en="Subject id",
        help="The subject id of the workflow task.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_task.status",
        columns=("workflow.workflow_tasks.status",),
        label="Status",
        name_en="Status",
        help="Of de taak open staat of afgehandeld is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_task.required_role",
        columns=("workflow.workflow_tasks.required_role",),
        label="Voor welke rol",
        name_en="Required role",
        help="De rol die deze taak hoort op te pakken — wie ze toegewezen krijgt, niet wie ze afhandelde.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="workflow.workflow_task.decision",
        columns=("workflow.workflow_tasks.decision",),
        label=None,
        name_en="Decision",
        help="The decision of the workflow task.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="workflow.workflow_task.done_at",
        columns=("workflow.workflow_tasks.done_at",),
        label="Afhandeldatum",
        name_en="Done at",
        help="Wanneer de taak afgesloten is. Leeg zolang ze open staat.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="workflow.workflow_task.done_by",
        columns=("workflow.workflow_tasks.done_by",),
        label="Afgehandeld door",
        name_en="Done by",
        help="Het e-mailadres van wie de taak afsloot. Groepeerbaar: dat is de vraag 'hoeveel heeft ieder van ons afgewerkt'.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
)


# The data the reporting universe stands on that no single stored column is (CR-33 phase 1).
UNIVERSE_ENTRIES: tuple[Attribute, ...] = (
    Attribute(
        key="workflow.workflow_task.created_at",
        columns=("workflow.workflow_tasks.created_at",),
        label="Aanmaakdatum taak",
        name_en="Created at",
        help="Wanneer de taak ontstond.",
        ai_exposure=AiExposure.INTERNAL,
    ),
)

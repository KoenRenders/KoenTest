"""The attributes of the `kernel` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="kernel.kernel_job.name",
        columns=("public.kernel_jobs.name",),
        label=None,
        name_en="Name",
        help="The name of the kernel job.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="kernel.kernel_job.payload",
        columns=("public.kernel_jobs.payload",),
        label=None,
        name_en="Payload",
        help="The payload of the kernel job.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="kernel.kernel_job.status",
        columns=("public.kernel_jobs.status",),
        label=None,
        name_en="Status",
        help="The status of the kernel job, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="kernel.kernel_job.run_at",
        columns=("public.kernel_jobs.run_at",),
        label=None,
        name_en="Run at",
        help="The run at of the kernel job.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="kernel.kernel_job.attempts",
        columns=("public.kernel_jobs.attempts",),
        label=None,
        name_en="Attempts",
        help="The attempts of the kernel job.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="kernel.kernel_job.max_attempts",
        columns=("public.kernel_jobs.max_attempts",),
        label=None,
        name_en="Max attempts",
        help="The max attempts of the kernel job.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="kernel.kernel_job.last_error",
        columns=("public.kernel_jobs.last_error",),
        label=None,
        name_en="Last error",
        help="The last error of the kernel job.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="kernel.tenant_setting.key",
        columns=("public.kernel_tenant_settings.key",),
        label=None,
        name_en="Key",
        help="The key of the tenant setting.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="kernel.tenant_setting.value",
        columns=("public.kernel_tenant_settings.value",),
        label=None,
        name_en="Value",
        help="The value of the tenant setting.",
        ai_exposure=AiExposure.NONE,  # K10
    ),
    Attribute(
        key="kernel.tenant_setting.value_encrypted",
        columns=("public.kernel_tenant_settings.value_encrypted",),
        label=None,
        name_en="Value encrypted",
        help="The value encrypted of the tenant setting.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
)

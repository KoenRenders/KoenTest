"""The attributes of the `auth` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="auth.login_token.email",
        columns=("auth.login_tokens.email",),
        label=None,
        name_en="Email",
        help="The email of the login token.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="auth.login_token.token",
        columns=("auth.login_tokens.token",),
        label=None,
        name_en="Token",
        help="The token of the login token.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="auth.login_token.otp_code",
        columns=("auth.login_tokens.otp_code",),
        label="Code uit de e-mail",
        name_en="Otp code",
        help="The otp code of the login token.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="auth.login_token.expires_at",
        columns=("auth.login_tokens.expires_at",),
        label=None,
        name_en="Expires at",
        help="The expires at of the login token.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="auth.login_token.used",
        columns=("auth.login_tokens.used",),
        label=None,
        name_en="Used",
        help="The used of the login token.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="auth.login_token.attempts",
        columns=("auth.login_tokens.attempts",),
        label=None,
        name_en="Attempts",
        help="The attempts of the login token.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="auth.login_token.purpose",
        columns=("auth.login_tokens.purpose",),
        label=None,
        name_en="Purpose",
        help="The purpose of the login token, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="auth.login_token.payload",
        columns=("auth.login_tokens.payload",),
        label=None,
        name_en="Payload",
        help="The payload of the login token.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="auth.user.email",
        columns=("auth.users.email",),
        label="E-mail",
        name_en="Email",
        help="The email of the user.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="auth.user.is_active",
        columns=("auth.users.is_active",),
        label="Actief",
        name_en="Is active",
        help="The is active of the user.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="auth.user_role.role_code",
        columns=("auth.user_roles.role_code",),
        label="Rollen",
        name_en="Role code",
        help="The role code of the user role, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
)

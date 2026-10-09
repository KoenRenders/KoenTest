"""Publieke facade van het auth-component (fase 1b, #399).

Andere componenten en de oude wereld importeren authenticatie/autorisatie
uitsluitend via deze module. De implementatie leeft in service.py (rollen per
request), session.py (HttpOnly-sessie + CSRF voor server-rendered schermen),
member_identity.py (e-mail -> Person/gezin), login.py (the sign-in flow) and
users.py (the users service of the back office). There is no JSON API and no
bearer token: the session is the one identity (CR-13 phase 4b, #1251).
"""

# CR-12 phase 2: the role list belongs to this domain's public surface, so
# that `workflow` reaches its FK target and its enum through one door.
from app.domains.auth.codes import LOGIN_PURPOSE, RIGHT, ROLE  # noqa: F401
from app.domains.auth.login import (  # noqa: F401
    AccountRequest,
    AccountRequestInvalid,
    Consumed,
    consume_code,
    consume_link,
    start_account,
    start_login,
)
from app.domains.auth.member_identity import (  # noqa: F401
    address_says_nobody,
    find_persons_by_email,
    has_household,
    login_person_for_email,
    resolve_household,
    sign_in_identity,
)
from app.domains.auth.models import (  # noqa: F401
    LoginPurpose,
    LoginToken,
    Right,
    Role,
    RoleCode,
    RoleLabel,
    RoleRight,
    User,
    UserRole,
)
from app.domains.auth.service import (  # noqa: F401
    get_user_role_rows,
    get_user_roles,
    has_login,
    landing_for,
    may,
    rights_of,
)
from app.domains.auth.session import (  # noqa: F401
    SESSION_COOKIE,
    admin_user_by_email,
    admits_admin_ui,
    back_office_home,
    csrf_from_request,
    csrf_token_for,
    make_session_value,
    may_mutate_payments,
    may_view_payments,
    read_session_value,
    require_admin_ui,
    require_csrf,
    require_finance_mutation,
    require_finance_ui,
    require_platform_right,
    require_right,
    require_tenant_workspace,
    session_cookie_secure,
    set_session_cookie,
)
from app.domains.auth.users import (  # noqa: F401
    is_platform_workspace,
    list_assignable_roles,
    role_options,
)

__all__ = [
    "list_assignable_roles",
    "role_options",
    "start_login",
    "find_persons_by_email",
    "login_person_for_email",
    "resolve_household",
    "has_household",
    "address_says_nobody",
    "sign_in_identity",
    "LoginPurpose",
    "LOGIN_PURPOSE",
    "LoginToken",
    "Role",
    "RoleCode",
    "RoleLabel",
    "ROLE",
    "Right",
    "RIGHT",
    "RoleRight",
    "rights_of",
    "may",
    "require_right",
    "User",
    "UserRole",
    "get_user_role_rows",
    "get_user_roles",
    "has_login",
    "landing_for",
    "SESSION_COOKIE",
    "admin_user_by_email",
    "admits_admin_ui",
    "back_office_home",
    "csrf_from_request",
    "csrf_token_for",
    "make_session_value",
    "read_session_value",
    "require_admin_ui",
    "may_mutate_payments",
    "require_finance_mutation",
    "may_view_payments",
    "require_finance_ui",
    "require_platform_right",
    "require_tenant_workspace",
    "is_platform_workspace",
    "require_csrf",
    "session_cookie_secure",
    "set_session_cookie",
]

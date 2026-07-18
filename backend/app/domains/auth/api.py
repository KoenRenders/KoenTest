"""Publieke facade van het auth-component (fase 1b, #399).

Andere componenten en de oude wereld importeren authenticatie/autorisatie
uitsluitend via deze module. De implementatie leeft in service.py (JWT +
rol-dependencies), session.py (HttpOnly-sessie + CSRF voor server-rendered
schermen), member_identity.py (e-mail -> Person/gezin) en router.py
(login-flow + gebruikersbeheer).
"""
from app.domains.auth.member_identity import (  # noqa: F401
    find_persons_by_email,
    login_person_for_email,
    resolve_household,
)
from app.domains.auth.models import ApiKey, LoginToken, User, UserRole  # noqa: F401
from app.domains.auth.service import (  # noqa: F401
    API_KEY_HEADER,
    create_access_token,
    decode_token,
    get_current_admin,
    get_current_finance,
    get_current_identity,
    get_current_member,
    get_finance_or_admin,
    get_user_roles,
    hash_api_key,
    require_api_key,
    require_member,
    require_roles,
)
from app.domains.auth.session import (  # noqa: F401
    SESSION_COOKIE,
    admin_user_by_email,
    csrf_from_request,
    csrf_token_for,
    make_session_value,
    read_session_value,
    require_admin_ui,
    require_finance_ui,
    require_csrf,
    set_session_cookie,
)

__all__ = [
    "find_persons_by_email", "login_person_for_email", "resolve_household",
    "ApiKey", "LoginToken", "User", "UserRole",
    "API_KEY_HEADER", "hash_api_key", "require_api_key",
    "create_access_token", "decode_token", "get_current_admin",
    "get_current_finance", "get_current_identity", "get_current_member",
    "get_finance_or_admin", "get_user_roles", "require_member", "require_roles",
    "SESSION_COOKIE", "admin_user_by_email", "csrf_from_request",
    "csrf_token_for", "make_session_value",
    "read_session_value", "require_admin_ui", "require_finance_ui", "require_csrf",
    "set_session_cookie",
]

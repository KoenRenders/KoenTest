# auth — componentcontract (fase 1b, #399)

**Doel.** Identiteit en autorisatie: de e-maillogin-flow (magic-link + OTP),
rol-afleiding per request, lid-identificatie (e-mail → Person),
de HttpOnly-sessie + CSRF voor server-rendered schermen, en gebruikersbeheer.

Since CR-13 phase 4b (#1251) the session is the one identity: the JSON routes
under `/api/v1/auth` and `/api/v1/users`, the bearer token they issued and the
guards that read it are gone — no caller was found for any of them.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Rollen** (`service.py`): `get_user_roles`, `get_user_role_rows`,
  `landing_for`, `has_login` — what someone may, asked of the data per request.
- **Sessie/CSRF** (`session.py`, #398): `SESSION_COOKIE`, `make_session_value`,
  `read_session_value`, `set_session_cookie`, `csrf_token_for`,
  `require_admin_ui`, `require_csrf`.
- **Lid-identiteit** (`member_identity.py`): `find_persons_by_email`,
  `resolve_household`, `login_person_for_email`.
- **Modellen als type**: `User`, `UserRole`, `LoginToken`, `ApiKey` (voor
  Depends-annotaties; queries erop horen binnen dit component).
- **Machine-consumenten** (§19.3): none. The guard `require_api_key` never
  guarded a route and left with the API-key routes; the model `ApiKey` and the
  table `auth.api_keys` (migratie 077) hold no row.

## Router

None. The sign-in is the screen's (`ui.py`: `/aanmelden`, `/aanmelden/code`, the
mail's link); the users screen (`admin_ui.py`) calls `users.py` as its service.

## Data

Schema `auth`: `users`, `user_roles`, `login_tokens` (migratie 076). Bewust
géén FK naar `public.role_codes` (§8: geen cross-schema FK's) — rolcodes
worden in de servicelaag gevalideerd. Lid-zijn heeft geen user-record: de
enige brug tussen backoffice-accounts en het ledendomein is de e-mailwaarde.

## Principes

- De sessie bevat enkel identiteit (het e-mailadres); capabilities worden per
  request uit de data afgeleid — nooit naast de identiteit bewaard.
- OTP's worden gehasht opgeslagen (SHA-256 + SECRET_KEY-pepper, #395), met
  brute-force-lockout (#268).

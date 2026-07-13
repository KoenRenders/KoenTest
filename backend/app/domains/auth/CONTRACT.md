# auth — componentcontract (fase 1b, #399)

**Doel.** Identiteit en autorisatie: de e-maillogin-flow (magic-link + OTP),
JWT-uitgifte, rol-afleiding per request, lid-identificatie (e-mail → Person),
de HttpOnly-sessie + CSRF voor server-rendered schermen, en gebruikersbeheer.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **JWT/rollen** (`service.py`): `create_access_token`, `decode_token`,
  `get_current_identity`, `get_user_roles`, `require_roles`,
  `get_current_admin`, `get_current_finance`, `get_finance_or_admin`,
  `get_current_member`, `require_member`.
- **Sessie/CSRF** (`session.py`, #398): `SESSION_COOKIE`, `make_session_value`,
  `read_session_value`, `set_session_cookie`, `csrf_token_for`,
  `require_admin_ui`, `require_csrf`.
- **Lid-identiteit** (`member_identity.py`): `find_persons_by_email`,
  `resolve_household`, `login_person_for_email`.
- **Modellen als type**: `User`, `UserRole`, `LoginToken`, `ApiKey` (voor
  Depends-annotaties; queries erop horen binnen dit component).
- **Machine-consumenten** (§19.3): `require_api_key` (X-API-Key-header),
  `hash_api_key`, `API_KEY_HEADER`. Beheer via `/auth/api-keys` (admin); de
  key is exact één keer zichtbaar bij aanmaak en wordt enkel gehasht bewaard
  (tabel `auth.api_keys`, migratie 077).

## Router

`router.py` — `/auth/*` (request-login, verify-login, verify-otp, me,
member/me) + gebruikersbeheer `/users/*` (via `users.py`), gemount onder
`/api/v1`.

## Data

Schema `auth`: `users`, `user_roles`, `login_tokens` (migratie 076). Bewust
géén FK naar `public.role_codes` (§8: geen cross-schema FK's) — rolcodes
worden in de servicelaag gevalideerd. Lid-zijn heeft geen user-record: de
enige brug tussen backoffice-accounts en het ledendomein is de e-mailwaarde.

## Principes

- Het token bevat enkel identiteit (`sub` = e-mail); capabilities worden per
  request uit de data afgeleid — nooit in het token gebakken.
- OTP's worden gehasht opgeslagen (SHA-256 + SECRET_KEY-pepper, #395), met
  brute-force-lockout (#268).

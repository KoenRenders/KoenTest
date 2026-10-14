# auth — identity, rights and the session

*First written for fase 1b, #399.*

## Purpose and process

**Doel.** Identiteit en autorisatie: de e-maillogin-flow (magic-link + OTP),
rol-afleiding per request, lid-identificatie (e-mail → Person),
de HttpOnly-sessie + CSRF voor server-rendered schermen, en gebruikersbeheer.

Since CR-13 phase 4b (#1251) the session is the one identity: the JSON routes
under `/api/v1/auth` and `/api/v1/users`, the bearer token they issued and the
guards that read it are gone — no caller was found for any of them.

*Process.* None of its own: the sign-in and the rights stand under every process of A2 (who may open a screen, who a visitor is). Its records are `User`, `UserRole`, `LoginToken` and the role's bundle of rights (`RoleRight`); none carries a `check()`.

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Rollen** (`service.py`): `get_user_roles`, `get_user_role_rows`,
  `landing_for`, `has_login` — what someone may, asked of the data per request.
- **Rights** (CR-24, #1722): `Right` (which rights exist), `rights_of` (the
  rights an address holds in the active workspace: those its roles there
  bundle), `may` (the same as a question) and `require_right(Right.…)` (the
  gate of a screen; it fails closed). A role is a bundle of rights, kept as
  rows in `auth.role_rights`. No gate or question names a role: the
  role-named ones left with CR-24 (`backend/tests/test_rights_gate.py`).
- **Sessie/CSRF** (`session.py`, #398): `SESSION_COOKIE`, `make_session_value`,
  `read_session_value`, `set_session_cookie`, `csrf_token_for`,
  `require_csrf`.
- **Lid-identiteit** (`member_identity.py`): `find_persons_by_email`,
  `resolve_household`, `login_person_for_email`.
- **Modellen als type**: `User`, `UserRole`, `LoginToken` (voor
  Depends-annotaties; queries erop horen binnen dit component).
- **Machine-consumenten** (§19.3): none. The guard `require_api_key` never
  guarded a route and left with the API-key routes; the model `ApiKey` and the
  empty table `auth.api_keys` (migratie 077) left in the same release.

*Counted in the code on 13 October 2026:* the facade exports 41 names (28 functions, 9 classes, 4 values); events it owns (`kernel/contracts/`): `AccountCodeEntered`, `AddressCodeEntered`, `CodeMailRequested`; ports it offers: none.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of mdm; subscribes to `BoardMemberReported`, `EmailAddressAdded`; calls no port.

## Owns

### Data

Schema `auth`: `users`, `user_roles`, `login_tokens` (migratie 076). Bewust
géén FK naar `public.role_codes` (§8: geen cross-schema FK's) — rolcodes
worden in de servicelaag gevalideerd. Lid-zijn heeft geen user-record: de
enige brug tussen backoffice-accounts en het ledendomein is de e-mailwaarde.

Since CR-24 (#1722) also `right_codes` and `right_labels` (the code list of
rights) and `role_rights` (role code, right code): the bundles, written by a
migration and the same in every workspace — no tenant column.

*Counted in the code on 13 October 2026:* schema `auth`, 10 tables (4 data, 6 code and label), 1 of them with `tenant_id`; status columns: none; jobs: none.

## Screens

### Router

None. The sign-in is the screen's (`ui.py`: `/aanmelden`, `/aanmelden/code`, the
mail's link); the users screen (`admin_ui.py`) calls `users.py` as its service.

`ui.py`: 12 routes — `/aanmelden`, `/aanmelden/code`, `/account-aanmaken`, `/afmelden`, and `/login`, `/login/verify`, `/admin/login`, `/leden/login`; `admin_ui.py`: 6 routes under `/admin/gebruikers`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| NIST SP 800-63B | §5.1.3, out-of-band authenticator | `auth.login_tokens` · `otp_code` (hash), `expires_at`, `attempts`, `used` | follows (CR-22 B3a; #268, #395) |
| ISO 8601 | date and time with offset | `DateTime(timezone=True)` on every timestamp | follows |

## Rules and gates

### Principes

- De sessie bevat enkel identiteit (het e-mailadres); capabilities worden per
  request uit de data afgeleid — nooit naast de identiteit bewaard.
- OTP's worden gehasht opgeslagen (SHA-256 + SECRET_KEY-pepper, #395), met
  brute-force-lockout (#268).

- **Rules whose home is this module** — No `@validates` and no `check()` in `models.py`; no `CheckConstraint` there. Its rules stand in its service. The rights are data: `auth.role_rights`.
- **Gates in this module's own `tests/`** — none among its 13 test files. The gates about it stand in `backend/tests/`: `test_rights_gate.py` (no gate or question named after a role) and `test_role_model_gates.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E3** — the security audit against the code that runs (#530): open; the API-key point is done (#1251).
- **E5** — the OPERATOR cross-tenant view: open, no designed screen.
- **E14** — a shared store for the rate limiters (part of E3): open; one uvicorn worker until then.
- **E34** — parked on v2.19: #1873 (a role shown by its label), #1886 (the left menu of an account page).

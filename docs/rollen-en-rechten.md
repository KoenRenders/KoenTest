# Rollen & rechten — autoritatieve referentie

> Deze matrix is **afgeleid en geverifieerd tegen de echte endpoint-checks** (niet
> bedacht). Bron: de security-audit #530 (endpoint × authz-matrix) + de daaruit
> geïmplementeerde gates (#543, #547). Bij twijfel wint de code; werk dit document
> bij als een gate wijzigt. Verifiërende tests: `test_role_model_gates.py`,
> `test_admin_users_authz.py`, `test_betalingen_ui.py`.

## De rollen (RoleCode)

| Rol | Seed | Betekenis | Scope |
|-----|------|-----------|-------|
| **ADMIN** | 001 "Beheerder" | Volledige beheerder **binnen één tenant** — sinds #963 letterlijk: de rolrij draagt de werkruimte. | per tenant |
| **FINANCE** | 056 "Penningmeester" | **Enkel** betalingen/vorderingen. Verder géén beheer. | per tenant |
| **OPERATOR** | 087 "Platformbeheerder" | **Platform-superuser**: telt mee voor élke rolcheck (`require_roles`), ziet/beheert alles over **alle tenants**. Enige die tenant-instellingen wijzigt en (toekomstig #546) tenants aanmaakt. | platform |
| **ACCOUNT_ADMIN** | 087 "Accountbeheerder" | Bedoeld voor "alle units binnen één account". **Nog niet functioneel ingevuld** — geeft vandaag géén algemene toegang (placeholder tot het multi-unit-verhaal). | (account) |
| ~~MEMBER~~ / ~~USER~~ | 001 | **Dood/legacy** — geen enkele autorisatie hangt eraan; uit de rollenkeuzelijst gefilterd (#521/#458). Lidmaatschap is **data-gedreven** (`Membership`), geen rol. | — |

## Roles per workspace (#963, 16 September 2026)

Since migration 126 a role assignment carries a **workspace dimension**:
`auth.user_roles.tenant_id` names the workspace the role applies in, and
`NULL` means **platform-wide** (today only OPERATOR). The consequences, per
Koen's three decisions of 15 September 2026:

- **ADMIN in workspace A is not ADMIN in workspace B.** `get_user_roles`
  answers "what may I do *here*": the platform-wide rows plus the rows of the
  workspace the request resolves to (§7 of the architecture doc — hostname,
  path prefix, tenant cookie).
- **OPERATOR is platform-wide** — one `NULL` row, valid in every workspace.
- **User management is workspace-bound.** The role checkboxes in
  `/admin/gebruikers` show and replace only the roles of the *active*
  workspace; assignments in other workspaces are never touched.
- **OPERATOR is granted only inside the platform workspace** (Koen,
  16 September 2026) — in a regular workspace the checkbox exists for no one,
  and a forged submission gets a 403 (`_ken_rollen_toe`, `auth/users.py`).
  Inside the platform the checkbox exists only for operators, and changing it
  is guarded again in the service layer (`set_roles_for_workspaces`).
- **The platform user screen manages roles per workspace**: one row of
  checkboxes per workspace on each user card, so an OPERATOR creates the
  first users of a new tenant and manages accounts on behalf of the
  afdelingen. OPERATOR counts for the user-management gate itself
  (ADMIN/OPERATOR, as the matrix below always said).
- **Existing data** migrated to Raak Millegem (org 2), except the accounts in
  the `SEED_ALLE_WERKRUIMTES_EMAILS` env var (comma-separated, set per host,
  never committed), whose non-OPERATOR roles were copied to every workspace.
- **My profile** (`/admin/profiel`) lists roles per workspace; the account
  menu offers "Werkruimte wisselen" only when more than one workspace applies
  (`/admin/werkruimte-wisselen`, links via the path prefix).

Verifying tests: `test_rollen_per_werkruimte.py`.

## Rol → bevoegdheden

| Vlak | Publiek (geen rol) | FINANCE | ADMIN | OPERATOR |
|------|--------------------|---------|-------|----------|
| Publieke registratie/inschrijving/idee/formulier | ✅ (rate-limited) | ✅ | ✅ | ✅ |
| Ledenportaal "Mijn gezin" (`/leden/gezin`) — **enkel eigen gezin** | ✅ na login (ownership afgedwongen) | — | — | — |
| Algemene admin-schermen (CMS, media, activiteiten, **leden**, formulieren, pagina's, wijzigingen, Raakje, e-maillog, werkbank, info) | ❌ | ❌ (403) | ✅ | ✅ |
| Betalingen **bekijken**/exporteren (`/admin/betalingen`) | ❌ | ✅ | ✅ | ✅ |
| Betalingen **muteren** (bevestigen/terugbetalen/bewerken) | ❌ | ✅ | ❌ | ✅ |
| **Gebruikers & rollen** beheren (`/admin/gebruikers`) | ❌ | ❌ (403) | ✅ | ✅ |
| **Tenants** — lijst, aanmaken én instellingen (`/admin/tenants`) | ❌ | ❌ | ❌ (403) | ✅ |

## Exclusieve bevoegdheden (wie is de énige)

- **Betalingen bevestigen/terugbetalen/bewerken** → FINANCE (of OPERATOR). Financiële
  scheiding (#83): een ADMIN zonder FINANCE mag betalingen wél zien, niet muteren.
  Afgedwongen door `_require_finance` (`domains/payment/ui.py`).
- **Gebruikers/rollen beheren** → ADMIN (of OPERATOR). Voorkomt dat FINANCE zichzelf
  naar ADMIN escaleert (#543). Afgedwongen door `_require_admin` (`auth/admin_ui.py`).
- **Tenant-config wijzigen / tenants aanmaken** → OPERATOR. Afgedwongen door
  `_require_operator` (`ui/settings_ui.py`).

## Waar het in de code zit

- **Algemene admin-gate**: `require_admin_ui` → `{ADMIN, OPERATOR}` (`auth/session.py`).
- **Betalingen-kijkgate**: `require_finance_ui` → `{ADMIN, FINANCE, OPERATOR}`.
- **Betalingen-schrijfgate**: `_require_finance` → `{FINANCE, OPERATOR}`.
- **JSON-API** (`/api/v1/...`): `get_current_admin` (ADMIN-only), `get_current_finance`,
  `require_roles(...)` (OPERATOR telt altijd mee).
- **Login-landing** volgt de rol: ADMIN/OPERATOR → `/admin/werkbank`, FINANCE →
  `/admin/betalingen`, gewoon lid → `/leden/gezin` (OTP- én magic-link-pad).
- **Nav** is role-aware: een FINANCE-only gebruiker ziet enkel Betalingen.

## Scope-dimensie (multi-tenancy)

- **Tenant-isolatie** is globaal afgedwongen (SQLAlchemy `do_orm_execute`-filter op
  `TenantMixin`, `kernel/tenancy.py`): ADMIN/FINANCE zien enkel data van hun eigen
  tenant. OPERATOR overstijgt tenants (platform). ACCOUNT_ADMIN zou per **account**
  (meerdere units) werken — die scope is nog niet gebouwd.
- Backoffice-accounts/rollen (`auth.users`/`user_roles`) zijn **globaal** (geen
  `TenantMixin`) — auth is een gedeeld domein.

## Openstaande punten

- **ACCOUNT_ADMIN** functioneel invullen (of bewust uit de brede set houden tot dan) —
  gekoppeld aan #546 (tenants) en het multi-unit-account-model.
- Een geautomatiseerde **doc-vs-code-consistentietest** (rol-eisen ↔ route-dependencies)
  is een mogelijke uitbreiding (raakt #529/#530); vandaag dekken de authz-tests
  hierboven de kern.

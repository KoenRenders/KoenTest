# Rollen & rechten — autoritatieve referentie

> Deze matrix is **afgeleid en geverifieerd tegen de echte endpoint-checks** (niet
> bedacht). Bron: de security-audit #530 (endpoint × authz-matrix) + de daaruit
> geïmplementeerde gates (#543, #547). Bij twijfel wint de code; werk dit document
> bij als een gate wijzigt. Verifiërende tests: `test_role_model_gates.py`,
> `test_admin_users_authz.py`, `test_betalingen_ui.py`.

## De rollen (RoleCode)

| Rol | Seed | Betekenis | Scope |
|-----|------|-----------|-------|
| **ADMIN** | 001 "Beheerder" | Volledige beheerder **binnen één tenant**. | per tenant |
| **FINANCE** | 056 "Penningmeester" | **Enkel** betalingen/vorderingen. Verder géén beheer. | per tenant |
| **OPERATOR** | 087 "Platformbeheerder" | **Platform-superuser**: telt mee voor élke rolcheck (`require_roles`), ziet/beheert alles over **alle tenants**. Enige die tenant-instellingen wijzigt en (toekomstig #546) tenants aanmaakt. | platform |
| **ACCOUNT_ADMIN** | 087 "Accountbeheerder" | Bedoeld voor "alle units binnen één account". **Nog niet functioneel ingevuld** — geeft vandaag géén algemene toegang (placeholder tot het multi-unit-verhaal). | (account) |
| ~~MEMBER~~ / ~~USER~~ | 001 | **Dood/legacy** — geen enkele autorisatie hangt eraan; uit de rollenkeuzelijst gefilterd (#521/#458). Lidmaatschap is **data-gedreven** (`Membership`), geen rol. | — |

## Rol → bevoegdheden

| Vlak | Publiek (geen rol) | FINANCE | ADMIN | OPERATOR |
|------|--------------------|---------|-------|----------|
| Publieke registratie/inschrijving/idee/formulier | ✅ (rate-limited) | ✅ | ✅ | ✅ |
| Ledenportaal "Mijn gezin" (`/leden/gezin`) — **enkel eigen gezin** | ✅ na login (ownership afgedwongen) | — | — | — |
| Algemene admin-schermen (CMS, media, activiteiten, **leden**, formulieren, pagina's, wijzigingen, Raakje, e-maillog, werkbank, info) | ❌ | ❌ (403) | ✅ | ✅ |
| Betalingen **bekijken**/exporteren (`/admin/betalingen`) | ❌ | ✅ | ✅ | ✅ |
| Betalingen **muteren** (bevestigen/terugbetalen/bewerken) | ❌ | ✅ | ❌ | ✅ |
| **Gebruikers & rollen** beheren (`/admin/gebruikers`) | ❌ | ❌ (403) | ✅ | ✅ |
| **Tenant-instellingen** (`/admin/instellingen`) | ❌ | ❌ | ❌ (403) | ✅ |
| **Tenant aanmaken** (toekomstig #546) | ❌ | ❌ | ❌ | ✅ |

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

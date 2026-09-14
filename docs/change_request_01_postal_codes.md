# Change Request 01

**Project:** Web Portal "Raak Millegem"

---

## CR-01: Extract postal codes and municipalities into a separate lookup table

Replace the plain-text `postal_code` and `municipality` columns on the families/members table with a normalized `postal_codes` lookup table. Addresses are now linked by `postal_code_id` foreign key.

**New table:** `postal_codes` (id, postal_code, municipality, created_at, updated_at)
**Seed file:** `backend/seed_postal_codes.py` reads `docs/postal_codes_seed.csv` (589 Belgian postal codes).

---

## CR-02: Replace database ENUMs with code tables

Remove PostgreSQL ENUM types (`registrationtypeenum`, `paymentstatusenum`) and replace with multilingual code tables. This makes adding new codes and translations possible without schema migrations.

**New tables:**
- `gender_codes`
- `contact_type_codes`
- `role_codes`
- `registration_type_codes`
- `payment_status_codes`

Each table has composite primary key (code, language) with NL seed data.

---

## CR-03: Rename `families` table to `members`

The concept of "family" is too restrictive. A "member" now represents a household grouping that is dynamic and can change over time. The `Family` model becomes `Member`.

**Renamed:** `families` → `members`, `Family` → `Member`

---

## CR-04: Rename `family_members` to `persons` and introduce `member_persons` junction

Individual persons are now a stable, permanent entity independent of any household. A new `member_persons` junction table links persons to member households, replacing the direct `family_id` foreign key on the old `family_members` table.

**New tables:** `persons`, `member_persons`
**Removed:** `family_members` table and `FamilyMember` model

---

## CR-05: Extract address into a separate `addresses` table

Address data moves from the household/family level to the person level. Each person can have at most one address (unique constraint on `person_id`). Address links to `postal_codes` via `postal_code_id`.

**New table:** `addresses` (id, person_id, street, house_number, bus_number, postal_code_id, created_at, updated_at)

---

## CR-06: Replace email/phone columns with a `contact_details` table

Instead of fixed `email` and `phone` columns on `family_members`, contact information is stored in a flexible `contact_details` table linked to a person, with a `contact_type_code` (EMAIL, MOBILE, PHONE).

**New table:** `contact_details` (id, person_id, contact_type_code, value, is_primary, created_at, updated_at)

---

## CR-07: Replace `admin_users` with `users` and `user_roles`

The single `admin_users` table with username login is replaced by a proper `users` table (email login, linked to a `Person`) and a `user_roles` junction table that assigns role codes (ADMIN, MEMBER, USER). Authentication now checks the `user_roles` table for the ADMIN role.

**New tables:** `users`, `user_roles`
**Removed:** `admin_users` table and `AdminUser` model

---

## CR-08: Apply brand guidelines to the frontend

Apply the official Raak Millegem brand palette and typography to the frontend.

**Brand colors:**
- Ocean Blue: `#0051a4`
- Golden Yellow: `#ffce00`
- Pumpkin Orange: `#f16532`
- Cool Green: `#3aba9b`
- Dark Green: `#005d29`
- Hot Pink: `#f17fb2`
- Watermelon Red: `#ee3a37`
- Indigo: `#460359`

**Typography:** Radio Canada Big (Google Fonts)

**Changes:**
- `frontend/src/app/globals.css`: CSS custom properties for brand colors and font
- `frontend/src/app/layout.tsx`: Import and apply Radio Canada Big font
- `frontend/tailwind.config.ts`: Extend theme with brand colors and font family
- `frontend/src/components/Navigation.tsx`: Ocean Blue background, Golden Yellow tagline

---

## CR-09: Replace Dutch README with an English README

The project README is rewritten in English and expanded to cover:
- Project description
- Full tech stack table
- Local development setup (prerequisites, step-by-step commands)
- Environment variables reference table
- Deployment instructions
- Links to documentation

---

*End of Change Request 01 document.*

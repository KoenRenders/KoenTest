# Change Request 03 – Activity Registration Form Types

## Overview

CR-03 introduces six distinct registration form types for activities in the Raak Millegem portal. Each form type collects different information from registrants, enabling the portal to handle everything from simple free sign-ups to paid product orders.

## Form Types

### INDIVIDUAL
- **Description**: Simple free registration with contact info only.
- **Extra fields**: None beyond the standard contact section.
- **Example**: Mannenkroegentocht

### GROUP
- **Description**: Free registration where a contact person signs up on behalf of a group.
- **Extra fields**: Number of people (group_size).
- **Example**: Bezoek wijndomein Aldeneyck

### TEAM
- **Description**: Free registration for a team competing in a tournament or activity.
- **Extra fields**: Team name (team_name).
- **Example**: Cornhole tornooi / Sjoelbak tornooi at Brood en Spelen

### AGE_CATEGORY
- **Description**: Free registration with a count per age category. The categories are configured per activity via `age_category_config` (JSON array of `{key, label}` objects).
- **Extra fields**: One number input per configured age category.
- **Example**: Zo vader zo zoon (vader count + meerderjarig zoon count)

### PAID_PER_PERSON
- **Description**: Paid registration with a per-person unit price. Registrant specifies how many people attend; total is computed as count × unit price.
- **Extra fields**: Number of people (group_size); price shown per person.
- **Example**: Bowlen at €6/person

### PAID_PRODUCTS
- **Description**: Paid registration where the registrant selects quantities from a product list. Products are defined as sub-registrations on the activity (is_free=false, no reg_form_type).
- **Extra fields**: Quantity selector per product; running total shown.
- **Example**: BBQ at Brood en Spelen (various BBQ menu options at different prices)

## Common Fields (all form types)

- **Contact name** (required)
- **E-mail** (optional)
- **Phone number** (optional)
- **Remarks** (optional textarea)

## Payment Section (paid form types only)

For PAID_PER_PERSON and PAID_PRODUCTS (or any activity with price > 0), a payment method selector is shown:
- **Mollie (online)** – redirects to Mollie payment (default)
- **Cash** – admin/manual entry; status set to PAID immediately
- **Overschrijving** (bank transfer) – status set to PAID immediately

## Sub-registration Forms

Sub-registrations can also carry a `reg_form_type`. When they do, an internal "Inschrijven" button is shown instead of an external link, opening the registration form with that sub-registration's form type.

## API Changes

- `POST /api/v1/activities/{id}/register` – accepts all new fields; creates `registration_items` for PAID_PRODUCTS.
- `GET /api/v1/activities/{id}/registrations/public` – public endpoint returning `PublicRegistrationSummary` with names and participant totals.

## Database Changes (migration 005)

- `activities.reg_form_type` VARCHAR(20) NOT NULL DEFAULT 'NONE'
- `activities.age_category_config` TEXT nullable
- `activity_sub_registrations.reg_form_type` VARCHAR(20) nullable
- `registrations`: contact_phone, team_name, group_size, age_categories, remarks, payment_method, payment_status, sub_registration_id
- New table `registration_items`: id, registration_id, sub_registration_id, quantity, unit_price, timestamps

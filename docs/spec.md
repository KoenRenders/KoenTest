# Web Portal "Raak Millegem" — Project Specification

---

## Goal of the application

Replace the current website with an interactive, user-friendly application for the Raak-Millegem association, focusing on:

- Registrations
- Activity management
- Idea submission
- Webshop for events (e.g., Brood en Spelen)

---

## Pages and functionalities

### Homepage

- **Registration button:**
  - Form for family members (names, addresses, contact details: email, phone, dates of birth).
- **Idea box:**
  - Field to submit ideas → automatically sends an email to raakmillegem@gmail.com AND stores the idea in the database for admin follow-up and archiving.
- **Activities overview:**
  - Structure: Per year (e.g., 2026, 2027) with:
    - Activity name (hyperlink to poster)
    - Date and time
    - Location
    - Maximum number of participants (if applicable)
    - Registration type: **per individual** or **per family**
    - Status indicator: Open / Full / Waitlist
    - Links: Register + List of registered participants

### Archive

Automatically move past activities to a separate page, retaining all data.

### Custom pages (CMS)

The admin can create, edit, and delete informational pages in **rich text format** (WYSIWYG editor). These pages appear in the navigation menu and are publicly visible.

This allows the association to maintain content such as meeting schedules, board information, and event details without developer intervention.

**Current website navigation → New portal:**

| Current | New portal |
|---|---|
| Home | Home (activities overview, registration, idea box) |
| Werking | CMS page: Werking |
| Kerstradio | CMS page: Kerstradio |
| Archief | Archive (automatic, based on past activities) |
| *(new)* | Webshop |

**Example CMS pages migrated from the existing website:**

- **Werking** — Contains three subsections:
  - *Vergadering:* Meeting schedule (first Thursday of every month at 20:00 in Zaal 1, Miloheem), agenda structure, and dates per year.
  - *Activiteiten:* How KWB Millegem supports member-organised activities: communication, insurance, financial coverage, venues. Rules for organising (minimum 2 trekkers, prior presentation at monthly meeting, no overlapping activities). Links to activity calendars per year.
  - *Bestuur:* Overview of board roles and current members (wijkmeesters, voorzitter, secretaris, penningmeester, cultuurraad, nieuwsbrief, website/social media, ledenadministratie).

- **Kerstradio** — Informational page for the annual Christmas radio event on Radio Gompel (105.6 FM / radiogompel.be). Contains: listening instructions, technical hotline, song request form link, interview schedule, "Raad de RODE DRAAD" game (hourly questions leading to a grand prize), and "Raad HET GELUID" game (sound guessing with drop-in times at the Kerstherberg).

**Requirements:**
- Admin can add new pages, edit existing ones, and remove pages.
- Each page has a title and a rich text body (supporting headings, bullet lists, hyperlinks, bold/italic).
- Pages are linked in the main navigation automatically when published.
- No coding required to manage page content.

> **Recommended WYSIWYG editor:** TipTap or Quill — both free and well-supported in React/Next.js.

### Webshop (for Brood en Spelen)

**Products:**

| Product | Regular price | Member price |
|---|---|---|
| Barbecue (3 pieces of meat) | €18 | €13 |
| Barbecue (2 pieces of meat) | €16 | €11 |
| Children's option | €10 | €5 |
| Vegetarian Barbecue (3 pieces) | €18 | €13 |
| Vegetarian Barbecue (2 pieces) | €16 | €11 |
| Vegetarian Children's option | €10 | €5 |

> Members receive a **€5 discount on every product**. The correct price is applied automatically based on member status at the time of ordering.

**Payment:**
- Integration with Mollie (🇳🇱 Belgian/Dutch payment solution).
- Supported methods: Bancontact, iDEAL, credit card, etc.

**Order management (admin):**
- Dashboard showing totals per product (e.g., "32 × Barbecue 3-piece") to support purchasing.
- Export orders to Excel/CSV for the barbecue-inkoop (purchasing overview).
- Each order receives a unique confirmation number, included in the confirmation email to the customer.

---

## Authentication & Roles

The application requires a login system with at least three distinct user types:

### Admin
- Create, edit, and delete activities
- Create, edit, and delete custom informational pages (CMS)
- View and manage registration lists per activity
- View and export webshop orders
- Follow up on submitted ideas
- Manage member data

### Member (lid)
A registered member of the Raak-Millegem association.
- Register for activities
- Place orders in the webshop
- Submit ideas
- Receives **€5 discount** on all webshop products and paid activities

### Non-member (niet-lid)
A visitor who is not a member of the association — e.g. a friend or family member of a member, or someone who heard about an event.
- Register for activities
- Place orders in the webshop at full price
- Submit ideas
- **No discount** applies

> **Note:** Admin access is secured by username/password login. A user account is only created when someone explicitly registers — not automatically. A user is optionally linked to a Person, which connects them to a Member household and determines discount eligibility via the chain: `User → Person → Member → Membership (annual)`.

---

## Confirmation Emails

Automatic confirmation emails are sent using **Python's built-in `smtplib`** via Gmail SMTP (raakmillegem@gmail.com). No external email service is needed for the expected volume (a few emails per week).

Emails are sent in the following cases:

- **Activity registration:** Confirmation to the registrant with activity details (name, date, time, location).
- **Webshop order:** Order confirmation to the customer with a summary of products ordered, total amount, unique confirmation number, and payment status.
- **Idea submission:** Optional acknowledgement to the submitter that their idea was received.

> **Setup required:** A Gmail "App Password" must be configured (separate from the regular Gmail password) to allow the application to send emails programmatically.

---

## Capacity Management for Activities

- Each activity can optionally have a **maximum number of participants**.
- When the limit is reached:
  - The activity is marked as **Full** in the overview.
  - New registrations are placed on a **waitlist**.
  - Registrants on the waitlist receive an automatic notification if a spot becomes available.
- The admin can view and manage the waitlist per activity.

---

## Member Management

### Core principle: Person vs. Member

- **Person** is the **stable, permanent entity** — it represents a real individual. A person never changes, even if their household situation does.
- **Member** is a **dynamic household grouping** — it represents a household at a point in time.
- The link between Person and Member is temporal: when a child moves out, they remain the same Person but are linked to a new Member of their own. The historical link to the parents' Member is retained.

### Structure

A **Member** is a household living at one address. Every Member has one **primary person** (hoofdgezinslid) and zero or more additional persons, linked via a junction table that tracks when each person joined or left the household.

### Person data

| Field | Description |
|---|---|
| Last name | Naam |
| First name | Voornaam |
| Date of birth | Geboortedatum |
| Gender | Via `gender_codes` lookup table |
| Mobile | Mobile phone number |

### Address data (linked to Person)

| Field | Description |
|---|---|
| Street | Straatnaam |
| House number | Huisnummer |
| Bus number | Busnummer (optional) |
| Postal code + Municipality | Via `postal_codes` lookup table |

One address per person.

### Contact details (linked to Person)

Stored in a separate `contact_details` table, allowing multiple entries per person per type:

| Type | Example |
|---|---|
| EMAIL | jan@example.com |
| MOBILE | 0499 12 34 56 |
| PHONE | 03 456 78 90 |

### Member types (roles within a household)

Each person in a household has a role:

| Code | Label (NL) | Label (EN) |
|---|---|---|
| HOOFDLID | Hoofdlid | Primary member |
| PARTNER | Partner | Partner |
| KIND | (Meerderjarig) kind | Adult child |

### Board member responsible per member

Each member household can be linked to a board member (a `Person` with a board role) who is responsible for that member. Stored as `board_member_id` on the `members` table (FK → `persons.id`).

### Gender codes

| Code | Label (NL) | Label (EN) |
|---|---|---|
| M | Man | Male |
| F | Vrouw | Female |
| X | X | X |
| U | Onbekend | Unknown |

### Annual membership

Membership is renewed **per year**. A Member can be active in 2025 but not in 2026. The system tracks membership via a separate `memberships` table per Member per year.

**Discount logic:** The €5 discount applies if the person's current Member group has an active membership for the current year.

### Admin responsibilities
- Add, edit, and deactivate persons and their contact details
- Manage household groupings (members) and their persons
- Renew or revoke membership per year per member group
- View membership history per member group
- Assign responsible board member per household

---

## Registration Form (CR-02)

### Visual layout

- **Row 1:** Street, house number, bus number
- **Row 2:** Postal code + municipality (single searchable dropdown/combobox — auto-fills municipality)
- Address placed **below the primary member fields**, above the option to add family members.

### Per-person fields

- First name, last name
- Date of birth (required)
- Gender (M / F / X / Unknown)
- Phone (left) | Mobile (right)
- Email address (full width, below phone/mobile)

### Postal code field

- Combobox (datalist) allowing search by postal code **or** municipality name.
- Municipality is auto-filled from the selected postal code — not a separate editable field.

### Member types within a family registration

The primary member is always **Hoofdlid**. Additional members can be:
- Partner
- (Adult) child (Meerderjarig kind)

---

## Activity Pricing

Almost all activities are **free of charge**. The system supports this as the default.

For future versions, the system must support **paid activities** with optional **member discounts**. Examples:

| Activity | Regular price | Member price |
|---|---|---|
| Walking tour | €10 | €5 |
| Comedy Night | €15 | €10 |

**Requirements for paid activities:**
- Each activity can optionally have a price (default: free).
- A separate (lower) member price can be defined per activity.
- Payment is handled via Mollie (same integration as the webshop).
- The registrant receives a payment confirmation by email.

### Registration types

Each activity has one of two registration modes, set by the admin:

- **Individual registration:** each person registers separately (e.g. a workshop with limited spots).
- **Family registration:** one registration covers the entire family (e.g. Brood en Spelen / BBQ). Any family member can submit the registration — it does not have to be the primary member.

### Discount rule (simplified)

> If the registrant or orderer belongs to a family with an **active membership for the current year** → member price applies.
> If not → full price applies.

No distinction is made between primary member and other family members. Any family member can register or order and the discount is applied automatically.

---

## GDPR / Privacy (AVG)

> **STATUS: ON HOLD — not needed for first version.**

The application collects personal data (names, addresses, dates of birth, email, phone numbers), including data of minors. Full GDPR compliance will be required in a later version:

- **Privacy declaration:** Visible and accessible on the website, explaining what data is collected, how it is used, and how long it is retained.
- **Explicit consent:** Registration forms include a mandatory checkbox with consent to data processing.
- **Right to erasure:** The admin panel allows deletion of member data upon request.
- **Data retention:** Personal data is only retained as long as necessary (to be defined per data type, e.g., event registrations deleted after X months post-event).
- **Data minimisation:** Only collect data that is strictly necessary for the purpose.

---

## Brand & Design

### Typography

- **Primary font:** [Radio Canada Big](https://fonts.google.com/specimen/Radio+Canada+Big) (Google Fonts)
- Applied to all headings, navigation, buttons, and UI labels.

### Colour palette

#### Primary colours

| Name | Role | HEX | RGB | CMYK | PMS |
|---|---|---|---|---|---|
| **Ocean Blue** | Primary dark background, header, buttons | `#0051a4` | 0 82 164 | 100 77 0 0 | 2935 |
| **Golden Yellow** | Tagline, accents, highlights | `#ffce00` | 255 207 1 | 0 18 100 0 | Yellow 012 |
| **White** | Text on Ocean Blue backgrounds | `#ffffff` | 255 255 255 | — | — |

#### Secondary colours (use where relevant)

| Name | HEX | RGB | CMYK | PMS |
|---|---|---|---|---|
| **Pumpkin Orange** | `#f16532` | 242 101 51 | 0 75 89 0 | 1645 |
| **Cool Green** | `#3aba9b` | 58 187 155 | 70 0 51 0 | 3255 |
| **Dark Green** | `#005d29` | 0 93 41 | 100 0 100 56 | 348 |
| **Hot Pink** | `#f17fb2` | 242 127 178 | 0 64 0 0 | 237 |
| **Watermelon Red** | `#ee3a37` | 239 59 55 | 0 92 84 0 | Red 032 |
| **Indigo** | `#460359` | 70 3 89 | 68 100 0 47 | 2617 |

### CSS custom properties

```css
:root {
  /* Typography */
  --font-primary: 'Radio Canada Big', sans-serif;

  /* Primary colours */
  --color-ocean-blue:    #0051a4;
  --color-golden-yellow: #ffce00;
  --color-white:         #ffffff;

  /* Secondary colours */
  --color-pumpkin-orange:  #f16532;
  --color-cool-green:      #3aba9b;
  --color-dark-green:      #005d29;
  --color-hot-pink:        #f17fb2;
  --color-watermelon-red:  #ee3a37;
  --color-indigo:          #460359;
}
```

If Tailwind CSS is used, extend the theme in `tailwind.config.ts` with the same values so utility classes are available (e.g. `bg-ocean-blue`, `text-golden-yellow`).

### Usage guidelines

- **Ocean Blue** is the dominant brand colour — use for the header, primary buttons, and key UI elements.
- **Golden Yellow** is the accent colour — use for the tagline, highlights, and call-to-action elements.
- **White** text is used on Ocean Blue backgrounds for maximum contrast.
- Secondary colours are available for category tags, status indicators, charts, and decorative elements.

---

## UI / Responsive Design

- The interface must be **mobile-first**: optimised for smartphones, as many members register via their phone.
- Equally, the interface must be **fully functional on desktop**: the association has members up to 80 years old who primarily use a desktop computer.
- Focus on simplicity, large readable fonts, and clear call-to-action buttons.
- Avoid unnecessary complexity in navigation.

---

## Technological Stack

| Layer | Technology | Motivation |
|---|---|---|
| Database | PostgreSQL | Robust, open source, scalable |
| Backend | Python + **FastAPI** | Async, high performance, industry standard for AI/ML integration |
| ORM | SQLAlchemy | Framework-independent, powerful, used across all Python projects |
| DB Migrations | Alembic | Tracks schema changes over time, works with SQLAlchemy |
| Data validation | Pydantic | Native to FastAPI, strict typing |
| Frontend | TypeScript + React + Next.js | Industry standard, large ecosystem, strong fit for future ERP applications. Next.js adds routing, server-side rendering and a clean project structure out of the box |
| Payments | Mollie API 🇳🇱 | Belgian/Dutch provider, supports Bancontact |
| Email | Python `smtplib` + Gmail SMTP | Built-in, no external service needed for current volume |
| Hosting | Hetzner 🇩🇪 / OVHcloud 🇫🇷 / Combell 🇧🇪 | European hosting, GDPR-friendly, PostgreSQL included |

**Why FastAPI over Django:**
Django would allow faster initial development (built-in admin, auth, migrations), but FastAPI is the deliberate choice here because of the long-term vision: building complex ERP applications with AI/ML capabilities. FastAPI is the standard in the Python ML/AI ecosystem, and the patterns learned here carry over directly to future projects.

---

## Infrastructure

### Server setup

A single **VPS (Virtual Private Server)** is sufficient for Raak Millegem and the first ERP prototypes. The application runs as **4 Docker containers**, each with a single responsibility, managed via Docker Compose.

```
Internet
    │
  Caddy (port 443, HTTPS)
    ├── <DOMAIN>      → Next.js (frontend)
    └── api.<DOMAIN>  → FastAPI (backend)
                                    │
                               PostgreSQL
                          (internal, not public)
```

### The 4 containers

| Container | Role |
|---|---|
| **PostgreSQL** | Stores all data (members, activities, orders, ideas). Only accessible by the FastAPI container. Data is stored on a separate Docker volume so it survives container updates and restarts. |
| **FastAPI** | All business logic: discount rules, capacity checks, Mollie payment processing, email sending. The only container that communicates with PostgreSQL. |
| **Next.js** | The user interface. Communicates with FastAPI via API calls. Has no direct access to the database. |
| **Caddy** | Receives all incoming traffic and routes it to the correct container. Manages HTTPS/SSL certificates automatically via Let's Encrypt. The only container exposed to the internet. |

### Reverse proxy

**Current choice: Caddy**
Caddy handles SSL certificates fully automatically — no manual configuration or Certbot needed. Ideal for getting started quickly.

**Future migration: Nginx**
Nginx is the industry standard with significantly more documentation, community resources, and wider adoption. When the project grows or team members are added, migrating to Nginx is recommended. The switch is straightforward as only the reverse proxy configuration changes — all other containers remain identical.

### Recommended hosting

**Hetzner CX22** 🇩🇪 — €6/month
- 2 vCPU, 4 GB RAM, 40 GB SSD
- OS: **Ubuntu 24.04 LTS** (supported until April 2029)
- Located in EU (Frankfurt or Helsinki)
- GDPR-friendly
- More than sufficient for Raak Millegem and a first ERP prototype

### Scaling path

| Phase | Setup |
|---|---|
| Raak Millegem | 1 VPS, 4 containers ✅ |
| ERP with higher traffic | Separate VPS for PostgreSQL |
| Heavy load | Load balancer + multiple FastAPI containers |
| Large team / enterprise | Kubernetes |

---

## Future Vision

Raak Millegem is the **first step in a broader development trajectory** towards complex ERP applications. The chosen stack (FastAPI + SQLAlchemy + PostgreSQL) forms a solid and reusable foundation for:

| Domain | AI/ML applications |
|---|---|
| Order Handling | Automated order processing, anomaly detection |
| Logistics | Route optimisation, delivery time prediction |
| Customs | Document classification, compliance checking |
| Warehousing | Stock level optimisation, picking route planning |
| Sales | Lead scoring, churn prediction |
| Demand Forecasting | Time series models (Prophet, statsforecast) |
| Supply Planning | Replenishment optimisation |

**Technologies that will be added as the vision grows:**

| Technology | Purpose |
|---|---|
| Celery + Redis | Async task queue for long-running ML jobs |
| Pandas / NumPy | Data manipulation and analysis |
| scikit-learn | Machine learning models |
| Prophet / statsforecast | Demand and sales forecasting |
| Kafka / RabbitMQ | High-volume event streaming (ERP scale) |

> Raak Millegem teaches the right patterns — REST API design, async backend, clean data models — that scale directly into this future.

---

## Code Conventions

All code is written in **English**: variable names, function names, class names, comments, commit messages, and API endpoints. Dutch is used only for user-facing content (UI labels, email templates).

### Python (FastAPI backend)

- Follow **PEP 8** as the base style guide.
- Use **Black** for automatic formatting (line length: 88 characters).
- Use **isort** for import ordering.
- **Type hints** are mandatory on all function signatures.
- Naming: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Write docstrings for all public functions and classes.

```python
# Correct
async def get_member_by_id(member_id: int) -> MemberResponse:
    """Retrieve a single member by their ID."""
    ...

# Incorrect
async def getMember(id):
    ...
```

### TypeScript / React / Next.js (frontend)

- Use **ESLint** + **Prettier** for linting and formatting.
- Enable **TypeScript strict mode** (`"strict": true` in `tsconfig.json`).
- Use **functional components only** — no class components.
- Naming:
  - Components: `PascalCase` (e.g., `ActivityCard`)
  - Functions and variables: `camelCase`
  - Constants: `UPPER_SNAKE_CASE`
  - Props interfaces: suffix with `Props` (e.g., `ActivityCardProps`)
  - Custom hooks: prefix with `use` (e.g., `useMemberStatus`)
- Every component gets its own file, named after the component.

```typescript
// Correct
interface ActivityCardProps {
  title: string;
  date: Date;
  isFull: boolean;
}

export default function ActivityCard({ title, date, isFull }: ActivityCardProps) { ... }

// Incorrect
export default function activity_card(props: any) { ... }
```

### Database (PostgreSQL / SQLAlchemy)

- **Everything in the database is lowercase** — table names, column names, index names, constraint names, no exceptions.
- Table names: **lowercase, plural, snake_case** (e.g., `persons`, `members`, `activities`, `orders`, `postal_codes`).
- Column names: **lowercase, snake_case** (e.g., `first_name`, `postal_code_id`, `is_primary`).
- Primary keys: always named `id`.
- Foreign keys: `{singular_table_name}_id` (e.g., `person_id`, `member_id`, `activity_id`).
- Lookup/code tables: named `{entity}_codes` (e.g., `gender_codes`, `contact_type_codes`).
- Every table has `created_at` and `updated_at` timestamp columns.

```sql
-- Correct
CREATE TABLE member_persons (
    id            serial PRIMARY KEY,
    member_id     integer NOT NULL REFERENCES members(id),
    person_id     integer NOT NULL REFERENCES persons(id),
    is_primary    boolean NOT NULL DEFAULT false,
    created_at    timestamp NOT NULL DEFAULT now(),
    updated_at    timestamp NOT NULL DEFAULT now()
);

-- Incorrect
CREATE TABLE MemberPersons (
    ID serial PRIMARY KEY,
    MemberID integer ...
);
```

### REST API

- Base path: `/api/v1/`
- Resource names: **lowercase, plural nouns** (e.g., `/api/v1/members`, `/api/v1/activities`)
- Use standard HTTP verbs: `GET`, `POST`, `PUT` / `PATCH`, `DELETE`

### Git

- **Branch naming:**
  - `feature/short-description` (e.g., `feature/member-registration`)
  - `bugfix/short-description`
  - `hotfix/short-description`

- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org):

```
feat: add member registration form
fix: correct discount calculation for non-members
chore: update dependencies
docs: add API endpoint documentation
refactor: extract address validation to separate service
```

---

## Recommended Development Priority

1. **Authentication + admin panel** (roles, login)
2. **Activity management** (create, edit, capacity, registration)
3. **Member registration form**
4. **Custom pages / CMS** (rich text pages for Vergadering, Activiteiten, Bestuur, etc.)
5. **Archive**
6. **Webshop + Mollie integration**
7. **Order management dashboard + CSV export**
8. **Idea box**
9. **Confirmation emails** (smtplib + Gmail)
10. **Waitlist notifications**
11. **GDPR compliance** (later version)

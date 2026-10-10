# Roles and rights

> **Rendered, never written.** This document comes from `app/domains/auth/docs.py`:
> the bundles in `auth.role_rights` and the right each route's gate asks. Change a
> bundle (a migration) or a gate, then run `python -m app.domains.auth.docs`; a
> test fails while the two differ. Design: CR-24, *Rights, part 1*.

## How it works

- **A gate asks a right, never a role.** A route names one right in its
  dependencies (`require_right`); whoever holds it in this workspace gets in.
- **A right is about one kind of object**, and there are two per object: viewing
  (`<object>.view`), asked by a route that only reads (GET), and changing
  (`<object>.manage`, for master data `<object>.masterdata`), asked by every
  other method.
- **A role is a bundle of rights**, kept as rows and the same in every workspace.
  A user may hold several roles; he holds a right when one of them bundles it.
- **Roles are given per workspace** (`auth.user_roles.tenant_id`): a role in
  workspace A is no role in workspace B. One role is platform-wide — the row
  without a workspace — and it is granted inside the platform workspace only.
- **A platform screen asks its right and the platform workspace**
  (`require_platform_right`): in a tenant's workspace it does not exist, also
  for who holds the right.
- **Everyone with a back-office role enters the back office by the workbench**,
  and sees in its menu the screens whose right he holds — nothing else.
- **A visitor and a member hold no role and no right.** What a member may do with
  his own household is decided by ownership, not by a right.

## The roles

| Role | On screen | Rights it bundles |
|---|---|---|
| `ADMIN` | Beheerder | 25 |
| `FINANCE` | Boekhouding | 3 |
| `OPERATOR` | Platformbeheerder | 36 |
| `ACCOUNT_ADMIN` | Accountbeheerder | 0 |
| `MASTERDATA` | Masterdata | 5 |
| `PRICING` | Prijsbeheer | 3 |
| `SALES` | Verkoop | 3 |
| `STOCK` | Voorraadbeheer | 3 |

A role that bundles nothing opens nothing of the back office.

## Which role holds which right

| Right | On screen | `ADMIN` | `FINANCE` | `OPERATOR` | `ACCOUNT_ADMIN` | `MASTERDATA` | `PRICING` | `SALES` | `STOCK` |
|---|---|---|---|---|---|---|---|---|---|
| `activity.view` | Activiteiten bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `activity.manage` | Activiteiten beheren | ✓ |  | ✓ |  |  |  |  |  |
| `form.view` | Formulieren bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `form.manage` | Formulieren beheren | ✓ |  | ✓ |  |  |  |  |  |
| `page.view` | Pagina's bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `page.manage` | Pagina's beheren | ✓ |  | ✓ |  |  |  |  |  |
| `media.view` | Media bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `media.manage` | Media beheren | ✓ |  | ✓ |  |  |  |  |  |
| `design.view` | Ontwerpen bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `design.manage` | Ontwerpen beheren | ✓ |  | ✓ |  |  |  |  |  |
| `newsletter.view` | Nieuwsbrieven bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `newsletter.manage` | Nieuwsbrieven beheren | ✓ |  | ✓ |  |  |  |  |  |
| `meeting.view` | Vergaderingen bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `meeting.manage` | Vergaderingen beheren | ✓ |  | ✓ |  |  |  |  |  |
| `report.view` | Rapporten bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `report.manage` | Rapporten beheren | ✓ |  | ✓ |  |  |  |  |  |
| `assistant.use` | Raakje gebruiken | ✓ |  | ✓ |  |  |  |  |  |
| `party.view` | Personen en organisaties bekijken | ✓ |  | ✓ |  | ✓ |  |  |  |
| `party.masterdata` | Personen en organisaties beheren | ✓ |  | ✓ |  | ✓ |  |  |  |
| `product.view` | Producten bekijken |  |  | ✓ |  | ✓ |  |  |  |
| `product.masterdata` | Producten beheren |  |  | ✓ |  | ✓ |  |  |  |
| `price.view` | Prijzen bekijken |  |  | ✓ |  |  | ✓ |  |  |
| `price.manage` | Prijzen beheren |  |  | ✓ |  |  | ✓ |  |  |
| `sales.view` | Bestellingen bekijken |  |  | ✓ |  |  |  | ✓ |  |
| `sales.manage` | Bestellingen beheren |  |  | ✓ |  |  |  | ✓ |  |
| `stock.view` | Voorraad bekijken |  |  | ✓ |  |  |  |  | ✓ |
| `stock.manage` | Voorraad beheren |  |  | ✓ |  |  |  |  | ✓ |
| `payment.view` | Betalingen bekijken | ✓ | ✓ | ✓ |  |  |  |  |  |
| `payment.manage` | Betalingen beheren |  | ✓ | ✓ |  |  |  |  |  |
| `workbench.use` | Werkbank gebruiken | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |
| `user.view` | Gebruikers bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `user.manage` | Gebruikers beheren | ✓ |  | ✓ |  |  |  |  |  |
| `settings.view` | Instellingen bekijken | ✓ |  | ✓ |  |  |  |  |  |
| `settings.manage` | Instellingen beheren | ✓ |  | ✓ |  |  |  |  |  |
| `platform.view` | Platform bekijken |  |  | ✓ |  |  |  |  |  |
| `platform.manage` | Platform beheren |  |  | ✓ |  |  |  |  |  |

## What each right opens

Every route whose gate asks the right. A right without a route here opens nothing yet: its screens come with a later change.

### `activity.view` — 13 routes

- `GET /admin/activiteiten`
- `GET /admin/activiteiten/nieuw`
- `GET /admin/activiteiten/nieuw/organisatoren`
- `GET /admin/activiteiten/{activity_id}`
- `GET /admin/activiteiten/{activity_id}/inschrijvingen`
- `GET /admin/activiteiten/{activity_id}/inschrijvingen/lijst`
- `GET /admin/activiteiten/{activity_id}/inschrijvingen/nieuw`
- `GET /admin/activiteiten/{activity_id}/kopieren`
- `GET /admin/activiteiten/{activity_id}/onderdelen/{component_id}/antwoorden`
- `GET /admin/activiteiten/{activity_id}/onderdelen/{component_id}/export`
- `GET /admin/activiteiten/{activity_id}/organisatoren`
- `GET /admin/inschrijvingen/{registration_id}`
- `GET /admin/inschrijvingen/{registration_id}/fragment`

### `activity.manage` — 18 routes

- `POST /admin/activiteiten/nieuw`
- `POST /admin/activiteiten/nieuw/raakje/voorstel`
- `POST /admin/activiteiten/{activity_id:int}/raakje/voorstel`
- `POST /admin/activiteiten/{activity_id}`
- `POST /admin/activiteiten/{activity_id}/annulering`
- `POST /admin/activiteiten/{activity_id}/inschrijvingen/nieuw`
- `POST /admin/activiteiten/{activity_id}/inschrijvingen/nieuw/prijzen`
- `POST /admin/activiteiten/{activity_id}/inschrijvingen/nieuw/totaal`
- `POST /admin/activiteiten/{activity_id}/inschrijvingen/{registration_id}/verwijderen`
- `POST /admin/activiteiten/{activity_id}/kopieren`
- `POST /admin/activiteiten/{activity_id}/status`
- `POST /admin/activiteiten/{activity_id}/verwijderen`
- `POST /admin/inschrijvingen/{registration_id}/antwoorden`
- `POST /admin/inschrijvingen/{registration_id}/antwoordlink`
- `POST /admin/inschrijvingen/{registration_id}/opmerking`
- `POST /admin/inschrijvingen/{registration_id}/opslaan`
- `POST /admin/inschrijvingen/{registration_id}/regels/{item_id}`
- `POST /admin/inschrijvingen/{registration_id}/totaal`

### `form.view` — 8 routes

- `GET /admin/formulieren`
- `GET /admin/formulieren/nieuw`
- `GET /admin/formulieren/{form_id}`
- `GET /admin/formulieren/{form_id}/afdruk`
- `GET /admin/formulieren/{form_id}/export`
- `GET /admin/formulieren/{form_id}/inzendingen`
- `GET /admin/formulieren/{form_id}/json`
- `GET /admin/formulieren/{form_id}/resultaten`

### `form.manage` — 17 routes

- `POST /admin/formulieren`
- `POST /admin/formulieren/{form_id}/instellingen`
- `POST /admin/formulieren/{form_id}/inzendingen/{submission_id}/verwijderen`
- `POST /admin/formulieren/{form_id}/json-import`
- `POST /admin/formulieren/{form_id}/opties/{option_id}`
- `POST /admin/formulieren/{form_id}/opties/{option_id}/verplaats`
- `POST /admin/formulieren/{form_id}/opties/{option_id}/verwijderen`
- `POST /admin/formulieren/{form_id}/secties`
- `POST /admin/formulieren/{form_id}/secties/{section_id}`
- `POST /admin/formulieren/{form_id}/secties/{section_id}/verplaats`
- `POST /admin/formulieren/{form_id}/secties/{section_id}/verwijderen`
- `POST /admin/formulieren/{form_id}/velden`
- `POST /admin/formulieren/{form_id}/velden/{field_id}`
- `POST /admin/formulieren/{form_id}/velden/{field_id}/opties`
- `POST /admin/formulieren/{form_id}/velden/{field_id}/verplaats`
- `POST /admin/formulieren/{form_id}/velden/{field_id}/verwijderen`
- `POST /admin/formulieren/{form_id}/verwijderen`

### `page.view` — 4 routes

- `GET /admin/paginas`
- `GET /admin/paginas/nieuw`
- `GET /admin/paginas/{page_id}`
- `GET /admin/paginas/{page_id}/voorbeeld`

### `page.manage` — 4 routes

- `POST /admin/paginas`
- `POST /admin/paginas/{page_id}`
- `POST /admin/paginas/{page_id}/verwijderen`
- `POST /admin/paginas/{page_id}/volgorde/{richting}`

### `media.view` — 3 routes

- `GET /admin/media`
- `GET /admin/media/kiezer`
- `GET /admin/media/nieuw`

### `media.manage` — 7 routes

- `POST /admin/media`
- `POST /admin/media/tags`
- `POST /admin/media/tags/{tag_id}`
- `POST /admin/media/tags/{tag_id}/verwijderen`
- `POST /admin/media/{asset_id}`
- `POST /admin/media/{asset_id}/verplaats`
- `POST /admin/media/{asset_id}/verwijderen`

### `design.view` — 7 routes

- `GET /admin/ontwerpen`
- `GET /admin/ontwerpen/nieuw`
- `GET /admin/ontwerpen/{design_id}`
- `GET /admin/ontwerpen/{design_id}/svg/{layout}`
- `GET /admin/ontwerpen/{design_id}/varianten`
- `GET /admin/ontwerpen/{design_id}/voorbeeld.pdf`
- `GET /admin/ontwerpen/{design_id}/voorbeeld.png`

### `design.manage` — 10 routes

- `POST /admin/ontwerpen`
- `POST /admin/ontwerpen/{design_id}`
- `POST /admin/ontwerpen/{design_id}/afbeelding`
- `POST /admin/ontwerpen/{design_id}/definitief`
- `POST /admin/ontwerpen/{design_id}/genereer`
- `POST /admin/ontwerpen/{design_id}/kies/{generation_id}`
- `POST /admin/ontwerpen/{design_id}/publiceer`
- `POST /admin/ontwerpen/{design_id}/svg`
- `POST /admin/ontwerpen/{design_id}/svg/verwijderen`
- `POST /admin/ontwerpen/{design_id}/verwijderen`

### `newsletter.view` — 12 routes

- `GET /admin/nieuwsbrieven`
- `GET /admin/nieuwsbrieven/abonnees`
- `GET /admin/nieuwsbrieven/abonnees/import`
- `GET /admin/nieuwsbrieven/instellingen`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/activiteiten`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/invoegen/activiteit/{activity_id:int}`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/invoegen/afsluiting`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/invoegen/kalender`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/raakje/gesprek`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/versturen`
- `GET /admin/nieuwsbrieven/{newsletter_id:int}/voorbeeld`

### `newsletter.manage` — 19 routes

- `POST /admin/nieuwsbrieven`
- `POST /admin/nieuwsbrieven/abonnees`
- `POST /admin/nieuwsbrieven/abonnees/import`
- `POST /admin/nieuwsbrieven/abonnees/import/bevestigen`
- `POST /admin/nieuwsbrieven/abonnees/{subscriber_id:int}/uitschrijven`
- `POST /admin/nieuwsbrieven/abonnees/{subscriber_id:int}/verwijderen`
- `POST /admin/nieuwsbrieven/instellingen`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/bewaren`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/bijlage`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/keuzes/{group}`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/keuzes/{group}/{activity_id:int}/weg`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/kopieren`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/opnieuw`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/raakje/vraag`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/toepassen`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/weigeren`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/testmail`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/versturen`
- `POST /admin/nieuwsbrieven/{newsletter_id:int}/verwijderen`

### `meeting.view` — 9 routes

- `GET /admin/vergaderingen`
- `GET /admin/vergaderingen/kring`
- `GET /admin/vergaderingen/nieuw`
- `GET /admin/vergaderingen/{meeting_id}`
- `GET /admin/vergaderingen/{meeting_id}/bestand/{file_id}`
- `GET /admin/vergaderingen/{meeting_id}/bewerken`
- `GET /admin/vergaderingen/{meeting_id}/kiezer`
- `GET /admin/vergaderingen/{meeting_id}/pdf`
- `GET /admin/vergaderingen/{meeting_id}/verstuur`

### `meeting.manage` — 21 routes

- `POST /admin/vergaderingen`
- `POST /admin/vergaderingen/kring`
- `POST /admin/vergaderingen/kring/nieuw`
- `POST /admin/vergaderingen/kring/ondertekening`
- `POST /admin/vergaderingen/kring/{relation_id}/beeindigen`
- `POST /admin/vergaderingen/kring/{relation_id}/start`
- `POST /admin/vergaderingen/{meeting_id}/aanwezigheid`
- `POST /admin/vergaderingen/{meeting_id}/bewerken`
- `POST /admin/vergaderingen/{meeting_id}/bijlage`
- `POST /admin/vergaderingen/{meeting_id}/bijlage/{file_id}/meesturen`
- `POST /admin/vergaderingen/{meeting_id}/bijlage/{file_id}/verwijder`
- `POST /admin/vergaderingen/{meeting_id}/gast`
- `POST /admin/vergaderingen/{meeting_id}/gast/{guest_id}/verwijder`
- `POST /admin/vergaderingen/{meeting_id}/heropen`
- `POST /admin/vergaderingen/{meeting_id}/ontvanger`
- `POST /admin/vergaderingen/{meeting_id}/ontvanger/{recipient_id}/verwijder`
- `POST /admin/vergaderingen/{meeting_id}/punt`
- `POST /admin/vergaderingen/{meeting_id}/punt/{item_id}`
- `POST /admin/vergaderingen/{meeting_id}/punt/{item_id}/verwijder`
- `POST /admin/vergaderingen/{meeting_id}/sectie`
- `POST /admin/vergaderingen/{meeting_id}/verstuur`

### `report.view` — 8 routes

- `GET /admin`
- `GET /admin/rapporten`
- `GET /admin/rapporten/dataset/{fact_key}.ods`
- `GET /admin/rapporten/export.ods`
- `GET /admin/rapporten/lijst`
- `GET /admin/rapporten/nieuw`
- `GET /admin/rapporten/paneel`
- `GET /admin/rapporten/{report_id}`

### `report.manage` — 4 routes

- `POST /admin/rapporten`
- `POST /admin/rapporten/{report_id}`
- `POST /admin/rapporten/{report_id}/kopieren`
- `POST /admin/rapporten/{report_id}/verwijderen`

### `assistant.use` — 5 routes

- `GET /admin/rapporten/raakje`
- `POST /admin/rapporten/raakje`
- `POST /admin/rapporten/raakje/activiteit/{activity_id}`
- `GET /admin/rapporten/raakje/paneel`
- `POST /admin/rapporten/raakje/scherm/{scherm}`

### `party.view` — 11 routes

- `GET /admin/leden`
- `GET /admin/leden-import`
- `GET /admin/leden/gezin/{family_id}`
- `GET /admin/leden/gezin/{family_id}/inschrijvingen`
- `GET /admin/leden/gezin/{family_id}/persoon/{person_id}/email-rij`
- `GET /admin/leden/lijst`
- `GET /admin/leden/nieuw`
- `GET /admin/leden/nieuw/persoon-rij`
- `GET /admin/organisatie`
- `GET /admin/personen`
- `GET /admin/personen/lijst`

### `party.masterdata` — 16 routes

- `POST /admin/leden`
- `POST /admin/leden-import/commit`
- `POST /admin/leden-import/preview`
- `POST /admin/leden/gezin/{family_id}/adres`
- `POST /admin/leden/gezin/{family_id}/bestuurslid`
- `POST /admin/leden/gezin/{family_id}/lidmaatschappen`
- `POST /admin/leden/gezin/{family_id}/lidmaatschappen/{membership_id}/verwijderen`
- `POST /admin/leden/gezin/{family_id}/personen`
- `POST /admin/leden/gezin/{family_id}/persoon/{person_id}`
- `POST /admin/leden/gezin/{family_id}/persoon/{person_id}/email`
- `POST /admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/hoofd`
- `POST /admin/leden/gezin/{family_id}/persoon/{person_id}/email/{contact_id}/verwijderen`
- `POST /admin/leden/gezin/{family_id}/persoon/{person_id}/verwijderen`
- `POST /admin/leden/gezin/{family_id}/verwijderen`
- `POST /admin/organisatie`
- `POST /admin/personen/{person_id}/verwijderen`

### `product.view` — 3 routes

- `GET /admin/producten`
- `GET /admin/producten/nieuw`
- `GET /admin/producten/{product_id}`

### `product.masterdata` — 4 routes

- `POST /admin/producten`
- `POST /admin/producten/{product_id}`
- `POST /admin/producten/{product_id}/status`
- `POST /admin/producten/{product_id}/verwijderen`

### `price.view` — 2 routes

- `GET /admin/prijzen`
- `GET /admin/prijzen/{product_id}`

### `price.manage` — 1 routes

- `POST /admin/prijzen/{product_id}`

### `sales.view` — 0 routes

- none

### `sales.manage` — 0 routes

- none

### `stock.view` — 0 routes

- none

### `stock.manage` — 0 routes

- none

### `payment.view` — 7 routes

- `GET /admin/activiteiten/{activity_id}/betalingen`
- `GET /admin/betalingen`
- `GET /admin/betalingen/export`
- `GET /admin/betalingen/lijst`
- `GET /admin/betalingen/{record_id}`
- `GET /admin/inschrijvingen/{registration_id}/betalingen`
- `GET /admin/leden/gezin/{family_id}/betalingen`

### `payment.manage` — 7 routes

- `POST /admin/betalingen/{record_id}/bevestigen`
- `POST /admin/betalingen/{record_id}/bewerken`
- `POST /admin/betalingen/{record_id}/bijwerken`
- `POST /admin/betalingen/{record_id}/refund`
- `POST /admin/betalingen/{record_id}/status`
- `POST /admin/betalingen/{record_id}/verversen`
- `POST /admin/betalingen/{record_id}/verwijderen`

### `workbench.use` — 8 routes

- `GET /admin/accountmenu`
- `GET /admin/profiel`
- `GET /admin/werkbank`
- `GET /admin/werkbank/lijst`
- `GET /admin/werkbank/taken/{task_id}`
- `POST /admin/werkbank/taken/{task_id}/afgehandeld`
- `GET /admin/werkruimte-wisselen`
- `GET /admin/werkruimte-wisselen/{tenant_id}`

### `user.view` — 2 routes

- `GET /admin/gebruikers`
- `GET /admin/gebruikers/nieuw`

### `user.manage` — 3 routes

- `POST /admin/gebruikers`
- `POST /admin/gebruikers/{user_id}`
- `POST /admin/gebruikers/{user_id}/verwijderen`

### `settings.view` — 10 routes

- `GET /admin/ai-context`
- `GET /admin/ai-context/lijst`
- `GET /admin/design-system`
- `GET /admin/e-maillog`
- `GET /admin/e-maillog/lijst`
- `GET /admin/info`
- `GET /admin/info/ai-kosten`
- `GET /admin/instellingen`
- `GET /admin/ledenwijzigingen`
- `GET /admin/ledenwijzigingen/export`

### `settings.manage` — 9 routes

- `POST /admin/ai-context/documenten/{asset_id}/opnieuw-lezen`
- `POST /admin/ai-context/notities`
- `POST /admin/ai-context/paginas/{page_id}/bewerken`
- `POST /admin/ai-context/paginas/{page_id}/toggle`
- `POST /admin/ai-context/{row_id}/bewerken`
- `POST /admin/ai-context/{row_id}/toggle`
- `POST /admin/ai-context/{row_id}/verwijderen`
- `POST /admin/e-maillog/{log_id}/verwijderen`
- `POST /admin/instellingen`

### `platform.view` — 7 routes

- `GET /admin/gebruikers/alle-werkruimtes`
- `GET /admin/organisaties`
- `GET /admin/organisaties/nieuw`
- `GET /admin/organisaties/{organization_id}`
- `GET /admin/tenants`
- `GET /admin/tenants/nieuw`
- `GET /admin/tenants/{tenant_id}`

### `platform.manage` — 4 routes

- `POST /admin/organisaties`
- `POST /admin/organisaties/{organization_id}`
- `POST /admin/tenants`
- `POST /admin/tenants/{tenant_id}`

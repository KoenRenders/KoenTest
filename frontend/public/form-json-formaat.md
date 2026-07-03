# Formulier-JSON — formaatgids (voor mensen & AI)

Deze gids beschrijft het JSON-formaat waarmee je een formulier voor het Raak-portaal
aanmaakt. Geef dit bestand aan een AI met de vraag: *"Ontwerp een formulier-JSON
volgens deze gids over <onderwerp>."* Importeer het resultaat via **Admin →
Formulieren → Importeer JSON** (het formulier komt binnen als **concept**; controleer
het en zet de status op *Open* om het publiek te maken).

> Tip: exporteer een bestaand formulier met de **JSON**-knop om een concreet voorbeeld
> te krijgen.

---

## Topniveau-object

| Veld | Type | Verplicht | Betekenis |
|---|---|---|---|
| `title` | string | **ja** | Titel van het formulier. |
| `description` | string | nee | Introtekst bovenaan (getoond op de eerste stap). |
| `status` | `"draft"` \| `"open"` \| `"closed"` | nee (default `draft`) | `open` = publiek invulbaar. |
| `is_anonymous` | bool | nee | `true` = geen naam/e-mail vragen, geen submitter bewaren. |
| `send_confirmation` | bool | nee | Stuur een bevestigingsmail (vereist dat de invuller een e-mail opgeeft; niet bij anoniem). |
| `confirmation_message` | string | nee | Bedanktekst die na het indienen op het scherm verschijnt. |
| `allow_edit` | bool | nee | Geef de invuller een wijzig-link om zijn antwoord later aan te passen. |
| `requires_login` | bool | nee | Enkel voor ingelogde gebruikers. |
| `max_submissions` | int \| null | nee | Maximum aantal inzendingen. |
| `sections` | array | nee | Secties (zie onder). Leeg = één ongegroepeerde lijst vragen. |
| `fields` | array | **ja** | De vragen/velden (zie onder). |

---

## `sections[]` — secties (optioneel, voor groepering + branching)

| Veld | Type | Betekenis |
|---|---|---|
| `title` | string | Titel van de sectie. |
| `description` | string | Optionele uitleg onder de titel. |
| `position` | int | Volgorde (0, 1, 2 …). |
| `next_section_index` | int \| null | Spring ná deze sectie naar de sectie met deze **index in de `sections`-lijst**. Moet **groter** zijn dan de eigen index (enkel vooruit). Leeg = de volgende sectie (lineair). |
| `next_is_end` | bool | `true` = beëindig het formulier na deze sectie. |

Een veld verwijst naar zijn sectie via `section_index` (zie onder). Als er secties zijn,
wordt het formulier een **wizard** (stap per stap).

---

## `fields[]` — velden/vragen

Gemeenschappelijke velden:

| Veld | Type | Betekenis |
|---|---|---|
| `field_type` | string | Zie de tabel hieronder. |
| `label` | string | **Verplicht.** De vraag/het label. |
| `help_text` | string | Optionele hulptekst onder het label. |
| `required` | bool | Verplicht in te vullen. |
| `position` | int | Volgorde binnen (de sectie of het formulier). |
| `section_index` | int \| null | Index van de sectie waartoe dit veld hoort. `null` = ongegroepeerd (bovenaan). |
| `options` | array | Enkel voor keuzevelden (zie onder). |

### Veldtypes (`field_type`)

| Waarde | Betekenis | Type-specifieke velden |
|---|---|---|
| `text` | Korte tekst | `min_length`, `max_length`, `regex_pattern` |
| `textarea` | Lange tekst | `min_length`, `max_length`, `regex_pattern` |
| `email` | E-mailadres | `min_length`, `max_length`, `regex_pattern` |
| `number` | Getal | `min_value`, `max_value` |
| `phone` | Telefoon/gsm (lichte validatie) | — |
| `select` | Keuzelijst (één keuze, dropdown) | `options` (branching mogelijk) |
| `radio` | Één keuze (knoppen) | `options` (branching mogelijk) |
| `checkbox` | Meerkeuze | `options` |
| `rating` | Beoordeling 1..N | `rating_max` (1–10, default 5), `rating_low_label`, `rating_high_label` |
| `info` | Louter informatief tekstblok (geen antwoord) | gebruik `label` (+ `help_text`) voor de tekst |

> Er is (nog) **geen** `date`-type.

### Rating-veld
- `rating_max`: aantal punten, **1 tot 10** (wordt geplafonneerd; default 5).
- `rating_low_label` / `rating_high_label`: labels bij de laagste/hoogste waarde
  (bv. "Zeer ontevreden" → "Zeer tevreden"). Leeg + 5 punten = standaard "zeer slecht → zeer goed".

---

## `options[]` — keuzeopties (enkel `select` / `radio` / `checkbox`)

| Veld | Type | Betekenis |
|---|---|---|
| `label` | string | **Verplicht.** De keuzetekst. |
| `value` | string \| null | Optionele interne waarde. |
| `position` | int | Volgorde. |
| `is_other` | bool | `true` = toont een vrij tekstveld ("Andere…") wanneer aangevinkt/gekozen. |
| `skip_to_section_index` | int \| null | **Branching** (enkel `radio`/`select`): kies je deze optie, spring dan naar de sectie met deze index (moet **later** zijn dan de sectie van het veld). |
| `skip_to_end` | bool | **Branching** (enkel `radio`/`select`): kies je deze optie, beëindig dan het formulier. |

---

## Validatieregels (anders weigert de import met een 422)

1. `title` en elk veld-`label` zijn verplicht.
2. `status` moet `draft`, `open` of `closed` zijn.
3. **Branching** (`skip_to_section_index` / `skip_to_end`) kan **enkel** bij `radio` of `select`.
4. Alle sprongen (`next_section_index`, `skip_to_section_index`) mogen **enkel vooruit**
   (naar een sectie met een hogere index). Geen lussen.
5. `rating_max` wordt begrensd tot 1–10.
6. Laat `id`-velden **weg** bij het aanmaken (die zijn enkel voor bewerken).

---

## Volledig voorbeeld — gebruikt élk veldtype en elke mogelijkheid

Dit voorbeeld is bewust **compleet**: het toont elk `field_type`, opties met
`is_other`, branching (`skip_to_section_index` en `skip_to_end`), sectie-navigatie
(`next_section_index`, `next_is_end`) en alle topniveau-vlaggen. (Een CI-test importeert
dit voorbeeld bij elke build, dus het blijft gegarandeerd geldig.)

```json
{
  "title": "Volledig voorbeeldformulier",
  "description": "Deze intro verschijnt bovenaan de eerste stap.",
  "status": "draft",
  "is_anonymous": false,
  "send_confirmation": true,
  "confirmation_message": "Bedankt! Je antwoord is goed ontvangen.",
  "allow_edit": true,
  "requires_login": false,
  "max_submissions": 500,
  "sections": [
    { "title": "Jouw gegevens", "description": "We stellen ons even voor.", "position": 0 },
    { "title": "Alleen bij Ja", "position": 1, "next_section_index": 2 },
    { "title": "Voor iedereen", "position": 2 },
    { "title": "Afsluiting", "position": 3, "next_is_end": true }
  ],
  "fields": [
    { "field_type": "info", "label": "Welkom — dit formulier toont elk veldtype.", "section_index": 0 },
    { "field_type": "text", "label": "Voornaam", "required": true, "section_index": 0,
      "help_text": "Zoals op je identiteitskaart.", "min_length": 2, "max_length": 40 },
    { "field_type": "email", "label": "E-mail", "required": true, "section_index": 0 },
    { "field_type": "phone", "label": "Gsm (optioneel)", "section_index": 0 },
    { "field_type": "number", "label": "Gezinsgrootte", "section_index": 0, "min_value": 1, "max_value": 15 },
    { "field_type": "select", "label": "Hoe hoorde je van ons?", "section_index": 0,
      "options": [
        { "label": "Website" },
        { "label": "Vrienden" },
        { "label": "Anders", "is_other": true }
      ] },
    { "field_type": "radio", "label": "Wil je de detailvragen invullen?", "required": true, "section_index": 0,
      "options": [
        { "label": "Ja", "skip_to_section_index": 1 },
        { "label": "Nee, sla over", "skip_to_section_index": 2 }
      ] },
    { "field_type": "rating", "label": "Hoe tevreden ben je?", "section_index": 1,
      "rating_max": 5, "rating_low_label": "Zeer ontevreden", "rating_high_label": "Zeer tevreden" },
    { "field_type": "checkbox", "label": "Wat vond je goed? (meerdere mogelijk)", "section_index": 1,
      "options": [
        { "label": "De sfeer" },
        { "label": "Het eten" },
        { "label": "De locatie" },
        { "label": "Anders", "is_other": true }
      ] },
    { "field_type": "textarea", "label": "Toelichting (optioneel)", "section_index": 1, "max_length": 500 },
    { "field_type": "radio", "label": "Mogen we je contacteren?", "section_index": 2,
      "options": [
        { "label": "Ja" },
        { "label": "Nee, en stop hier", "skip_to_end": true }
      ] },
    { "field_type": "text", "label": "Postcode", "section_index": 2,
      "help_text": "4 cijfers.", "regex_pattern": "^[0-9]{4}$" },
    { "field_type": "info", "label": "Bedankt! Klik op versturen om af te ronden.", "section_index": 3 }
  ]
}
```

Wat dit voorbeeld demonstreert: een niet-anonieme wizard met vier secties; de eerste
`radio` **vertakt** (Ja → "Alleen bij Ja", Nee → rechtstreeks "Voor iedereen") en die
takken **komen samen** (via `next_section_index`); een `radio`-optie met `skip_to_end`
(formulier vroegtijdig beëindigen); een `select`/`checkbox` met een "Andere…"-optie
(`is_other`); een configureerbare `rating`; validatie op tekst (`min_length`/`max_length`/
`regex_pattern`) en getal (`min_value`/`max_value`); `info`-tekstblokken; en de vlaggen
`send_confirmation`, `confirmation_message`, `allow_edit` en `max_submissions`.

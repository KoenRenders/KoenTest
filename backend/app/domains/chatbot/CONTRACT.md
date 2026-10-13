# chatbot — componentcontract (fase 4c, #404; uitgebreid met CR-07, #917)

## Purpose and process

**Doel.** Raakje: de gespreksKERN, en de publieke assistent als eerste pakket
erop. De kern is domeinvrij — de lus, de provider-naad, de budgetten, de
naadwachter en het uitgaand logboek — en weet niets van activiteiten of van
rapporten. Een *capability-pakket* levert tools plus dispatcher en woont bij de
eigenaar van de gegevens: de publieke bot hier (`tools.py`), de
backoffice-assistent in `reporting/assistant.py`. Er is dus één Raakje, niet
twee: dezelfde lus met een andere gereedschapskist.

*Process (A2.4.6 — a question to Raakje on the site; the back-office assistant of A2.4.4 runs on the same loop).* Its records are `ChatbotInfo` (the context a board keeps) and `AiCallLog` (one row per outgoing call); none carries a `check()`.

## Publishes

### Facade (`api.py`)

- `ChatbotInfo` (model als type).
- `has_extracted_text(db, asset_id)` — a read: whether a document's text was read
  already. Media's reading job asks it before it reads again (CR-13 phase 4d,
  #1251).
- **Subscribes to** `DocumentTextExtracted` (`kernel/contracts/media.py`,
  `handlers.py`): the text media read of a document goes into the chatbot's own
  row for it, in the reading job's transaction. Until phase 4d media wrote that
  row itself.
- **De naad**, voor wie een pakket bouwt: `run_chat` (de lus; krijgt `tools` en
  `dispatch` als parameter), `GuardedProvider` + `public_rules`/`admin_rules`
  (de wachter), `sink_for` (het logboek), `get_provider`, `SeamBlocked`,
  `ChatTimeout`, en de twee dagbudgetten. Eén export, zodat een pakket de
  internals niet hoeft te kennen — en zodat wachter en logboek niet te omzeilen
  zijn door er een eigen lus naast te schrijven.

- **An answer in a fixed shape** (#1968): `json_answer(provider, messages, first=None)`
  and `UnusableAnswer`. Wherever Raakje must answer with a JSON object, the caller
  goes through it: the call asks the provider for JSON, an answer that does not
  parse is asked for once more, and the failure is logged without a word of the
  answer (`answers.py`).

**De publieke gereedschapskist wordt lazy geïmporteerd** (in `run_public_chat`).
Op modulehoogte haalt ze `media.api` binnen, dat voor de poster-extractie
`chatbot.api` importeert; sinds de facade de naad exporteert, loopt die kring
terug. Een domeinvrije lus die zijn eerste pakket importeert, had die kring
sowieso niet mogen hebben.

*Counted in the code on 13 October 2026:* the facade exports 35 names (24 functions, 8 classes, 3 values); events it owns (`kernel/contracts/`): none; ports it offers: none.

## Consumes

### Providers

- Chat: **kale httpx** tegen de Mistral chat-completions-API (§19.3 ✓; de
  `mistralai`-SDK wordt hier niet gebruikt).
- STT (Voxtral realtime, `chatbot/stt/` — the voice input of the widget, moved here from `domains/stt` in CR-13 phase 4: an adapter belongs under the domain that uses it): gebruikt nog wél de
  `mistralai[realtime]`-SDK — de realtime-websocketvervanging vergt verificatie
  tegen het live endpoint en staat als expliciet restpunt op #404.

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, cms, mdm, media, membership, payment; subscribes to `DocumentTextExtracted`; calls `ReadTextAgain` (media), `SubmitMessage` (forms).

## Owns

### Data

Schema `ai` (migratie 084): `chatbot_info`; migratie 118: `ai_call_log`. `media_asset_id` en `cms_page_id`
zijn soft-refs (§8; ORM via expliciete primaryjoin). `stt` blijft schemaloos
(capaciteit).

*Counted in the code on 13 October 2026:* schema `ai`, 10 tables (2 data, 8 code and label), 2 of them with `tenant_id`; status columns: `ai_call_log.status` (code list `ai_status`: ok, blocked, error, moderated — the outcome of one call, no lifecycle); jobs: none.

## Screens

### Routers & schermen

- `ui.py` — **`/raakje`** (htmx-vraag/antwoord, server-side compleet — geen
  SSE) en **`/admin/ai-context`** (notities, aan/uit, verwijderen).
- Kill-switch: `CHAT_ENABLED` (bestaand) geldt ook voor het htmx-scherm.

`ui.py`: 10 routes under `/raakje/vraag` and `/admin/ai-context`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| ISO 4217 | currency code | `ai.ai_call_log` · `cost_currency`, beside `cost_amount` | follows |

## Rules and gates

### Naadwachter en logboek (CR-07 §5.8/§6.4)

- `seam.py` — onafhankelijke controle vlak vóór de HTTP-post: patronen
  (telefoon, IBAN, en bij de beheerderskant e-mail) plus, enkel daar, de
  ledennamen. Blokkeert i.p.v. te versturen. **Deelt geen code met de
  tokenisatie of met `ai_exposure`** — een controle die samen met haar onderwerp
  faalt, controleert niets. De patronen slaan het system-bericht over: daar
  staan het e-mailadres en de IBAN van de vereniging met opzet in.
- `logbook.py` — één rij per uitgaande oproep, mét tokenverbruik en welke schil
  belde, in een **eigen sessie** gecommit: een rij hier zegt dat er data vertrok,
  en dat mag niet verdwijnen als de beurt erna misloopt.

- **Rules whose home is this module** — No `@validates` and no `check()` in `models.py`; no `CheckConstraint` there. Its rules stand in its service.
- **Gates in this module's own `tests/`** — none among its 9 test files. The gates about it stand in `backend/tests/`: `test_ai_log_coverage_gate.py`, `test_public_tool_boundary_gate.py`, `test_assistant_gate.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E16** — Raakje in the back office (CR-07): built in v2.5.0; the close-out of the document is due (E38).

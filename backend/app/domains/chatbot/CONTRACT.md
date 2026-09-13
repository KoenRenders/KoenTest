# chatbot — componentcontract (fase 4c, #404; uitgebreid met CR-07, #917)

**Doel.** Raakje: de gespreksKERN, en de publieke assistent als eerste pakket
erop. De kern is domeinvrij — de lus, de provider-naad, de budgetten, de
naadwachter en het uitgaand logboek — en weet niets van activiteiten of van
rapporten. Een *capability-pakket* levert tools plus dispatcher en woont bij de
eigenaar van de gegevens: de publieke bot hier (`tools.py`), de
backoffice-assistent in `reporting/assistant.py`. Er is dus één Raakje, niet
twee: dezelfde lus met een andere gereedschapskist.

## Facade (`api.py`)

- `ChatbotInfo` (model als type; gebruikt door de media-extractie).
- **De naad**, voor wie een pakket bouwt: `run_chat` (de lus; krijgt `tools` en
  `dispatch` als parameter), `GuardedProvider` + `public_rules`/`admin_rules`
  (de wachter), `sink_for` (het logboek), `get_provider`, `SeamBlocked`,
  `ChatTimeout`, en de twee dagbudgetten. Eén export, zodat een pakket de
  internals niet hoeft te kennen — en zodat wachter en logboek niet te omzeilen
  zijn door er een eigen lus naast te schrijven.

**De publieke gereedschapskist wordt lazy geïmporteerd** (in `run_public_chat`).
Op modulehoogte haalt ze `media.api` binnen, dat voor de poster-extractie
`chatbot.api` importeert; sinds de facade de naad exporteert, loopt die kring
terug. Een domeinvrije lus die zijn eerste pakket importeert, had die kring
sowieso niet mogen hebben.

## Routers & schermen

- `router.py` — `POST /api/v1/chat` (SSE, React-widget; vervalt bij #405).
- `info_router.py` — admin-API voor de ai-context.
- `ui.py` — **`/raakje`** (htmx-vraag/antwoord, server-side compleet — geen
  SSE) en **`/admin/ai-context`** (notities, aan/uit, verwijderen).
- Kill-switch: `CHAT_ENABLED` (bestaand) geldt ook voor het htmx-scherm.

## Providers

- Chat: **kale httpx** tegen de Mistral chat-completions-API (§19.3 ✓; de
  `mistralai`-SDK wordt hier niet gebruikt).
- STT (Voxtral realtime, `domains/stt`): gebruikt nog wél de
  `mistralai[realtime]`-SDK — de realtime-websocketvervanging vergt verificatie
  tegen het live endpoint en staat als expliciet restpunt op #404.

## Naadwachter en logboek (CR-07 §5.8/§6.4)

- `seam.py` — onafhankelijke controle vlak vóór de HTTP-post: patronen
  (telefoon, IBAN, en bij de beheerderskant e-mail) plus, enkel daar, de
  ledennamen. Blokkeert i.p.v. te versturen. **Deelt geen code met de
  tokenisatie of met `ai_exposure`** — een controle die samen met haar onderwerp
  faalt, controleert niets. De patronen slaan het system-bericht over: daar
  staan het e-mailadres en de IBAN van de vereniging met opzet in.
- `logbook.py` — één rij per uitgaande oproep, mét tokenverbruik en welke schil
  belde, in een **eigen sessie** gecommit: een rij hier zegt dat er data vertrok,
  en dat mag niet verdwijnen als de beurt erna misloopt.

## Data

Schema `ai` (migratie 084): `chatbot_info`; migratie 118: `ai_call_log`. `media_asset_id` en `cms_page_id`
zijn soft-refs (§8; ORM via expliciete primaryjoin). `stt` blijft schemaloos
(capaciteit).

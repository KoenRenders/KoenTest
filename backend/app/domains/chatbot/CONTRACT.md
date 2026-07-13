# chatbot — componentcontract (fase 4c, #404)

**Doel.** Raakje: de publieke assistent (chat-completions met tool-grounding),
de context-opbouw (documenten/CMS/notities) en het beheer daarvan.

## Facade (`api.py`)

- `ChatbotInfo` (model als type; gebruikt door de media-extractie).

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

## Data

Schema `ai` (migratie 084): `chatbot_info`. `media_asset_id` en `cms_page_id`
zijn soft-refs (§8; ORM via expliciete primaryjoin). `stt` blijft schemaloos
(capaciteit).

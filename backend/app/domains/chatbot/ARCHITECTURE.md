# Architectuur — chatbot 'Raakje' (#205)

Publieke website-chatbot die bezoekers informeert over Raak Millegem, hun naar de
juiste activiteit begeleidt, en hen via de bestaande IdeaBox een vraag/idee laat
achterlaten. Dit document legt uit **hoe data van ons systeem bij het taalmodel
komt** en waar de grenzen liggen.

## De kern in drie zinnen

1. **Wij trainen niets en hebben geen privé-model.** We gebruiken Mistral's
   gedeelde, gehoste model (`mistral-small-latest` = Mistral Small 4) via hun API.
2. **Wij injecteren niets ín het model.** De gewichten veranderen nooit. Onze data
   reist **per vraag mee als tekst** (input), wordt één keer gelezen, en is daarna
   weg — geen opslag, geen training (Mistral traint standaard niet op API-data).
3. **Het model is stateless.** Het onthoudt niets tussen gesprekken; elke call
   draagt de nodige context opnieuw mee.

Analogie: Mistral is een belezen consultant die perfect Nederlands spreekt maar
**niets** over Raak Millegem weet. Bij elke vraag geven we hem een verse briefing,
hij mag ons dingen laten opzoeken, hij formuleert een antwoord — en vergeet daarna
alles. We sturen hem nooit naar school.

## Wie levert wat

| | Van **Mistral** | Van **ons** |
|---|---|---|
| Taalbegrip, vlot Nederlands, redeneren | ✅ | |
| Beslissen welke tool nodig is, antwoord formuleren | ✅ | |
| De **feiten** (CMS-tekst, activiteiten, datums, prijzen) | | ✅ (uit onze DB) |
| De regels ("verzin niets, structuurvelden winnen") | | ✅ (in onze prompt) |

De *wijsheid* (taal/intelligentie) komt van Mistral; de *waarheid* (data) van ons.

## Sturen we de hele database mee? Nee.

Twee mechanismen, allebei strak begrensd:

- **Context-stuffing** (`context.py`): enkel de tekst van **gepubliceerde
  CMS-pagina's**, afgetopt op `MAX_CMS_CHARS` (12.000 tekens). Geen ledentabel,
  geen activiteitentabel — alleen publieke paginatekst.
- **Tool use** (`tools.py`): activiteiten/prijzen gaan **niet** vooraf mee. Het
  model krijgt een lijst functies die het mág aanroepen; pas op aanvraag voert
  **onze** backend de query uit en stuurt enkel het **gevraagde stukje** als JSON
  terug. De data blijft in onze DB; het model ziet nooit de volledige tabel.
- **Caps**: geschiedenis ≤ 20 berichten, elk ≤ 2.000 tekens; max 4 tool-rondes.

Per call ≈ persona + afgetopte CMS-tekst + kort gesprek + (eventueel) klein
JSON-resultaat. Zou de CMS ooit enorm worden, dan stap je over op RAG (alleen
relevante stukjes ophalen). Voor één vereniging is dat niet nodig.

## De reisweg van één vraag

```
Browser (ChatWidget.tsx, streamChat in api.ts)
   │  POST /api/v1/chat   { messages: [...] }
   ▼
ONZE BACKEND  (routers/chat.py — API-key staat hier, serverside)
   │  1. vangrails: rate-limit + dagbudget (limiter.py), 2000-tekens-cap (schemas/chat.py)
   │  2. prompt = [system: persona + CMS-tekst (context.py)] + gespreksgeschiedenis
   │  3. + lijst van 3 toegelaten tools (tools.py)
   ▼
MISTRAL API  (providers/mistral.py → api.mistral.ai — het gedeelde model)
   │  leest de briefing en kiest:
   ├─(a) "ik kan antwoorden"            → stuurt tekst terug
   └─(b) "roep get_upcoming_activities" → vraagt een tool aan
   ▼                                          ▲
ONZE BACKEND voert de tool uit ───────────────┘   (SQL op onze DB → JSON terug)
   │  de lus (service.py: run_chat) herhaalt tot een eindantwoord, max 4 rondes
   ▼
ONZE BACKEND streamt het eindantwoord als SSE terug → Browser toont het live
```

## Componenten

| Bestand | Rol |
|---|---|
| `providers/base.py` | De naad: `LLMProvider.complete(messages, tools)`. |
| `providers/mistral.py` | **Enige** plek die met Mistral praat (httpx → REST). |
| `providers/mock.py` | Afhankelijkheidsvrije, data-bewuste stub (CI/lokaal, geen kost). |
| `providers/factory.py` | Kiest provider op `CHAT_LLM_PROVIDER` (auto/mistral/mock). |
| `context.py` | System-prompt: persona + vangrails + gepubliceerde CMS-tekst. |
| `tools.py` | De 3 publieke tools + dispatch = de **security-grens** (allowlist). |
| `service.py` | De tool-loop tussen provider en tools. |
| `../../routers/chat.py` | `POST /api/v1/chat` (SSE), key serverside, limieten. |
| `../../schemas/chat.py` | Vorm-validatie (per-bericht cap, geschiedenis). |
| `frontend/.../ChatWidget.tsx` | Zwevend widget, SSE-streaming, STT-mic. |

## Swapbare provider-laag

De productie-eis is **Mistral (EU-verwerker)**, maar alles loopt via `LLMProvider`.
Een andere provider (Ionos, Infomaniak, self-hosted open model) inschuiven raakt
**enkel** de `providers/`-map; router, tools, context en widget blijven ongemoeid.
`CHAT_LLM_PROVIDER=auto` kiest Mistral zodra er een `MISTRAL_API_KEY` staat, anders
de kosteloze mock.

## Security-grens

De bot kan **uitsluitend** de 3 tools in de allowlist aanroepen — twee publieke
lees-acties op activiteiten en `submit_idea` (hergebruikt exact het IdeaBox-
schrijfpad + bevestigingsmail). `execute_tool` weigert elke andere naam. **Geen**
ledendata, betalingen of admin via de bot. Naar Mistral gaat enkel publieke
informatie + wat de bezoeker zelf typt.

## Kosten

Mistral Small 4: ±$0.10 input / $0.30 output per miljoen tokens. Eén
context-gestookte vraag ≈ 10k input + ~300 output ≈ **€0,001–0,003**. ~1.000
vragen/maand ≈ **€1–3**. De volumelimiet (2.000 tekens/bericht, 20.000/IP/dag) is
daarom vooral een misbruik-rem, geen budgetnoodzaak.

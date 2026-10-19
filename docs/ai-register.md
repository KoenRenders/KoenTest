# AI register

Every use of AI in this project, in the application and in the way we build it, with the class we give it under Regulation (EU) 2024/1689 (the AI Act). State as of 16 October 2026; the application dates of the regulation may shift, so a date is never copied from here into a decision.

## 1. Purpose and upkeep

- **One row per AI use.** The change that adds an AI use (a change request, an issue) adds its row in the same change; the change that removes one removes the row.
- **Owner:** Koen. The row says what goes to the model, who is in the loop, the class, and what guards and logs the call.
- **The class is our reading** of the regulation, written down so that the next reader sees the reasoning and can challenge it. It is not an external ruling.
- A row marked *open* names something not yet verified in the code or not yet decided; the list is in section 6.

## 2. Our roles

- **Provider of the AI-enabled portal.** We build the portal and put its AI functions in service for the associations that use it (Raakje, the drafting helpers, dictation, the illustrations).
- **Deployer of third-party models.** The models themselves are made by others (Mistral, Black Forest Labs, and for building: Anthropic, DeepSeek). Their makers carry the duties of a model provider; we carry those of whoever integrates and uses it.
- The association that runs a portal is the deployer of the functions on its own screens. Rows below describe the function, not the association.

## 3. AI in the application

| ID | Function | Model, provider, region | What goes to the model | Human in the loop | Class (our reading) | Transparency duty | Guard and log |
|---|---|---|---|---|---|---|---|
| A1 | **Raakje, public chatbot** (chatbot domain) | `mistral-small-latest`, Mistral, France (EU) | The visitor's question, published site texts, public activity data through three tools (activities, activity detail, leave an idea). A visitor may type their own name and e-mail to leave an idea | None for answers (a visitor reads them); an idea lands in the idea box for people | Limited risk: it talks to natural persons | The visitor must know it is AI. The opening button says "onze AI-assistent"; the panel text is *open* | Public guard rules (phone and IBAN patterns, input cap 2 000 characters, daily character budget, at most 4 tool rounds); every call in `ai.ai_call_log`, surface *public*; off by default (`chat_enabled`) |
| A2 | **Raakje in the back office** (reporting assistant) | `mistral-medium-latest`, Mistral, France (EU) | A question from a signed-in administrator and report results composed through two tools; objects marked *tokenised* leave as tokens, not names; the model never sees SQL | The administrator reads the answer and decides | Minimal risk: internal reporting aid, decides nothing about a person | Staff know it is AI from context; the label says assistant | Back-office guard rules (names from the member administration, e-mail, phone, IBAN), per-user daily budget, wall-clock limit; call and verbatim payload logged, surface *admin*, capability *reporting*; off by default (`admin_chat_enabled`) and per-tenant switch |
| A3 | **Newsletter drafting** (newsletter domain) | `mistral-medium-latest`, Mistral, France (EU) | The author's instruction, the chosen activities (names, dates), the current letter, public texts. Never a recipient, never an audience | The author reviews the proposal and applies it with a click; the model never sends | Minimal risk | Text goes to members after human review and editing; no machine-marking duty on us | Back-office guard rules, facts only through markers the server fills; logged under capability *newsletter_drafting* |
| A4 | **Activity proposer** (activities domain) | `mistral-medium-latest`, Mistral, France (EU) | What the user asked in the panel and what the activity record already holds | The form takes the values on *Toepassen*; one save stores them | Minimal risk | None beyond the assistant label | Back-office guard rules; location, day and hour are proposed only when grounded in a source, the rest is named as left out; logged under capability *activity_drafting* |
| A5 | **Speech to text** (dictation) | `voxtral-mini-transcribe-realtime`, Mistral, France (EU) | The speech of the person who dictates, streamed from the browser through our server | The person reads the text and edits it | Minimal risk: no emotion recognition, no identification of a person by voice | None specific | Handshake rate limit per IP, daily audio cap per IP; logged under capability *dictation*; browser-native dictation is the alternative path |
| A6 | **Reading documents** (media domain) | `mistral-ocr-latest`, Mistral, France (EU) | A scanned PDF or an image uploaded to the media library; a PDF with a text layer is read locally and sent nowhere | The text supplements soft information; dates, prices and locations come from structured fields and win | Minimal risk | None | Runs once per asset as a background task; logged under capability *ocr*; switch `ocr_enabled` |
| A7 | **Design Studio illustrations** | FLUX.2 [pro], Black Forest Labs, Germany (EU endpoint) | A prompt written by the server around the user's description; no personal data | The user picks one of four variants or discards them | Limited risk: synthetic images | Our line-art illustrations show no real person, place or event; whether the provider marks its output in a machine-readable way is not verified | Kill switch `designstudio_ai_images_enabled` (off by default), monthly budget per unit and per platform, reservation before the call, provider moderation refusals kept; logged under capability *image*, surface *designstudio* |
| A8 | **Mailbox agent** (CR-39, planned, not built) | To be chosen in the study of the change request | Condition R7 of the change request: no e-mail address, VAT number, national register number, name of a person or company, or bank account number goes to an AI model, not even in Europe | A person decides every outcome | Set after the study | Set after the study | Defined in the change request after the study |

## 4. AI in how we build

All of these are development aids. None decides anything about a person, so all fall under minimal risk. Claude Code and OpenCode are named deviations from Europe First (see `AGENTS.md`).

| ID | Tool, vendor, region | Used for | What it can reach | Controls |
|---|---|---|---|---|
| B1 | **Claude Code**, Anthropic, United States | The master, development, design-documentation and architecture sessions: code, change requests, reviews | Its own working copy of this public repository and what a session reads in a command | No personal data from an environment is taken into a session: counts, internal ids, amounts and dates only. Only the master session merges to `master`, deploys and reads an environment. Every commit carries a trailer naming the tool |
| B2 | **Mistral Vibe** (`mistral-vibe2`), Mistral, France (EU) | Building under a change request or issue assigned by Koen | Its own system user, working copy and rootless Docker | On leave until 1 November 2026. Waits after every *ready for review*; never merges or deploys; every pull request is read by a Claude session |
| B3 | **OpenCode** (`opencode1`) on DeepSeek's own API, China | Building under a change request or issue assigned by Koen, as an evaluation | A system user of its own, without sudo, outside the Docker group, with a clone of this repository, a token for this repository only, and no access to the project folder with real data | Ten limits in `AGENTS.md`: five enforced by the machine (own working copy, no `.env` with real values, no `raak` or SSH keys, never against an environment, no access to the project folder), five checked in every pull request (no secret or hostname in the diff, no pasted environment output, made-up test data, no real call to an outside service, trailer `Tool: opencode1`). Waits after every *ready for review* |

## 5. Duties for every row

- **AI literacy.** Everyone who works with these functions is expected to understand what a model can and cannot do. The records of this are `AGENTS.md` (how sessions work), `docs/chatbot.md` and `docs/raakje-backoffice.md` (what reaches a model and what stops it), and the study inside CR-39.
- **No prohibited practice.** None of the rows involves social scoring, manipulation, emotion recognition at work or in education, biometric categorisation, or untargeted scraping of faces. A new row that comes near one stops there and goes to Koen first.
- **High-risk domains.** None of the rows decides on hiring, assessment or tasks of staff, credit, insurance, education or access to essential services. A function that does moves out of this table into its own design with the provider duties of the regulation (risk management, documentation, logging, human oversight, conformity assessment, registration).
- **No approval from an authority is needed to ship** a function of minimal or limited risk. Duties for limited risk are the transparency lines above.
- **Vendor notes.** Mistral (France) and Black Forest Labs (Germany) are EU companies and are called on their EU endpoints. Anthropic (United States) and DeepSeek (China) appear only in the build, with the controls of section 4. When a provider changes its terms, its model version or its region, the row is revisited.

## 6. What we log today, and what is open

**Logged today.**
- `ai.ai_call_log`: one row per call, blocked calls included. It holds the surface (*public*, *admin*, *designstudio*), the capability, the actor, the model name, the provider and endpoint, the status (*ok*, *blocked*, *error*, *moderated*), tokens, duration, cost, and the verbatim payload as it left (cut at 100 000 characters with a visible marker). Rows are never updated by the application.
- The cost screens read the same table.
- The **guard** at the provider seam checks every payload once more, immediately before the post, independently of the classification and tokenisation upstream; a refusal is itself a row.

**Open points to verify or decide.**
1. **Says it is AI.** The public widget button does ("onze AI-assistent"). Whether the text inside the panel, the back-office panel and the drafting panels say it too is not checked.
2. **Model and prompt version.** The model name is logged per call; whether a version of the prompt or the persona is recorded is not verified.
3. **Apply and reject.** Applying a newsletter or activity proposal is an editor action; whether it is recorded next to the call (accepted, edited, rejected) is not verified, and the log in the code does not show it.
4. **Retention.** The AI log is append-only and the code names no cleanup job for it. How long rows are kept, and for the payload column in particular, is not decided.
5. **Dictation and documents.** Whether the log keeps the audio or the document text, or only the call, is not verified for A5 and A6.
6. **A8.** The class, the transparency lines and the logging of the mailbox agent follow from the study of CR-39.

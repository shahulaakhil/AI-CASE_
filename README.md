# LitigatAI

An AI workbench for Indian litigation practice. Ten tools that cover a matter
from the first brief to the final filing, in one web app you can deploy on
Render in a few minutes.

Built as a FastAPI service with a hand written single page front end. No build
step, no Node toolchain, no database server required.

---

## Demo

![Demo highlights](docs/demo/law-project-preview.gif)

Highlights from the full walkthrough, looping. Nothing here is mocked: every
answer on screen came back from a live model while the recording was running.

**Full walkthrough, 6m 17s, all 15 steps captioned:**
[law-project-litigatai.mp4](docs/demo/law-project-litigatai.mp4) (6.2 MB)
&nbsp;·&nbsp;
[captions (.srt)](docs/demo/law-project-litigatai.srt)

> GitHub cannot play a committed mp4 inline, so that link downloads the file
> rather than streaming it. The GIF above is the inline preview.

---

## Screenshots

Every image below was captured from the live deployment, not from a mockup.

![The workspace on opening](docs/screenshots/01-dashboard.png)

*Ten tools in the sidebar, with live counts for matters tracked, hearings due
this week and dates that have already passed.*

![A drafted plaint with its citations](docs/screenshots/04-document-drafter.png)

*A plaint drafted from a paragraph of facts, in Indian court format, with every
authority it relies on pulled out beside it and clickable through to the
Authority Check tool.*

![A cited research answer](docs/screenshots/03-legal-research.png)

*A research question answered with a short answer, the statutory position, the
case law, and the points that still need checking before you rely on them.*

![A judgment turned into a chronology](docs/screenshots/07-list-of-dates.png)

*A judgment in, a filing ready chronology out: ten dated events, each with the
paragraph it came from and its legal significance.*

![The hearing diary](docs/screenshots/09-court-tracker.png)

*The Court Tracker. One date has already passed and needs an update, one falls
this week.*

![Five providers in the model picker](docs/screenshots/15-model-picker.png)

*Five AI providers with live model lists. Two are supplied by the host here, and
the rest switch on the moment a visitor adds their own key.*

<details>
<summary>The rest of the tools, the light theme and the phone layout</summary>

| | |
| --- | --- |
| ![Toolkit](docs/screenshots/02-toolkit.png) The ten tools | ![Judgment Summariser](docs/screenshots/06-judgment-summariser.png) Judgment Summariser |
| ![Counter Arguments](docs/screenshots/08-counter-arguments.png) Counter Arguments | ![Case detail](docs/screenshots/10-tracker-detail.png) A matter with its hearing history |
| ![Bare Acts](docs/screenshots/11-bare-acts.png) Bare Acts | ![Authority Check](docs/screenshots/12-authority-check.png) Authority Check |
| ![Translate and OCR](docs/screenshots/13-translate-ocr.png) Translate and OCR | ![Prompt Enhancer](docs/screenshots/14-prompt-enhancer.png) Prompt Enhancer |
| ![Bring your own key](docs/screenshots/16-api-keys.png) Bring your own key | ![Light theme](docs/screenshots/17-light-theme.png) The light theme |
| ![Phone layout](docs/screenshots/18-mobile.png) On a phone | ![Phone navigation](docs/screenshots/19-mobile-nav.png) Phone navigation |

</details>

---

## Two branches

| Branch | What is on it |
| --- | --- |
| **`main`** | This version. FastAPI, a no build front end, bring your own key, deployable free on Render. |
| **`streamlit`** | The original Streamlit application, preserved unchanged at commit [`734fabe3`](../../tree/streamlit). |

The Streamlit version still runs. It was rebuilt rather than patched because
Streamlit re-runs the whole script on every interaction, which fights against a
multi step legal workflow, and because a Streamlit deployment cannot accept a
visitor's own API key per request.

---

## What it does

| Tool | What it gives you |
| --- | --- |
| List of Dates | Every material date pulled out of a case file into a court ready chronology you can edit and export |
| Judgment Summariser | A structured brief: case details, facts, issues, arguments, held, ratio, significance |
| Judgment Q&A | Upload a judgment once, ask multiple questions, and see answers grounded in retrieved passages with page citations |
| Authority Check | Whether a cited judgment is still good law, with the citing judgments that decide it |
| Translate and OCR | Text out of scans, any Indian language into English, then a question box over the document |
| Legal Research | Cited answers on Indian law, grounded in Indian Kanoon retrieval, or answers drawn from an uploaded judgment |
| Prompt Enhancer | A rough question rewritten into a structured research instruction, handed straight to Legal Research |
| Bare Acts | Eleven Indian statutes indexed section by section, with amendment history and an ask box on any provision |
| Document Drafter | Plaints, written statements, arbitration pleadings, counter claims, notices and applications, with citations marked inline |
| Counter Arguments | Every claim in the other side's pleading extracted, rated, rebutted, then assembled into a written statement |
| Court Tracker | A hearing diary with next dates, outcomes, status and an eCourts CNR lookup |

Every AI answer can be exported as DOCX, PDF, CSV, Markdown or plain text.

---

## Bring your own API key

The app works with **Groq, Google Gemini, Cloudflare Workers AI, OpenAI and
Hugging Face**. You need **one** of them, and it can come from either side:

- **The visitor's key.** Anyone using the app can open **API keys** in the top
  bar, paste their own key, and have it tested against the provider on the
  spot. The key is kept in that browser's local storage, sent as a request
  header with that person's own calls, and used for those calls only. It is
  never written to the server's disk, its logs, or its database, and no other
  visitor can see or use it. This is what lets the app be hosted publicly on a
  free plan without the operator paying for anyone's inference.
- **The operator's key.** Any key set in the environment works as a default for
  every visitor who has not brought their own. A visitor's key always wins for
  their own request.

The panel labels which is which, so nobody has to guess whose credit a call is
spending: **your key** or **provided by host**.

Set `ALLOW_CLIENT_KEYS=0` for a private deployment that must refuse visitor
keys and run only on its own.

Whatever keys are present are detected per request, only usable providers appear
in the model picker, and every tool runs on whichever one you select.

Routing is strict: the provider and model you choose in the picker are what get
called. There is no silent switch to a different provider behind your back. If
the selected provider rate limits you or runs out of credit, the app says so and
tells you what to do about it.

Two extras worth knowing:

- **Model lists are live.** On start up each provider is asked what it can
  actually serve, and the picker shows the intersection of that with a curated
  short list. A model retired by the provider disappears on its own, and new
  ones show up without a code change. You can also type any model id by hand.
- **Vision is tracked per model.** Scanned PDFs and images need a model that can
  read pictures. The app knows which ones can, and if your selected model
  cannot, it names the ones that can rather than failing obscurely.

| Provider | Environment variable | Request header | Free tier | Get a key |
| --- | --- | --- | --- | --- |
| Google Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `X-LLM-Key-gemini` | yes | https://aistudio.google.com/apikey |
| Groq | `GROQ_API_KEY` | `X-LLM-Key-groq` | yes | https://console.groq.com/keys |
| Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN` **and** `CLOUDFLARE_ACCOUNT_ID` | `X-LLM-Key-cloudflare` and `X-LLM-Account-cloudflare` | yes, daily allowance | https://dash.cloudflare.com/profile/api-tokens |
| OpenAI | `OPENAI_API_KEY` | `X-LLM-Key-openai` | no | https://platform.openai.com/api-keys |
| Hugging Face | `HUGGINGFACE_API_KEY` or `HF_TOKEN` | `X-LLM-Key-huggingface` | limited | https://huggingface.co/settings/tokens |
| Indian Kanoon | `INDIAN_KANOON_API_TOKEN` | `X-LLM-Key-kanoon` | no | https://api.indiankanoon.org/ |

`OPENAI_BASE_URL` points the OpenAI adapter at any OpenAI compatible gateway, so
a self hosted or corporate endpoint works through the same path. A visitor can
do the same for their own requests with `X-LLM-Base-openai`, which the UI
exposes under **Advanced** on the OpenAI and Hugging Face cards. Only `https`
gateways are accepted.

### Cloudflare needs two values, not one

Cloudflare is the only provider here that cannot be configured with a key
alone. Its account id is part of the request URL:

```
https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1/chat/completions
```

So both `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are required, and the
provider reports itself unavailable, with that reason, when only one is present.
A visitor supplies the account id in a second field next to the key.

The account id is validated as letters and digits only before it is placed in
the URL, so a crafted value cannot escape its path segment or redirect the
request to another host. The token needs the **Workers AI** permission.

Model ids are the full namespaced form. These were taken from Cloudflare's own
model pages rather than guessed:

| Model | Context | Note |
| --- | --- | --- |
| `@cf/openai/gpt-oss-120b` | 128k | Strongest reasoning of the four |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 24k | Quick, capable default |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | 131k | Natively multimodal, reads scanned pages |
| `@cf/qwen/qwen3-30b-a3b-fp8` | 32k | |

Cloudflare's OpenAI compatibility layer serves no `/v1/models` route, so the
model picker is filled from Cloudflare's own `ai/models/search` catalogue
filtered to text generation, and falls back to the four above if that call
fails.

### How a visitor's key is handled

Worth being precise about, since it is someone else's credential:

- It is read from a request header into a context variable that lives for the
  length of that one request, and is dropped when the request ends. The
  provider adapters are process wide singletons, so the adapter is shared but
  the credential never is.
- Model lists and provider SDK clients are cached under a SHA-256 fingerprint
  of the key, never under the provider name alone, so one visitor's cached
  state is never handed to another.
- Nothing logs a key. `/api/config` reports only *which* providers a request
  has a key for, never the value.
- A credential over 512 characters, or carrying anything outside printable
  ASCII, is rejected before it can reach an upstream `Authorization` header.
- API responses are sent `Cache-Control: no-store`, because a response can
  depend on the caller's key.
- A key the provider rejects is deleted from the browser instead of being
  retried on every later call.

The honest caveat: a key in `localStorage` is only as safe as the page it sits
on, so serve the app over HTTPS and treat a revocable key as the right kind of
key to paste into any BYOK app, including this one.

---

## Deploy to Render

### With the blueprint

1. Push this folder to GitHub as its own repository:

   ```bash
   cd law-project-hoster
   git init
   git add .
   git commit -m "LitigatAI"
   git remote add origin https://github.com/<you>/litigatai.git
   git push -u origin main
   ```

   `.gitignore` already keeps `.env` and the local database out of the commit.
2. In Render, choose **New** then **Blueprint** and select the repository.
   `render.yaml` is picked up automatically.
3. Add at least one provider key under **Environment**.
4. Deploy. The health check at `/api/health` turns green and the app is live.

### If you keep this as a subfolder of a bigger repository

Render only reads a blueprint named `render.yaml` that sits at the **root of the
repository**. A `render.yaml` inside a subfolder is never picked up. So if this
folder lives inside another repository, do one of these:

- Copy the ready made file to the repository root:

  ```bash
  cp law-project-hoster/render.root.yaml render.yaml
  git add render.yaml && git commit -m "Render blueprint" && git push
  ```

  It is the same blueprint with `rootDir: law-project-hoster` already set.

- Or skip blueprints entirely: create the Web Service by hand and set
  **Root Directory** to `law-project-hoster` in the dashboard.

### Forking, cloning, or handing it to someone else

The project is not tied to any repository, account or URL, so a fork or a fresh
clone under a different GitHub account deploys exactly the same way. Two things
to know:

- **API keys do not travel with the code.** `.env` is in `.gitignore` and never
  reaches the repository, and every key in the blueprint is marked `sync: false`,
  which tells Render to ask for the value rather than copy it. Whoever deploys
  the fork adds their own keys under **Environment**. Without at least one, the
  app still starts and every screen loads, and the model picker explains which
  variable to set.
- **The public URL is claimed first come first served.** Service names are unique
  per account, so two accounts can both run a service called `litigatai`, but the
  `onrender.com` subdomain is global. If `litigatai.onrender.com` is taken, the
  second deploy gets a suffixed address such as `litigatai-a1b2.onrender.com`.
  Rename the service in `render.yaml` if you want to choose it yourself.

The case tracker starts empty in a new deployment, because its data lives in the
database rather than the repository.

### By hand

Create a new **Web Service** and set:

- **Root directory**: blank if this folder is the repository root, otherwise
  `law-project-hoster`
- **Runtime**: Python 3
- **Build command**: `pip install -r requirements.txt`
- **Start command**:
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 65`
- **Health check path**: `/api/health`

Then add your keys under Environment.

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | no | Google Gemini, as a default for every visitor |
| `GROQ_API_KEY` | no | Groq |
| `OPENAI_API_KEY` | no | OpenAI or a compatible gateway |
| `HUGGINGFACE_API_KEY` | no | Hugging Face Inference Providers |
| `CLOUDFLARE_API_TOKEN` | no | Cloudflare Workers AI, needs the account id too |
| `CLOUDFLARE_ACCOUNT_ID` | with the token | The account whose Workers AI is called. Part of the URL, so both halves are required |
| `ALLOW_CLIENT_KEYS` | no | `1` by default. `0` refuses visitor supplied keys |
| `DEMO_SEED` | no | `1` inserts five sample matters into an empty tracker at start up |
| `INDIAN_KANOON_API_TOKEN` | no | Live case law retrieval for Legal Research and Authority Check |
| `DATABASE_URL` | no | Postgres for the case tracker and judgment indexes, so they survive a redeploy |
| `OPENAI_BASE_URL` | no | Point the OpenAI adapter at another gateway |
| `GEMINI_MODEL`, `GROQ_MODEL`, `OPENAI_MODEL`, `HUGGINGFACE_MODEL` | no | Move one model to the top of its picker |
| `MAX_UPLOAD_MB` | no | Upload ceiling, 25 by default |
| `MAX_OCR_PAGES` | no | Pages sent to a vision model per document, 8 by default |
| `CORS_ORIGINS` | no | Comma separated origins, only needed for a separate front end |

Judgment Q&A uses `sentence-transformers/all-MiniLM-L6-v2` locally for
embeddings and needs no embedding API key. Local development downloads and
caches the model on first use; the Render blueprints fetch it during the build
so the first user upload does not wait on a model download. The existing
selected LLM provider (Groq Qwen, when selected) generates the grounded answer.
Judgment text, chunk vectors, and page metadata are stored in the configured
SQLite/Postgres database; removing a judgment from its upload card deletes its
index.

None of the five provider keys is required any more: with
`ALLOW_CLIENT_KEYS` left on, a deployment with no keys at all boots fine and
asks each visitor for one. A full annotated list is in `.env.example`.

### What data actually reaches a deployment

Worth being exact about, because two of the three answers are different:

| Path | Committed? | On a free Render instance |
| --- | --- | --- |
| `data/bare_acts_data.json` | yes, 36 KB | Ships with the repository. Eleven Acts, indexed section by section, so Bare Acts works fully with no setup |
| `data/litigatai.db` | **no**, `.gitignore` has `data/*.db` | Stores the case tracker and judgment indexes. Free Render has an ephemeral disk, so data is lost on restart or deploy |

That means the Court Tracker is a blank screen on a fresh deployment unless
you do one of two things:

- **For a demo,** set `DEMO_SEED=1`. Five realistic matters are inserted at
  start up, but only into a tracker that is genuinely empty, so this can never
  overwrite real data. Their hearing dates are computed relative to the day the
  app boots, which keeps one matter overdue and three upcoming however long
  the deployment has been running. A fixed date would drift into the past and
  the diary would look empty again a month later.
- **For real use,** set `DATABASE_URL` to a Postgres connection string. The
  same schema is used and the data survives a redeploy. Render's own free
  Postgres expires 30 days after creation, so prefer a provider whose free tier
  does not, such as Neon.

Judgment indexes are stored in the same database and are deleted when a user
removes the judgment from its upload card.

---

## Run it locally

```bash
cd law-project-hoster

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS and Linux

pip install -r requirements.txt

cp .env.example .env            # then add at least one key

uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000. Interactive API docs are at `/api/docs`.

There is also a `Dockerfile` if you would rather run a container:

```bash
docker build -t litigatai .
docker run -p 8000:8000 --env-file .env litigatai
```

`app/settings.py` reads `.env` from this directory only, and only to fill in
variables the real environment has not already set, so a hosted deployment
always takes the platform's environment as the source of truth. Set
`LITIGATAI_IGNORE_DOTENV=1` to skip the file entirely, which is handy when you
want to see how the app behaves with one specific key and nothing else.

---

## How it is put together

```
law-project-hoster/
├── app/
│   ├── main.py              FastAPI app, static hosting, error handling
│   ├── settings.py          Environment. Nothing raises when a key is absent
│   ├── db.py                SQLite by default, Postgres when DATABASE_URL is set
│   ├── schemas.py           Request and response models
│   ├── api/routes.py        Every endpoint
│   ├── api/byok.py          Reads a visitor's own key out of the request headers
│   ├── llm/
│   │   ├── base.py          Provider contract, JSON coercion, output sanitising
│   │   ├── keyring.py       Per request credentials, held only for that request
│   │   ├── providers.py     Gemini, Groq, Cloudflare, OpenAI, Hugging Face adapters
│   │   └── registry.py      Discovery, selection and the calls tools make
│   └── services/
│       ├── documents.py     PDF, DOCX, image and text extraction with vision OCR
│       ├── rag.py           Judgment chunking, embeddings, vector retrieval and grounded Q&A
│       ├── kanoon.py        Indian Kanoon client
│       ├── analysis.py      List of Dates, Judgment Summariser, Authority Check
│       ├── research.py      Legal Research, Prompt Enhancer, translation, document chat
│       ├── drafting.py      Document Drafter, Counter Arguments
│       ├── bare_acts.py     Statute library
│       ├── tracker.py       Case diary and eCourts lookup
│       ├── seed.py          Sample matters, inserted only into an empty tracker
│       └── exports.py       DOCX, PDF and CSV builders
├── web/
│   ├── index.html           App shell and icon sprite
│   ├── styles.css           Design system, light and dark
│   └── app.js               Views, routing, components, markdown renderer
├── data/bare_acts_data.json Statute corpus
├── docs/demo/               Walkthrough video, captions and preview GIF
├── docs/screenshots/        Stills of every tool, from the live deployment
├── render.yaml              Render blueprint
├── render.root.yaml         Same blueprint for use from a parent repository
├── Dockerfile               Container build
└── requirements.txt
```

Four of the five providers speak the OpenAI chat completions protocol, so they
share one adapter with different base URLs. Gemini has its own. Above them,
`registry.py` is the only thing the tools talk to, which is why adding a
provider is a small change in one file.

### The front end

Vanilla JavaScript, hash routed, no framework and no build step. The whole UI is
one `app.js` that builds DOM nodes directly, plus a design system in
`styles.css` driven by CSS custom properties, so the light and dark themes are
one set of token definitions rather than two stylesheets. The markdown renderer
is written in the file, which keeps model output rendering dependency free and
lets it give citation markers, verification flags and source references their
own styling.

---

## API

`GET /api/docs` has the interactive reference. Every endpoint accepts optional
`X-LLM-Key-<provider>` and `X-LLM-Base-<provider>` headers, which override the
server's own credentials for that one request. The shape in brief:

```
GET  /api/health                      Service, providers and storage status
GET  /api/config                      Providers, models, document types, limits
POST /api/providers/verify            Test one provider key and list what it can call
POST /api/providers/verify/kanoon     Test an Indian Kanoon token
POST /api/extract                     File in, plain text out, vision OCR when needed

POST /api/tools/list-of-dates         Chronology from document text
POST /api/tools/summarise             Structured judgment brief
POST /api/tools/authority-check       Treatment of a cited judgment
POST /api/tools/translate             Language detection and English translation
POST /api/tools/document-chat         Questions over an extracted document
POST /api/tools/research              Cited answer on Indian law
POST /api/tools/research/document     Answer confined to an uploaded judgment
POST /api/tools/enhance-prompt        Structured research prompt
POST /api/tools/draft                 Drafted pleading plus its citations
POST /api/tools/counter/claims        Claims extracted from the opposing pleading
POST /api/tools/counter/draft         Rebuttal to one claim
POST /api/tools/counter/draft-all     Rebuttals to every claim
POST /api/tools/counter/assemble      Written statement built from the rebuttals
POST /api/tools/counter/ask           Advice on a claim or its rebuttal

GET  /api/acts                        Statute catalogue
GET  /api/acts/search?q=              Section search
GET  /api/acts/detail?name=           Sections and amendments for one act
POST /api/acts/ask                    Question on a provision

GET    /api/cases                     Case diary and summary counts
POST   /api/cases                     Add a matter
PATCH  /api/cases/{id}                Update a matter
DELETE /api/cases/{id}                Remove a matter
POST   /api/cases/{id}/hearings       Log a hearing
GET    /api/cases/upcoming?days=      Upcoming and overdue dates
POST   /api/cases/ecourts             eCourts CNR lookup

POST /api/export                      DOCX, PDF, CSV, Markdown or text download
```

Every AI request carries `provider` and `model`. Omit them and the first
configured provider and its default model are used.

Errors come back in one shape, with something the user can act on:

```json
{
  "error": {
    "message": "Groq call failed: rate limit reached for openai/gpt-oss-120b",
    "provider": "groq",
    "model": "openai/gpt-oss-120b",
    "retryable": true,
    "hint": "Groq rejected the call for rate or quota reasons. Wait a moment, or pick a different provider in the model picker."
  }
}
```

---

## Limits worth stating plainly

- **Verify everything before filing.** Every draft and every research answer is
  a first draft. The app marks uncertain citations as `verify` and repeats the
  warning on screen and in every exported document, but the responsibility for
  checking an authority is the advocate's.
- **Indian Kanoon is optional.** Without a token, Legal Research and Authority
  Check still answer, from the model's own knowledge, and say so on screen.
- **eCourts is captcha protected.** The CNR lookup often fails for that reason.
  Manual entry is the reliable route and the interface says so.
- **OCR reads the first `MAX_OCR_PAGES` pages**, eight by default, and needs a
  provider with a vision model.
- **Free tiers run out.** Every provider here except OpenAI has a free tier,
  and each will rate limit under heavy use. The app surfaces that clearly. Quotas are counted per
  model, so a different model on the same provider usually still works, and the
  picker lets you switch in two clicks.

---

## Licence and credits

Built for the ILTN Vibeathon. The statute corpus in `data/bare_acts_data.json`
is a curated extract for demonstration and is not a substitute for the official
bare acts.

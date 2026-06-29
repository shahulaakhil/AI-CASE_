# ⚖️ LitigatAI — AI-Powered Litigation & Dispute Resolution Platform

**LitigatAI** is a Streamlit-based AI platform built for Indian advocates, litigation interns, and legal researchers. It provides 10 integrated tools that automate the most time-consuming parts of legal practice — from extracting dates out of case files to drafting counter-arguments against an opponent's pleadings.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [The 10 Tools — Detailed](#3-the-10-tools--detailed)
4. [Data Sources — What Is and Isn't in This Project](#4-data-sources--what-is-and-isnt-in-this-project)
5. [Legal Coverage — Honest Assessment](#5-legal-coverage--honest-assessment)
6. [AI Models & API Stack](#6-ai-models--api-stack)
7. [Setup & Installation](#7-setup--installation)
8. [Configuration (.env Reference)](#8-configuration-env-reference)
9. [Project Structure](#9-project-structure)
10. [Limitations & Known Gaps](#10-limitations--known-gaps)
11. [Dependencies](#11-dependencies)

---

## 1. Project Overview

| Attribute | Detail |
|-----------|--------|
| **Platform** | Streamlit multi-page web app |
| **Primary LLM** | Google Gemini 2.5 Flash |
| **Fast/Routing LLM** | Groq Llama 3.3 70B |
| **Fallback LLM** | Siemens OpenAI-compatible API (`gpt-oss-120b-onprem`) |
| **Case Law Source** | Indian Kanoon API (live) |
| **Court Status Source** | eCourts (ecourts.gov.in) via public API |
| **Hardcoded Legal Data** | 10 Indian Acts, ~60 key sections (see §5) |
| **Document Formats** | Input: PDF, DOCX, images. Output: DOCX, CSV, JSON |
| **Language Support** | Hindi, Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Urdu, Odia → English OCR + translation |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  LITIGATAI  (app.py)                        │
│                  Streamlit Web Application                  │
│                                                             │
│  Sidebar navigation → 10 tool pages                        │
│  Dashboard: tool cards + upcoming hearings widget           │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼──────┐ ┌────▼──────┐ ┌───▼───────┐
    │  pages/   │ │  core/    │ │  utils/   │
    │  (10 UIs) │ │ (logic)   │ │ (helpers) │
    └───────────┘ └─────┬─────┘ └───────────┘
                        │
              ┌─────────▼──────────┐
              │      llm.py        │
              │  ┌──────────────┐  │
              │  │ Gemini 2.5F  │  │  ← primary (text + vision)
              │  │ Groq Llama3.3│  │  ← routing / fast classification
              │  │ Siemens GPT  │  │  ← fallback on Gemini 429
              │  └──────────────┘  │
              └──────────┬─────────┘
                         │
          ┌──────────────┼───────────────┐
          │              │               │
   ┌──────▼──────┐  ┌────▼────┐  ┌──────▼──────┐
   │ data/ (JSON)│  │Live APIs│  │ File I/O    │
   │             │  │         │  │             │
   │ bare_acts   │  │ Kanoon  │  │ pdf_utils   │
   │ court_cases │  │ eCourts │  │ docx_utils  │
   └─────────────┘  └─────────┘  └─────────────┘
```

**Request flow for a typical tool:**
1. User uploads a file or types a query in a Streamlit page
2. Page calls the relevant `core/` module
3. Core module extracts text (via `utils/pdf_utils.py`) and/or calls the Kanoon API (via `utils/kanoon.py`)
4. `core/llm.py` dispatches to Gemini (primary) → Siemens (fallback on quota exhaustion)
5. Response is rendered in the UI and optionally downloaded as DOCX/CSV

---

## 3. The 10 Tools — Detailed

### 📅 Tool 1 — List of Dates
**File:** `pages/1_List_of_Dates.py` | **Core:** `core/list_of_dates.py`

Extracts every material date and event from uploaded legal documents and produces a court-ready chronological table.

- **Input:** PDF, DOCX (text-based or scanned), plain text
- **OCR:** Scanned PDFs → rendered page-by-page to PNG → Gemini Vision OCR. Image-based DOCX → embedded images extracted → Gemini Vision OCR.
- **Output:** JSON array `[{date, event, source, significance}]`, downloadable as DOCX table or CSV
- **LLM Task:** Gemini extracts dates, describes event in legal language (≤25 words), identifies source paragraph, assigns legal significance
- **Prompt strategy:** System prompt instructs model to be exhaustive — no date skipped. Approximate dates ("sometime in January 2022") are included with a note.

---

### 🔍 Tool 2 — Legal Research Assistant
**File:** `pages/2_Legal_Research.py` | **Core:** `core/legal_research.py`

Ask any question about Indian law and receive a cited answer backed by actual case law from Indian Kanoon.

- **Step 1 (Groq):** Intent classification — categorises query as `STATUTE`, `CASE_LAW`, `PROCEDURE`, or `GENERAL`. Extracts jurisdiction, relevant acts, and builds an optimised short-form Kanoon search query.
- **Step 2 (Kanoon API):** Live search returns up to 10 relevant judgments with citations, bench, and publication date.
- **Step 3 (Gemini):** Synthesis — structures a full answer with inline citations to Kanoon results. Falls back to AI legal knowledge for general principles where Kanoon results are tangential.
- **Integration with Tool 5:** The Prompt Enhancer can pre-fill this tool's query field.
- **Kanoon results displayed:** Title, citation, bench, headline snippet, link to full document

---

### ⚖️ Tool 3 — Authority Check
**File:** `pages/3_Authority_Check.py` | **Core:** `core/authority_check.py`

Verifies whether a cited Indian judgment is still authoritative — or has been overruled, distinguished, or limited.

- **Input:** Citation string (e.g., `Maneka Gandhi v Union of India, AIR 1978 SC 597`) or case name
- **Step 1:** Strips citation codes (AIR/SCC/SCR) to extract party names; searches Kanoon for the target case
- **Step 2:** Uses word-overlap scoring (`_best_matching_tid`) to find the correct TID among search results — avoids picking an unrelated first result
- **Step 3:** Searches `citedby:{tid}` to retrieve all cases that have cited this judgment
- **Step 4 (Gemini):** Reads citing cases and classifies treatment:
  - **GOOD LAW** — consistently followed, no adverse treatment
  - **CAUTIONED** — followed with reservations or modified
  - **DISTINGUISHED** — distinguished on facts in some cases
  - **OVERRULED** — expressly overruled by a larger bench or higher court
  - **UNKNOWN** — insufficient data
- **Output:** Verdict badge + full reasoning with specific citing case names

---

### 🌐 Tool 4 — Translation + OCR + Ask AI
**File:** `pages/4_Translation_OCR.py` | **Core:** `core/doc_translator.py`

Handles legal documents in any Indian language — extracts text, translates to English, and lets you chat with the document.

- **Supported input languages:** Hindi, Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Urdu, Odia, English
- **OCR pipeline:**
  - Digital PDF → PyMuPDF (`fitz`)
  - Scanned PDF → page-by-page PNG → Gemini Vision OCR (up to 8 pages)
  - Image-based DOCX → extract embedded images → Gemini Vision OCR
  - Direct image (JPG/PNG) → Gemini Vision OCR
- **Language detection:** Gemini identifies source language from first 500 characters
- **Translation:** Gemini translates with legal terminology preserved, party names transliterated, section numbers exact. Adds Translator's Note for ambiguous terms.
- **Ask AI:** Chat interface backed by Gemini — answers questions strictly from document content with inline paragraph/section references

---

### ✨ Tool 5 — Prompt Enhancer
**File:** `pages/5_Prompt_Enhancer.py` | **Core:** `core/prompt_enhancer.py`

Transforms a rough lawyer's query into a structured, high-quality LLM prompt for better research outcomes.

- **Input:** Raw legal question (e.g., "can consumer file complaint against builder for delay")
- **Classification (Groq):** Legal area assigned from: `CONSTITUTIONAL`, `CONTRACT`, `CRIMINAL`, `CIVIL_PROCEDURE`, `CONSUMER`, `PROPERTY`, `FAMILY`, `ARBITRATION`, `LABOUR`, `TAX`, `IP`, `CORPORATE`, `BANKING`, `GENERAL`
- **Output:** Structured prompt with: Legal Area, Jurisdiction (state/HC/SC), Relevant Acts, Specific Question, Key Concepts, Desired Output Format
- **Integration:** "Send to Legal Research" button pre-fills Tool 2's query field via `st.session_state`

---

### 📝 Tool 6 — Document Drafter
**File:** `pages/6_Document_Drafter.py` | **Core:** `core/doc_drafter.py`

Drafts Indian legal documents with auto-generated inline citations.

**Supported document types:**
| Document | When Used |
|----------|-----------|
| Suit (Plaint) | Civil suit to initiate proceedings |
| Statement of Claims | Consumer forum / arbitration claims |
| Written Statement | Defendant's reply to plaint |
| Rejoinder | Plaintiff's reply to Written Statement |
| Vakalatnama | Advocate's authority to appear |
| Counter-claim | Defendant's independent claim |
| Application / Interlocutory | IA/MA within a pending suit |
| Legal Notice | Pre-litigation notice under s. 80 CPC etc. |

- **Inline citations:** Gemini marks `[CITE: Act s.XX]` and `[CITE: CaseName]` throughout the draft — these are then extracted and displayed as a separate reference list
- **Court-ready format:** Proper cause title, paragraph numbering, prayer clause
- **Download:** As formatted DOCX via `utils/docx_utils.py`

---

### 🗓️ Tool 7 — Court Date & Case Status Tracker
**File:** `pages/7_Court_Tracker.py` | **Core:** `core/court_tracker.py`

Manages your entire case docket in one place.

- **Local storage:** Cases stored in `data/court_cases.json` (persists between sessions)
- **eCourts integration:** Enter a CNR (Case Number Record) → fetches live status from `services.ecourts.gov.in/ecourtindia_v6/cases/case_status_cnr`
- **Fields tracked:** Case name, case number, CNR, court, client, case type, status, hearing dates, notes, filing date
- **Dashboard:** Homepage widget shows all hearings within 7 days with colour-coded urgency (red ≤2 days, orange ≤5, green otherwise)
- **Manual fallback:** If eCourts API is unavailable, all data can be entered manually

---

### 📖 Tool 8 — Judgment Summariser
**File:** `pages/8_Judgment_Summariser.py` | **Core:** `core/judgment_summariser.py`

Converts a full judgment (any length, any format) into a structured legal brief.

- **OCR pipeline:** Same as Tool 4 — handles digital PDFs, scanned PDFs (up to 10 pages via Gemini Vision), image-based DOCX
- **Structured output:**
  - **Case Details:** Name, citation (AIR/SCC/SCR format), court, bench, date
  - **Facts:** All material facts in chronological order
  - **Issues:** Each question of law/fact framed by the court
  - **Petitioner Arguments:** Key contentions with statutory/case basis
  - **Respondent Arguments:** Key contentions with statutory/case basis
  - **Held:** Final order/decree precisely stated
  - **Ratio Decidendi:** Legal principle(s) established
  - **Significance:** Why this judgment matters for Indian law
  - **Key Statutes Cited:** List
  - **Key Cases Cited:** List
- **Fallback:** If Gemini JSON fails, falls back to plain-text structured summary
- **Download:** As DOCX brief

---

### 📚 Tool 9 — Bare Acts & Amendments Tracker
**File:** `pages/9_Bare_Acts.py` | **Core:** `core/bare_acts.py`

Browse and search Indian legislation with amendment history.

- **Source:** `data/bare_acts_data.json` (hardcoded — see §5 for exact coverage)
- **Features:**
  - Browse all 10 acts → select any section → view full text
  - View amendment history per section (which act amended it, when, what changed)
  - Full-text search across all sections and all acts simultaneously
  - Ask AI: type a question about any provision → Gemini answers with reference to the section text
- **Acts included:** See §5 below for the exact list with section counts

---

### ⚔️ Tool 10 — Counter Arguments Drafter
**File:** `pages/10_Counter_Arguments.py` | **Core:** `core/counter_args.py`

A 4-step wizard that reads the opponent's pleading and drafts a complete Written Statement.

- **Step 1 — Upload:** Upload opponent's plaint/statement of claims (PDF/DOCX)
- **Step 2 — Extract Claims (Gemini JSON):** Identifies each legal claim/allegation as `{claim_number, claim_text, legal_basis, remedy_sought}`
- **Step 3 — Draft Counters (Gemini per claim):** For each extracted claim, generates a counter-argument with: legal basis to deny, distinguishing cases, applicable exceptions, suggested factual rebuttals
- **Step 4 — Assemble (Gemini):** Compiles all counter-arguments into a complete Written Statement in Indian court format with preliminary objections, para-wise reply, and prayer
- **Interactive:** You can ask follow-up questions about any specific claim before assembling
- **Download:** Final Written Statement as DOCX

---

## 4. Data Sources — What Is and Isn't in This Project

This is the most important section. The project uses **three distinct types of data sources**, each with different reliability and coverage guarantees.

### A. Hardcoded JSON Data (`data/bare_acts_data.json`)

This file is a manually curated snapshot of selected provisions from 10 Indian Acts. It is **static** — it does not auto-update when Parliament amends a law.

**Exact contents:**

| Act | Year | Sections Included | Notes |
|-----|------|-------------------|-------|
| Consumer Protection Act | 2019 | 9 (Definitions, Jurisdiction, Complaints, Product Liability, Unfair Contracts, etc.) | Covers District/State/National Commission hierarchy |
| Code of Civil Procedure | 1908 | 9 (O. 6 R.17 Amendment, O. 7 Plaint, O. 8 WS, O. 39 Injunctions, s.9, s.10, s.151, etc.) | Key provisions for civil litigation |
| Arbitration & Conciliation Act | 1996 | 6 (s.7, s.8, s.9, s.11, s.34, s.36) | Arbitration agreements, court intervention, enforcement |
| Limitation Act | 1963 | 6 (s.3, s.5, s.14, Arts. 54, 58, 113) | Includes extension and condonation |
| Indian Contract Act | 1872 | 6 (s.2, s.13, s.14, s.73, s.124, s.126) | Offer, acceptance, breach, indemnity, guarantee |
| Specific Relief Act | 1963 | 4 (s.10, s.14, s.38, s.41) | Specific performance, perpetual/mandatory injunctions |
| Transfer of Property Act | 1882 | 5 (s.5, s.54, s.58, s.105, s.111) | Sale, mortgage, lease |
| Bharatiya Nyaya Sanhita | 2023 | 5 (s.3 General Exceptions, s.100 Culpable Homicide, s.101 Murder, s.318 Cheating, s.351 Criminal Intimidation) | Replaces IPC 1860 |
| Bharatiya Nagarik Suraksha Sanhita | 2023 | 3 (s.173 FIR, s.242 Charge, s.479 Bail) | Replaces CrPC 1973 |
| Bharatiya Sakshya Adhiniyam | 2023 | 4 (s.57 Electronic Records, s.22 Admissions, s.113 Presumptions, s.63 Secondary Evidence) | Replaces Indian Evidence Act 1872 |

**Indian Contract Act — Special Contracts (additional module):**

| Act Component | Sections |
|---------------|---------|
| Special Contracts | s.148 Bailment, s.182 Agency, s.10 Wagering (void) |

**Total: ~60 sections across 10 Acts + 1 Special Contracts module**

### B. Live API Data

| Source | Data Provided | Authentication | Notes |
|--------|--------------|----------------|-------|
| **Indian Kanoon API** (`api.indiankanoon.org`) | Full-text search of Supreme Court, High Court, and Tribunal judgments; case documents; citation relationships (`citedby:`) | Requires `INDIAN_KANOON_API_TOKEN` (register at api.indiankanoon.org) | Without token → mock/placeholder results. With token → millions of real judgments |
| **eCourts** (`services.ecourts.gov.in`) | Live case status, next date, court, bench — for any case with a CNR number | No auth required (public endpoint) | Can return HTTP 400 for invalid CNR; occasional downtime |

### C. AI Model Knowledge (Gemini / Groq / Siemens)

These models have broad legal knowledge from their training data, which includes:
- Indian statutes (IPC, ICA, CPC, Constitution, etc.)
- Supreme Court landmark judgments
- Legal principles and doctrines

**Important caveat:** AI model knowledge has a training cutoff date and should not be relied upon as authoritative for recent legislative amendments or judgment updates. Always verify AI-generated legal content against primary sources.

---

## 5. Legal Coverage — Honest Assessment

### What This Project DOES Cover

| Area | Coverage |
|------|---------|
| Consumer law | Consumer Protection Act 2019 — key sections (hardcoded) + live Kanoon judgments |
| Civil procedure | CPC 1908 — 9 key sections (hardcoded) + live Kanoon judgments |
| Arbitration | Arbitration & Conciliation Act 1996 — 6 key sections (hardcoded) |
| Limitation | Limitation Act 1963 — 6 key sections (hardcoded) |
| Contract law | Indian Contract Act 1872 — 9 key sections (hardcoded) |
| Property law | Transfer of Property Act 1882 — 5 key sections (hardcoded) |
| Criminal law | Bharatiya Nyaya Sanhita 2023 — 5 key sections (hardcoded); full IPC/BNS via AI knowledge |
| Criminal procedure | Bharatiya Nagarik Suraksha Sanhita 2023 — 3 key sections (hardcoded) |
| Evidence | Bharatiya Sakshya Adhiniyam 2023 — 4 key sections (hardcoded) |
| Civil relief | Specific Relief Act 1963 — 4 key sections (hardcoded) |
| Case law (general) | Live via Indian Kanoon API — covers SC, HC, Tribunal judgments (millions of documents) |
| Document languages | 10 Indian languages → English OCR + translation via Gemini Vision |

### What This Project DOES NOT Cover (Not in the JSON or any live feed)

| Area | Status |
|------|--------|
| **Constitution of India** | ❌ Not in hardcoded data. AI models have constitutional knowledge but it is not a verified, section-by-section database. |
| **Income Tax Act 1961** | ❌ Not present |
| **Companies Act 2013** | ❌ Not present |
| **GST / Indirect Taxes** | ❌ Not present |
| **Labour & Employment Laws** (ID Act, POSH, etc.) | ❌ Not present |
| **Intellectual Property** (TM Act, Patents, Copyright) | ❌ Not present |
| **Banking & Finance** (SARFAESI, FEMA, RBI Act) | ❌ Not present |
| **Real Estate (RERA)** | ❌ Not present |
| **Family & Personal Laws** (Hindu Marriage, MMA, etc.) | ❌ Not present |
| **Environmental Laws** | ❌ Not present |
| **Motor Vehicles Act** | ❌ Not present |
| **RTI Act, Prevention of Corruption Act** | ❌ Not present |
| **State legislation** | ❌ Not present |
| **High Court Rules / Civil Court Rules** | ❌ Not present |
| **Recent amendments (post-2021)** | ⚠️ Partially — BNS/BNSS/BSA 2023 are included; others may be outdated in the hardcoded JSON. AI model knowledge may cover some gaps. |
| **Law Commission Reports** | ❌ Not present |
| **Notifications / Circulars** | ❌ Not present |

### Amendment Currency

- The hardcoded JSON was manually curated. **It does not auto-update.**
- The three 2023 codes (BNS, BNSS, BSA) are included as they replaced IPC, CrPC, and Indian Evidence Act.
- For the most authoritative up-to-date text of any provision, always cross-check with:
  - [India Code](https://www.indiacode.nic.in) (official legislative portal)
  - [Legislative Department, MoLJ](https://legislative.gov.in)
  - [eCourts / SCI website](https://main.sci.gov.in) for rules of court

---

## 6. AI Models & API Stack

### Primary LLM — Google Gemini 2.5 Flash

- **SDK:** `google-genai` (new SDK, not deprecated `google-generativeai`)
- **Model ID:** `gemini-2.5-flash`
- **Used for:** All synthesis, drafting, translation, summarisation, JSON structured output
- **Vision capability:** `gemini_vision()` — used for OCR on scanned PDFs and image-based DOCX
- **Rate limits (free tier):** 20 requests/day. After exhaustion, automatically falls back to Siemens API.
- **Quota handling:** Parses the `retry in Xs` delay from 429 error messages; sleeps and retries up to 3 times; then falls back to Siemens.

### Fast/Routing LLM — Groq Llama 3.3 70B

- **SDK:** `groq`
- **Model ID:** `llama-3.3-70b-versatile`
- **Used for:** Intent classification (Legal Research routing), legal area classification (Prompt Enhancer), Kanoon query building — tasks where speed matters more than depth
- **Rate limits:** Groq free tier is generous (~14,400 tokens/minute). Unlikely to be exhausted in normal use.

### Fallback LLM — Siemens OpenAI-compatible API

- **SDK:** `openai` (OpenAI Python SDK, `base_url` overridden)
- **Base URL:** `https://api.siemens.com/llm/v1`
- **Model ID:** `gpt-oss-120b-onprem`
- **Used for:** Automatic fallback when Gemini hits daily quota limit
- **Capability:** Text generation only — **no vision/OCR capability**. OCR-dependent tools (scanned PDFs) will fail if Gemini quota is exhausted.
- **JSON output:** Prompted to return plain JSON; markdown fences stripped via regex before parsing.

### Indian Kanoon API

- **Base URL:** `https://api.indiankanoon.org`
- **Registration:** [api.indiankanoon.org](https://api.indiankanoon.org) — token required
- **Endpoints used:**
  - `POST /search/` — full-text judgment search. Returns `{docs, found, categories}`. Each doc has: `tid, title, headline, fragment, citation, bench, publishdate, numcites, numcitedby`
  - `POST /doc/{tid}/` — fetch full judgment HTML by TID
  - `POST /search/` with `formInput: "citedby:{tid}"` — all cases that cited a given judgment
- **Coverage:** Supreme Court, all High Courts, various Tribunals (NGT, SAT, NCLT, etc.), District Courts (partial)
- **Without token:** The platform falls back to placeholder results. Tools 2 and 3 still function via Gemini AI knowledge but without verified citations.

### eCourts API

- **Base URL:** `https://services.ecourts.gov.in/ecourtindia_v6/`
- **Endpoint:** `POST /cases/case_status_cnr`
- **Auth:** None (public endpoint)
- **Input:** CNR number (18-character unique case identifier assigned by eCourts)
- **Returns:** Case title, case number, filing date, stage, next hearing date, court, bench
- **Limitation:** Only works for cases listed on the eCourts platform. Not all courts are integrated.

---

## 7. Setup & Installation

### Prerequisites

- Python 3.10+
- A Google Gemini API key ([aistudio.google.com](https://aistudio.google.com))
- A Groq API key ([console.groq.com](https://console.groq.com))
- (Optional) Indian Kanoon API token ([api.indiankanoon.org](https://api.indiankanoon.org))
- (Optional) Siemens API key for fallback

### Installation

```bash
# 1. Clone / navigate to the project
cd law-project

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env             # or edit .env directly
# Fill in your API keys (see §8 below)

# 5. Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

### First Run Checklist

- [ ] `GOOGLE_API_KEY` set — required for all AI features
- [ ] `GROQ_API_KEY` set — required for routing/classification
- [ ] `INDIAN_KANOON_API_TOKEN` set — required for live case law in Tools 2 & 3
- [ ] `SIEMENS_API_KEY` set — optional, enables fallback when Gemini quota exhausted
- [ ] Upload a PDF or DOCX to test Tool 1 (List of Dates)

---

## 8. Configuration (.env Reference)

```env
# ──────────────────────────────────────────
# REQUIRED
# ──────────────────────────────────────────

# Google Gemini 2.5 Flash (primary LLM + OCR vision)
# Get from: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your_google_api_key_here

# Groq Llama 3.3 70B (fast routing/classification)
# Get from: https://console.groq.com
GROQ_API_KEY=your_groq_api_key_here

# ──────────────────────────────────────────
# OPTIONAL — but strongly recommended
# ──────────────────────────────────────────

# Indian Kanoon API (live case law for Tools 2 & 3)
# Register at: https://api.indiankanoon.org
# Without this, Tools 2 & 3 use only AI knowledge — no verified citations
INDIAN_KANOON_API_TOKEN=your_kanoon_token_here

# Siemens OpenAI-compatible fallback (when Gemini daily quota exhausted)
SIEMENS_API_KEY=your_siemens_key_here
SIEMENS_BASE_URL=https://api.siemens.com/llm/v1
SIEMENS_MODEL=gpt-oss-120b-onprem

# ──────────────────────────────────────────
# MODEL OVERRIDES (optional)
# ──────────────────────────────────────────

GEMINI_MODEL=gemini-2.5-flash
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## 9. Project Structure

```
law-project/
│
├── app.py                        # Main Streamlit dashboard + hearings widget
├── requirements.txt
├── .env                          # API keys (git-ignored)
│
├── .streamlit/
│   └── config.toml               # Theme (navy #1B4F72, serif font), max upload 50MB
│
├── pages/                        # Streamlit multi-page routing
│   ├── 1_List_of_Dates.py
│   ├── 2_Legal_Research.py
│   ├── 3_Authority_Check.py
│   ├── 4_Translation_OCR.py
│   ├── 5_Prompt_Enhancer.py
│   ├── 6_Document_Drafter.py
│   ├── 7_Court_Tracker.py
│   ├── 8_Judgment_Summariser.py
│   ├── 9_Bare_Acts.py
│   └── 10_Counter_Arguments.py
│
├── core/                         # Business logic (no UI imports)
│   ├── config.py                 # Env loading, path constants
│   ├── llm.py                    # Gemini / Groq / Siemens clients + retry/fallback
│   ├── list_of_dates.py          # Tool 1 logic
│   ├── legal_research.py         # Tool 2 logic
│   ├── authority_check.py        # Tool 3 logic
│   ├── doc_translator.py         # Tool 4 logic
│   ├── prompt_enhancer.py        # Tool 5 logic
│   ├── doc_drafter.py            # Tool 6 logic
│   ├── court_tracker.py          # Tool 7 logic + eCourts API
│   ├── judgment_summariser.py    # Tool 8 logic
│   ├── bare_acts.py              # Tool 9 logic
│   └── counter_args.py           # Tool 10 logic
│
├── utils/
│   ├── pdf_utils.py              # PDF/DOCX text extraction + image extraction
│   ├── kanoon.py                 # Indian Kanoon API wrapper
│   └── docx_utils.py             # DOCX generation (court-formatted output)
│
├── data/
│   ├── bare_acts_data.json       # 10 Indian Acts, ~60 sections, amendment history
│   └── court_cases.json          # User's case docket (local JSON storage)
│
├── uploads/                      # Temp storage for uploaded files
└── output/                       # Generated DOCX/CSV downloads
```

---

## 10. Limitations & Known Gaps

### Legal Data Limitations

| Limitation | Impact |
|-----------|--------|
| Only 10 acts hardcoded (~60 sections each) | Tool 9 Bare Acts can only browse these 10 acts. Questions about other laws rely on AI knowledge only. |
| Constitution not in hardcoded data | Constitutional questions answered by AI from training knowledge — not a verified section-by-section database |
| Amendment history is manually curated | No auto-sync with Parliament / India Code. May be outdated for acts amended after the JSON was last updated. |
| BNS/BNSS/BSA 2023 included but not complete | Only key sections included; full acts are much larger |
| No state legislation | State-specific rules, amendments, or state-level acts not covered |

### API / Quota Limitations

| Limitation | Impact |
|-----------|--------|
| Gemini free tier: 20 requests/day | Platform will exhaust quota quickly in a demo or heavy-use session. Set `SIEMENS_API_KEY` for fallback. |
| Siemens fallback: text only | Vision/OCR (scanned PDFs, image DOCX) requires Gemini. If Gemini quota is exhausted, OCR-dependent tools will error. |
| Kanoon token required for live case law | Without token, Tools 2 & 3 return no real judgments — only AI knowledge |
| eCourts API: public, no SLA | Can go down or return 400/503. Only covers courts on the eCourts platform. |
| Indian Kanoon coverage | Not every HC/District Court judgment is indexed. Tribunal coverage varies. |

### Technical Limitations

| Limitation | Impact |
|-----------|--------|
| Gemini Vision OCR: max 5-10 pages per document | Long scanned judgments (100+ pages) will only have first 5-10 pages OCR'd |
| Text truncation: max ~20,000 characters sent to LLM | Very long documents get truncated before synthesis |
| court_cases.json is local | No multi-user or cloud sync — case data is per-machine only |
| No authentication | The Streamlit app has no login — do not host publicly with sensitive client data |
| No real-time Parliament feed | Cannot detect when a new amendment is enacted |

---

## 11. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `streamlit` | ≥1.35.0 | Web UI framework |
| `openai` | ≥1.30.0 | Siemens fallback LLM (OpenAI-compatible) |
| `google-genai` | ≥0.8.0 | Gemini 2.5 Flash (primary LLM + Vision OCR) |
| `groq` | ≥0.9.0 | Groq Llama 3.3 70B (fast routing) |
| `python-dotenv` | ≥1.0.0 | `.env` file loading |
| `pymupdf` | ≥1.24.0 | PDF text extraction and page rendering (`fitz`) |
| `python-docx` | ≥1.1.0 | DOCX reading and generation |
| `pandas` | ≥2.2.0 | DataFrame for tables / CSV export |
| `Pillow` | ≥10.0.0 | Image processing |
| `requests` | ≥2.31.0 | HTTP calls to eCourts API |
| `python-dateutil` | ≥2.9.0 | Robust date parsing |
| `reportlab` | ≥4.0.0 | PDF generation (available, not currently used in active tools) |
| `pydantic` | ≥2.7.0 | Data validation (available, not currently used in active tools) |
| `deep-translator` | ≥1.11.0 | Translation fallback (available; Gemini used instead) |
| `pytesseract` | ≥0.3.10 | Tesseract OCR (available; Gemini Vision used instead) |
| `rank_bm25` | ≥0.2.2 | BM25 search (available for future local search features) |

---

## Recommended External Resources for Legal Research

Since this project does not contain a complete database of Indian law, the following authoritative sources should be used alongside it:

| Resource | URL | What It Has |
|----------|-----|------------|
| India Code | https://www.indiacode.nic.in | All Central Acts, official text, amendments |
| Legislative Department | https://legislative.gov.in | Bills, acts, statutory rules |
| Supreme Court of India | https://main.sci.gov.in | SCI judgments, cause lists, rules |
| eCourts Services | https://services.ecourts.gov.in | District/HC cause lists, case status |
| Indian Kanoon | https://indiankanoon.org | Free search of SCI/HC/Tribunal judgments |
| Manupatra / SCC Online | *(subscription)* | Comprehensive case law + commentaries |
| Law Commission of India | https://lawcommissionofindia.nic.in | Reports, recommendations |
| MCA21 | https://www.mca.gov.in | Company law filings, NCLT orders |

---

*This README was generated after a full code audit of the project. All claims about what is and is not present in the codebase are based on direct inspection of the source files and data files.*

# 🌱 OutreachAI — Animal Advocacy Email Outreach Automation

> **Open-source MVP** that takes an animal advocacy nonprofit from zero to a personalized outreach email draft in minutes — powered by AI, enriched by real data, always reviewed by humans before sending.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://react.dev)

---

## 🎯 What It Does

OutreachAI automates the most time-consuming parts of cold outreach:

```
Domain Keyword ("veganism")
        │
        ▼
  🏢 Target Discovery     ← DB fuzzy search + OpenCorporates
        │
        ▼
  🔬 Research Enrichment  ← Hunter.io + Serper news + Humantic AI (DISC)
        │
        ▼
  🤖 3-Call AI Pipeline   ← Call 1: Individual analysis
        │                    Call 2: Company analysis  
        │                    Call 3: Draft personalized email
        ▼
  👁️ Human Review         ← Edit, approve, or regenerate
        │
        ▼
  📤 Send / Gmail Push    ← Copy-paste or push to Gmail draft
        │
        ▼
  📊 Reply Tracking       ← Log replies, auto-schedule follow-ups
        │
        ▼
  🔄 Follow-up Engine     ← Daily APScheduler job at 08:00 AM
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Domain Search** | Fuzzy domain keyword search across your company database |
| 📧 **Email Discovery** | Hunter.io finds and verifies contact emails |
| 🏢 **Company Enrichment** | OpenCorporates legal data, Serper news intelligence |
| 🧠 **Personality Profiling** | Humantic AI DISC profiling from LinkedIn URLs |
| 🤖 **3-Call LLM Pipeline** | Individual → Company → Draft (Claude 3.5 Sonnet via OpenRouter) |
| 👁️ **Human Review Loop** | Every email reviewed before sending — no auto-send |
| 📋 **Copy/Paste Export** | One-click copy for Gmail, Outlook, any email client |
| 📤 **Gmail Push** | OAuth 2.0 integration — push drafts directly to Gmail |
| 📊 **Reply Tracking** | Log replies, mark as known, full reply history |
| 🔄 **Follow-up Automation** | Daily scheduled job generates LLM follow-up drafts |
| 🌐 **React Dashboard** | Full-featured UI with dark glassmorphism design |

---

## 🛠️ Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| Database | SQLite (dev) → PostgreSQL (prod) |
| Scheduler | APScheduler 3.x |
| HTTP Client | httpx (async) |
| Templates | Jinja2 (LLM prompts) |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 18 + Vite |
| Styling | Vanilla CSS (dark glassmorphism) |
| Fonts | Inter + JetBrains Mono |
| API Client | Fetch + custom hooks |

### External APIs
| API | Purpose | Free Tier |
|---|---|---|
| [OpenRouter](https://openrouter.ai) | LLM (Claude 3.5 Sonnet) | Pay per token |
| [Hunter.io](https://hunter.io) | Email discovery | 25 req/month |
| [Serper](https://serper.dev) | Web + news search | 2,500 req/month |
| [OpenCorporates](https://opencorporates.com) | Company registry | Free tier |
| [Humantic AI](https://humantic.ai) | Personality profiling | Free trial |
| [Gmail API](https://developers.google.com/gmail) | Draft push | Free |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/Sucharita2006/Email-Outreach-Automation.git
cd Email-Outreach-Automation
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```env
# Required for email generation
OPENROUTER_API_KEY=sk-or-...

# Optional — app works without these (graceful fallback)
HUNTER_API_KEY=your_hunter_key
SERPER_API_KEY=your_serper_key
OPENCORPORATES_API_TOKEN=your_oc_token
HUMANTIC_API_KEY=your_humantic_key

# Your organization details
NONPROFIT_NAME=Animals First Foundation
NONPROFIT_MISSION=We advocate for the protection and rights of all animals.
NONPROFIT_SENDER_NAME=Alex Johnson
NONPROFIT_SENDER_ROLE=Outreach Coordinator
```

> **Note:** The app works without any API keys — all enrichment services have graceful fallbacks and email generation will still run if OPENROUTER_API_KEY is set.

### 4. Seed the Database

```bash
# Seed with 20 bundled alternative protein companies
python backend/scripts/seed_from_gfi.py

# Or seed from a GFI CSV export
# Download from: https://gfi.org/resource/alternative-protein-company-database/
python backend/scripts/seed_from_gfi.py --csv data/gfi_companies.csv

# Reset and re-seed
python backend/scripts/seed_from_gfi.py --clear
```

### 5. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

### 6. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

- App: `http://localhost:5173`

---

## 📖 Usage Workflow

### Generate Your First Email

1. **Open** `http://localhost:5173`
2. **Companies** → verify your target companies are seeded
3. **Generate Email** → select campaign → select individual + company → click **Generate**
4. Watch the 3-call pipeline run:
   - Call 1: Individual personality analysis
   - Call 2: Company mission fit analysis
   - Call 3: Final email draft
5. **Review the draft** → edit if needed → **Copy** or **Push to Gmail**

### Track Replies

1. **Email Drafts** → find your sent email
2. **Tracking → Log Reply** → mark as replied or ignored
3. Follow-ups are automatically scheduled (7 days after no reply)
4. The APScheduler job runs daily at 08:00 AM to generate follow-up drafts

### Connect Gmail (Optional)

1. Set `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` in `.env`
2. **Tracking → Gmail Integration → Connect Gmail**
3. Authorize via browser
4. Use **Push to Gmail** on any draft to send with one click

---

## 🗂️ Project Structure

```
Email-Outreach-Automation/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI + APScheduler
│   │   ├── config.py                  # All settings via .env
│   │   ├── database/
│   │   │   ├── models.py              # SQLAlchemy models (5 tables)
│   │   │   └── session.py             # Async DB session
│   │   ├── routers/
│   │   │   ├── campaigns.py           # Campaign CRUD
│   │   │   ├── targets.py             # Company + individual CRUD
│   │   │   ├── research.py            # 15 enrichment endpoints
│   │   │   ├── emails.py              # 13 email generation endpoints
│   │   │   └── tracking.py            # 12 tracking endpoints
│   │   ├── services/
│   │   │   ├── llm_service.py         # OpenRouter client
│   │   │   ├── research_orchestrator.py # 3-call LLM pipeline
│   │   │   ├── hunter_service.py      # Hunter.io integration
│   │   │   ├── serper_service.py      # Serper web/news search
│   │   │   ├── opencorporates_service.py # Company registry
│   │   │   ├── humantic_service.py    # DISC personality profiling
│   │   │   ├── gmail_service.py       # Gmail OAuth + draft push
│   │   │   ├── email_service.py       # Email management layer
│   │   │   ├── tracker_service.py     # Reply tracking
│   │   │   └── followup_service.py    # Follow-up generation
│   │   ├── prompts/
│   │   │   ├── individual_analysis.j2 # Call 1 prompt
│   │   │   ├── company_analysis.j2    # Call 2 prompt
│   │   │   ├── cold_outreach.j2       # Call 3 prompt (email draft)
│   │   │   └── followup.j2            # Follow-up prompt
│   │   └── utils/
│   │       ├── fuzzy_match.py         # rapidfuzz domain search
│   │       ├── rate_limiter.py        # API rate limiting
│   │       └── cache_manager.py       # TTL cache logic
│   ├── scripts/
│   │   └── seed_from_gfi.py           # Database seeder
│   └── alembic/                       # DB migrations
├── frontend/
│   └── src/
│       ├── App.jsx                    # Main app + navigation
│       ├── api.js                     # API client (40+ endpoints)
│       ├── components.jsx             # Shared UI components
│       ├── index.css                  # Design system
│       └── pages/
│           ├── Targets.jsx            # Dashboard, Companies, Individuals
│           ├── Emails.jsx             # Generate wizard + Drafts review
│           └── Tracking.jsx           # Tracking dashboard + Reply logger
├── data/
│   ├── seed_data.json                 # 20 companies + 5 individuals
│   └── domain_tag_map.json            # Product type → domain tag mapping
├── .env.example                       # All API key placeholders
├── requirements.txt
└── README.md
```

---

## 🔑 Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | ✅ For email gen | OpenRouter LLM access |
| `HUNTER_API_KEY` | Optional | Email discovery |
| `SERPER_API_KEY` | Optional | Web/news search |
| `OPENCORPORATES_API_TOKEN` | Optional | Company registry |
| `HUMANTIC_API_KEY` | Optional | DISC personality |
| `GMAIL_CLIENT_ID` | Optional | Gmail OAuth |
| `GMAIL_CLIENT_SECRET` | Optional | Gmail OAuth |
| `NONPROFIT_NAME` | Recommended | Your org name in emails |
| `NONPROFIT_MISSION` | Recommended | Used in LLM prompts |
| `NONPROFIT_SENDER_NAME` | Recommended | Email sign-off name |
| `NONPROFIT_SENDER_ROLE` | Recommended | Email sign-off role |
| `DATABASE_URL` | Auto | `sqlite+aiosqlite:///./outreach.db` |
| `FOLLOWUP_1_DAYS` | Auto | Days before 1st follow-up (default: 7) |
| `FOLLOWUP_2_DAYS` | Auto | Days before 2nd follow-up (default: 14) |
| `LLM_BATCH_CONCURRENCY` | Auto | Parallel LLM calls (default: 10) |

---

## 🔒 Security & Ethics

- **No auto-sending** — every email requires human approval before it leaves your system
- **Draft-only by default** — approve → copy/paste or push to Gmail draft
- **Never commit `.env`** — it's in `.gitignore`
- **Rate limiting** — all API calls are rate-limited to respect provider limits
- **Cache-first** — TTL caching minimizes API costs (30-day OC, 7-day Serper, 14-day Hunter)

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🙏 Data Sources

- **Primary seed data**: [GFI Alternative Protein Company Database](https://gfi.org/resource/alternative-protein-company-database/) (Free, open-access)
- **Company data**: [OpenCorporates](https://opencorporates.com)
- **Contact discovery**: [Hunter.io](https://hunter.io)
- **News intelligence**: [Serper](https://serper.dev)
- **Personality data**: [Humantic AI](https://humantic.ai)

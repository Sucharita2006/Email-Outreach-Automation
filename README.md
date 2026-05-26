# Email Outreach Automation

An open-source MVP that enables animal advocacy nonprofits to conduct **domain-targeted cold email outreach** at scale — from company discovery to personalized draft generation, reply tracking, and follow-up automation.

## Features

- 🔍 **Domain-based target discovery** — search your database by advocacy domain (e.g., "veganism")
- 📧 **Email discovery** via Hunter.io — verified contacts per company
- 🏢 **Company enrichment** via OpenCorporates — legal name, status, incorporation
- 🌐 **Web intelligence** via Serper — recent news, advocacy signals
- 🧠 **Personality profiling** via Humantic AI — DISC-adapted email tone
- ✉️ **AI-generated personalized drafts** via OpenRouter LLM — 3-call architecture
- 👁️ **Human review** before any email is sent — copy/paste or Gmail draft
- 📊 **Reply tracking** — known contacts, follow-up scheduling

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | SQLite (dev) → PostgreSQL (prod) |
| LLM | OpenRouter API (Claude 3.5 Sonnet / Llama 3.1 70B) |
| APIs | Hunter.io, Serper, OpenCorporates, Humantic AI |
| Frontend | React (Vite), shadcn/ui, TailwindCSS, Zustand |
| Scheduler | APScheduler |

## Project Structure

```
email_outreach/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI entry point
│   │   ├── database/
│   │   │   ├── models.py                  # SQLAlchemy models
│   │   │   └── session.py                 # DB session
│   │   ├── routers/                       # API route handlers
│   │   ├── services/                      # Business logic + API integrations
│   │   ├── prompts/                       # Jinja2 LLM prompt templates
│   │   └── utils/                         # Shared utilities
│   └── alembic/                           # Database migrations
├── frontend/                              # React app (Sprint 10)
├── data/
│   ├── seed_data.json                     # Sample data for testing
│   └── domain_tag_map.json               # GFI product_type → domain_tags
├── .env.example                           # API key template
├── requirements.txt
└── README.md
```

## Getting Started

### 1. Clone & Setup Environment

```bash
git clone https://github.com/YOUR_USERNAME/email-outreach-automation.git
cd email-outreach-automation

# Create virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env and fill in all API keys
```

Required keys:
- `OPENROUTER_API_KEY` — [openrouter.ai](https://openrouter.ai)
- `HUNTER_API_KEY` — [hunter.io](https://hunter.io)
- `SERPER_API_KEY` — [serper.dev](https://serper.dev)
- `OPENCORPORATES_API_TOKEN` — [opencorporates.com](https://opencorporates.com)
- `HUMANTIC_API_KEY` — [humantic.ai](https://humantic.ai)

### 3. Initialize Database

```bash
cd backend
alembic upgrade head
```

### 4. Run the Development Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

### 5. Seed the Database (Sprint 1b)

```bash
# Download GFI CSV from https://gfi.org/resource/alternative-protein-company-database/
# Place it at: data/gfi_companies.csv
python backend/scripts/seed_from_gfi.py
```

## Development Phases

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Complete | DB schema, FastAPI boilerplate, GitHub setup |
| Phase 2 | 🔜 Next | Target selection + fuzzy domain search |
| Phase 3–7 | Planned | API integrations + research orchestrator |
| Phase 8–9 | Planned | LLM email generation |
| Phase 10–15 | Planned | Frontend, tracking, follow-ups |

## Environment Variables Reference

See [`.env.example`](.env.example) for a full list of required configuration values.

## Security

- **Never commit `.env`** — it is in `.gitignore`
- All emails are **draft-only** — no automatic sending
- Human review is **required** before any email leaves the system

## License

MIT License — see [LICENSE](LICENSE)

## Contributing

This is an open-source project for animal advocacy nonprofits.
Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) *(coming soon)*

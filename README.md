# Outreach AI: Automated Partnership & Advocacy Pipeline

A full-stack, AI-driven platform that automates partnership outreach for mission-driven organizations. Outreach AI discovers relevant organizations, identifies key decision-makers, and generates highly personalized outreach emails using multi-stage LLM reasoning — empowering advocacy groups to scale their impact without losing the human touch.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green.svg) ![React](https://img.shields.io/badge/React-18-blue.svg) ![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791.svg)

---

## 🌍 Why Outreach AI Matters

Building meaningful partnerships is critical for advocacy groups and non-profits, but finding the right organizations, hunting down decision-makers, and writing custom emails is incredibly time-consuming. 

Traditional mass-email campaigns rely on generic templates that end up in spam. Conversely, manually researching and writing highly personalized emails to hundreds of targets simply doesn't scale.

**Outreach AI introduces an automated robotic SDR pipeline that:**
- **Continuously discovers** relevant organizations based on your specific advocacy domain (e.g., animal welfare, alternative proteins).
- **Aggregates live intelligence** from web searches, news articles, and business registries to understand *why* a target is relevant.
- **Finds the right people** by automatically locating key decision-makers and their verified contact information.
- **Generates hyper-personalized drafts** using a 3-stage LLM reasoning pipeline to tailor the message specifically to the target's recent news, background, and personality.
- **Tracks engagement automatically** by connecting directly to Gmail to monitor replies and schedule follow-ups.

By combining deterministic data aggregation with LLM semantic reasoning, Outreach AI delivers **true personalization at scale** — giving resource-constrained organizations the leverage they need to build real partnerships.

---

## 🚀 Core Features

### 🔍 Automated Target Discovery
Tell the system your campaign domain (e.g., "veganism"), and the multi-threaded discovery engine gets to work:
- Scours the web (via Serper) for organizations active in your space.
- Cross-references with Hunter.io to find actual humans and verified emails.
- Pulls company registry data (via OpenCorporates) for deep organizational context.
- Stores everything in a PostgreSQL database for easy curation.

### 🧠 Three-Call LLM Personalization Pipeline
Outreach AI separates research from drafting to ensure maximum relevance.
1. **Call 1 — Individual Analysis:** The LLM analyzes the person's role, background, and personality (via Humantic AI integration) to determine the best tone (e.g., DISC personality matching).
2. **Call 2 — Company Analysis:** The LLM reviews recent news and the company's mission to find the perfect "hook" aligning with your non-profit's goals.
3. **Call 3 — Synthesis & Drafting:** A final LLM call merges these insights into a highly personalized, compelling email draft.

### 🔁 Human-in-the-Loop Regeneration
Never send a robotic-sounding email. If a draft isn't quite right:
- Click **Regenerate** and provide a quick natural-language instruction (e.g., *"Make it sound more urgent and mention our new sanctuary"*).
- The AI runs in a FastAPI background task to avoid timeouts, then automatically refreshes the frontend modal with the new draft.

### 📧 Gmail Integration & Reply Tracking
Complete the loop without leaving the dashboard:
- **OAuth Integration:** Securely connect your Gmail account.
- **Direct Sending:** Push approved drafts directly to your Gmail outbox.
- **Automated Polling:** The system polls your inbox to match replies to your sent emails, automatically updating the status to "Replied" or "Bounced".
- **Smart Follow-ups:** A scheduled background job (APScheduler) generates highly-contextual follow-up drafts for targets who haven't replied after 7 days.

### 📈 Interactive Glassmorphic Dashboard
A modern, animated web interface visualizes your outreach pipeline:
- **Campaign Setup:** Define your mission and discover targets in one click.
- **Target Curation:** Review discovered companies and individuals with rich context badges and relevance scores.
- **Draft Review:** Edit, regenerate, and approve emails before they go out.
- **Follow-up Tracking:** Monitor engagement history and action items in real-time.

---

## 💡 Key Innovation

Most outreach tools are just glorified mail merges — they blast the exact same template to a CSV of emails, occasionally swapping out `{{first_name}}`.

**Outreach AI is an intelligence system.** It acts as an automated researcher and copywriter. 
The hybrid architecture is the key differentiator:
- **Hard Data Fetching** (Hunter, Serper, OpenCorporates) ensures you are contacting real people at real companies with factual background info.
- **Semantic LLM Reasoning** handles the nuance of *why* your organization should partner with them, crafting a narrative that a generic mail merge could never achieve.

---

## 🧠 Technical Architecture

```text
User Intent (Domain)
     ↓
FastAPI Orchestrator (Async)
     ├── Serper API (Web/News Intelligence)
     ├── Hunter.io (Email/Contact Discovery)
     ├── Humantic AI (Personality Analysis)
     └── OpenCorporates (Business Verification)
     ↓
OpenRouter LLM (3-Call Parallel Analysis Pipeline)
     ↓
PostgreSQL Database (asyncpg + SQLAlchemy ORM)
     ↓
React + Vite Dashboard (Glassmorphic UI)
     ↓
Gmail API (Direct Push & Reply Polling)
```

**Backend (`backend/`)**
- Built with **FastAPI** and **SQLAlchemy** (Async engine).
- **Database:** PostgreSQL (via `asyncpg`), gracefully falls back to SQLite (`aiosqlite`) for local dev without a Postgres URL.
- **Background Tasks:** Orchestration of LLM calls to bypass strict cloud timeout limits (like Render's 100s limit).
- **Intelligent TTL Caching:** Minimizes external API costs by aggressively caching Serper (7 days), Hunter (14 days), and OpenCorporates (30 days) responses.

**Frontend (`frontend/`)**
- Built with **React 18**, **Vite**, and **Tailwind CSS**.
- Beautiful, highly responsive Glassmorphic design.
- Polling mechanisms for seamless background generation updates.

---

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+
- [OpenRouter API Key](https://openrouter.ai/) (Required for LLM drafting)
- (Optional) PostgreSQL database instance

### 1. Clone & Configure
```bash
git clone https://github.com/Sucharita2006/Email-Outreach-Automation.git
cd Email-Outreach-Automation
cp backend/.env.example backend/.env
```
*Edit `backend/.env` and add your API keys, non-profit details, and `DATABASE_URL` (e.g., `postgresql://user:pass@localhost:5432/outreach`).*

### 2. Start the Backend
```bash
cd backend
pip install -r requirements.txt

# Seed the database with sample data (optional)
python scripts/seed_from_gfi.py

# Start the server
uvicorn app.main:app --reload --port 8000
```
*API available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.*

### 3. Start the Frontend
```bash
cd frontend
npm install
npm run dev
```
*App is now live at `http://localhost:5173`.*

---

## 🔮 Future Improvements
- **Advanced Reply Classification:** Train a lightweight model to automatically categorize replies as *Positive*, *Negative*, or *Forwarded*.
- **Multi-Channel Sequences:** Expand beyond email to automatically draft LinkedIn connection requests based on the same LLM research profile.
- **A/B Testing Analytics:** Track open and reply rates across different LLM prompt strategies to mathematically determine which angles convert best.

---

## 📜 License
This project is released under the MIT License.

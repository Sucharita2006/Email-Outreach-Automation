# Contributing to OutreachAI

Thank you for wanting to help! OutreachAI is built for animal advocacy nonprofits and relies on open-source contributors to grow. 🌱

---

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Email-Outreach-Automation.git
   cd Email-Outreach-Automation
   ```
3. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Set up the dev environment** (see [README.md](README.md))
5. **Make your changes**, run tests, commit
6. **Open a Pull Request** against `main`

---

## Development Setup

```bash
# Backend
python -m venv venv && venv\Scripts\activate  # Windows
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Seed sample data
python backend/scripts/seed_from_gfi.py
```

---

## What to Work On

### Good First Issues
- Add more domain tags to `data/domain_tag_map.json`
- Improve the Jinja2 prompt templates in `backend/app/prompts/`
- Add more seed companies to `data/seed_data.json`
- Add unit tests for `fuzzy_match.py` or `cache_manager.py`
- Improve error messages in the frontend

### Bigger Features
- **PostgreSQL support** — swap SQLite for PostgreSQL in production
- **Bulk CSV import from frontend** — drag-and-drop CSV upload UI
- **Alembic migrations** — add versioned schema migrations
- **Celery + Redis** — replace APScheduler for distributed deployments
- **Email thread matching** — smarter Gmail reply detection
- **Multi-user support** — per-user campaigns and API keys

---

## Code Style

### Backend (Python)
- Follow PEP 8
- Use type hints on all function signatures
- Write docstrings for all public functions
- Keep service functions pure and testable (no direct DB access in services — use passed sessions)
- All DB queries must use `async/await`

### Frontend (React/JS)
- Use functional components and hooks only
- Keep components small and focused
- Use the existing CSS design system — no inline styles unless unavoidable
- Add `id` attributes to interactive elements

---

## Commit Messages

Use conventional commit format:
```
feat: add bulk email approval endpoint
fix: handle missing individual email in tracker
docs: update README with Gmail setup instructions
refactor: extract email parsing to utility function
test: add unit tests for cache_manager TTL logic
```

---

## Testing

```bash
# Run backend tests
cd backend && pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_fuzzy_match.py
```

---

## Pull Request Checklist

Before submitting:
- [ ] Code follows the style guidelines above
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] No secrets or API keys committed
- [ ] `.env` is NOT committed
- [ ] PR description explains what changed and why

---

## Reporting Bugs

Open a GitHub Issue with:
1. What you were trying to do
2. What happened instead
3. Steps to reproduce
4. Python version, OS, relevant error messages

---

## Questions?

Open a GitHub Discussion or an Issue tagged `question`.

---

## Code of Conduct

Be kind, be helpful, be respectful. This project exists to help animals — please bring that spirit to your contributions.

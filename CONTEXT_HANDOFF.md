# Context Handoff: arXiv Research Digest App

Use this file as the **single source of context** when continuing work in another Codex chat.

## Project goal

Build a clone-and-run app that:
- takes user free-text research interests,
- fetches latest papers from arXiv,
- sends scheduled digest emails,
- supports user-managed subscriptions,
- currently constrained to Gmail sender/recipient.

## Current implementation status

### Core app
- Main web app: `app.py` (Flask + SQLite + APScheduler + SMTP + arXiv fetching).
- Also has `main.py` standalone mailer (legacy/alternate runner).

### Implemented features
- Free-text interest input.
- Frequency options: daily / every 2 days / weekly.
- Major timezones dropdown.
- Scheduled digest checking every minute.
- Subscriber manage link with pause/resume/delete.
- Optional admin login and admin controls.
- Health endpoint (`/healthz`).
- Failure tracking and auto-pause after repeated send failures.
- Gmail-only validation for sender and recipient.

### Repo files that matter
- `app.py` -> production path for the current app.
- `README.md` -> run and behavior documentation.
- `.env.example` -> required env configuration.
- `requirements.txt` -> Python deps.

## Constraints observed in container

- Package/network installs may fail due proxy 403 in this Codex environment.
- Browser screenshot flow may fail if app dependencies cannot be installed in container.
- Ollama install/download was blocked in this environment; local machine should be used for that.

## Known quality gaps / risk items

1. Local/dev defaults still need secure secret handling in real deployment.
2. No formal automated test suite yet.
3. Parser is currently rule-based; local LLM parsing is planned as enhancement.
4. SQLite is fine for MVP, but Postgres may be preferable for multi-user scaling.

## Recommended immediate next priorities

1. **End-to-end local validation**
   - Run app locally, create subscription, verify digest send, test manage routes.
2. **Add automated tests**
   - parser tests,
   - scheduler eligibility tests,
   - route tests for subscribe/manage/admin/health.
3. **Parser upgrade path**
   - integrate local Ollama parsing with strict fallback and query validation.
4. **Operational hardening**
   - better logging,
   - structured error reporting,
   - optional retry/backoff refinements.

## Local run commands (baseline)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SENDER_EMAIL="your_gmail_address@gmail.com"
export SENDER_PASSWORD="your_gmail_app_password"
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="465"
export SECRET_KEY="replace-with-random-secret"
export ADMIN_PASSWORD="optional-admin-password"
export PUBLIC_BASE_URL="http://localhost:5000"
python app.py
```

Health check:

```bash
curl http://localhost:5000/healthz
```

## Instructions for the next Codex chat

Prompt the next chat with:

1. "Read `CONTEXT_HANDOFF.md` and `README.md` first."
2. "Validate app locally and report what fails/passes."
3. "Implement from `Next priorities` in order, with tests."
4. "Keep Gmail-only constraint unless explicitly changed."

This should allow continuation without context loss.

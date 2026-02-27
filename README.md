# arXiv Research Digest (One-Stop Local App)

A one-stop app that gives you a local web link (`http://localhost:5000`) where users can submit:
- free-text research interest paragraph,
- email frequency (daily / every 2 days / weekly),
- morning time,
- major timezone.

The app converts interest text into an arXiv query, fetches latest papers from arXiv, and sends digest emails on the chosen schedule.

## What is included now

- arXiv-backed paper retrieval.
- Gmail-only sender and recipient validation (current scope).
- Free-text interest parsing into arXiv query syntax.
- Timezone-aware scheduler with failure tracking and auto-pause after repeated send failures.
- Subscriber self-management link (pause/resume/delete).
- Optional admin login for reviewing and controlling all subscriptions.
- Health endpoint (`/healthz`) for basic runtime checks.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure environment variables:

```bash
export SENDER_EMAIL="your_gmail_address@gmail.com"
export SENDER_PASSWORD="your_gmail_app_password"
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="465"
export SECRET_KEY="replace-with-random-secret"
export ADMIN_PASSWORD="optional-admin-password"
export PUBLIC_BASE_URL="http://localhost:5000"
```

> For Gmail, use an App Password and ensure 2FA is enabled.

## Run

```bash
python app.py
```

Open:
- `http://localhost:5000`

## Admin and subscriber management

- If `ADMIN_PASSWORD` is set:
  - visit `/admin/login` and authenticate,
  - view all subscriptions,
  - pause/resume/delete any subscription.
- Every subscriber receives a private manage link after creation and in digest emails:
  - pause/resume their own subscription,
  - delete (unsubscribe).

## Scheduling behavior

- Scheduler checks due subscriptions every minute.
- Runs only active subscriptions.
- On send failure, increments failure count and stores last error.
- Auto-pauses a subscription after 3 consecutive failures.

## Health check

Use:

```bash
curl http://localhost:5000/healthz
```

This reports:
- database connectivity,
- scheduler running state,
- Gmail sender configuration validity,
- admin password mode.

## Notes

- This implementation uses a lightweight rule-based free-text parser.
- You can later plug in a local open-source LLM parser (for example, Ollama) without changing scheduling or subscription lifecycle flows.

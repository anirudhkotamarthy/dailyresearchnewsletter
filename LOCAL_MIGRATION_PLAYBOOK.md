# Local Migration Playbook (Container -> Your Machine)

This playbook helps you move current progress from this Codex/container workflow to your own local machine and continue in a new Codex chat with minimal friction.

## 1) Export current code from this repo to your local machine

### Option A (recommended): push branch to GitHub and clone locally

From this container repo:

```bash
git status
git log --oneline -n 5
git push origin HEAD
```

Then on your local machine:

```bash
git clone <your-repo-url>
cd dailyresearchnewsletter
git checkout <the-branch-you-pushed>
```

### Option B: manual copy (if you do not want to push yet)

From this container, copy these files out and place into your local folder:

- `app.py`
- `main.py`
- `requirements.txt`
- `.env.example`
- `README.md`
- `CONTEXT_HANDOFF.md`
- `LOCAL_MIGRATION_PLAYBOOK.md`

---

## 2) Local machine setup

On your local machine:

```bash
cd dailyresearchnewsletter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set environment variables (or use direnv/.env loader):

```bash
export SENDER_EMAIL="your_gmail_address@gmail.com"
export SENDER_PASSWORD="your_gmail_app_password"
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="465"
export SECRET_KEY="replace-with-random-secret"
export ADMIN_PASSWORD="optional-admin-password"
export PUBLIC_BASE_URL="http://localhost:5000"
```

---

## 3) Run and validate locally

```bash
python app.py
```

Open:
- `http://localhost:5000`

Health check:

```bash
curl http://localhost:5000/healthz
```

Expected checks:
- DB connectivity true
- scheduler running true
- gmail_sender_configured true (when env is valid)

---

## 4) Move from “works locally” to “shareable repo anyone can clone”

When local works:

```bash
git add app.py main.py requirements.txt .env.example README.md CONTEXT_HANDOFF.md LOCAL_MIGRATION_PLAYBOOK.md
git commit -m "Stabilize local arXiv digest app and add migration/context handoff docs"
git push origin <your-branch>
```

Then either:
- open PR -> merge to main, or
- push directly to main (if you control the repo and prefer direct updates).

---

## 5) New Codex chat handoff

In your new Codex conversation, start with:

1. "Read `CONTEXT_HANDOFF.md` first."
2. "Then run local validation commands from that file."
3. "Continue roadmap from the `Next Priorities` section."

This avoids context loss and repeated re-discovery.

---

## 6) Optional: local open-source model enablement

If you want local LLM parsing:

- Install and run Ollama on your machine.
- Choose a model (for example `qwen2.5:3b` on smaller machines).
- Update parser integration in app to use local endpoint with fallback.

Suggested first integration behavior:
- Try local LLM parse
- Validate schema/query
- Fallback to rule-based parser on error/timeout


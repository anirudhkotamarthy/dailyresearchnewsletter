import os
import re
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, jsonify, redirect, render_template_string, request, session
from flask_sqlalchemy import SQLAlchemy

ARXIV_API_URL = "https://export.arxiv.org/api/query"
GMAIL_DOMAIN = "gmail.com"
MAJOR_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Paris",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
]
FREQUENCY_TO_DAYS = {"daily": 1, "every_2_days": 2, "weekly": 7}

CATEGORY_HINTS = {
    "nlp": "cs.CL",
    "language model": "cs.CL",
    "llm": "cs.CL",
    "vision": "cs.CV",
    "computer vision": "cs.CV",
    "reinforcement learning": "cs.LG",
    "causal": "stat.ML",
    "robot": "cs.RO",
    "robotics": "cs.RO",
    "audio": "cs.SD",
    "security": "cs.CR",
    "graph": "cs.LG",
    "optimization": "math.OC",
    "theory": "cs.LO",
}

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///newsletter.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

db = SQLAlchemy(app)
scheduler: BackgroundScheduler | None = None


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    interest_text = db.Column(db.Text, nullable=False)
    query = db.Column(db.Text, nullable=False)
    frequency = db.Column(db.String(32), nullable=False)
    timezone_name = db.Column(db.String(64), nullable=False)
    send_time = db.Column(db.String(5), nullable=False)
    manage_token = db.Column(db.String(64), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


@dataclass
class Paper:
    title: str
    authors: list[str]
    summary: str
    link: str
    published: datetime


def is_gmail_address(email: str) -> bool:
    email = email.strip().lower()
    if "@" not in email:
        return False
    return email.split("@", maxsplit=1)[1] == GMAIL_DOMAIN


def parse_interest_to_query(interest_text: str) -> str:
    lowered = interest_text.lower()
    categories = {category for hint, category in CATEGORY_HINTS.items() if hint in lowered}
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", lowered)
    stopwords = {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "into",
        "about",
        "papers",
        "research",
        "latest",
        "want",
        "looking",
        "please",
        "their",
        "this",
    }
    keywords = [token for token in tokens if token not in stopwords][:8]

    query_parts: list[str] = []
    if categories:
        query_parts.extend(f"cat:{category}" for category in sorted(categories))
    if keywords:
        query_parts.extend(f'all:"{keyword}"' for keyword in keywords)

    if not query_parts:
        return "cat:cs.AI"

    return "+AND+".join(query_parts)


def fetch_latest_papers(query: str, max_results: int = 10, days_back: int = 1) -> list[Paper]:
    encoded = quote_plus(query, safe=':+"')
    url = (
        f"{ARXIV_API_URL}?search_query={encoded}"
        f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    papers: list[Paper] = []

    for entry in feed.entries:
        published = datetime.strptime(entry.published, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if published < cutoff:
            continue
        papers.append(
            Paper(
                title=" ".join(entry.title.split()),
                authors=[author.name for author in entry.authors],
                summary=" ".join(entry.summary.split()),
                link=entry.link,
                published=published,
            )
        )
    return papers


def format_email(subscription: Subscription, papers: list[Paper]) -> tuple[str, str]:
    subject = f"arXiv Digest - {datetime.now().strftime('%Y-%m-%d')}"
    lines = [
        f"Interest: {subscription.interest_text}",
        f"Query used: {subscription.query}",
        "",
    ]

    if not papers:
        lines.append("No new papers found in this cycle. Try broadening your interest text.")
    else:
        for idx, paper in enumerate(papers, start=1):
            lines.extend(
                [
                    f"{idx}. {paper.title}",
                    f"Authors: {', '.join(paper.authors)}",
                    f"Published: {paper.published.strftime('%Y-%m-%d %H:%M UTC')}",
                    f"Link: {paper.link}",
                    f"Summary: {paper.summary[:500]}...",
                    "",
                ]
            )

    lines.extend(
        [
            "---",
            f"Manage your subscription: {request_url_base()}/manage/{subscription.manage_token}",
        ]
    )
    return subject, "\n".join(lines)


def request_url_base() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:5000")


def send_email(recipient_email: str, subject: str, body: str) -> None:
    sender_email = os.environ.get("SENDER_EMAIL", "").strip().lower()
    sender_password = os.environ.get("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))

    if not sender_email or not sender_password:
        raise RuntimeError("SENDER_EMAIL and SENDER_PASSWORD must be configured.")
    if not is_gmail_address(sender_email):
        raise RuntimeError("SENDER_EMAIL must be a Gmail address for current app constraints.")

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=20) as server:
        server.login(sender_email, sender_password)
        server.send_message(message)


def should_send_now(subscription: Subscription, now_utc: datetime) -> bool:
    user_tz = ZoneInfo(subscription.timezone_name)
    local_now = now_utc.astimezone(user_tz)
    hh, mm = [int(part) for part in subscription.send_time.split(":")]

    if local_now.hour != hh or local_now.minute != mm:
        return False

    if subscription.last_sent_at is None:
        return True

    last_local_date = subscription.last_sent_at.astimezone(user_tz).date()
    delta_days = (local_now.date() - last_local_date).days
    return delta_days >= FREQUENCY_TO_DAYS[subscription.frequency]


def process_due_subscriptions() -> None:
    with app.app_context():
        now_utc = datetime.now(timezone.utc)
        due_subscriptions = Subscription.query.filter_by(active=True).all()
        for subscription in due_subscriptions:
            if not should_send_now(subscription, now_utc):
                continue
            try:
                days_back = FREQUENCY_TO_DAYS[subscription.frequency]
                papers = fetch_latest_papers(subscription.query, max_results=10, days_back=days_back)
                subject, body = format_email(subscription, papers)
                send_email(subscription.email, subject, body)
                subscription.last_sent_at = now_utc
                subscription.failed_attempts = 0
                subscription.last_error = None
                db.session.commit()
            except Exception as exc:
                subscription.failed_attempts += 1
                subscription.last_error = str(exc)
                if subscription.failed_attempts >= 3:
                    subscription.active = False
                    subscription.last_error = f"Auto-paused after 3 failures. Last error: {exc}"
                db.session.commit()


def require_admin() -> bool:
    if not ADMIN_PASSWORD:
        return True
    return session.get("is_admin") is True


FORM_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>arXiv Morning Digest</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 30px auto; padding: 0 16px; }
    input, textarea, select, button { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 12px; }
    textarea { min-height: 100px; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 14px; }
    .ok { background: #e8f7e8; padding: 10px; border-radius: 6px; margin-bottom: 14px; }
    .warn { background: #fff3cd; padding: 10px; border-radius: 6px; margin-bottom: 14px; }
    .muted { color: #555; font-size: 0.9rem; }
    .actions { display: flex; gap: 8px; }
    .actions form { flex: 1; }
  </style>
</head>
<body>
  <h1>arXiv Research Digest</h1>
  {% if message %}<div class=\"ok\">{{ message }}</div>{% endif %}
  {% if warning %}<div class=\"warn\">{{ warning }}</div>{% endif %}

  <div class=\"card\">
    <h2>Create subscription</h2>
    <p class=\"muted\">Gmail-only for now. Enter a paragraph, pick frequency/time/timezone.</p>
    <form method=\"post\" action=\"/subscribe\">
      <label>Recipient Gmail</label>
      <input type=\"email\" name=\"email\" required />

      <label>Interest paragraph</label>
      <textarea name=\"interest_text\" placeholder=\"Example: papers on multimodal LLM reasoning, retrieval, and clinical evaluation\" required></textarea>

      <label>Frequency</label>
      <select name=\"frequency\" required>
        <option value=\"daily\">Daily</option>
        <option value=\"every_2_days\">Once every 2 days</option>
        <option value=\"weekly\">Weekly</option>
      </select>

      <label>Major timezone</label>
      <select name=\"timezone_name\" required>
        {% for tz in timezones %}
        <option value=\"{{ tz }}\">{{ tz }}</option>
        {% endfor %}
      </select>

      <label>Morning time</label>
      <input type=\"time\" name=\"send_time\" value=\"07:30\" required />

      <button type=\"submit\">Save subscription</button>
    </form>
  </div>

  {% if is_admin %}
  <div class=\"card\">
    <h2>Subscriptions (admin)</h2>
    <ul>
      {% for s in subscriptions %}
      <li>
        <strong>{{ s.email }}</strong> — {{ s.frequency }} at {{ s.send_time }} ({{ s.timezone_name }})
        — {% if s.active %}active{% else %}paused{% endif %}
        <br />
        <span class=\"muted\">Failures: {{ s.failed_attempts }}{% if s.last_error %} | Last error: {{ s.last_error }}{% endif %}</span>
        <div class=\"actions\">
          <form method=\"post\" action=\"/admin/toggle/{{ s.id }}\">
            <button type=\"submit\">{% if s.active %}Pause{% else %}Resume{% endif %}</button>
          </form>
          <form method=\"post\" action=\"/admin/delete/{{ s.id }}\">
            <button type=\"submit\">Delete</button>
          </form>
        </div>
      </li>
      {% else %}
      <li>No subscriptions yet.</li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}

  <div class=\"card\">
    <h2>Manage by link</h2>
    <p class=\"muted\">Each subscriber gets a private manage link in digest emails and after creation.</p>
  </div>
</body>
</html>
"""

MANAGE_TEMPLATE = """
<!doctype html>
<html>
<head><meta charset=\"utf-8\" /><title>Manage Subscription</title></head>
<body style=\"font-family:Arial;max-width:700px;margin:20px auto;\">
  <h1>Manage Subscription</h1>
  <p>Email: <strong>{{ s.email }}</strong></p>
  <p>Status: <strong>{{ 'active' if s.active else 'paused' }}</strong></p>
  <p>Frequency: {{ s.frequency }}</p>
  <p>Time: {{ s.send_time }} ({{ s.timezone_name }})</p>
  <p>Interest: {{ s.interest_text }}</p>
  <form method=\"post\" action=\"/manage/{{ s.manage_token }}/toggle\"><button type=\"submit\">{% if s.active %}Pause{% else %}Resume{% endif %}</button></form>
  <form method=\"post\" action=\"/manage/{{ s.manage_token }}/delete\" style=\"margin-top:8px\"><button type=\"submit\">Unsubscribe (Delete)</button></form>
  <p><a href=\"/\">Back</a></p>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!doctype html>
<html><head><meta charset=\"utf-8\" /><title>Admin Login</title></head>
<body style=\"font-family:Arial;max-width:500px;margin:20px auto;\">
<h1>Admin Login</h1>
{% if message %}<p style=\"color:#a00\">{{ message }}</p>{% endif %}
<form method=\"post\" action=\"/admin/login\">
  <label>Password</label>
  <input type=\"password\" name=\"password\" required style=\"width:100%;padding:8px;margin:8px 0;\" />
  <button type=\"submit\">Login</button>
</form>
</body></html>
"""


@app.get("/healthz")
def healthz() -> Any:
    with app.app_context():
        try:
            db.session.execute(db.text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

    sender_email = os.environ.get("SENDER_EMAIL", "")
    health = {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "scheduler_running": bool(scheduler and scheduler.running),
        "gmail_sender_configured": bool(sender_email and is_gmail_address(sender_email)),
        "admin_password_enabled": bool(ADMIN_PASSWORD),
    }
    return jsonify(health), (200 if db_ok else 503)


@app.get("/")
def index() -> Any:
    subscriptions = Subscription.query.order_by(Subscription.created_at.desc()).all() if require_admin() else []
    message = request.args.get("message", "")
    warning = ""
    sender_email = os.environ.get("SENDER_EMAIL", "")
    if sender_email and not is_gmail_address(sender_email):
        warning = "SENDER_EMAIL is not a Gmail address. This app currently supports Gmail sender accounts only."

    return render_template_string(
        FORM_TEMPLATE,
        subscriptions=subscriptions,
        timezones=MAJOR_TIMEZONES,
        message=message,
        warning=warning,
        is_admin=require_admin(),
    )


@app.post("/subscribe")
def subscribe() -> Any:
    email = request.form["email"].strip().lower()
    interest_text = request.form["interest_text"].strip()
    frequency = request.form["frequency"].strip()
    timezone_name = request.form["timezone_name"].strip()
    send_time = request.form["send_time"].strip()

    if not is_gmail_address(email):
        return redirect("/?message=Recipient+must+be+a+Gmail+address")
    if frequency not in FREQUENCY_TO_DAYS:
        return redirect("/?message=Invalid+frequency")
    if timezone_name not in MAJOR_TIMEZONES:
        return redirect("/?message=Invalid+timezone")

    query = parse_interest_to_query(interest_text)
    manage_token = secrets.token_urlsafe(24)
    subscription = Subscription(
        email=email,
        interest_text=interest_text,
        query=query,
        frequency=frequency,
        timezone_name=timezone_name,
        send_time=send_time,
        manage_token=manage_token,
    )
    db.session.add(subscription)
    db.session.commit()
    manage_link = f"{request_url_base()}/manage/{manage_token}"
    return redirect(f"/?message=Subscription+saved.+Manage+link:+{manage_link}")


@app.get("/manage/<token>")
def manage_subscription(token: str) -> Any:
    subscription = Subscription.query.filter_by(manage_token=token).first_or_404()
    return render_template_string(MANAGE_TEMPLATE, s=subscription)


@app.post("/manage/<token>/toggle")
def manage_toggle(token: str) -> Any:
    subscription = Subscription.query.filter_by(manage_token=token).first_or_404()
    subscription.active = not subscription.active
    subscription.last_error = None
    db.session.commit()
    return redirect(f"/manage/{token}")


@app.post("/manage/<token>/delete")
def manage_delete(token: str) -> Any:
    subscription = Subscription.query.filter_by(manage_token=token).first_or_404()
    db.session.delete(subscription)
    db.session.commit()
    return redirect("/?message=Subscription+deleted")


@app.get("/admin/login")
def admin_login_page() -> Any:
    if not ADMIN_PASSWORD:
        return redirect("/")
    return render_template_string(LOGIN_TEMPLATE, message="")


@app.post("/admin/login")
def admin_login() -> Any:
    if not ADMIN_PASSWORD:
        return redirect("/")
    password = request.form.get("password", "")
    if password != ADMIN_PASSWORD:
        return render_template_string(LOGIN_TEMPLATE, message="Invalid password")
    session["is_admin"] = True
    return redirect("/")


@app.post("/admin/toggle/<int:subscription_id>")
def admin_toggle(subscription_id: int) -> Any:
    if not require_admin():
        abort(403)
    subscription = Subscription.query.get_or_404(subscription_id)
    subscription.active = not subscription.active
    db.session.commit()
    return redirect("/?message=Subscription+status+updated")


@app.post("/admin/delete/<int:subscription_id>")
def admin_delete(subscription_id: int) -> Any:
    if not require_admin():
        abort(403)
    subscription = Subscription.query.get_or_404(subscription_id)
    db.session.delete(subscription)
    db.session.commit()
    return redirect("/?message=Subscription+deleted")


def start_scheduler() -> BackgroundScheduler:
    global scheduler
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
    )
    scheduler.add_job(process_due_subscriptions, "interval", minutes=1, id="digest_processor", replace_existing=True)
    scheduler.start()
    return scheduler


def ensure_schema_compatibility() -> None:
    with app.app_context():
        db.create_all()
        result = db.session.execute(db.text("PRAGMA table_info(subscription)"))
        columns = {row[1] for row in result.fetchall()}
        alter_statements = []

        if "manage_token" not in columns:
            alter_statements.append("ALTER TABLE subscription ADD COLUMN manage_token VARCHAR(64)")
        if "active" not in columns:
            alter_statements.append("ALTER TABLE subscription ADD COLUMN active BOOLEAN DEFAULT 1")
        if "failed_attempts" not in columns:
            alter_statements.append("ALTER TABLE subscription ADD COLUMN failed_attempts INTEGER DEFAULT 0")
        if "last_error" not in columns:
            alter_statements.append("ALTER TABLE subscription ADD COLUMN last_error TEXT")

        for statement in alter_statements:
            db.session.execute(db.text(statement))

        db.session.commit()

        existing = Subscription.query.filter((Subscription.manage_token.is_(None)) | (Subscription.manage_token == "")).all()
        for subscription in existing:
            subscription.manage_token = secrets.token_urlsafe(24)
        db.session.commit()


if __name__ == "__main__":
    ensure_schema_compatibility()
    scheduler_instance = start_scheduler()
    try:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
    finally:
        scheduler_instance.shutdown(wait=False)

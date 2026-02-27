import os
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import List

import feedparser
import schedule


ARXIV_API_URL = "https://export.arxiv.org/api/query"


@dataclass
class Paper:
    title: str
    authors: List[str]
    summary: str
    link: str
    published: datetime


@dataclass
class Settings:
    query: str
    recipient_email: str
    sender_email: str
    sender_password: str
    smtp_server: str
    smtp_port: int
    interval_hours: int
    max_results: int



def load_settings() -> Settings:
    return Settings(
        query=os.getenv("RESEARCH_QUERY", "cat:cs.AI"),
        recipient_email=os.environ["RECIPIENT_EMAIL"],
        sender_email=os.environ["SENDER_EMAIL"],
        sender_password=os.environ["SENDER_PASSWORD"],
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        interval_hours=int(os.getenv("INTERVAL_HOURS", "24")),
        max_results=int(os.getenv("MAX_RESULTS", "10")),
    )



def fetch_latest_papers(query: str, max_results: int = 10, hours_back: int = 24) -> List[Paper]:
    url = (
        f"{ARXIV_API_URL}?search_query={query}"
        f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )

    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    papers: List[Paper] = []
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



def format_email(query: str, papers: List[Paper]) -> tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"Research Digest ({today}) - {query}"

    if not papers:
        body = (
            f"No new papers were found in the last cycle for query: {query}\n\n"
            "Tip: broaden your query or increase MAX_RESULTS."
        )
        return subject, body

    lines = [
        f"Here are the latest {len(papers)} paper(s) for query: {query}",
        "",
    ]

    for idx, paper in enumerate(papers, start=1):
        lines.extend(
            [
                f"{idx}. {paper.title}",
                f"   Authors: {', '.join(paper.authors)}",
                f"   Published: {paper.published.strftime('%Y-%m-%d %H:%M UTC')}",
                f"   Link: {paper.link}",
                f"   Summary: {paper.summary[:500]}...",
                "",
            ]
        )

    return subject, "\n".join(lines)



def send_email(settings: Settings, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.sender_email
    message["To"] = settings.recipient_email
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.smtp_server, settings.smtp_port, context=context) as server:
        server.login(settings.sender_email, settings.sender_password)
        server.send_message(message)



def run_once(settings: Settings) -> None:
    papers = fetch_latest_papers(
        query=settings.query,
        max_results=settings.max_results,
        hours_back=settings.interval_hours,
    )
    subject, body = format_email(settings.query, papers)
    send_email(settings, subject, body)
    print(f"[{datetime.now().isoformat()}] Sent digest with {len(papers)} papers.")



def main() -> None:
    settings = load_settings()

    print("Starting daily research newsletter service")
    print(f"Query: {settings.query}")
    print(f"Interval: every {settings.interval_hours} hour(s)")

    run_once(settings)

    schedule.every(settings.interval_hours).hours.do(run_once, settings=settings)
    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    main()

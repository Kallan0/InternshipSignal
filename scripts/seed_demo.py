from datetime import datetime, timedelta, timezone

import httpx


now = datetime.now(timezone.utc)
messages = [
    {
        "external_id": "demo-acme-applied",
        "sender": "talent@acme.example",
        "subject": "Application received for Software Engineer Intern at Acme",
        "body_text": "Thank you for applying. We received your application for Software Engineer Intern.",
        "received_at": (now - timedelta(days=8)).isoformat(),
    },
    {
        "external_id": "demo-acme-interview",
        "sender": "talent@acme.example",
        "subject": "Interview invitation for Software Engineer Intern at Acme",
        "body_text": "We would like to schedule an interview for the Software Engineer Intern role.",
        "received_at": (now - timedelta(days=2)).isoformat(),
    },
    {
        "external_id": "demo-northstar-review",
        "sender": "recruiting@northstar.example",
        "subject": "An update about the Data Analyst Intern role at Northstar",
        "body_text": "The hiring team is discussing the candidate and will be in touch soon.",
        "received_at": now.isoformat(),
    },
]

for message in messages:
    response = httpx.post("http://localhost:8000/api/emails/import", json=message, timeout=10)
    response.raise_for_status()
    print(response.json())

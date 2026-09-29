from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def test_email_import_is_idempotent_and_creates_application():
    payload = {
        "external_id": "gmail-123",
        "sender": "careers@example.com",
        "subject": "Application received for Software Engineer Intern at Example",
        "body_text": "Thank you for applying. We received your application.",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with TestClient(app) as client:
        first = client.post("/api/emails/import", json=payload)
        second = client.post("/api/emails/import", json=payload)
        applications = client.get("/api/applications")
    assert first.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert len(applications.json()) == 1


def test_ambiguous_job_email_enters_review_queue():
    payload = {
        "external_id": "gmail-ambiguous",
        "sender": "recruiter@example.org",
        "subject": "A quick update about the role",
        "body_text": "The hiring team will contact the candidate soon.",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with TestClient(app) as client:
        client.post("/api/emails/import", json=payload)
        queue = client.get("/api/review-queue")
    assert len(queue.json()) == 1


def test_accept_email_removes_it_from_review_queue():
    payload = {
        "external_id": "gmail-accept-me",
        "sender": "recruiter@example.org",
        "subject": "A quick update about the role",
        "body_text": "The hiring team will contact the candidate soon.",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with TestClient(app) as client:
        imported = client.post("/api/emails/import", json=payload)
        email_id = imported.json()["email_id"]
        accepted = client.post(f"/api/emails/{email_id}/accept")
        accepted_again = client.post(f"/api/emails/{email_id}/accept")
        queue = client.get("/api/review-queue")
        accepted_history = client.get("/api/accepted-emails")
        metrics = client.get("/api/metrics")

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted_again.json()["status"] == "already-accepted"
    assert queue.json() == []
    assert accepted_history.json()[0]["email_id"] == email_id
    assert metrics.json()["human_reviewed"] == 1
    assert metrics.json()["human_agreement_rate"] == 1
    assert metrics.json()["accepted_by_status"]["UNKNOWN"] == 1


def test_remove_email_cleans_derived_records_and_prevents_reimport():
    payload = {
        "external_id": "gmail-remove-me",
        "sender": "student@internshala.com",
        "subject": "Application received for Software Engineer Intern at Example",
        "body_text": "Thank you for applying. We received your application.",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with TestClient(app) as client:
        imported = client.post("/api/emails/import", json=payload)
        email_id = imported.json()["email_id"]
        removed = client.delete(f"/api/emails/{email_id}")
        applications = client.get("/api/applications")
        missing = client.delete(f"/api/emails/{email_id}")

    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    assert removed.json()["application_removed"] == 1
    assert applications.json() == []
    assert missing.status_code == 404


def test_removed_sender_is_used_for_future_classification():
    first = {
        "external_id": "gmail-learn-first",
        "sender": "Internshala Alerts <alerts@internshala.com>",
        "subject": "Application received for Software Engineer Intern at Example",
        "body_text": "Thank you for applying. We received your application.",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    second = {**first, "external_id": "gmail-learn-second"}
    with TestClient(app) as client:
        imported = client.post("/api/emails/import", json=first)
        removed = client.delete(f"/api/emails/{imported.json()['email_id']}")
        learned = client.post("/api/emails/import", json=second)
        queue = client.get("/api/review-queue")

    assert removed.status_code == 200
    assert learned.status_code == 201
    assert learned.json()["classification"]["provider"] == "user-exclusion-pattern"
    assert learned.json()["classification"]["is_relevant"] is False
    assert queue.json() == []

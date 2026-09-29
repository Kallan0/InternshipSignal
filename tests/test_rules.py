from app.domain import ApplicationStatus
from app.services.rules import classify_with_rules


def test_rejection_has_strong_deterministic_evidence():
    result = classify_with_rules("Update", "We regret to inform you that we are not moving forward.")
    assert result.status is ApplicationStatus.REJECTED
    assert result.confidence >= 0.95


def test_newsletter_is_not_assumed_relevant():
    result = classify_with_rules("Weekly recipes", "Three great dinners for the weekend")
    assert result.status is ApplicationStatus.UNKNOWN
    assert result.confidence >= 0.9


def test_job_alert_is_not_an_application_email():
    result = classify_with_rules(
        "LinkedIn Job Alert: Software Engineering Intern roles",
        "Jobs matching your profile and new jobs for you this week.",
    )
    assert result.status is ApplicationStatus.UNKNOWN
    assert result.is_relevant is False
    assert result.confidence >= 0.95


def test_actual_application_message_beats_job_alert_phrase():
    result = classify_with_rules(
        "Application received",
        "Thank you for applying. Your application was received. Manage job alerts in your profile.",
    )
    assert result.status is ApplicationStatus.APPLICATION_RECEIVED

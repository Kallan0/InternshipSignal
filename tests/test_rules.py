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

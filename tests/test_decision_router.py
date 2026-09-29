from app.domain import ApplicationStatus
from app.schemas import ClassificationResult
from app.services.decision_router import ConfidenceRouter
from app.services.rules import RuleMatch


def result(status: ApplicationStatus, confidence: float, relevant: bool = True) -> ClassificationResult:
    return ClassificationResult(
        is_relevant=relevant, status=status, confidence=confidence, provider="laya", summary="test"
    )


def test_supported_medium_prediction_keeps_automatic_path():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    output = router.route(
        result(ApplicationStatus.INTERVIEW, 0.8),
        RuleMatch(ApplicationStatus.INTERVIEW, 0.96, ["interview phrase"]),
    )
    assert output.status is ApplicationStatus.INTERVIEW
    assert output.needs_review is False
    assert output.provider == "laya+rules"


def test_conflict_is_visible_instead_of_silent_override():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    output = router.route(
        result(ApplicationStatus.OFFER, 0.94),
        RuleMatch(ApplicationStatus.REJECTED, 0.99, ["rejection phrase"]),
    )
    assert output.status is ApplicationStatus.OFFER
    assert output.needs_review is True
    assert any("conflict" in item for item in output.evidence)


def test_low_confidence_uses_fallback():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    fallback = result(ApplicationStatus.NEXT_ROUND, 0.88)
    output = router.route(
        result(ApplicationStatus.UNKNOWN, 0.4),
        RuleMatch(ApplicationStatus.UNKNOWN, 0.55, []),
        lambda: fallback,
    )
    assert output is fallback
    assert any("escalated" in item for item in output.evidence)
    assert output.needs_review is True


def test_llm_and_rule_agreement_can_clear_fallback_review():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    fallback = result(ApplicationStatus.NEXT_ROUND, 0.95)
    output = router.route(
        result(ApplicationStatus.NEXT_ROUND, 0.4),
        RuleMatch(ApplicationStatus.NEXT_ROUND, 0.91, ["next-stage phrase"]),
        lambda: fallback,
    )
    assert output.needs_review is False
    assert any("corroborated" in item for item in output.evidence)


def test_strong_rule_agreement_avoids_expensive_fallback():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    calls = 0

    def fallback():
        nonlocal calls
        calls += 1
        return result(ApplicationStatus.INTERVIEW, 0.9)

    output = router.route(
        result(ApplicationStatus.INTERVIEW, 0.4),
        RuleMatch(ApplicationStatus.INTERVIEW, 0.96, ["explicit interview phrase"]),
        fallback,
    )
    assert calls == 0
    assert output.provider == "laya+rules"


def test_fallback_failure_keeps_primary_in_review_queue():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    primary = result(ApplicationStatus.UNKNOWN, 0.4)

    def unavailable():
        raise RuntimeError("local model returned invalid output")

    output = router.route(
        primary,
        RuleMatch(ApplicationStatus.UNKNOWN, 0.55, []),
        unavailable,
    )
    assert output is primary
    assert output.needs_review is True
    assert any("fallback unavailable" in item for item in output.evidence)


def test_known_job_alert_rule_skips_model_review():
    router = ConfidenceRouter(high=0.9, medium=0.7)
    output = router.route(
        result(ApplicationStatus.INTERVIEW, 0.94),
        RuleMatch(ApplicationStatus.UNKNOWN, 0.99, ["job alert"], is_relevant=False),
    )
    assert output.is_relevant is False
    assert output.status is ApplicationStatus.UNKNOWN
    assert output.needs_review is False

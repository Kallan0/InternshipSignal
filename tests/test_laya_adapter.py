from app.domain import ApplicationStatus
from app.services.classifiers import LayaClassifier, build_laya_state


def test_context_budget_keeps_start_and_end():
    state = build_laya_state("Subject", "sender@example.test", "START" + "x" * 4000 + "END")
    assert "START" in state["body"]
    assert "END" in state["body"]
    assert "long middle omitted" in state["body"]


def test_laya_wire_response_maps_to_domain_result_without_loading_weights():
    classifier = object.__new__(LayaClassifier)
    classifier.model = "typed-decisions"
    raw = {
        "answers": {
            "relevant": {"noul": 0.91},
            "status": {"choice": "interview", "confidence": 0.82},
        },
        "routing": {"model": "typed-decisions"},
    }
    result = classifier._to_result(raw, "Interview", "jobs@example.test", "Meet us")
    assert result.status is ApplicationStatus.INTERVIEW
    assert result.is_relevant is True
    assert result.provider == "laya:typed-decisions"

from datetime import datetime, timezone

from app.domain import ApplicationStatus
from app.schemas import ClassificationResult, EmailImport
from app.services.decision_router import ConfidenceRouter
from app.services.pipeline import ProcessingPipeline


class BatchProvider:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, str, str]]] = []

    def classify_many(self, rows: list[tuple[str, str, str]]) -> list[ClassificationResult]:
        self.calls.append(rows)
        return [
            ClassificationResult(
                is_relevant=True,
                status=ApplicationStatus.APPLICATION_RECEIVED,
                confidence=0.96,
                provider="test-batch",
                summary=subject,
            )
            for subject, _, _ in rows
        ]


def email(external_id: str) -> EmailImport:
    return EmailImport(
        external_id=external_id,
        sender="careers@example.test",
        subject=f"Application received {external_id}",
        body_text="Thank you for applying. Your application was received.",
        received_at=datetime.now(timezone.utc),
    )


def test_batch_classification_uses_provider_batch_api_once():
    provider = BatchProvider()
    pipeline = object.__new__(ProcessingPipeline)
    pipeline.classifier = provider
    pipeline.ollama = None
    pipeline.router = ConfidenceRouter(high=0.9, medium=0.7)

    results = pipeline.classify_many([email("one"), email("two")])

    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 2
    assert [result.status for _, _, result in results] == [
        ApplicationStatus.APPLICATION_RECEIVED,
        ApplicationStatus.APPLICATION_RECEIVED,
    ]

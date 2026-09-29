from pathlib import Path
from typing import Protocol, Sequence

import joblib

from app.config import Settings
from app.domain import ApplicationStatus
from app.schemas import ClassificationResult
from app.services.rules import classify_with_rules, infer_company, infer_role


class ClassificationProvider(Protocol):
    def classify(self, subject: str, sender: str, body: str) -> ClassificationResult: ...


STATUS_CRITERIA = {
    "application_received": "confirms that a submitted job application was received",
    "under_review": "says the application or candidate is currently being reviewed",
    "assessment": "invites, assigns, or discusses a test, challenge, or assessment",
    "interview": "invites, schedules, reschedules, or discusses an interview",
    "next_round": "advances the candidate to another stage without a more specific label",
    "offer": "makes or communicates an employment or internship offer",
    "rejected": "ends the candidacy or says the applicant will not move forward",
    "action_required": "requires an applicant response or action without a clearer stage",
    "unknown": "application-related, but the email does not establish a supported status",
}
STATUS_FROM_LAYA = {key: ApplicationStatus(key.upper()) for key in STATUS_CRITERIA}
LAYA_QUESTIONS = {
    "relevant": {
        "type": "noul",
        "instructions": "Is this about a specific job or internship application by the recipient?",
        "criteria": {
            "false": "newsletter, job alert, marketing, personal mail, or unrelated notification",
            "true": "communication about the recipient's specific application or hiring process",
        },
    },
    "status": {
        "type": "choice",
        "instructions": "What single application status is established by the newest message?",
        "criteria": STATUS_CRITERIA,
    },
}


def build_laya_state(subject: str, sender: str, body: str) -> dict[str, str]:
    """Keep the newest evidence inside Laya's finite context window."""
    if len(body) > 3_200:
        body = f"{body[:2_700]}\n\n[long middle omitted]\n\n{body[-300:]}"
    return {"from": sender[:500], "subject": subject[:1_000], "body": body}


class RulesClassifier:
    def classify(self, subject: str, sender: str, body: str) -> ClassificationResult:
        match = classify_with_rules(subject, body, sender)
        relevant = match.is_relevant if match.is_relevant is not None else (
            match.status is not ApplicationStatus.UNKNOWN or match.confidence < 0.90
        )
        return ClassificationResult(
            is_relevant=relevant,
            status=match.status,
            confidence=match.confidence,
            provider="rules",
            evidence=match.evidence,
            needs_review=relevant and match.status is ApplicationStatus.UNKNOWN,
            company=infer_company(sender, subject),
            role=infer_role(subject, body),
            summary=subject or body[:160],
        )


class BaselineMLClassifier:
    def __init__(self, model_path: str):
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Train the baseline first; model not found at {self.path}")
        artifact = joblib.load(self.path)
        if isinstance(artifact, dict) and artifact.get("version") == 2:
            self.relevance_model = artifact["relevance"]
            self.status_model = artifact["status"]
        else:
            # Backward compatibility with the first single-head artifact.
            self.relevance_model = None
            self.status_model = artifact

    def classify(self, subject: str, sender: str, body: str) -> ClassificationResult:
        text = f"{subject}\n{body}"
        status_probabilities = self.status_model.predict_proba([text])[0]
        status_index = int(status_probabilities.argmax())
        status = ApplicationStatus(self.status_model.classes_[status_index])
        status_confidence = float(status_probabilities[status_index])
        if self.relevance_model is None:
            is_relevant = status is not ApplicationStatus.UNKNOWN
            relevance_probability = float(is_relevant)
        else:
            relevance_probabilities = self.relevance_model.predict_proba([text])[0]
            true_index = list(self.relevance_model.classes_).index(True)
            relevance_probability = float(relevance_probabilities[true_index])
            is_relevant = relevance_probability >= 0.5
        confidence = status_confidence if is_relevant else 1 - relevance_probability
        return ClassificationResult(
            is_relevant=is_relevant,
            status=status,
            confidence=confidence,
            provider="tfidf-logistic-regression",
            evidence=[
                f"status probability: {status_confidence:.3f}",
                f"relevance probability: {relevance_probability:.3f}",
            ],
            company=infer_company(sender, subject),
            role=infer_role(subject, body),
            summary=subject or body[:160],
        )


class LayaClassifier:
    """Primary typed-decision adapter; weights remain lazy until first prediction."""

    def __init__(self, model: str, device: str | None = None, max_loaded: int = 1):
        try:
            from laya import Router
        except ImportError as exc:
            raise RuntimeError("Install the optional Laya extra: uv sync --extra laya") from exc
        kwargs = {"max_loaded": max_loaded}
        if device:
            kwargs["device"] = device
        self.router = Router(**kwargs)
        self.model = model

    def classify(self, subject: str, sender: str, body: str) -> ClassificationResult:
        result = self.router.predict(
            build_laya_state(subject, sender, body), LAYA_QUESTIONS, model=self.model
        )
        return self._to_result(result, subject, sender, body)

    def classify_many(self, rows: Sequence[tuple[str, str, str]], batch_size: int = 16) -> list[ClassificationResult]:
        requests = [
            {
                "state": build_laya_state(subject, sender, body),
                "questions": LAYA_QUESTIONS,
                "model": self.model,
            }
            for subject, sender, body in rows
        ]
        raw_results = self.router.predict_batch(requests, batch_size=batch_size)
        return [
            self._to_result(result, subject, sender, body)
            for result, (subject, sender, body) in zip(raw_results, rows, strict=True)
        ]

    def _to_result(self, result: dict, subject: str, sender: str, body: str) -> ClassificationResult:
        answers = result["answers"]
        status_answer = answers["status"]
        relevant_probability = float(answers["relevant"]["noul"])
        status = STATUS_FROM_LAYA.get(status_answer["choice"], ApplicationStatus.UNKNOWN)
        route = result.get("routing", {}).get("model", self.model)
        return ClassificationResult(
            is_relevant=relevant_probability >= 0.5,
            status=status,
            confidence=float(status_answer["confidence"]),
            provider=f"laya:{route}",
            evidence=[
                f"Laya status confidence: {float(status_answer['confidence']):.3f}",
                f"Laya relevance probability: {relevant_probability:.3f}",
                "checkpoint confidence is provisional until calibrated on held-out project data",
            ],
            company=infer_company(sender, subject),
            role=infer_role(subject, body),
            summary=subject or body[:160],
        )


def build_classifier(settings: Settings) -> ClassificationProvider:
    providers = {
        "rules": lambda: RulesClassifier(),
        "baseline": lambda: BaselineMLClassifier(settings.classifier_model_path),
        "laya": lambda: LayaClassifier(settings.laya_model, settings.laya_device, settings.laya_max_loaded),
    }
    try:
        return providers[settings.classifier_provider]()
    except KeyError as exc:
        raise ValueError(f"Unknown CLASSIFIER_PROVIDER={settings.classifier_provider!r}") from exc

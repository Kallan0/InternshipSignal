from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import ApplicationStatus
from app.models import Application, ApplicationEvent, Classification, EmailMessage
from app.schemas import ClassificationResult, EmailImport
from app.services.classifiers import build_classifier
from app.services.application_matcher import ApplicationMatcher
from app.services.decision_router import ConfidenceRouter
from app.services.exclusions import matching_pattern
from app.services.normalizer import normalize_email
from app.services.ollama import OllamaAnalyzer
from app.services.rules import classify_with_rules
from app.services.status_resolver import resolve_current_status


class ProcessingPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.classifier = build_classifier(self.settings)
        self.ollama = OllamaAnalyzer(self.settings) if self.settings.ollama_enabled else None
        self.router = ConfidenceRouter(self.settings.ml_high_confidence, self.settings.ml_medium_confidence)
        self.matcher = ApplicationMatcher()

    def classify(self, email: EmailImport, clean_body: str) -> ClassificationResult:
        result = self.classifier.classify(email.subject, email.sender, clean_body)
        return self._route(email, clean_body, result)

    def _route(self, email: EmailImport, clean_body: str, result: ClassificationResult) -> ClassificationResult:
        rule = classify_with_rules(email.subject, clean_body, email.sender)
        fallback = None
        if self.ollama:
            fallback = lambda: self.ollama.analyze(email.subject, email.sender, clean_body)
        return self.router.route(result, rule, fallback)

    def classify_many(self, emails: list[EmailImport]) -> list[tuple[EmailImport, str, ClassificationResult]]:
        """Classify a Gmail page in one Laya request when the provider supports it."""
        clean_bodies = [normalize_email(email.body_html, email.body_text) for email in emails]
        batch_predict = getattr(self.classifier, "classify_many", None)
        if callable(batch_predict):
            primary = batch_predict([
                (email.subject, email.sender, body) for email, body in zip(emails, clean_bodies, strict=True)
            ])
        else:
            primary = [
                self.classifier.classify(email.subject, email.sender, body)
                for email, body in zip(emails, clean_bodies, strict=True)
            ]
        return [
            (email, body, self._route(email, body, result))
            for email, body, result in zip(emails, clean_bodies, primary, strict=True)
        ]

    def ingest(self, session: Session, email: EmailImport) -> tuple[EmailMessage, ClassificationResult, bool]:
        existing = session.scalar(select(EmailMessage).where(EmailMessage.gmail_message_id == email.external_id))
        if existing:
            stored = existing.classification
            result = ClassificationResult(
                is_relevant=stored.is_relevant,
                status=ApplicationStatus(stored.status),
                confidence=stored.confidence,
                provider=stored.provider,
                evidence=stored.evidence,
                needs_review=stored.needs_review,
                summary=existing.subject,
            )
            return existing, result, False

        clean_body = normalize_email(email.body_html, email.body_text)
        pattern = matching_pattern(session, email.sender)
        if pattern:
            result = ClassificationResult(
                is_relevant=False,
                status=ApplicationStatus.UNKNOWN,
                confidence=1.0,
                provider="user-exclusion-pattern",
                evidence=[f"user exclusion matched {pattern.kind}: {pattern.value}"],
                summary=email.subject or clean_body[:160],
            )
        else:
            result = self.classify(email, clean_body)
        message = self.ingest_classified(session, email, clean_body, result)
        session.commit()
        session.refresh(message)
        return message, result, True

    def ingest_classified(
        self, session: Session, email: EmailImport, clean_body: str, result: ClassificationResult
    ) -> EmailMessage:
        """Persist a pre-classified email without committing; used by batched Gmail sync."""
        message = EmailMessage(
            gmail_message_id=email.external_id,
            gmail_thread_id=email.thread_id,
            sender=email.sender,
            recipient=email.recipient,
            subject=email.subject,
            body_text=clean_body,
            received_at=email.received_at,
            gmail_labels=email.labels,
        )
        session.add(message)
        session.flush()
        if result.is_relevant:
            company = result.company or "Unknown company"
            role = result.role or "Unknown role"
            match = self.matcher.match_or_create(session, company, role, email.thread_id)
            application = match.application
            result.evidence.append(f"application match: {match.reason} ({match.score:.2f})")
            message.application_id = application.id
            session.add(ApplicationEvent(
                application_id=application.id,
                email_id=message.id,
                status=result.status.value,
                occurred_at=email.received_at,
                summary=result.summary or email.subject,
                source=result.provider,
                confidence=result.confidence,
            ))
            session.flush()
            self.resolve_status(session, application)

        session.add(Classification(
            email_id=message.id,
            is_relevant=result.is_relevant,
            status=result.status.value,
            confidence=result.confidence,
            provider=result.provider,
            evidence=result.evidence,
            needs_review=result.needs_review,
        ))

        message.is_processed = True
        return message

    @staticmethod
    def resolve_status(session: Session, application: Application) -> None:
        events = list(session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application.id)
        ))
        resolved = resolve_current_status(events)
        if resolved:
            status, event = resolved
            application.current_status = status.value
            application.latest_update_at = event.occurred_at

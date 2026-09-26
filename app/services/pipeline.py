from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import ApplicationStatus
from app.models import Application, ApplicationEvent, Classification, EmailMessage
from app.schemas import ClassificationResult, EmailImport
from app.services.classifiers import build_classifier
from app.services.application_matcher import ApplicationMatcher
from app.services.decision_router import ConfidenceRouter
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
        rule = classify_with_rules(email.subject, clean_body)
        fallback = None
        if self.ollama:
            fallback = lambda: self.ollama.analyze(email.subject, email.sender, clean_body)
        return self.router.route(result, rule, fallback)

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
        # Model inference can take minutes on CPU. Run it before beginning a
        # SQLite write transaction so dashboard corrections/removals are not
        # blocked for the entire inference window.
        result = self.classify(email, clean_body)
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
        session.commit()
        session.refresh(message)
        return message, result, True

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

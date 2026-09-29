from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Application,
    ApplicationEvent,
    Classification,
    EmailAccount,
    EmailMessage,
    Feedback,
    IgnoredEmail,
)
from app.schemas import ApplicationDetail, ApplicationSummary, CorrectionRequest, EmailImport
from app.services.pipeline import ProcessingPipeline
from app.services.status_resolver import resolve_current_status
from app.config import get_settings
from app.services.gmail import authorization_url, gmail_readiness, save_callback, sync_account
from app.services.ollama import OllamaAnalyzer
from app.services.exclusions import record_removed_sender

router = APIRouter(prefix="/api")


@lru_cache
def get_pipeline() -> ProcessingPipeline:
    return ProcessingPipeline()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/classifier/status")
def classifier_status() -> dict:
    settings = get_settings()
    payload: dict = {
        "provider": settings.classifier_provider,
        "high_confidence": settings.ml_high_confidence,
        "medium_confidence": settings.ml_medium_confidence,
        "ollama_enabled": settings.ollama_enabled,
    }
    if settings.classifier_provider == "laya":
        try:
            import laya
            payload.update({"installed": True, "version": laya.__version__, "model": settings.laya_model})
        except ImportError:
            payload.update({"installed": False, "model": settings.laya_model})
    return payload


@router.get("/llm/status")
def llm_status() -> dict:
    settings = get_settings()
    status = OllamaAnalyzer(settings).status()
    status["enabled"] = settings.ollama_enabled
    return status


@router.get("/auth/google/start")
def google_auth_start() -> dict[str, str]:
    try:
        return {"authorization_url": authorization_url(get_settings())}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/auth/google/readiness")
def google_auth_readiness() -> dict:
    return gmail_readiness(get_settings())


@router.get("/accounts")
def list_accounts(session: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": item.id, "email_address": item.email_address, "last_synced_at": item.last_synced_at}
        for item in session.scalars(select(EmailAccount).order_by(EmailAccount.created_at))
    ]


@router.get("/auth/google/callback")
def google_auth_callback(code: str, state: str, session: Session = Depends(get_db)) -> RedirectResponse:
    try:
        save_callback(session, get_settings(), code, state)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(f"{get_settings().frontend_url}?gmail=connected")


@router.post("/accounts/{account_id}/sync")
def gmail_sync(
    account_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
    pipeline: ProcessingPipeline = Depends(get_pipeline),
) -> dict[str, object]:
    try:
        return sync_account(session, get_settings(), pipeline, account_id, limit)
    except (LookupError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/emails/import", status_code=201)
def import_email(
    payload: EmailImport,
    session: Session = Depends(get_db),
    pipeline: ProcessingPipeline = Depends(get_pipeline),
) -> dict:
    message, result, created = pipeline.ingest(session, payload)
    return {"email_id": message.id, "created": created, "classification": result.model_dump(mode="json")}


@router.get("/applications", response_model=list[ApplicationSummary])
def list_applications(
    status: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    session: Session = Depends(get_db),
) -> list[Application]:
    statement = select(Application).order_by(Application.latest_update_at.desc())
    if status:
        statement = statement.where(Application.current_status == status)
    if search:
        term = f"%{search}%"
        statement = statement.where(or_(Application.company.ilike(term), Application.role.ilike(term)))
    return list(session.scalars(statement))


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def application_detail(application_id: int, session: Session = Depends(get_db)) -> Application:
    application = session.scalar(
        select(Application).options(selectinload(Application.events)).where(Application.id == application_id)
    )
    if not application:
        raise HTTPException(404, "Application not found")
    return application


@router.get("/review-queue")
def review_queue(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.execute(
        select(EmailMessage, Classification)
        .join(Classification)
        .where(Classification.needs_review.is_(True))
        .order_by(EmailMessage.received_at.desc())
    ).all()
    return [
        {
            "email_id": email.id,
            "subject": email.subject,
            "sender": email.sender,
            "received_at": email.received_at,
            "status": classification.status,
            "confidence": classification.confidence,
            "evidence": classification.evidence,
        }
        for email, classification in rows
    ]


@router.get("/accepted-emails")
def accepted_emails(
    limit: int = Query(default=12, ge=1, le=100), session: Session = Depends(get_db)
) -> list[dict]:
    """Recent human-approved predictions, retained after they leave the review queue."""
    rows = session.execute(
        select(EmailMessage, Feedback, Application)
        .join(Feedback, Feedback.email_id == EmailMessage.id)
        .outerjoin(Application, Application.id == EmailMessage.application_id)
        .where(Feedback.note == "prediction accepted")
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "email_id": email.id,
            "subject": email.subject,
            "sender": email.sender,
            "received_at": email.received_at,
            "status": feedback.corrected_status,
            "accepted_at": feedback.created_at,
            "application_id": application.id if application else None,
            "company": application.company if application else None,
            "role": application.role if application else None,
        }
        for email, feedback, application in rows
    ]


@router.post("/emails/{email_id}/correction")
def correct_classification(
    email_id: int,
    payload: CorrectionRequest,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    email = session.scalar(
        select(EmailMessage).options(selectinload(EmailMessage.classification)).where(EmailMessage.id == email_id)
    )
    if not email or not email.classification:
        raise HTTPException(404, "Classified email not found")
    previous = email.classification.status
    email.classification.status = payload.status.value
    email.classification.needs_review = False
    session.add(Feedback(
        email_id=email.id,
        predicted_status=previous,
        corrected_status=payload.status.value,
        note=payload.note,
    ))
    if email.application_id:
        application = session.get(Application, email.application_id)
        event = session.scalar(
            select(ApplicationEvent).where(ApplicationEvent.email_id == email.id).limit(1)
        )
        if event:
            event.status = payload.status.value
            event.source = "human-correction"
            event.confidence = 1.0
        if payload.company:
            application.company = payload.company
        if payload.role:
            application.role = payload.role
        ProcessingPipeline.resolve_status(session, application)
    session.commit()
    return {"status": "corrected"}


@router.post("/emails/{email_id}/accept")
def accept_classification(email_id: int, session: Session = Depends(get_db)) -> dict[str, str]:
    email = session.scalar(
        select(EmailMessage).options(selectinload(EmailMessage.classification)).where(EmailMessage.id == email_id)
    )
    if not email or not email.classification:
        raise HTTPException(404, "Classified email not found")
    if not email.classification.needs_review:
        return {"status": "already-accepted"}

    accepted_status = email.classification.status
    email.classification.needs_review = False
    session.add(Feedback(
        email_id=email.id,
        predicted_status=accepted_status,
        corrected_status=accepted_status,
        note="prediction accepted",
    ))
    event = session.scalar(
        select(ApplicationEvent).where(ApplicationEvent.email_id == email.id).limit(1)
    )
    if event:
        event.source = "human-accepted"
        event.confidence = 1.0
    session.commit()
    return {"status": "accepted"}


@router.delete("/emails/{email_id}")
def remove_email(email_id: int, session: Session = Depends(get_db)) -> dict[str, str | int | None]:
    email = session.get(EmailMessage, email_id)
    if not email:
        raise HTTPException(404, "Email not found")

    application_id = email.application_id
    ignored = session.scalar(
        select(IgnoredEmail).where(IgnoredEmail.gmail_message_id == email.gmail_message_id)
    )
    if not ignored:
        session.add(IgnoredEmail(
            gmail_message_id=email.gmail_message_id,
            sender=email.sender,
            subject=email.subject,
        ))
    record_removed_sender(session, email.sender)

    session.execute(delete(Feedback).where(Feedback.email_id == email.id))
    session.execute(delete(ApplicationEvent).where(ApplicationEvent.email_id == email.id))
    session.execute(delete(Classification).where(Classification.email_id == email.id))
    session.delete(email)
    session.flush()

    application_removed = False
    if application_id:
        application = session.get(Application, application_id)
        events = list(session.scalars(
            select(ApplicationEvent).where(ApplicationEvent.application_id == application_id)
        ))
        remaining_emails = session.scalar(
            select(func.count(EmailMessage.id)).where(EmailMessage.application_id == application_id)
        ) or 0
        if application and not events and remaining_emails == 0:
            session.delete(application)
            application_removed = True
        elif application:
            resolved = resolve_current_status(events)
            if resolved:
                status, event = resolved
                application.current_status = status.value
                application.latest_update_at = event.occurred_at

    session.commit()
    return {
        "status": "removed",
        "email_id": email_id,
        "application_id": application_id,
        "application_removed": int(application_removed),
    }


@router.get("/metrics")
def metrics(session: Session = Depends(get_db)) -> dict:
    total = session.scalar(select(func.count(Application.id))) or 0
    classifications = session.scalar(select(func.count(Classification.id))) or 0
    review = session.scalar(
        select(func.count(Classification.id)).where(Classification.needs_review.is_(True))
    ) or 0
    llm_escalations = session.scalar(
        select(func.count(Classification.id)).where(Classification.provider.like("ollama:%"))
    ) or 0
    status_rows = session.execute(
        select(Application.current_status, func.count(Application.id)).group_by(Application.current_status)
    ).all()
    provider_rows = session.execute(
        select(Classification.provider, func.count(Classification.id)).group_by(Classification.provider)
    ).all()
    accepted_status_rows = session.execute(
        select(Feedback.corrected_status, func.count(Feedback.id))
        .where(Feedback.note == "prediction accepted")
        .group_by(Feedback.corrected_status)
    ).all()
    feedback_total = session.scalar(select(func.count(Feedback.id))) or 0
    corrected_total = session.scalar(
        select(func.count(Feedback.id)).where(Feedback.predicted_status != Feedback.corrected_status)
    ) or 0
    agreed_total = feedback_total - corrected_total
    return {
        "total_applications": total,
        "needs_review": review,
        "manual_review_rate": review / max(classifications, 1),
        "llm_escalation_rate": llm_escalations / max(classifications, 1),
        "by_status": dict(status_rows),
        "by_provider": dict(provider_rows),
        "accepted_by_status": dict(accepted_status_rows),
        "human_reviewed": feedback_total,
        "human_agreement_rate": agreed_total / max(feedback_total, 1),
        "human_corrections": corrected_total,
    }

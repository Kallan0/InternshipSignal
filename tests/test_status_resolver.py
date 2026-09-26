from datetime import datetime, timedelta, timezone

from app.domain import ApplicationStatus
from app.models import ApplicationEvent
from app.services.status_resolver import resolve_current_status


NOW = datetime.now(timezone.utc)


def event(status: ApplicationStatus, offset: int, source: str = "laya") -> ApplicationEvent:
    return ApplicationEvent(
        application_id=1,
        status=status.value,
        occurred_at=NOW + timedelta(days=offset),
        summary=status.value,
        source=source,
    )


def test_late_generic_review_message_does_not_regress_interview():
    resolved = resolve_current_status([
        event(ApplicationStatus.INTERVIEW, 1),
        event(ApplicationStatus.UNDER_REVIEW, 2),
    ])
    assert resolved[0] is ApplicationStatus.INTERVIEW


def test_terminal_status_is_sticky_against_non_terminal_updates():
    resolved = resolve_current_status([
        event(ApplicationStatus.REJECTED, 1),
        event(ApplicationStatus.UNDER_REVIEW, 2),
    ])
    assert resolved[0] is ApplicationStatus.REJECTED


def test_human_correction_can_override_a_terminal_state():
    resolved = resolve_current_status([
        event(ApplicationStatus.REJECTED, 1),
        event(ApplicationStatus.INTERVIEW, 2, source="human-correction"),
    ])
    assert resolved[0] is ApplicationStatus.INTERVIEW


def test_unknown_does_not_replace_known_status():
    resolved = resolve_current_status([
        event(ApplicationStatus.ASSESSMENT, 1),
        event(ApplicationStatus.UNKNOWN, 2),
    ])
    assert resolved[0] is ApplicationStatus.ASSESSMENT

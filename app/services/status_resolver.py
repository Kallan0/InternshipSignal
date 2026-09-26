from collections.abc import Iterable

from app.domain import ApplicationStatus
from app.models import ApplicationEvent


EARLY_STATUSES = {ApplicationStatus.APPLICATION_RECEIVED, ApplicationStatus.UNDER_REVIEW}
ADVANCED_STATUSES = {
    ApplicationStatus.ASSESSMENT,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.NEXT_ROUND,
}
TERMINAL_STATUSES = {ApplicationStatus.OFFER, ApplicationStatus.REJECTED}


def resolve_current_status(events: Iterable[ApplicationEvent]) -> tuple[ApplicationStatus, ApplicationEvent] | None:
    ordered = sorted(events, key=lambda event: (event.occurred_at, event.id or 0))
    current: ApplicationStatus | None = None
    chosen: ApplicationEvent | None = None
    for event in ordered:
        status = ApplicationStatus(event.status)
        if event.source == "human-correction":
            current, chosen = status, event
            continue
        if status is ApplicationStatus.UNKNOWN and current is not None:
            continue
        if current in TERMINAL_STATUSES and status not in TERMINAL_STATUSES:
            continue
        if current in ADVANCED_STATUSES and status in EARLY_STATUSES:
            continue
        current, chosen = status, event
    if current is None or chosen is None:
        return None
    return current, chosen

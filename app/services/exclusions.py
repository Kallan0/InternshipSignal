"""User-taught exclusions kept conservative to avoid hiding applications."""

from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExclusionPattern


def sender_address(sender: str) -> str:
    address = parseaddr(sender)[1].strip().lower()
    return address or sender.strip().lower()


def record_removed_sender(session: Session, sender: str) -> None:
    """Learn only the precise sender; domains can contain legitimate mail too."""
    address = sender_address(sender)
    if address:
        _record(session, "sender", address)


def _record(session: Session, kind: str, value: str) -> None:
    pattern = session.scalar(select(ExclusionPattern).where(
        ExclusionPattern.kind == kind, ExclusionPattern.value == value
    ))
    if not pattern:
        session.add(ExclusionPattern(kind=kind, value=value, is_active=True))
        return
    pattern.confirmations += 1
    pattern.is_active = True


def matching_pattern(session: Session, sender: str) -> ExclusionPattern | None:
    address = sender_address(sender)
    patterns = list(session.scalars(select(ExclusionPattern).where(
        ExclusionPattern.is_active.is_(True), ExclusionPattern.kind == "sender"
    )))
    for pattern in patterns:
        if pattern.kind == "sender" and pattern.value == address:
            return pattern
    return None

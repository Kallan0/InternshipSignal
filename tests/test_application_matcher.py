from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Application, EmailMessage
from app.services.application_matcher import ApplicationMatcher


def test_same_thread_wins_over_changed_entity_wording():
    with SessionLocal() as session:
        application = Application(company="Northstar Labs", role="Software Engineer Intern")
        session.add(application)
        session.flush()
        session.add(EmailMessage(
            application_id=application.id,
            gmail_message_id="first",
            gmail_thread_id="thread-1",
            sender="jobs@northstar.test",
            subject="Original",
            body_text="",
            received_at=datetime.now(timezone.utc),
        ))
        session.commit()

        match = ApplicationMatcher().match_or_create(
            session, "Different extracted company", "Unknown role", "thread-1"
        )
        assert match.application.id == application.id
        assert match.reason == "same Gmail thread"


def test_normalized_role_aliases_match_existing_application():
    with SessionLocal() as session:
        application = Application(company="Acme Robotics, Inc.", role="Software Engineering Internship")
        session.add(application)
        session.commit()

        match = ApplicationMatcher().match_or_create(
            session, "Acme Robotics", "SWE Intern", None
        )
        assert match.application.id == application.id
        assert match.created is False


def test_different_roles_at_one_company_remain_separate():
    with SessionLocal() as session:
        first = Application(company="BluePeak", role="Data Analyst Intern")
        session.add(first)
        session.commit()

        match = ApplicationMatcher().match_or_create(
            session, "BluePeak", "Product Design Intern", None
        )
        assert match.application.id != first.id
        assert match.created is True


def test_unknown_placeholder_reuses_existing_application():
    with SessionLocal() as session:
        first = Application(company="Unknown company", role="Unknown role")
        session.add(first)
        session.commit()

        match = ApplicationMatcher().match_or_create(
            session, "Unknown company", "Unknown role", None
        )
        assert match.application.id == first.id
        assert match.reason == "exact company and role"
        assert match.created is False

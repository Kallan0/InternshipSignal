from app.database import SessionLocal
from app.services.exclusions import matching_pattern, record_removed_sender


def test_exact_sender_never_suppresses_another_sender_at_the_same_domain():
    with SessionLocal() as session:
        record_removed_sender(session, "Internshala Alerts <alerts@internshala.com>")
        session.commit()

        assert matching_pattern(session, "alerts@internshala.com") is not None
        assert matching_pattern(session, "jobs@internshala.com") is None

        record_removed_sender(session, "Internshala Jobs <jobs@internshala.com>")
        session.commit()

        assert matching_pattern(session, "updates@internshala.com") is None
        assert matching_pattern(session, "jobs@internshala.com") is not None

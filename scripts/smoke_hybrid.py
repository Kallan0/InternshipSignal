from datetime import datetime, timezone

from app.schemas import EmailImport
from app.services.normalizer import normalize_email
from app.services.pipeline import ProcessingPipeline


pipeline = ProcessingPipeline()
cases = [
    EmailImport(
        external_id="smoke-explicit-interview",
        sender="recruiting@example.test",
        subject="Interview invitation",
        body_text="We would like to schedule an interview for your internship application.",
        received_at=datetime.now(timezone.utc),
    ),
    EmailImport(
        external_id="smoke-ambiguous-next-stage",
        sender="recruiting@example.test",
        subject="An update about your application",
        body_text="We enjoyed meeting you and would like to move you to the next stage. Details will follow.",
        received_at=datetime.now(timezone.utc),
    ),
]

for email in cases:
    clean = normalize_email(email.body_html, email.body_text)
    result = pipeline.classify(email, clean)
    print(email.external_id)
    print(result.model_dump_json(indent=2))

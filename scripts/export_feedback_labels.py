"""Export human-reviewed dashboard decisions as a private training dataset.

The output deliberately remains ignored by Git because it contains email content.
"""

import argparse
import csv
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import EmailMessage, Feedback


def main() -> None:
    parser = argparse.ArgumentParser(description="Export human-reviewed email labels for retraining.")
    parser.add_argument("--database-url", default="sqlite:///./email_tracker.db")
    parser.add_argument("--output", default="data/feedback_labels.csv")
    args = parser.parse_args()

    engine = create_engine(args.database_url)
    with Session(engine) as session:
        rows = session.execute(
            select(EmailMessage, Feedback)
            .join(Feedback, Feedback.email_id == EmailMessage.id)
            .order_by(Feedback.created_at)
        ).all()

    unique: dict[int, tuple[EmailMessage, Feedback]] = {}
    for email, feedback in rows:
        unique[email.id] = (email, feedback)  # retain the latest human decision per email

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "external_id", "group_id", "sender", "subject", "body", "label", "is_relevant", "notes"
        ])
        writer.writeheader()
        for email, feedback in unique.values():
            writer.writerow({
                "external_id": email.gmail_message_id,
                "group_id": f"thread-{email.gmail_thread_id or email.application_id or email.id}",
                "sender": email.sender,
                "subject": email.subject,
                "body": email.body_text,
                "label": feedback.corrected_status,
                "is_relevant": "true",
                "notes": feedback.note or "human reviewed",
            })
    print(f"Exported {len(unique)} human-reviewed labels to {output}")


if __name__ == "__main__":
    main()

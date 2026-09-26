import csv
from pathlib import Path


COMPANIES = ["Northstar Labs", "Acme Robotics", "BluePeak", "Orbit Systems", "Cedar Analytics", "NovaWorks"]
ROLES = [
    "Software Engineer Intern", "Data Analyst Intern", "Machine Learning Intern",
    "Product Design Intern", "Backend Developer Intern", "Business Analyst Intern",
]
CONTACTS = ["Maya", "Daniel", "Priya", "Jordan", "Elena", "Sam"]
DATES = ["October 3", "October 7", "October 12", "October 18", "October 24", "October 29"]

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "APPLICATION_RECEIVED": [
        ("Application received — {role}", "Thank you for applying to {company}. We received your application for the {role} position."),
        ("We have your application", "This confirms your submission for {role} at {company}. Our recruiting team has received it."),
        ("Submission confirmation for {company}", "Your application for {role} was successfully submitted and is now in our system."),
        ("Thanks for applying", "Thanks for your interest in {company}. Your {role} application has been received."),
        ("Application ID created", "We created an applicant record for your {role} submission. No action is required right now."),
        ("Your application is in", "Good news—your application to the {role} opening at {company} reached our talent team."),
    ],
    "UNDER_REVIEW": [
        ("Application review update", "Your application for {role} is currently under review by the {company} hiring team."),
        ("Your candidacy is being reviewed", "Our recruiters are reviewing your background for the {role} opportunity."),
        ("Status: review in progress", "The hiring team at {company} is evaluating your application. We will contact you after review."),
        ("Still considering your application", "Your {role} application remains active while the team completes its review."),
        ("Recruiting update from {company}", "We are carefully reviewing applicants for {role}, including your submission."),
        ("Application remains in consideration", "Your profile is with the hiring manager for review. There is nothing you need to do."),
    ],
    "ASSESSMENT": [
        ("Technical assessment invitation", "Please complete the coding assessment for {role} by {date}. The assessment link is in your portal."),
        ("Next step: online test", "We invite you to take an online skills test for the {company} {role} application."),
        ("Coding challenge for {role}", "Your next step is a coding challenge. Submit your solution before {date}."),
        ("Complete your candidate assessment", "To continue with {company}, finish the assigned assessment in the testing platform."),
        ("Assessment deadline reminder", "Your {role} assessment is still incomplete and must be submitted by {date}."),
        ("Case study exercise", "Please prepare and upload the case study exercise for the {role} selection process."),
    ],
    "INTERVIEW": [
        ("Interview invitation — {role}", "We would like to schedule an interview for your {company} application. Choose a time before {date}."),
        ("Let's arrange your interview", "The team would like to meet you regarding the {role} position. Please select an interview slot."),
        ("Interview scheduled with {company}", "Your interview for {role} is confirmed for {date}. Joining details are in the calendar invite."),
        ("Availability for a conversation", "Could you share your availability for a 30-minute interview about the {role} opportunity?"),
        ("Technical interview details", "Your technical interview with the {company} engineering team will take place on {date}."),
        ("Interview rescheduling request", "We need to reschedule your {role} interview. Please choose another available time."),
    ],
    "NEXT_ROUND": [
        ("You are moving to the next stage", "We are pleased to progress your {role} application to the next round at {company}."),
        ("Update on your candidacy", "You have advanced to the next stage of our selection process. More details will follow."),
        ("Progressing your application", "The team enjoyed learning about you and would like to continue with another round."),
        ("Next-round confirmation", "This message confirms that your candidacy for {role} has progressed to the next round."),
        ("Moving forward with {company}", "We would like to move forward with the next stage of the hiring process."),
        ("Another stage in the process", "Your application was selected to continue. {contact} will send the next-round details separately."),
    ],
    "OFFER": [
        ("Offer for {role}", "We are pleased to offer you the {role} position at {company}. Please review the attached offer letter."),
        ("Your internship offer", "Congratulations! {company} would like to extend an internship offer to you."),
        ("Employment offer enclosed", "Attached is your formal employment offer for {role}. Please respond by {date}."),
        ("Welcome to {company}", "We are delighted to make you an offer to join us as a {role}."),
        ("Offer details and next steps", "Your offer letter is ready in the candidate portal. Sign it before {date} to accept."),
        ("Congratulations from our team", "Following the selection process, we would like to offer you the {role} opportunity."),
    ],
    "REJECTED": [
        ("Update regarding your application", "We regret to inform you that we will not be moving forward with your {role} application."),
        ("Your {company} application", "After careful consideration, we selected other candidates for the {role} position."),
        ("Application decision", "Unfortunately, we are unable to progress your candidacy to the next stage."),
        ("Thank you for your interest", "We have decided not to proceed with your application at this time."),
        ("Status update from {company}", "The position has been filled, and your application will not move forward."),
        ("Decision on the {role} role", "Although your background is strong, we are pursuing applicants whose experience more closely matches our needs."),
    ],
    "ACTION_REQUIRED": [
        ("Action required for your application", "Please log in and complete the missing information on your {role} application."),
        ("Please confirm your details", "We need you to confirm your contact information before we can continue processing your application."),
        ("Candidate response needed", "Reply to this message by {date} to keep your application active."),
        ("Incomplete application", "Your {company} candidate profile is incomplete. Upload the requested document to continue."),
        ("Consent required", "Please review and accept the candidate privacy notice in the application portal."),
        ("Verify your email address", "Use the verification link to confirm the email attached to your {role} application."),
    ],
    "UNKNOWN": [
        ("An update from {company}", "There has been activity on your {role} application. Sign in to the portal to view the update."),
        ("Regarding your recent application", "Thank you for your patience. {contact} from recruiting will contact you when more information is available."),
        ("Candidate portal notification", "A new message was added to your candidate profile, but this email does not include its contents."),
        ("Recruiting team message", "We wanted to keep in touch regarding {role}. We do not have a decision or next step to share yet."),
        ("Application correspondence", "This is an automated notification related to your application at {company}."),
        ("A note about the hiring process", "Timelines for the team have changed. We will send a separate update when your status changes."),
    ],
}

NEGATIVE_TEMPLATES = [
    ("jobs-alert", "New {role} jobs this week", "Here are recommended openings based on your job alert preferences."),
    ("newsletter", "The weekly technology briefing", "Read this week's articles, engineering news, and product announcements."),
    ("shopping", "Your order has shipped", "Your package is on the way and is expected to arrive by {date}."),
    ("banking", "Card transaction notification", "A purchase was made using your card. Review it in your banking app."),
    ("social", "You have new profile views", "People viewed your professional profile this week."),
    ("course", "Continue your Python course", "Your next lesson is ready. Resume learning where you stopped."),
    ("event", "Career fair registration open", "Register for the upcoming virtual career fair and meet participating employers."),
    ("marketing", "Grow your recruiting pipeline", "Discover software that helps hiring teams manage candidates and job postings."),
    ("receipt", "Payment receipt", "We received your subscription payment. This receipt is for your records."),
    ("personal", "Lunch this weekend?", "Are you free to meet on Saturday? Let me know what time works."),
]


def render(template: str, index: int) -> str:
    return template.format(
        company=COMPANIES[index], role=ROLES[index], contact=CONTACTS[index], date=DATES[index]
    )


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for status, templates in TEMPLATES.items():
        for template_index, (subject, body) in enumerate(templates):
            for variant in range(len(COMPANIES)):
                rows.append({
                    "external_id": f"syn-{status.lower()}-{template_index + 1}-{variant + 1}",
                    "group_id": f"{status.lower()}-template-{template_index + 1}",
                    "sender": f"{CONTACTS[variant].lower()}@{COMPANIES[variant].lower().replace(' ', '')}.test",
                    "subject": render(subject, variant),
                    "body": render(body, variant),
                    "label": status,
                    "is_relevant": "true",
                    "notes": "synthetic bootstrap example",
                })
    for template_index, (family, subject, body) in enumerate(NEGATIVE_TEMPLATES):
        for variant in range(len(COMPANIES)):
            rows.append({
                "external_id": f"syn-negative-{family}-{variant + 1}",
                "group_id": f"negative-{family}",
                "sender": f"notice-{family}@example.test",
                "subject": render(subject, variant),
                "body": render(body, variant),
                "label": "UNKNOWN",
                "is_relevant": "false",
                "notes": "synthetic hard negative",
            })
    return rows


def main() -> None:
    output = Path("data/labels.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic labeled emails to {output}")


if __name__ == "__main__":
    main()

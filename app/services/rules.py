import re
from dataclasses import dataclass

from app.domain import ApplicationStatus


@dataclass(frozen=True)
class RuleMatch:
    status: ApplicationStatus
    confidence: float
    evidence: list[str]
    is_relevant: bool | None = None


STATUS_RULES: list[tuple[ApplicationStatus, float, tuple[str, ...]]] = [
    (ApplicationStatus.REJECTED, 0.99, ("we regret to inform", "not moving forward", "other candidates")),
    (ApplicationStatus.OFFER, 0.97, ("offer letter", "pleased to offer", "employment offer")),
    (ApplicationStatus.INTERVIEW, 0.96, ("schedule an interview", "interview invitation", "interview scheduled")),
    (ApplicationStatus.ASSESSMENT, 0.95, ("complete the assessment", "coding challenge", "technical assessment")),
    (ApplicationStatus.NEXT_ROUND, 0.91, ("next stage", "next round", "progressed to")),
    (ApplicationStatus.UNDER_REVIEW, 0.91, ("under review", "reviewing your application")),
    (ApplicationStatus.APPLICATION_RECEIVED, 0.95, ("application received", "thank you for applying", "received your application")),
    (ApplicationStatus.ACTION_REQUIRED, 0.88, ("action required", "please respond", "complete your profile")),
]

RELEVANCE_TERMS = (
    "application", "candidate", "intern", "internship", "position", "role", "recruiter",
    "interview", "assessment", "hiring", "job", "offer",
)

# Status rules run first, so an actual application receipt or interview from a
# job board is never hidden just because its sender also sends alerts.
IRRELEVANCE_PHRASES = (
    "job alert", "job alerts", "jobs you may be interested in", "jobs you might be interested in",
    "jobs matching your profile", "recommended jobs", "new jobs for you", "job recommendations",
    "weekly job digest", "career digest", "based on your profile",
)


def classify_with_rules(subject: str, body: str, sender: str = "") -> RuleMatch:
    text = f"{subject}\n{body}".lower()
    for status, confidence, phrases in STATUS_RULES:
        hits = [phrase for phrase in phrases if phrase in text]
        if hits:
            return RuleMatch(status, confidence, [f'phrase: "{hit}"' for hit in hits])
    irrelevant_hits = [phrase for phrase in IRRELEVANCE_PHRASES if phrase in text]
    if irrelevant_hits:
        return RuleMatch(
            ApplicationStatus.UNKNOWN,
            0.99,
            [f'job-alert phrase: "{hit}"' for hit in irrelevant_hits],
            is_relevant=False,
        )
    relevant_hits = sorted({term for term in RELEVANCE_TERMS if term in text})
    if relevant_hits:
        return RuleMatch(ApplicationStatus.UNKNOWN, 0.55, [f"term: {term}" for term in relevant_hits[:4]])
    return RuleMatch(ApplicationStatus.UNKNOWN, 0.92, ["no internship-related evidence"])


def infer_company(sender: str, subject: str) -> str:
    subject_match = re.search(r"(?:at|from|with)\s+([A-Z][\w&. -]{1,50})", subject)
    if subject_match:
        return subject_match.group(1).strip(" .-|:")
    domain_match = re.search(r"@([\w.-]+)", sender)
    if not domain_match:
        return "Unknown company"
    host = domain_match.group(1).lower().split(".")[-2]
    return host.replace("-", " ").title()


def infer_role(subject: str, body: str) -> str:
    patterns = (
        r"(?:for|as) (?:the )?([\w +#./-]+?(?:intern|internship|engineer|developer|analyst|designer))\b",
        r"([\w +#./-]+? intern(?:ship)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, f"{subject} {body}", re.IGNORECASE)
        if match:
            return " ".join(match.group(1).strip().split()).title()
    return "Unknown role"

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, EmailMessage


@dataclass(frozen=True)
class ApplicationMatch:
    application: Application
    reason: str
    score: float
    created: bool = False


def _words(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\bswe\b", "software engineer", value)
    value = re.sub(r"\bsoftware engineering\b", "software engineer", value)
    value = re.sub(r"\b(internship|intern)\b", "", value)
    return re.findall(r"[a-z0-9]+", value)


def normalize_company(value: str) -> str:
    ignored = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "company", "co"}
    return " ".join(word for word in _words(value) if word not in ignored)


def normalize_role(value: str) -> str:
    return " ".join(_words(value))


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_words, right_words = set(left.split()), set(right.split())
    union = left_words | right_words
    jaccard = len(left_words & right_words) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    return 0.65 * sequence + 0.35 * jaccard


class ApplicationMatcher:
    """Conservative matcher: thread identity first, then normalized entities."""

    def match_or_create(
        self,
        session: Session,
        company: str,
        role: str,
        thread_id: str | None,
    ) -> ApplicationMatch:
        if thread_id:
            threaded = session.scalar(
                select(EmailMessage)
                .where(
                    EmailMessage.gmail_thread_id == thread_id,
                    EmailMessage.application_id.is_not(None),
                )
                .order_by(EmailMessage.received_at.desc())
                .limit(1)
            )
            if threaded:
                return ApplicationMatch(session.get(Application, threaded.application_id), "same Gmail thread", 1.0)

        exact = session.scalar(
            select(Application).where(
                Application.company == company,
                Application.role == role,
            )
        )
        if exact:
            return ApplicationMatch(exact, "exact company and role", 1.0)

        normalized_company = normalize_company(company)
        normalized_role = normalize_role(role)
        candidates = list(session.scalars(select(Application)))
        best: tuple[float, Application] | None = None
        company_candidates: list[Application] = []
        for candidate in candidates:
            candidate_company = normalize_company(candidate.company)
            company_score = similarity(normalized_company, candidate_company)
            if normalized_company and normalized_company != "unknown" and company_score >= 0.90:
                company_candidates.append(candidate)
                role_score = similarity(normalized_role, normalize_role(candidate.role))
                score = 0.45 * company_score + 0.55 * role_score
                if best is None or score > best[0]:
                    best = (score, candidate)

        if best and best[0] >= 0.82 and normalized_role not in {"", "unknown role"}:
            return ApplicationMatch(best[1], "normalized company and role similarity", best[0])
        if len(company_candidates) == 1 and normalized_role in {"", "unknown role"}:
            return ApplicationMatch(company_candidates[0], "only application for normalized company", 0.80)

        application = Application(company=company, role=role)
        session.add(application)
        session.flush()
        return ApplicationMatch(application, "no safe existing match", 0.0, created=True)

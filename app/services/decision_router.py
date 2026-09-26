from collections.abc import Callable

from app.domain import ApplicationStatus
from app.schemas import ClassificationResult
from app.services.rules import RuleMatch


class ConfidenceRouter:
    """Combine model confidence, deterministic evidence, and optional escalation."""

    def __init__(self, high: float, medium: float):
        if not 0 <= medium <= high <= 1:
            raise ValueError("Confidence thresholds must satisfy 0 <= medium <= high <= 1")
        self.high = high
        self.medium = medium

    def route(
        self,
        primary: ClassificationResult,
        rule: RuleMatch,
        fallback: Callable[[], ClassificationResult] | None = None,
    ) -> ClassificationResult:
        rule_found = rule.status is not ApplicationStatus.UNKNOWN

        if rule_found and not primary.is_relevant:
            primary.is_relevant = True
            primary.status = rule.status
            primary.provider = f"{primary.provider}+rules-recovery"
            primary.evidence = [*rule.evidence, "rules recovered a model relevance miss", *primary.evidence]
            primary.needs_review = True
            return primary

        if rule_found and primary.status is rule.status:
            primary.provider = f"{primary.provider}+rules"
            primary.evidence = [*rule.evidence, *primary.evidence]
            if rule.confidence >= 0.95:
                primary.evidence.append("strong deterministic evidence accepted without LLM escalation")
                return primary
        elif rule_found and primary.status is not ApplicationStatus.UNKNOWN:
            predicted = primary.status
            primary.evidence = [
                *rule.evidence,
                f"provider/rule conflict: {predicted.value} vs {rule.status.value}",
                *primary.evidence,
            ]
            if primary.confidence < self.high and rule.confidence >= 0.95:
                primary.status = rule.status
            primary.provider = f"{primary.provider}+rules-conflict"
            primary.needs_review = True
            return primary

        if primary.is_relevant and primary.confidence < self.medium:
            if fallback:
                try:
                    escalated = fallback()
                except (RuntimeError, ValueError) as exc:
                    primary.needs_review = True
                    primary.evidence.append(
                        f"fallback unavailable ({type(exc).__name__}); retained primary result for review"
                    )
                    return primary
                escalated.evidence.append(f"escalated from {primary.provider} at {primary.confidence:.3f}")
                if rule_found and escalated.status is rule.status:
                    escalated.evidence.append("LLM result corroborated by deterministic evidence")
                elif rule_found:
                    escalated.needs_review = True
                    escalated.evidence.append(
                        f"LLM/rule conflict: {escalated.status.value} vs {rule.status.value}"
                    )
                else:
                    escalated.needs_review = True
                    escalated.evidence.append("uncorroborated LLM result requires human review")
                return escalated
            primary.needs_review = True
            primary.evidence.append("below automatic confidence threshold")
        elif primary.is_relevant and primary.confidence < self.high and not rule_found:
            primary.needs_review = True
            primary.evidence.append("medium confidence without deterministic support")

        if primary.is_relevant and primary.status is ApplicationStatus.UNKNOWN:
            primary.needs_review = True
        return primary

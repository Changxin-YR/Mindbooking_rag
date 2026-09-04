from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    CONDITIONAL_APPROVE = "CONDITIONAL_APPROVE"
    RETURN_FOR_CHANGES = "RETURN_FOR_CHANGES"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT = "REJECT"
    OFFLINE = "OFFLINE"
    BAN_PROPOSAL = "BAN_PROPOSAL"


class ReviewSubmissionStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"


@dataclass(slots=True)
class ReviewSubmission:
    id: str
    book_id: str
    submission_type: str
    fixed_version_ids: tuple[str, ...]
    status: ReviewSubmissionStatus = ReviewSubmissionStatus.PENDING
    decision_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewDecisionRecord:
    id: str
    submission_id: str
    reviewer_id: str
    decision: ReviewDecision
    actor_type: str
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

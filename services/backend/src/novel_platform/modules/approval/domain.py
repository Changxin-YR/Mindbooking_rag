from dataclasses import dataclass
from enum import StrEnum


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(slots=True)
class ApprovalRequest:
    id: str
    action: str
    requester_id: str
    critical: bool
    status: ApprovalStatus = ApprovalStatus.PENDING

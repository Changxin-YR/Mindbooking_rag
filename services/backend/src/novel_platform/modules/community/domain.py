from dataclasses import dataclass, field
from enum import StrEnum


class ReportStatus(StrEnum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class ReportSubmission:
    id: str
    case_id: str
    reporter_id: str
    reason: str


@dataclass(slots=True)
class ReportCase:
    id: str
    content_type: str
    content_id: str
    status: ReportStatus = ReportStatus.OPEN
    submissions: list[ReportSubmission] = field(default_factory=list)

from dataclasses import dataclass
from enum import StrEnum


class RankingKind(StrEnum):
    ALGORITHM = "ALGORITHM"
    RECOMMENDATION_SCORE = "RECOMMENDATION_SCORE"
    EDITORIAL = "EDITORIAL"
    CAMPAIGN = "CAMPAIGN"


class CampaignStatus(StrEnum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class RetentionAction(StrEnum):
    DELETE = "DELETE"
    ANONYMIZE = "ANONYMIZE"
    ARCHIVE = "ARCHIVE"
    KEEP = "KEEP"
    DOMAIN_CONTROLLED = "DOMAIN_CONTROLLED"


@dataclass(frozen=True, slots=True)
class Campaign:
    id: str
    title: str
    start_date: str
    end_date: str
    status: CampaignStatus = CampaignStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class RewardGrant:
    id: str
    subject_id: str
    reward_type: str
    amount: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RankingItem:
    id: str
    book_id: str
    kind: RankingKind
    score: int
    rank: int
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    id: str
    account_id: str
    book_id: str
    score: int
    personalized: bool


@dataclass(frozen=True, slots=True)
class OperationJob:
    id: str
    job_type: str
    status: str = "QUEUED"


@dataclass(frozen=True, slots=True)
class ExportJob:
    id: str
    requester_id: str
    resource_type: str
    status: str = "QUEUED"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    resource_type: str
    action: RetentionAction
    days: int

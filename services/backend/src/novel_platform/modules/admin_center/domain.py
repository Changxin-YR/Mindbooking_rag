from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewRule:
    code: str
    severity: str
    recommended_action: str
    auto_block_policy: bool
    subject_types: tuple[str, ...]
    version: str


@dataclass(frozen=True, slots=True)
class ReviewerQuality:
    reviewer_id: str
    accuracy_bps: int
    false_positive_bps: int
    miss_bps: int
    overturn_bps: int
    avg_handle_seconds: int
    complaint_bps: int


@dataclass(frozen=True, slots=True)
class AuthorAlert:
    id: str
    author_id: str
    alert_type: str
    summary: str
    risk_level: str
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class User360View:
    account_id: str
    phone: str
    real_name: str
    asset_cents: int | None
    membership_level: int
    growth_level: int


@dataclass(frozen=True, slots=True)
class CsatRecord:
    ticket_id: str
    score: int

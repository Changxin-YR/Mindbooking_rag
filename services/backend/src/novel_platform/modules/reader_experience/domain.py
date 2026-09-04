from dataclasses import dataclass, field
from enum import StrEnum


class FollowTargetType(StrEnum):
    AUTHOR = "AUTHOR"
    ACCOUNT = "ACCOUNT"


class CorrectionKind(StrEnum):
    TYPO = "TYPO"
    DUPLICATE_CHAPTER = "DUPLICATE_CHAPTER"
    MISSING_CHAPTER = "MISSING_CHAPTER"
    FORMATTING = "FORMATTING"
    POLICY = "POLICY"
    COPYRIGHT = "COPYRIGHT"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class BookRating:
    id: str
    account_id: str
    book_id: str
    overall_score: int
    plot_score: int
    character_score: int
    writing_score: int
    update_score: int
    eligibility_metric_version: str
    eligible_words: int


@dataclass(frozen=True, slots=True)
class GrowthEvent:
    id: str
    account_id: str
    source: str
    points: int


@dataclass(slots=True)
class GrowthProfile:
    account_id: str
    points: int = 0
    level: int = 1
    membership_level: int = 0
    fan_level: int = 0
    events: list[GrowthEvent] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CorrectionReport:
    id: str
    account_id: str
    book_id: str
    chapter_id: str
    kind: CorrectionKind
    position: int
    description: str
    status: str = "OPEN"


@dataclass(frozen=True, slots=True)
class MinorProtection:
    account_id: str
    is_minor: bool
    policy_version: str

    @property
    def purchase_allowed(self) -> bool:
        return not self.is_minor

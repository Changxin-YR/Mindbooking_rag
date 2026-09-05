from dataclasses import dataclass
from enum import StrEnum


class AccessResult(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    RESTRICTED = "RESTRICTED"
    FREE = "FREE"
    PURCHASED = "PURCHASED"
    LIMITED_FREE = "LIMITED_FREE"
    MEMBER_FREE = "MEMBER_FREE"
    VIP_REQUIRED = "VIP_REQUIRED"


@dataclass(frozen=True, slots=True)
class AccessDecision:
    result: AccessResult
    allowed: bool


@dataclass(frozen=True, slots=True)
class TtsSegment:
    index: int
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class TtsMetadata:
    book_id: str
    chapter_id: str
    access: AccessResult
    voice: str
    speed: float
    provider: str
    segments: tuple[TtsSegment, ...]


@dataclass(slots=True)
class ReadingProgress:
    account_id: str
    book_id: str
    last_chapter_id: str | None = None
    last_chapter_number: int = 0
    last_position: int = 0
    furthest_chapter_id: str | None = None
    furthest_chapter_number: int = 0
    furthest_position: int = 0
    revision: int = 0
    current_session_id: str | None = None


class ProgressConflict(ValueError):
    def __init__(self, current: ReadingProgress) -> None:
        super().__init__("reading progress revision conflict")
        self.current = current

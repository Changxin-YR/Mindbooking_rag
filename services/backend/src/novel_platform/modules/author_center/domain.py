from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WritingStat:
    author_id: str
    business_date: str
    words: int
    goal: int


@dataclass(frozen=True, slots=True)
class AuthorTask:
    id: str
    code: str
    title: str
    target: int


@dataclass(frozen=True, slots=True)
class TaskProgress:
    author_id: str
    task_id: str
    progress: int
    claimed: bool


@dataclass(frozen=True, slots=True)
class LearningContent:
    id: str
    category: str
    title: str


@dataclass(frozen=True, slots=True)
class ChapterFunnel:
    book_id: str
    chapter_id: str
    entrants: int
    completion_bps: int
    next_chapter_bps: int
    subscription_bps: int


@dataclass(frozen=True, slots=True)
class Appeal:
    id: str
    author_id: str
    subject_type: str
    subject_id: str
    reason: str
    status: str = "OPEN"

from uuid import uuid4

from novel_platform.modules.author_center.domain import (
    Appeal,
    AuthorTask,
    ChapterFunnel,
    LearningContent,
    TaskProgress,
    WritingStat,
)
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.operation.domain import Campaign


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AuthorCenterService:
    def __init__(self, operation: OperationService | None = None) -> None:
        self.operation = operation or OperationService()
        self._stats: dict[tuple[str, str], WritingStat] = {}
        self._tasks: dict[str, AuthorTask] = {}
        self._progress: dict[tuple[str, str], TaskProgress] = {}
        self._progress_requests: dict[str, TaskProgress] = {}
        self._learning: dict[str, LearningContent] = {}
        self._learning_progress: dict[tuple[str, str], int] = {}
        self._funnels: dict[str, ChapterFunnel] = {}
        self._appeals: dict[str, Appeal] = {}

    def record_daily_writing(
        self, author_id: str, business_date: str, words: int, goal: int
    ) -> WritingStat:
        if words < 0 or goal < 0 or not author_id.strip() or not business_date.strip():
            raise ValueError("WRITING_STAT_INVALID")
        stat = WritingStat(author_id, business_date, words, goal)
        self._stats[(author_id, business_date)] = stat
        return stat

    def calendar(self, author_id: str) -> tuple[WritingStat, ...]:
        return tuple(
            sorted(
                (stat for stat in self._stats.values() if stat.author_id == author_id),
                key=lambda stat: stat.business_date,
            )
        )

    def create_task(self, code: str, title: str, target: int) -> AuthorTask:
        if not code.strip() or not title.strip() or target <= 0:
            raise ValueError("AUTHOR_TASK_INVALID")
        task = AuthorTask(_id("TASK"), code, title, target)
        self._tasks[task.id] = task
        return task

    def progress_task(
        self, author_id: str, task_id: str, progress: int, idempotency_key: str
    ) -> TaskProgress:
        task = self._tasks[task_id]
        if progress < 0 or not idempotency_key.strip():
            raise ValueError("AUTHOR_TASK_PROGRESS_INVALID")
        existing = self._progress_requests.get(idempotency_key)
        if existing is not None:
            return existing
        result = TaskProgress(
            author_id, task.id, min(progress, task.target), progress >= task.target
        )
        self._progress[(author_id, task.id)] = result
        self._progress_requests[idempotency_key] = result
        return result

    def create_campaign(self, title: str, start_date: str, end_date: str) -> Campaign:
        return self.operation.create_campaign(title, start_date, end_date)

    def enroll_campaign(self, author_id: str, campaign_id: str) -> bool:
        return self.operation.enroll_campaign(author_id, campaign_id)

    def publish_learning(self, category: str, title: str) -> LearningContent:
        if not category.strip() or not title.strip():
            raise ValueError("LEARNING_CONTENT_INVALID")
        content = LearningContent(_id("LESSON"), category.strip(), title.strip())
        self._learning[content.id] = content
        return content

    def read_learning(self, content_id: str) -> LearningContent:
        return self._learning[content_id]

    def mark_learning_progress(self, author_id: str, content_id: str, percent: int) -> int:
        self.read_learning(content_id)
        if not 0 <= percent <= 100:
            raise ValueError("LEARNING_PROGRESS_INVALID")
        self._learning_progress[(author_id, content_id)] = percent
        return percent

    def learning_progress(self, author_id: str, content_id: str) -> int:
        return self._learning_progress.get((author_id, content_id), 0)

    def record_chapter_funnel(
        self,
        book_id: str,
        chapter_id: str,
        entrants: int,
        completion_bps: int,
        next_chapter_bps: int,
        subscription_bps: int,
    ) -> ChapterFunnel:
        rates = (completion_bps, next_chapter_bps, subscription_bps)
        if entrants < 0 or any(rate < 0 or rate > 10_000 for rate in rates):
            raise ValueError("CHAPTER_FUNNEL_INVALID")
        funnel = ChapterFunnel(book_id, chapter_id, entrants, *rates)
        self._funnels[chapter_id] = funnel
        return funnel

    def open_appeal(
        self, author_id: str, subject_type: str, subject_id: str, reason: str
    ) -> Appeal:
        if (
            not author_id.strip()
            or not subject_type.strip()
            or not subject_id.strip()
            or not reason.strip()
        ):
            raise ValueError("APPEAL_INVALID")
        appeal = Appeal(_id("APPEAL"), author_id, subject_type, subject_id, reason.strip())
        self._appeals[appeal.id] = appeal
        return appeal

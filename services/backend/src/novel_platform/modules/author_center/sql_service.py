"""SQL persistence for Writer derived facts and workflow records."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.author_center.application import AuthorCenterService
from novel_platform.modules.author_center.domain import (
    Appeal,
    AuthorTask,
    ChapterFunnel,
    LearningContent,
    TaskProgress,
    WritingStat,
)
from novel_platform.modules.operation.application import OperationService


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SqlAuthorCenterService(AuthorCenterService):
    """Persist every AuthorCenter fact represented by the public API."""

    def __init__(self, engine: Engine, operation: OperationService | None = None) -> None:
        super().__init__(operation)
        self.engine = engine
        metadata = sa.MetaData()
        self._stats: Any = sa.Table("author_daily_writing_stats", metadata, autoload_with=engine)
        self._tasks: Any = sa.Table("author_task_definitions", metadata, autoload_with=engine)
        self._progress: Any = sa.Table("author_task_progress", metadata, autoload_with=engine)
        self._learning: Any = sa.Table("writer_learning_contents", metadata, autoload_with=engine)
        self._learning_progress: Any = sa.Table(
            "writer_learning_progress", metadata, autoload_with=engine
        )
        self._funnels: Any = sa.Table("chapter_funnel_metrics", metadata, autoload_with=engine)
        self._appeals: Any = sa.Table("author_appeals", metadata, autoload_with=engine)

    def record_daily_writing(
        self, author_id: str, business_date: str, words: int, goal: int
    ) -> WritingStat:
        if words < 0 or goal < 0 or not author_id.strip() or not business_date.strip():
            raise ValueError("WRITING_STAT_INVALID")
        try:
            parsed_date = date.fromisoformat(business_date)
        except ValueError as exc:
            raise ValueError("WRITING_STAT_INVALID") from exc
        stat = WritingStat(author_id, parsed_date.isoformat(), words, goal)
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._stats.c.author_id).where(
                    self._stats.c.author_id == author_id,
                    self._stats.c.business_date == parsed_date,
                )
            ).scalar_one_or_none()
            values = {"words": words, "goal": goal}
            if exists is None:
                connection.execute(
                    self._stats.insert().values(
                        author_id=author_id,
                        business_date=parsed_date,
                        created_at=datetime.now(UTC),
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._stats.update()
                    .where(
                        self._stats.c.author_id == author_id,
                        self._stats.c.business_date == parsed_date,
                    )
                    .values(**values)
                )
        return stat

    def calendar(self, author_id: str) -> tuple[WritingStat, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(self._stats)
                .where(self._stats.c.author_id == author_id)
                .order_by(self._stats.c.business_date)
            ).mappings()
            return tuple(
                WritingStat(
                    str(row["author_id"]),
                    row["business_date"].isoformat(),
                    int(row["words"]),
                    int(row["goal"]),
                )
                for row in rows
            )

    def create_task(self, code: str, title: str, target: int) -> AuthorTask:
        if not code.strip() or not title.strip() or target <= 0:
            raise ValueError("AUTHOR_TASK_INVALID")
        task = AuthorTask(_id("TASK"), code.strip(), title.strip(), target)
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    self._tasks.insert().values(
                        id=task.id,
                        code=task.code,
                        title=task.title,
                        target=task.target,
                        created_at=datetime.now(UTC),
                    )
                )
        except IntegrityError as exc:
            raise ValueError("AUTHOR_TASK_EXISTS") from exc
        return task

    def progress_task(
        self, author_id: str, task_id: str, progress: int, idempotency_key: str
    ) -> TaskProgress:
        if progress < 0 or not author_id.strip() or not idempotency_key.strip():
            raise ValueError("AUTHOR_TASK_PROGRESS_INVALID")
        with self.engine.begin() as connection:
            task_row = (
                connection.execute(sa.select(self._tasks).where(self._tasks.c.id == task_id))
                .mappings()
                .one_or_none()
            )
            if task_row is None:
                raise KeyError(task_id)
            requested = min(progress, int(task_row["target"]))
            key_column = self._progress.c.get("idempotency_key")
            if key_column is not None:
                duplicate = (
                    connection.execute(
                        sa.select(self._progress).where(key_column == idempotency_key)
                    )
                    .mappings()
                    .one_or_none()
                )
                if duplicate is not None:
                    if duplicate["author_id"] != author_id or duplicate["task_id"] != task_id:
                        raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
                    return TaskProgress(
                        str(duplicate["author_id"]),
                        str(duplicate["task_id"]),
                        int(duplicate["progress"]),
                        bool(duplicate["claimed"]),
                    )
            current = (
                connection.execute(
                    sa.select(self._progress)
                    .where(
                        self._progress.c.author_id == author_id,
                        self._progress.c.task_id == task_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            result = TaskProgress(
                author_id, task_id, requested, requested >= int(task_row["target"])
            )
            values: dict[str, object] = {"progress": result.progress, "claimed": result.claimed}
            if key_column is not None:
                values["idempotency_key"] = idempotency_key
            if current is None:
                connection.execute(
                    self._progress.insert().values(
                        author_id=author_id,
                        task_id=task_id,
                        created_at=datetime.now(UTC),
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._progress.update()
                    .where(
                        self._progress.c.author_id == author_id,
                        self._progress.c.task_id == task_id,
                    )
                    .values(**values)
                )
            return result

    def publish_learning(self, category: str, title: str) -> LearningContent:
        if not category.strip() or not title.strip():
            raise ValueError("LEARNING_CONTENT_INVALID")
        content = LearningContent(_id("LESSON"), category.strip(), title.strip())
        with self.engine.begin() as connection:
            connection.execute(
                self._learning.insert().values(
                    id=content.id,
                    category=content.category,
                    title=content.title,
                    created_at=datetime.now(UTC),
                )
            )
        return content

    def read_learning(self, content_id: str) -> LearningContent:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(self._learning).where(self._learning.c.id == content_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(content_id)
        return LearningContent(str(row["id"]), str(row["category"]), str(row["title"]))

    def mark_learning_progress(self, author_id: str, content_id: str, percent: int) -> int:
        self.read_learning(content_id)
        if not 0 <= percent <= 100:
            raise ValueError("LEARNING_PROGRESS_INVALID")
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._learning_progress.c.author_id).where(
                    self._learning_progress.c.author_id == author_id,
                    self._learning_progress.c.content_id == content_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._learning_progress.insert().values(
                        author_id=author_id,
                        content_id=content_id,
                        percent=percent,
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                connection.execute(
                    self._learning_progress.update()
                    .where(
                        self._learning_progress.c.author_id == author_id,
                        self._learning_progress.c.content_id == content_id,
                    )
                    .values(percent=percent)
                )
        return percent

    def learning_progress(self, author_id: str, content_id: str) -> int:
        with self.engine.connect() as connection:
            value = connection.execute(
                sa.select(self._learning_progress.c.percent).where(
                    self._learning_progress.c.author_id == author_id,
                    self._learning_progress.c.content_id == content_id,
                )
            ).scalar_one_or_none()
        return int(value or 0)

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
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._funnels.c.chapter_id).where(
                    self._funnels.c.chapter_id == chapter_id
                )
            ).scalar_one_or_none()
            values = {
                "book_id": book_id,
                "entrants": entrants,
                "completion_bps": completion_bps,
                "next_chapter_bps": next_chapter_bps,
                "subscription_bps": subscription_bps,
            }
            if exists is None:
                connection.execute(
                    self._funnels.insert().values(
                        chapter_id=chapter_id,
                        created_at=datetime.now(UTC),
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._funnels.update()
                    .where(self._funnels.c.chapter_id == chapter_id)
                    .values(**values)
                )
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
        with self.engine.begin() as connection:
            connection.execute(
                self._appeals.insert().values(
                    id=appeal.id,
                    author_id=appeal.author_id,
                    subject_type=appeal.subject_type,
                    subject_id=appeal.subject_id,
                    reason=appeal.reason,
                    status=appeal.status,
                    created_at=datetime.now(UTC),
                )
            )
        return appeal


__all__ = ["SqlAuthorCenterService"]

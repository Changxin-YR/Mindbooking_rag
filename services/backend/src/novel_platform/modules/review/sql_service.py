"""SQLAlchemy review adapter for the existing content and review schema."""

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import BookVisibility
from novel_platform.modules.review.application import ReviewService, _id
from novel_platform.modules.review.domain import (
    ReviewDecision,
    ReviewDecisionRecord,
    ReviewSubmission,
    ReviewSubmissionStatus,
)


class SqlReviewService(ReviewService):
    """Persist the ReviewService contract without changing its domain objects."""

    def __init__(self, engine: Engine, content: ContentService) -> None:
        super().__init__(content)
        self.engine = engine
        metadata = sa.MetaData()
        self._submissions_table: Any = sa.Table(
            "review_submissions", metadata, autoload_with=engine
        )
        self._submission_versions: Any = sa.Table(
            "review_submission_versions", metadata, autoload_with=engine
        )
        self._tasks: Any = sa.Table("review_tasks", metadata, autoload_with=engine)
        self._decisions: Any = sa.Table("review_decisions", metadata, autoload_with=engine)
        self._assigned_staff_column = (
            self._tasks.c.assigned_staff_id if "assigned_staff_id" in self._tasks.c else None
        )

    def submit_first_listing(self, book_id: str, fixed_version_ids: list[str]) -> ReviewSubmission:
        book = self.content.get_book(book_id)
        if book.visibility is BookVisibility.PUBLIC:
            raise ValueError("public book does not need first listing review")
        if not fixed_version_ids:
            raise ValueError("first listing requires at least one fixed version")
        if len(fixed_version_ids) != len(set(fixed_version_ids)):
            raise ValueError("fixed chapter versions must be unique")
        chapter_ids: set[str] = set()
        for version_id in fixed_version_ids:
            version = self.content.get_chapter_version(version_id)
            chapter = self.content.get_chapter(version.chapter_id)
            volume = self.content.get_volume(chapter.volume_id)
            if volume.book_id != book.id:
                raise ValueError("fixed chapter version does not belong to book")
            if chapter.id in chapter_ids:
                raise ValueError("first listing allows one version per chapter")
            chapter_ids.add(chapter.id)

        submission = ReviewSubmission(
            id=_id("SUB"),
            book_id=book_id,
            submission_type="FIRST_LISTING",
            fixed_version_ids=tuple(fixed_version_ids),
        )
        created_at = datetime.now(UTC)
        with self.engine.begin() as connection:
            values: dict[str, Any] = {
                "id": submission.id,
                "book_id": submission.book_id,
                "submission_type": submission.submission_type,
                "status": submission.status.value,
            }
            if "created_at" in self._submissions_table.c:
                values["created_at"] = created_at
            connection.execute(self._submissions_table.insert().values(**values))
            connection.execute(
                self._submission_versions.insert(),
                [
                    {
                        "submission_id": submission.id,
                        "chapter_version_id": version_id,
                        "position": position,
                    }
                    for position, version_id in enumerate(fixed_version_ids)
                ],
            )
            task_values: dict[str, Any] = {
                "id": _id("TASK"),
                "submission_id": submission.id,
                "task_type": "HUMAN_REVIEW",
                "status": "PENDING",
            }
            if "created_at" in self._tasks.c:
                task_values["created_at"] = created_at
            if self._assigned_staff_column is not None:
                task_values["assigned_staff_id"] = None
            connection.execute(self._tasks.insert().values(**task_values))
        self.content.set_book_visibility(book_id, BookVisibility.PENDING_FIRST_REVIEW)
        return submission

    def get_submission(self, submission_id: str) -> ReviewSubmission:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._submissions_table).where(
                        self._submissions_table.c.id == submission_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(submission_id)
            version_ids = connection.execute(
                sa.select(self._submission_versions.c.chapter_version_id)
                .where(self._submission_versions.c.submission_id == submission_id)
                .order_by(self._submission_versions.c.position)
            ).scalars()
            decision_id = connection.execute(
                sa.select(self._decisions.c.id)
                .where(self._decisions.c.submission_id == submission_id)
                .limit(1)
            ).scalar_one_or_none()
            return ReviewSubmission(
                id=str(row["id"]),
                book_id=str(row["book_id"]),
                submission_type=str(row["submission_type"]),
                fixed_version_ids=tuple(str(value) for value in version_ids),
                status=ReviewSubmissionStatus(str(row["status"])),
                decision_id=str(decision_id) if decision_id is not None else None,
            )

    def list_submissions(self) -> list[ReviewSubmission]:
        statement = sa.select(self._submissions_table)
        if "created_at" in self._submissions_table.c:
            statement = statement.order_by(
                self._submissions_table.c.created_at, self._submissions_table.c.id
            )
        else:
            statement = statement.order_by(self._submissions_table.c.id)
        with self.engine.begin() as connection:
            submission_ids = list(
                connection.execute(statement).scalars(self._submissions_table.c.id)
            )
            return [self.get_submission(str(submission_id)) for submission_id in submission_ids]

    def assign_submission(self, submission_id: str, staff_id: str) -> None:
        if not staff_id.strip():
            raise ValueError("REVIEW_ASSIGNEE_REQUIRED")
        if self._assigned_staff_column is None:
            raise RuntimeError("REVIEW_ASSIGNMENT_MIGRATION_REQUIRED")
        with self.engine.begin() as connection:
            result = connection.execute(
                self._tasks.update()
                .where(self._tasks.c.submission_id == submission_id)
                .values(assigned_staff_id=staff_id.strip())
            )
            if result.rowcount == 0:
                raise KeyError(submission_id)

    def list_submissions_for_scope(
        self, scope_type: str, scope_value: str
    ) -> list[ReviewSubmission]:
        if scope_type.upper() in {"ALL", "GLOBAL"} and scope_value == "*":
            return self.list_submissions()
        if scope_type.upper() not in {"SELF", "ASSIGNED"} or self._assigned_staff_column is None:
            return []
        with self.engine.begin() as connection:
            statement = (
                sa.select(self._submissions_table.c.id)
                .select_from(
                    self._submissions_table.join(
                        self._tasks,
                        self._tasks.c.submission_id == self._submissions_table.c.id,
                    )
                )
                .where(self._tasks.c.assigned_staff_id == scope_value)
                .distinct()
            )
            submission_ids = list(connection.execute(statement).scalars())
        return [self.get_submission(str(submission_id)) for submission_id in submission_ids]

    def get_decision(self, decision_id: str) -> ReviewDecisionRecord:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._decisions).where(self._decisions.c.id == decision_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(decision_id)
            decided_at = row["created_at"]
            if not isinstance(decided_at, datetime):
                raise TypeError("review decision timestamp is invalid")
            if decided_at.tzinfo is None:
                decided_at = decided_at.replace(tzinfo=UTC)
            return ReviewDecisionRecord(
                id=str(row["id"]),
                submission_id=str(row["submission_id"]),
                reviewer_id=str(row["reviewer_id"]),
                decision=ReviewDecision(str(row["decision"])),
                actor_type=str(row["actor_type"]),
                decided_at=decided_at,
            )

    def decide(
        self,
        submission_id: str,
        reviewer_id: str,
        decision: ReviewDecision,
        actor_type: str = "human",
    ) -> ReviewDecisionRecord:
        submission = self.get_submission(submission_id)
        if actor_type != "human" and decision is ReviewDecision.APPROVE:
            raise ValueError("first listing approval requires a human reviewer")
        if submission.status is not ReviewSubmissionStatus.PENDING:
            raise ValueError("review submission is already decided")
        if decision is ReviewDecision.APPROVE and not submission.fixed_version_ids:
            raise ValueError("approval requires fixed chapter versions")

        status = (
            ReviewSubmissionStatus.APPROVED
            if decision is ReviewDecision.APPROVE
            else ReviewSubmissionStatus.REJECTED
            if decision in (ReviewDecision.REJECT, ReviewDecision.OFFLINE)
            else ReviewSubmissionStatus.RETURNED
        )
        if decision is ReviewDecision.APPROVE:
            self.content.publish_fixed_versions(submission.book_id, submission.fixed_version_ids)

        record = ReviewDecisionRecord(
            id=_id("DEC"),
            submission_id=submission.id,
            reviewer_id=reviewer_id,
            decision=decision,
            actor_type=actor_type,
            decided_at=datetime.now(UTC),
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._decisions.insert().values(
                    id=record.id,
                    submission_id=record.submission_id,
                    reviewer_id=record.reviewer_id,
                    decision=record.decision.value,
                    actor_type=record.actor_type,
                    created_at=record.decided_at,
                )
            )
            connection.execute(
                self._submissions_table.update()
                .where(self._submissions_table.c.id == submission.id)
                .values(status=status.value)
            )
            connection.execute(
                self._tasks.update()
                .where(self._tasks.c.submission_id == submission.id)
                .values(status="COMPLETED")
            )
        return record

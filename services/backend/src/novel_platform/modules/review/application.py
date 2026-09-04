from uuid import uuid4

from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import BookVisibility
from novel_platform.modules.review.domain import (
    ReviewDecision,
    ReviewDecisionRecord,
    ReviewSubmission,
    ReviewSubmissionStatus,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ReviewService:
    def __init__(self, content: ContentService) -> None:
        self.content = content
        self._submissions: dict[str, ReviewSubmission] = {}
        self._decisions: dict[str, ReviewDecisionRecord] = {}

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
        self._submissions[submission.id] = submission
        self.content.set_book_visibility(book_id, BookVisibility.PENDING_FIRST_REVIEW)
        return submission

    def get_submission(self, submission_id: str) -> ReviewSubmission:
        return self._submissions[submission_id]

    def list_submissions(self) -> list[ReviewSubmission]:
        return list(self._submissions.values())

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
        record = ReviewDecisionRecord(
            id=_id("DEC"),
            submission_id=submission.id,
            reviewer_id=reviewer_id,
            decision=decision,
            actor_type=actor_type,
        )
        self._decisions[record.id] = record
        submission.decision_id = record.id
        if decision is ReviewDecision.APPROVE:
            self.content.publish_fixed_versions(submission.book_id, submission.fixed_version_ids)
            submission.status = ReviewSubmissionStatus.APPROVED
        elif decision in (ReviewDecision.REJECT, ReviewDecision.OFFLINE):
            submission.status = ReviewSubmissionStatus.REJECTED
        else:
            submission.status = ReviewSubmissionStatus.RETURNED
        return record

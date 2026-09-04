from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.review.domain import ReviewDecision


class FirstListingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed_version_ids: list[str]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str
    decision: ReviewDecision
    actor_type: str = "human"


class ReviewSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    book_id: str
    submission_type: str
    fixed_version_ids: tuple[str, ...]
    status: str


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    submission_id: str
    reviewer_id: str
    decision: str
    actor_type: str
    decided_at: object


def build_review_routers(service: ReviewService) -> tuple[APIRouter, APIRouter, APIRouter]:
    reader = APIRouter(prefix="/api/v1", tags=["reader-review"])
    writer = APIRouter(prefix="/writer/api/v1", tags=["writer-review"])
    admin = APIRouter(prefix="/admin/api/v1", tags=["admin-review"])

    @writer.post(
        "/books/{book_id}/first-listing-submissions",
        response_model=ReviewSubmissionResponse,
        status_code=201,
        operation_id="writer_submit_first_listing",
    )
    def submit_first_listing(
        book_id: str, payload: FirstListingRequest
    ) -> ReviewSubmissionResponse:
        try:
            submission = service.submit_first_listing(book_id, payload.fixed_version_ids)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="book not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReviewSubmissionResponse(
            id=submission.id,
            book_id=submission.book_id,
            submission_type=submission.submission_type,
            fixed_version_ids=submission.fixed_version_ids,
            status=submission.status.value,
        )

    @admin.get(
        "/reviews",
        response_model=list[ReviewSubmissionResponse],
        operation_id="admin_list_review_submissions",
    )
    def list_reviews() -> list[ReviewSubmissionResponse]:
        return [
            ReviewSubmissionResponse(
                id=item.id,
                book_id=item.book_id,
                submission_type=item.submission_type,
                fixed_version_ids=item.fixed_version_ids,
                status=item.status.value,
            )
            for item in service.list_submissions()
        ]

    @admin.post(
        "/reviews/{submission_id}/decisions",
        response_model=ReviewDecisionResponse,
        status_code=201,
        operation_id="admin_decide_review",
    )
    def decide_review(submission_id: str, payload: DecisionRequest) -> ReviewDecisionResponse:
        try:
            record = service.decide(
                submission_id, payload.reviewer_id, payload.decision, payload.actor_type
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="review submission not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReviewDecisionResponse(
            id=record.id,
            submission_id=record.submission_id,
            reviewer_id=record.reviewer_id,
            decision=record.decision.value,
            actor_type=record.actor_type,
            decided_at=record.decided_at,
        )

    return reader, writer, admin

from uuid import uuid4

from novel_platform.modules.operation.domain import (
    ExportJob,
    OperationJob,
    RankingItem,
    RankingKind,
    Recommendation,
    RetentionAction,
    RetentionPolicy,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class OperationService:
    def __init__(self) -> None:
        self.rankings: dict[str, RankingItem] = {}
        self.recommendations: dict[str, Recommendation] = {}
        self.jobs: dict[str, OperationJob] = {}
        self.exports: dict[str, ExportJob] = {}
        self.policies: dict[str, RetentionPolicy] = {}
        self.legal_holds: set[str] = set()

    def publish_ranking(
        self, book_ids: list[str], kind: RankingKind, scores: list[int], snapshot_id: str
    ) -> list[RankingItem]:
        if len(book_ids) != len(scores) or not book_ids:
            raise ValueError("RANKING_INPUT_INVALID")
        if kind is RankingKind.EDITORIAL:
            ordered = list(zip(book_ids, scores, strict=True))
        else:
            ordered = sorted(
                zip(book_ids, scores, strict=True), key=lambda item: item[1], reverse=True
            )
        items = []
        for rank, (book_id, score) in enumerate(ordered, 1):
            item = RankingItem(_id("RANK"), book_id, kind, score, rank, snapshot_id)
            self.rankings[item.id] = item
            items.append(item)
        return items

    def editorial_slot(self, book_id: str, position: int, snapshot_id: str) -> RankingItem:
        if position < 1:
            raise ValueError("INVALID_EDITORIAL_POSITION")
        return self.publish_ranking([book_id], RankingKind.EDITORIAL, [position], snapshot_id)[0]

    def recommend(
        self, account_id: str, book_ids: list[str], personalized: bool
    ) -> list[Recommendation]:
        if not personalized:
            book_ids = book_ids[:]
        result = []
        for index, book_id in enumerate(book_ids):
            item = Recommendation(
                _id("REC"), account_id, book_id, len(book_ids) - index, personalized
            )
            self.recommendations[item.id] = item
            result.append(item)
        return result

    def enqueue(self, job_type: str) -> OperationJob:
        job = OperationJob(_id("JOB"), job_type)
        self.jobs[job.id] = job
        return job

    def request_export(self, requester_id: str, resource_type: str) -> ExportJob:
        job = ExportJob(_id("EXP"), requester_id, resource_type)
        self.exports[job.id] = job
        return job

    def set_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        if policy.days < 0:
            raise ValueError("INVALID_RETENTION_DAYS")
        self.policies[policy.resource_type] = policy
        return policy

    def mark_legal_hold(self, resource_id: str) -> None:
        self.legal_holds.add(resource_id)

    def retention_action(self, resource_id: str, resource_type: str) -> RetentionAction:
        if resource_id in self.legal_holds:
            return RetentionAction.KEEP
        return self.policies.get(
            resource_type, RetentionPolicy(resource_type, RetentionAction.DOMAIN_CONTROLLED, 0)
        ).action

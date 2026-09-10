from uuid import uuid4

from novel_platform.modules.operation.domain import (
    Campaign,
    ExportJob,
    OperationJob,
    RankingItem,
    RankingKind,
    Recommendation,
    RetentionAction,
    RetentionPolicy,
    RewardGrant,
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
        self.campaigns: dict[str, Campaign] = {}
        self.campaign_enrollments: set[tuple[str, str]] = set()
        self.rewards: dict[str, RewardGrant] = {}

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

    def public_rankings(self, kind: RankingKind = RankingKind.ALGORITHM) -> tuple[RankingItem, ...]:
        items = [item for item in self.rankings.values() if item.kind is kind]
        if not items:
            return ()
        latest_snapshot = items[-1].snapshot_id
        return tuple(
            sorted(
                (item for item in items if item.snapshot_id == latest_snapshot),
                key=lambda item: item.rank,
            )
        )

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

    def create_campaign(self, title: str, start_date: str, end_date: str) -> Campaign:
        if not title.strip() or not start_date.strip() or not end_date.strip():
            raise ValueError("CAMPAIGN_INVALID")
        campaign = Campaign(_id("CAMP"), title.strip(), start_date, end_date)
        self.campaigns[campaign.id] = campaign
        return campaign

    def enroll_campaign(self, account_id: str, campaign_id: str) -> bool:
        if campaign_id not in self.campaigns:
            raise KeyError(campaign_id)
        enrollment = (account_id, campaign_id)
        if enrollment in self.campaign_enrollments:
            return False
        self.campaign_enrollments.add(enrollment)
        return True

    def grant_reward(
        self, subject_id: str, reward_type: str, amount: int, idempotency_key: str
    ) -> RewardGrant:
        if amount <= 0 or not idempotency_key.strip():
            raise ValueError("REWARD_INVALID")
        existing = self.rewards.get(idempotency_key)
        if existing is not None:
            return existing
        grant = RewardGrant(_id("REWARD"), subject_id, reward_type, amount, idempotency_key)
        self.rewards[idempotency_key] = grant
        return grant

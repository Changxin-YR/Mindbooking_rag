"""SQLAlchemy adapter for operational ranking and campaign facts."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.operation.application import OperationService
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


class SqlOperationService(OperationService):
    """Persist operational facts while keeping the application contract unchanged."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._rankings: Any = sa.Table("ranking_items", metadata, autoload_with=engine)
        self._recommendations: Any = sa.Table("recommendations", metadata, autoload_with=engine)
        self._jobs: Any = sa.Table("operation_jobs", metadata, autoload_with=engine)
        self._exports: Any = sa.Table("export_jobs", metadata, autoload_with=engine)
        self._policies: Any = sa.Table("retention_policies", metadata, autoload_with=engine)
        self._holds: Any = sa.Table("operation_legal_holds", metadata, autoload_with=engine)
        self._campaigns: Any = sa.Table("operation_campaigns", metadata, autoload_with=engine)
        self._enrollments: Any = sa.Table(
            "operation_campaign_enrollments", metadata, autoload_with=engine
        )
        self._rewards: Any = sa.Table("operation_reward_grants", metadata, autoload_with=engine)

    def publish_ranking(
        self, book_ids: list[str], kind: RankingKind, scores: list[int], snapshot_id: str
    ) -> list[RankingItem]:
        if len(book_ids) != len(scores) or not book_ids:
            raise ValueError("RANKING_INPUT_INVALID")
        ordered = (
            list(zip(book_ids, scores, strict=True))
            if kind is RankingKind.EDITORIAL
            else sorted(zip(book_ids, scores, strict=True), key=lambda item: item[1], reverse=True)
        )
        items = [
            RankingItem(_id("RANK"), book_id, kind, score, rank, snapshot_id)
            for rank, (book_id, score) in enumerate(ordered, 1)
        ]
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                self._rankings.insert(),
                [
                    {
                        "id": item.id,
                        "book_id": item.book_id,
                        "kind": item.kind.value,
                        "score": item.score,
                        "rank": item.rank,
                        "snapshot_id": item.snapshot_id,
                        "created_at": now,
                    }
                    for item in items
                ],
            )
        return items

    def public_rankings(self, kind: RankingKind = RankingKind.ALGORITHM) -> tuple[RankingItem, ...]:
        with self.engine.begin() as connection:
            latest_snapshot = connection.execute(
                sa.select(self._rankings)
                .where(self._rankings.c.kind == kind.value)
                .order_by(self._rankings.c.created_at.desc(), self._rankings.c.id.desc())
                .limit(1)
            ).mappings().one_or_none()
            if latest_snapshot is None:
                return ()
            rows = connection.execute(
                sa.select(self._rankings)
                .where(
                    self._rankings.c.kind == kind.value,
                    self._rankings.c.snapshot_id == latest_snapshot["snapshot_id"],
                )
                .order_by(self._rankings.c.rank, self._rankings.c.created_at)
            ).mappings()
            return tuple(self._ranking_from_row(row) for row in rows)

    def recommend(
        self, account_id: str, book_ids: list[str], personalized: bool
    ) -> list[Recommendation]:
        if not personalized:
            book_ids = book_ids[:]
        result = [
            Recommendation(_id("REC"), account_id, book_id, len(book_ids) - index, personalized)
            for index, book_id in enumerate(book_ids)
        ]
        with self.engine.begin() as connection:
            connection.execute(
                self._recommendations.insert(),
                [
                    {
                        "id": item.id,
                        "account_id": item.account_id,
                        "book_id": item.book_id,
                        "score": item.score,
                        "personalized": item.personalized,
                        "created_at": datetime.now(UTC),
                    }
                    for item in result
                ],
            )
        return result

    def enqueue(self, job_type: str) -> OperationJob:
        job = OperationJob(_id("JOB"), job_type)
        with self.engine.begin() as connection:
            connection.execute(
                self._jobs.insert().values(
                    id=job.id,
                    job_type=job.job_type,
                    status=job.status,
                    created_at=datetime.now(UTC),
                )
            )
        return job

    def request_export(self, requester_id: str, resource_type: str) -> ExportJob:
        job = ExportJob(_id("EXP"), requester_id, resource_type)
        with self.engine.begin() as connection:
            connection.execute(
                self._exports.insert().values(
                    id=job.id,
                    requester_id=job.requester_id,
                    resource_type=job.resource_type,
                    status=job.status,
                    created_at=datetime.now(UTC),
                )
            )
        return job

    def set_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        if policy.days < 0:
            raise ValueError("INVALID_RETENTION_DAYS")
        with self.engine.begin() as connection:
            existing = connection.execute(
                sa.select(self._policies.c.resource_type)
                .where(self._policies.c.resource_type == policy.resource_type)
                .with_for_update()
            ).scalar_one_or_none()
            values = {"action": policy.action.value, "days": policy.days}
            if existing is None:
                connection.execute(
                    self._policies.insert().values(
                        resource_type=policy.resource_type,
                        created_at=datetime.now(UTC),
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._policies.update()
                    .where(self._policies.c.resource_type == policy.resource_type)
                    .values(**values)
                )
        return policy

    def mark_legal_hold(self, resource_id: str) -> None:
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._holds.c.resource_id).where(self._holds.c.resource_id == resource_id)
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._holds.insert().values(
                        resource_id=resource_id, created_at=datetime.now(UTC)
                    )
                )

    def retention_action(self, resource_id: str, resource_type: str) -> RetentionAction:
        with self.engine.begin() as connection:
            held = connection.execute(
                sa.select(self._holds.c.resource_id).where(self._holds.c.resource_id == resource_id)
            ).scalar_one_or_none()
            if held is not None:
                return RetentionAction.KEEP
            action = connection.execute(
                sa.select(self._policies.c.action).where(
                    self._policies.c.resource_type == resource_type
                )
            ).scalar_one_or_none()
            return (
                RetentionAction(action) if action is not None else RetentionAction.DOMAIN_CONTROLLED
            )

    def create_campaign(self, title: str, start_date: str, end_date: str) -> Campaign:
        if not title.strip() or not start_date.strip() or not end_date.strip():
            raise ValueError("CAMPAIGN_INVALID")
        campaign = Campaign(_id("CAMP"), title.strip(), start_date, end_date)
        with self.engine.begin() as connection:
            connection.execute(
                self._campaigns.insert().values(
                    id=campaign.id,
                    title=campaign.title,
                    start_date=campaign.start_date,
                    end_date=campaign.end_date,
                    status=campaign.status.value,
                    created_at=datetime.now(UTC),
                )
            )
        return campaign

    def enroll_campaign(self, account_id: str, campaign_id: str) -> bool:
        with self.engine.begin() as connection:
            campaign = connection.execute(
                sa.select(self._campaigns.c.id).where(self._campaigns.c.id == campaign_id)
            ).scalar_one_or_none()
            if campaign is None:
                raise KeyError(campaign_id)
            existing = connection.execute(
                sa.select(self._enrollments.c.account_id).where(
                    self._enrollments.c.account_id == account_id,
                    self._enrollments.c.campaign_id == campaign_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False
            connection.execute(
                self._enrollments.insert().values(
                    account_id=account_id, campaign_id=campaign_id, created_at=datetime.now(UTC)
                )
            )
            return True

    def grant_reward(
        self, subject_id: str, reward_type: str, amount: int, idempotency_key: str
    ) -> RewardGrant:
        if amount <= 0 or not idempotency_key.strip():
            raise ValueError("REWARD_INVALID")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._rewards)
                    .where(self._rewards.c.idempotency_key == idempotency_key)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                return self._reward_from_row(row)
            reward = RewardGrant(_id("REWARD"), subject_id, reward_type, amount, idempotency_key)
            connection.execute(
                self._rewards.insert().values(
                    id=reward.id,
                    subject_id=reward.subject_id,
                    reward_type=reward.reward_type,
                    amount=reward.amount,
                    idempotency_key=reward.idempotency_key,
                    created_at=datetime.now(UTC),
                )
            )
            return reward

    @staticmethod
    def _ranking_from_row(row: sa.RowMapping) -> RankingItem:
        return RankingItem(
            str(row["id"]),
            str(row["book_id"]),
            RankingKind(str(row["kind"])),
            int(row["score"]),
            int(row["rank"]),
            str(row["snapshot_id"]),
        )

    @staticmethod
    def _reward_from_row(row: sa.RowMapping) -> RewardGrant:
        return RewardGrant(
            str(row["id"]),
            str(row["subject_id"]),
            str(row["reward_type"]),
            int(row["amount"]),
            str(row["idempotency_key"]),
        )


__all__ = ["SqlOperationService"]

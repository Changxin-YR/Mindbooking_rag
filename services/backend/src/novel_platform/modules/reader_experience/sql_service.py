"""SQLAlchemy adapter for reader ratings, growth, and safety preferences."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reader_experience.domain import (
    BookRating,
    CorrectionKind,
    CorrectionReport,
    FollowTargetType,
    GrowthEvent,
    GrowthProfile,
    MinorProtection,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SqlReaderExperienceService(ReaderExperienceService):
    """Persist the existing Reader Experience service contract."""

    def __init__(self, engine: Engine, min_rating_words: int = 1_000) -> None:
        super().__init__(min_rating_words)
        self.engine = engine
        metadata = sa.MetaData()
        self._ratings: Any = sa.Table("book_user_ratings", metadata, autoload_with=engine)
        self._rating_versions: Any = sa.Table(
            "book_user_rating_versions", metadata, autoload_with=engine
        )
        self._follows: Any = sa.Table("follow_relations", metadata, autoload_with=engine)
        self._growth_profiles: Any = sa.Table(
            "user_growth_profiles", metadata, autoload_with=engine
        )
        self._growth_events: Any = sa.Table("user_growth_events", metadata, autoload_with=engine)
        self._corrections: Any = sa.Table(
            "content_correction_reports", metadata, autoload_with=engine
        )
        self._minor: Any = sa.Table("minor_protection_profiles", metadata, autoload_with=engine)

    def rate(
        self,
        account_id: str,
        book_id: str,
        overall_score: int,
        plot_score: int,
        character_score: int,
        writing_score: int,
        eligible_words: int,
        update_score: int = 5,
    ) -> BookRating:
        scores = (overall_score, plot_score, character_score, writing_score, update_score)
        if any(score < 1 or score > 5 for score in scores):
            raise ValueError("RATING_SCORE_INVALID")
        if eligible_words < self.min_rating_words:
            raise ValueError("RATING_NOT_ELIGIBLE")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._ratings)
                    .where(
                        self._ratings.c.account_id == account_id,
                        self._ratings.c.book_id == book_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            rating_id = str(row["id"]) if row is not None else _id("RATE")
            values = {
                "overall_score": overall_score,
                "plot_score": plot_score,
                "character_score": character_score,
                "writing_score": writing_score,
                "update_score": update_score,
                "eligibility_metric_version": "effective-reading-v1",
                "eligible_words": eligible_words,
            }
            if row is None:
                connection.execute(
                    self._ratings.insert().values(
                        id=rating_id,
                        account_id=account_id,
                        book_id=book_id,
                        created_at=now,
                        **values,
                    )
                )
            else:
                connection.execute(
                    self._ratings.update().where(self._ratings.c.id == rating_id).values(**values)
                )
            version_id = connection.execute(
                sa.select(sa.func.coalesce(sa.func.max(self._rating_versions.c.id), 0) + 1)
            ).scalar_one()
            connection.execute(
                self._rating_versions.insert().values(
                    id=version_id,
                    rating_id=rating_id,
                    overall_score=overall_score,
                    plot_score=plot_score,
                    character_score=character_score,
                    writing_score=writing_score,
                    update_score=update_score,
                    created_at=now,
                )
            )
        return BookRating(
            rating_id,
            account_id,
            book_id,
            overall_score,
            plot_score,
            character_score,
            writing_score,
            update_score,
            "effective-reading-v1",
            eligible_words,
        )

    def rating_history(self, account_id: str, book_id: str) -> tuple[BookRating, ...]:
        with self.engine.begin() as connection:
            parent = (
                connection.execute(
                    sa.select(self._ratings).where(
                        self._ratings.c.account_id == account_id,
                        self._ratings.c.book_id == book_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if parent is None:
                return ()
            versions = connection.execute(
                sa.select(self._rating_versions)
                .where(self._rating_versions.c.rating_id == parent["id"])
                .order_by(self._rating_versions.c.id)
            ).mappings()
            return tuple(
                BookRating(
                    str(parent["id"]),
                    account_id,
                    book_id,
                    int(row["overall_score"]),
                    int(row["plot_score"]),
                    int(row["character_score"]),
                    int(row["writing_score"]),
                    int(row["update_score"]),
                    str(parent["eligibility_metric_version"]),
                    int(parent["eligible_words"]),
                )
                for row in versions
            )

    def follow(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            target = FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        if not target_id or (target is FollowTargetType.ACCOUNT and target_id == account_id):
            raise ValueError("FOLLOW_TARGET_INVALID")
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._follows.c.id).where(
                    self._follows.c.account_id == account_id,
                    self._follows.c.target_type == target.value,
                    self._follows.c.target_id == target_id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                return False
            follow_id = connection.execute(
                sa.select(sa.func.coalesce(sa.func.max(self._follows.c.id), 0) + 1)
            ).scalar_one()
            connection.execute(
                self._follows.insert().values(
                    id=follow_id,
                    account_id=account_id,
                    target_type=target.value,
                    target_id=target_id,
                    created_at=datetime.now(UTC),
                )
            )
            return True

    def unfollow(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        with self.engine.begin() as connection:
            result = connection.execute(
                self._follows.delete().where(
                    self._follows.c.account_id == account_id,
                    self._follows.c.target_type == target_type,
                    self._follows.c.target_id == target_id,
                )
            )
            return result.rowcount > 0

    def following(self, account_id: str) -> tuple[tuple[str, str], ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._follows.c.target_type, self._follows.c.target_id)
                .where(self._follows.c.account_id == account_id)
                .order_by(self._follows.c.target_type, self._follows.c.target_id)
            )
            return tuple((str(row.target_type), str(row.target_id)) for row in rows)

    def is_following(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            target = FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        with self.engine.begin() as connection:
            return (
                connection.execute(
                    sa.select(self._follows.c.id).where(
                        self._follows.c.account_id == account_id,
                        self._follows.c.target_type == target.value,
                        self._follows.c.target_id == target_id,
                    )
                ).scalar_one_or_none()
                is not None
            )

    def add_growth(self, account_id: str, source: str, points: int) -> GrowthEvent:
        if points <= 0:
            raise ValueError("GROWTH_POINTS_INVALID")
        event = GrowthEvent(_id("GROW"), account_id, source, points)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._growth_profiles)
                    .where(self._growth_profiles.c.account_id == account_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            total = points + (int(row["points"]) if row is not None else 0)
            level = 1 + sum(total >= threshold for threshold in (100, 500, 1_500))
            if row is None:
                connection.execute(
                    self._growth_profiles.insert().values(
                        account_id=account_id,
                        points=total,
                        level=level,
                        membership_level=0,
                        fan_level=0,
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                connection.execute(
                    self._growth_profiles.update()
                    .where(self._growth_profiles.c.account_id == account_id)
                    .values(points=total, level=level)
                )
            connection.execute(
                self._growth_events.insert().values(
                    id=event.id,
                    account_id=event.account_id,
                    source=event.source,
                    points=event.points,
                    created_at=datetime.now(UTC),
                )
            )
        return event

    def growth(self, account_id: str) -> GrowthProfile:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._growth_profiles).where(
                        self._growth_profiles.c.account_id == account_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            events = connection.execute(
                sa.select(self._growth_events)
                .where(self._growth_events.c.account_id == account_id)
                .order_by(self._growth_events.c.created_at, self._growth_events.c.id)
            ).mappings()
            profile = GrowthProfile(
                account_id,
                int(row["points"]) if row is not None else 0,
                int(row["level"]) if row is not None else 1,
                int(row["membership_level"]) if row is not None else 0,
                int(row["fan_level"]) if row is not None else 0,
            )
            profile.events.extend(
                GrowthEvent(str(item["id"]), account_id, str(item["source"]), int(item["points"]))
                for item in events
            )
            return profile

    def submit_correction(
        self,
        account_id: str,
        book_id: str,
        chapter_id: str,
        kind: CorrectionKind,
        position: int,
        description: str,
    ) -> CorrectionReport:
        if position < 0 or not description.strip():
            raise ValueError("CORRECTION_INVALID")
        report = CorrectionReport(
            _id("COR"), account_id, book_id, chapter_id, kind, position, description.strip()
        )
        with self.engine.begin() as connection:
            connection.execute(
                self._corrections.insert().values(
                    id=report.id,
                    account_id=report.account_id,
                    book_id=report.book_id,
                    chapter_id=report.chapter_id,
                    kind=report.kind.value,
                    position=report.position,
                    description=report.description,
                    status=report.status,
                    created_at=datetime.now(UTC),
                )
            )
        return report

    def set_minor_protection(
        self, account_id: str, is_minor: bool, policy_version: str
    ) -> MinorProtection:
        if not policy_version.strip():
            raise ValueError("MINOR_POLICY_VERSION_REQUIRED")
        protection = MinorProtection(account_id, is_minor, policy_version)
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._minor.c.account_id).where(self._minor.c.account_id == account_id)
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(
                    self._minor.insert().values(
                        account_id=account_id,
                        is_minor=is_minor,
                        policy_version=policy_version.strip(),
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                connection.execute(
                    self._minor.update()
                    .where(self._minor.c.account_id == account_id)
                    .values(is_minor=is_minor, policy_version=policy_version.strip())
                )
        return protection

    def minor_protection(self, account_id: str) -> MinorProtection:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._minor).where(self._minor.c.account_id == account_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return MinorProtection(account_id, False, "minor-v1")
            return MinorProtection(account_id, bool(row["is_minor"]), str(row["policy_version"]))


__all__ = ["SqlReaderExperienceService"]

from uuid import uuid4

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


class ReaderExperienceService:
    def __init__(self, min_rating_words: int = 1_000) -> None:
        self.min_rating_words = min_rating_words
        self._ratings: dict[tuple[str, str], list[BookRating]] = {}
        self._follows: set[tuple[str, FollowTargetType, str]] = set()
        self._growth: dict[str, GrowthProfile] = {}
        self._corrections: dict[str, CorrectionReport] = {}
        self._minor: dict[str, MinorProtection] = {}

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
        key = (account_id, book_id)
        history = self._ratings.setdefault(key, [])
        rating = BookRating(
            history[0].id if history else _id("RATE"),
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
        history.append(rating)
        return rating

    def rating_history(self, account_id: str, book_id: str) -> tuple[BookRating, ...]:
        return tuple(self._ratings.get((account_id, book_id), ()))

    def follow(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            target = FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        if not target_id or (target is FollowTargetType.ACCOUNT and target_id == account_id):
            raise ValueError("FOLLOW_TARGET_INVALID")
        key = (account_id, target, target_id)
        if key in self._follows:
            return False
        self._follows.add(key)
        return True

    def unfollow(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            target = FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        key = (account_id, target, target_id)
        if key not in self._follows:
            return False
        self._follows.remove(key)
        return True

    def following(self, account_id: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (target_type.value, target_id)
                for owner, target_type, target_id in self._follows
                if owner == account_id
            )
        )

    def is_following(self, account_id: str, target_type: str, target_id: str) -> bool:
        try:
            target = FollowTargetType(target_type)
        except ValueError as exc:
            raise ValueError("FOLLOW_TARGET_INVALID") from exc
        return (account_id, target, target_id) in self._follows

    def add_growth(self, account_id: str, source: str, points: int) -> GrowthEvent:
        if points <= 0:
            raise ValueError("GROWTH_POINTS_INVALID")
        profile = self._growth.setdefault(account_id, GrowthProfile(account_id))
        event = GrowthEvent(_id("GROW"), account_id, source, points)
        profile.events.append(event)
        profile.points += points
        profile.level = 1 + sum(profile.points >= threshold for threshold in (100, 500, 1_500))
        return event

    def growth(self, account_id: str) -> GrowthProfile:
        return self._growth.setdefault(account_id, GrowthProfile(account_id))

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
        self._corrections[report.id] = report
        return report

    def set_minor_protection(
        self, account_id: str, is_minor: bool, policy_version: str
    ) -> MinorProtection:
        if not policy_version.strip():
            raise ValueError("MINOR_POLICY_VERSION_REQUIRED")
        protection = MinorProtection(account_id, is_minor, policy_version)
        self._minor[account_id] = protection
        return protection

    def minor_protection(self, account_id: str) -> MinorProtection:
        return self._minor.get(account_id, MinorProtection(account_id, False, "minor-v1"))

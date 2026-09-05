from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.author.domain import AuthorProfile


class AuthorRepository(Protocol):
    def create_profile(self, profile: AuthorProfile) -> None: ...

    def profile(self, profile_id: str) -> AuthorProfile | None: ...

    def profile_for_account(self, account_id: str) -> AuthorProfile | None: ...

    def has_account_profile(self, account_id: str) -> bool: ...

    def has_pen_name(self, normalized_pen_name: str) -> bool: ...

    def change_pen_name(self, profile_id: str, pen_name: str, normalized_pen_name: str) -> None: ...

    def pen_name_history(self, profile_id: str) -> list[str]: ...


class InMemoryAuthorRepository:
    """Development repository; production wiring must provide a transactional adapter."""

    def __init__(self) -> None:
        self._guard = RLock()
        self._profiles: dict[str, AuthorProfile] = {}
        self._profile_by_account: dict[str, str] = {}
        self._pen_names: set[str] = set()

    def create_profile(self, profile: AuthorProfile) -> None:
        with self._guard:
            if (
                profile.account_id in self._profile_by_account
                or profile.normalized_pen_name in self._pen_names
            ):
                raise ValueError("author uniqueness constraint violated")
            self._profiles[profile.id] = profile
            self._profile_by_account[profile.account_id] = profile.id
            self._pen_names.add(profile.normalized_pen_name)

    def profile(self, profile_id: str) -> AuthorProfile | None:
        with self._guard:
            return self._profiles.get(profile_id)

    def profile_for_account(self, account_id: str) -> AuthorProfile | None:
        with self._guard:
            profile_id = self._profile_by_account.get(account_id)
            return self._profiles.get(profile_id) if profile_id else None

    def has_account_profile(self, account_id: str) -> bool:
        with self._guard:
            return account_id in self._profile_by_account

    def has_pen_name(self, normalized_pen_name: str) -> bool:
        with self._guard:
            return normalized_pen_name in self._pen_names

    def change_pen_name(self, profile_id: str, pen_name: str, normalized_pen_name: str) -> None:
        with self._guard:
            profile = self._profiles[profile_id]
            self._pen_names.add(normalized_pen_name)
            profile.pen_name = pen_name.strip()
            profile.normalized_pen_name = normalized_pen_name
            profile.pen_name_history.append(profile.pen_name)

    def pen_name_history(self, profile_id: str) -> list[str]:
        with self._guard:
            return list(self._profiles[profile_id].pen_name_history)


author_profiles = sa.table(
    "author_profiles",
    sa.column("id", sa.String),
    sa.column("account_id", sa.String),
    sa.column("pen_name", sa.String),
    sa.column("normalized_pen_name", sa.String),
)
author_pen_name_registry = sa.table(
    "author_pen_name_registry",
    sa.column("normalized_pen_name", sa.String),
    sa.column("author_profile_id", sa.String),
)
pen_name_history = sa.table(
    "pen_name_history",
    sa.column("id", sa.String),
    sa.column("author_profile_id", sa.String),
    sa.column("pen_name", sa.String),
    sa.column("normalized_pen_name", sa.String),
    sa.column("created_at", sa.DateTime),
)


class SqlAuthorRepository:
    """SQL adapter for the author profile and pen-name facts."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_profile(self, profile: AuthorProfile) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    author_profiles.insert().values(
                        id=profile.id,
                        account_id=profile.account_id,
                        pen_name=profile.pen_name,
                        normalized_pen_name=profile.normalized_pen_name,
                    )
                )
                connection.execute(
                    author_pen_name_registry.insert().values(
                        normalized_pen_name=profile.normalized_pen_name,
                        author_profile_id=profile.id,
                    )
                )
                connection.execute(
                    pen_name_history.insert().values(
                        id=uuid4().hex,
                        author_profile_id=profile.id,
                        pen_name=profile.pen_name,
                        normalized_pen_name=profile.normalized_pen_name,
                        created_at=datetime.now(UTC),
                    )
                )
        except IntegrityError as exc:
            raise ValueError("author uniqueness constraint violated") from exc

    def profile(self, profile_id: str) -> AuthorProfile | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(
                        author_profiles.c.id,
                        author_profiles.c.account_id,
                        author_profiles.c.pen_name,
                        author_profiles.c.normalized_pen_name,
                    ).where(author_profiles.c.id == profile_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            history = connection.execute(
                sa.select(pen_name_history.c.pen_name)
                .where(pen_name_history.c.author_profile_id == profile_id)
                .order_by(pen_name_history.c.created_at, pen_name_history.c.id)
            )
            return AuthorProfile(
                id=str(row["id"]),
                account_id=str(row["account_id"]),
                pen_name=str(row["pen_name"]),
                normalized_pen_name=str(row["normalized_pen_name"]),
                pen_name_history=[str(history_row[0]) for history_row in history],
            )

    def profile_for_account(self, account_id: str) -> AuthorProfile | None:
        with self.engine.begin() as connection:
            profile_id = connection.execute(
                sa.select(author_profiles.c.id)
                .where(author_profiles.c.account_id == account_id)
                .limit(1)
            ).scalar_one_or_none()
        return self.profile(str(profile_id)) if profile_id is not None else None

    def has_account_profile(self, account_id: str) -> bool:
        with self.engine.begin() as connection:
            return (
                connection.execute(
                    sa.select(sa.literal(True))
                    .select_from(author_profiles)
                    .where(author_profiles.c.account_id == account_id)
                    .limit(1)
                ).scalar_one_or_none()
                is not None
            )

    def has_pen_name(self, normalized_pen_name: str) -> bool:
        with self.engine.begin() as connection:
            return (
                connection.execute(
                    sa.select(sa.literal(True))
                    .select_from(author_pen_name_registry)
                    .where(author_pen_name_registry.c.normalized_pen_name == normalized_pen_name)
                    .limit(1)
                ).scalar_one_or_none()
                is not None
            )

    def change_pen_name(self, profile_id: str, pen_name: str, normalized_pen_name: str) -> None:
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    author_profiles.update()
                    .where(author_profiles.c.id == profile_id)
                    .values(pen_name=pen_name.strip(), normalized_pen_name=normalized_pen_name)
                )
                if result.rowcount != 1:
                    raise KeyError(profile_id)
                connection.execute(
                    author_pen_name_registry.insert().values(
                        normalized_pen_name=normalized_pen_name,
                        author_profile_id=profile_id,
                    )
                )
                connection.execute(
                    pen_name_history.insert().values(
                        id=uuid4().hex,
                        author_profile_id=profile_id,
                        pen_name=pen_name.strip(),
                        normalized_pen_name=normalized_pen_name,
                        created_at=datetime.now(UTC),
                    )
                )
        except IntegrityError as exc:
            raise ValueError("pen name has already been used") from exc

    def pen_name_history(self, profile_id: str) -> list[str]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(pen_name_history.c.pen_name)
                .where(pen_name_history.c.author_profile_id == profile_id)
                .order_by(pen_name_history.c.created_at, pen_name_history.c.id)
            ).all()
            if (
                not rows
                and connection.execute(
                    sa.select(author_profiles.c.id).where(author_profiles.c.id == profile_id)
                ).scalar_one_or_none()
                is None
            ):
                raise KeyError(profile_id)
            return [str(row[0]) for row in rows]

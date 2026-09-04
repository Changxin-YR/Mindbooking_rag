from threading import RLock
from typing import Protocol

from novel_platform.modules.author.domain import AuthorProfile


class AuthorRepository(Protocol):
    def create_profile(self, profile: AuthorProfile) -> None: ...

    def profile(self, profile_id: str) -> AuthorProfile | None: ...

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

import re
from dataclasses import replace

from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.reading.domain import (
    AccessDecision,
    AccessResult,
    ProgressConflict,
    ReadingProgress,
    TtsMetadata,
    TtsSegment,
)


class ContentAccessService:
    def check(
        self,
        *,
        book_available: bool,
        chapter_available: bool,
        restricted: bool,
        policy: CommercialPolicy,
        purchased: bool,
        limited_free: bool,
        member_free: bool,
    ) -> AccessDecision:
        if not book_available or not chapter_available:
            return AccessDecision(AccessResult.UNAVAILABLE, False)
        if restricted:
            return AccessDecision(AccessResult.RESTRICTED, False)
        if policy is CommercialPolicy.FREE:
            return AccessDecision(AccessResult.FREE, True)
        if purchased:
            return AccessDecision(AccessResult.PURCHASED, True)
        if limited_free:
            return AccessDecision(AccessResult.LIMITED_FREE, True)
        if member_free:
            return AccessDecision(AccessResult.MEMBER_FREE, True)
        return AccessDecision(AccessResult.VIP_REQUIRED, False)

    check_chapter_access = check


class ReadingService:
    def __init__(self) -> None:
        self._progress: dict[tuple[str, str], ReadingProgress] = {}

    @staticmethod
    def build_tts_metadata(
        *,
        book_id: str,
        chapter_id: str,
        content: str,
        access: AccessResult,
        voice: str,
        speed: float,
    ) -> TtsMetadata:
        if not content.strip():
            segments: tuple[TtsSegment, ...] = ()
        else:
            parts = tuple(
                part.strip() for part in re.split(r"(?<=[。！？!?；;\n])", content) if part.strip()
            )
            segments = tuple(
                TtsSegment(index, part, index * 500, (index + 1) * 500)
                for index, part in enumerate(parts)
            )
        return TtsMetadata(
            book_id=book_id,
            chapter_id=chapter_id,
            access=access,
            voice=voice,
            speed=speed,
            provider="deterministic",
            segments=segments,
        )

    def get_progress(self, account_id: str, book_id: str) -> ReadingProgress:
        return self._progress.get((account_id, book_id), ReadingProgress(account_id, book_id))

    def start_session(self, account_id: str, book_id: str, session_id: str) -> ReadingProgress:
        progress = self.get_progress(account_id, book_id)
        progress.current_session_id = session_id
        self._progress[(account_id, book_id)] = progress
        return progress

    def update_progress(
        self,
        account_id: str,
        book_id: str,
        *,
        chapter_id: str,
        chapter_number: int,
        position: int,
        expected_revision: int,
        session_id: str,
    ) -> ReadingProgress:
        key = (account_id, book_id)
        progress = self._progress.get(key, ReadingProgress(account_id, book_id))
        if progress.revision != expected_revision:
            raise ProgressConflict(replace(progress))
        if chapter_number < 1 or position < 0:
            raise ValueError("reading position is invalid")
        if progress.current_session_id is None:
            progress.current_session_id = session_id
        is_current_session = progress.current_session_id == session_id
        changed = False
        if is_current_session and (
            progress.last_chapter_id != chapter_id
            or progress.last_position != position
            or progress.last_chapter_number != chapter_number
        ):
            progress.last_chapter_id = chapter_id
            progress.last_chapter_number = chapter_number
            progress.last_position = position
            changed = True
        furthest = (progress.furthest_chapter_number, progress.furthest_position)
        incoming = (chapter_number, position)
        if incoming > furthest:
            progress.furthest_chapter_id = chapter_id
            progress.furthest_chapter_number = chapter_number
            progress.furthest_position = position
            changed = True
        if changed:
            progress.revision += 1
        self._progress[key] = progress
        return progress

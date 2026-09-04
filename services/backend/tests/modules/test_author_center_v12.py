import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from novel_platform.modules.author_center.application import AuthorCenterService


def test_writing_calendar_and_chapter_funnel_use_derived_facts() -> None:
    service = AuthorCenterService()
    service.record_daily_writing("author-1", "2026-09-04", 1200, 1000)
    service.record_daily_writing("author-1", "2026-09-03", 800, 1000)

    calendar = service.calendar("author-1")
    assert [item.words for item in calendar] == [800, 1200]
    funnel = service.record_chapter_funnel("book-1", "chapter-1", 100, 7000, 4200, 1800)
    assert funnel.completion_bps == 7000
    assert funnel.next_chapter_bps == 4200


def test_author_task_progress_is_idempotent_and_campaign_enrollment_is_separate() -> None:
    service = AuthorCenterService()
    task = service.create_task("FIRST_CHAPTER", "完成首章", 1)
    first = service.progress_task("author-1", task.id, 1, "request-1")
    second = service.progress_task("author-1", task.id, 1, "request-1")
    assert first == second
    assert first.progress == 1

    campaign = service.create_campaign("秋日征文", "2026-09-01", "2026-10-01")
    assert service.enroll_campaign("author-1", campaign.id) is True
    assert service.enroll_campaign("author-1", campaign.id) is False


def test_learning_content_and_appeal_keep_author_boundaries() -> None:
    service = AuthorCenterService()
    content = service.publish_learning("开篇", "如何写好第一章")
    assert service.read_learning(content.id).title == "如何写好第一章"
    service.mark_learning_progress("author-1", content.id, 80)
    assert service.learning_progress("author-1", content.id) == 80

    appeal = service.open_appeal("author-1", "CHAPTER", "chapter-1", "请求复核")
    assert appeal.status == "OPEN"

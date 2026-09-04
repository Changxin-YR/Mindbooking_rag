from uuid import uuid4

from novel_platform.modules.community.domain import ReportCase, ReportSubmission


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class CommunityService:
    def __init__(self) -> None:
        self._cases: dict[tuple[str, str], ReportCase] = {}
        self._by_id: dict[str, ReportCase] = {}

    def submit_report(
        self, content_type: str, content_id: str, reporter_id: str, reason: str
    ) -> ReportCase:
        if not content_type or not content_id or not reporter_id or not reason:
            raise ValueError("report fields are required")
        key = (content_type, content_id)
        case = self._cases.get(key)
        if case is None:
            case = ReportCase(id=_id("CASE"), content_type=content_type, content_id=content_id)
            self._cases[key] = case
            self._by_id[case.id] = case
        if any(item.reporter_id == reporter_id for item in case.submissions):
            raise ValueError("reporter already submitted for content")
        case.submissions.append(
            ReportSubmission(id=_id("RPT"), case_id=case.id, reporter_id=reporter_id, reason=reason)
        )
        return case

    def get_case(self, case_id: str) -> ReportCase:
        try:
            return self._by_id[case_id]
        except KeyError as exc:
            raise KeyError(f"report case {case_id} not found") from exc

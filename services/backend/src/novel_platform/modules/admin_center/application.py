from uuid import uuid4

from novel_platform.modules.admin_center.domain import (
    AuthorAlert,
    CsatRecord,
    ReviewerQuality,
    ReviewRule,
    User360View,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AdminCenterService:
    def __init__(self) -> None:
        self._rules: dict[str, ReviewRule] = {}
        self._quality: dict[str, ReviewerQuality] = {}
        self._alerts: dict[str, AuthorAlert] = {}
        self._csat: dict[str, CsatRecord] = {}

    def add_review_rule(
        self,
        code: str,
        severity: str,
        recommended_action: str,
        auto_block_policy: bool,
        subject_types: tuple[str, ...],
        version: str,
    ) -> ReviewRule:
        if (
            not code.strip()
            or not severity.strip()
            or not recommended_action.strip()
            or not version.strip()
            or not subject_types
        ):
            raise ValueError("REVIEW_RULE_INVALID")
        rule = ReviewRule(
            code, severity, recommended_action, auto_block_policy, subject_types, version
        )
        self._rules[f"{code}:{version}"] = rule
        return rule

    def list_review_rules(self) -> tuple[ReviewRule, ...]:
        return tuple(self._rules.values())

    def record_reviewer_quality(
        self,
        reviewer_id: str,
        accuracy_bps: int,
        false_positive_bps: int,
        miss_bps: int,
        overturn_bps: int,
        avg_handle_seconds: int,
        complaint_bps: int,
    ) -> ReviewerQuality:
        rates = (accuracy_bps, false_positive_bps, miss_bps, overturn_bps, complaint_bps)
        if any(rate < 0 or rate > 10_000 for rate in rates) or avg_handle_seconds < 0:
            raise ValueError("REVIEWER_QUALITY_INVALID")
        quality = ReviewerQuality(
            reviewer_id,
            accuracy_bps,
            false_positive_bps,
            miss_bps,
            overturn_bps,
            avg_handle_seconds,
            complaint_bps,
        )
        self._quality[reviewer_id] = quality
        return quality

    def create_author_alert(
        self, author_id: str, alert_type: str, summary: str, risk_level: str
    ) -> AuthorAlert:
        if not author_id.strip() or not alert_type.strip() or not summary.strip():
            raise ValueError("AUTHOR_ALERT_INVALID")
        alert = AuthorAlert(_id("ALERT"), author_id, alert_type, summary.strip(), risk_level)
        self._alerts[alert.id] = alert
        return alert

    def user360(
        self,
        account_id: str,
        phone: str,
        real_name: str,
        asset_cents: int,
        membership_level: int,
        growth_level: int,
        sensitive: bool = False,
    ) -> User360View:
        if len(phone) < 7:
            raise ValueError("USER360_PHONE_INVALID")
        masked_phone = f"{phone[:3]}****{phone[-4:]}"
        return User360View(
            account_id,
            phone if sensitive else masked_phone,
            "已实名" if real_name else "未实名",
            asset_cents if sensitive else None,
            membership_level,
            growth_level,
        )

    def record_csat(self, ticket_id: str, score: int) -> CsatRecord:
        if not 1 <= score <= 5:
            raise ValueError("CSAT_SCORE_INVALID")
        record = CsatRecord(ticket_id, score)
        self._csat[ticket_id] = record
        return record

    def support_dashboard(self) -> dict[str, int]:
        return {
            "csat_count": len(self._csat),
            "open_alert_count": sum(item.status == "OPEN" for item in self._alerts.values()),
        }

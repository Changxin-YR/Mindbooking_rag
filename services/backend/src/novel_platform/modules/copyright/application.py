from uuid import uuid4

from novel_platform.modules.copyright.domain import CopyrightComplaint, CopyrightDossier, RightItem


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class CopyrightService:
    def __init__(self) -> None:
        self.dossiers: dict[str, CopyrightDossier] = {}
        self.rights: dict[str, RightItem] = {}
        self.complaints: dict[str, CopyrightComplaint] = {}

    def create_dossier(self, book_id: str) -> CopyrightDossier:
        dossier = CopyrightDossier(_id("DOS"), book_id)
        self.dossiers[dossier.id] = dossier
        return dossier

    def add_right(
        self,
        dossier_id: str,
        region: str,
        language: str,
        media: str,
        exclusive: bool,
        start_year: int,
        end_year: int,
    ) -> RightItem:
        dossier = self.dossiers[dossier_id]
        if end_year <= start_year:
            raise ValueError("INVALID_RIGHT_RANGE")
        item = RightItem(
            _id("RIGHT"), dossier_id, region, language, media, exclusive, start_year, end_year
        )
        for right in self.rights.values():
            if (
                right.region == item.region
                and right.language == item.language
                and right.media == item.media
                and right.exclusive
                and item.exclusive
                and right.start_year < item.end_year
                and item.start_year < right.end_year
            ):
                raise ValueError("RIGHT_CONFLICT_MANUAL_LEGAL_REVIEW")
        self.rights[item.id] = item
        dossier.right_ids.append(item.id)
        return item

    def complain(self, book_id: str, claimant_id: str, reason: str) -> CopyrightComplaint:
        complaint = CopyrightComplaint(_id("CMP"), book_id, claimant_id, reason)
        self.complaints[complaint.id] = complaint
        return complaint

    def attach_evidence(self, complaint_id: str, evidence_id: str) -> CopyrightComplaint:
        complaint = self.complaints[complaint_id]
        complaint.evidence_ids.append(evidence_id)
        complaint.status = "EVIDENCE_REVIEW"
        return complaint

    def counter_notice(self, complaint_id: str, notice: str) -> CopyrightComplaint:
        complaint = self.complaints[complaint_id]
        complaint.counter_notice = notice
        complaint.status = "COUNTER_NOTICE"
        return complaint

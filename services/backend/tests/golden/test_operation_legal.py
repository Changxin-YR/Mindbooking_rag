import pytest

from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.operation.domain import RankingKind, RetentionAction, RetentionPolicy


def test_operation_keeps_editorial_order_separate_from_algorithm_score() -> None:
    service = OperationService()
    algorithm = service.publish_ranking(["b1", "b2"], RankingKind.ALGORITHM, [1, 9], "snap-1")
    editorial = service.editorial_slot("b1", 1, "snap-2")
    assert [item.book_id for item in algorithm] == ["b2", "b1"]
    assert editorial.kind is RankingKind.EDITORIAL
    assert editorial.score == 1


def test_right_conflict_and_legal_hold_block_retention_delete() -> None:
    copyright_service = CopyrightService()
    dossier = copyright_service.create_dossier("book-1")
    values = {
        "region": "CN",
        "language": "zh",
        "media": "AUDIO",
        "exclusive": True,
        "start_year": 2026,
        "end_year": 2028,
    }
    copyright_service.add_right(dossier.id, **values)
    with pytest.raises(ValueError, match="RIGHT_CONFLICT"):
        copyright_service.add_right(dossier.id, **values)
    legal = LegalService()
    case = legal.open_case("book-1")
    legal.hold(case.id, "book-1")
    service = OperationService()
    service.set_retention_policy(RetentionPolicy("book", RetentionAction.DELETE, 30))
    service.mark_legal_hold("book-1")
    assert service.retention_action("book-1", "book") is RetentionAction.KEEP

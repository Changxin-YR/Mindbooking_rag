from typing import Never

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from novel_platform.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from novel_platform.core.middleware import RequestContextMiddleware
from novel_platform.core.settings import Settings
from novel_platform.interfaces.http.health import build_health_router
from novel_platform.modules.admin_center.api import build_admin_center_router
from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.approval.api import build_approval_router
from novel_platform.modules.approval.application import ApprovalService
from novel_platform.modules.author.application import AuthorApplication
from novel_platform.modules.author.http import build_author_router
from novel_platform.modules.author.repository import InMemoryAuthorRepository
from novel_platform.modules.author_center.api import build_author_center_router
from novel_platform.modules.author_center.application import AuthorCenterService
from novel_platform.modules.author_finance.api import build_author_finance_router
from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.commerce.api import build_refund_router
from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.commerce.refund import RefundService
from novel_platform.modules.community.api import build_community_router
from novel_platform.modules.community.application import CommunityService
from novel_platform.modules.content.api import build_content_routers
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.copyright.api import build_copyright_router
from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.governance.api import build_governance_router
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.iam.application import IdentityApplication
from novel_platform.modules.iam.http import build_iam_router
from novel_platform.modules.iam.repository import InMemoryIdentityRepository
from novel_platform.modules.legal.api import build_legal_router
from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.library.api import build_library_router
from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.notification.api import build_notification_router
from novel_platform.modules.notification.application import NotificationService
from novel_platform.modules.operation.api import build_operation_router
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.http import build_platform_router
from novel_platform.modules.platform.repository import InMemoryPlatformRepository
from novel_platform.modules.reader_experience.api import build_reader_experience_router
from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reading.api import build_reading_router
from novel_platform.modules.reading.application import ReadingService
from novel_platform.modules.review.api import build_review_routers
from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.risk.api import build_risk_router
from novel_platform.modules.risk.application import RiskService
from novel_platform.modules.support.api import build_support_router
from novel_platform.modules.support.application import SupportService
from novel_platform.modules.wallet.api import build_reader_router as build_wallet_router
from novel_platform.modules.wallet.application import WalletService


def _refund_source_unavailable(_payment_no: str, _recharge_no: str) -> Never:
    raise ValueError("REFUND_SOURCE_NOT_FOUND")


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(build_health_router("root"))
    app.include_router(build_health_router("reader"), prefix="/api/v1")
    app.include_router(build_health_router("writer"), prefix="/writer/api/v1")
    app.include_router(build_health_router("admin"), prefix="/admin/api/v1")

    identity = IdentityApplication(InMemoryIdentityRepository())
    author = AuthorApplication(InMemoryAuthorRepository())
    platform = PlatformApplication(InMemoryPlatformRepository())
    content = ContentService()
    review = ReviewService(content)
    reading = ReadingService()
    library = LibraryService()
    commerce = CommerceService(WalletService())
    refunds = RefundService(_refund_source_unavailable, lambda _snapshot: None)
    community = CommunityService()
    notifications = NotificationService()
    support = SupportService()
    risk = RiskService()
    approvals = ApprovalService()
    author_finance = AuthorFinanceService()
    operation = OperationService()
    author_center = AuthorCenterService(operation)
    admin_center = AdminCenterService()
    copyright_service = CopyrightService()
    legal = LegalService()
    reader_experience = ReaderExperienceService()
    governance = GovernanceService()

    app.include_router(build_iam_router(identity), prefix="/api/v1")
    app.include_router(build_author_router(author), prefix="/writer/api/v1")
    app.include_router(build_platform_router(platform), prefix="/admin/api/v1")
    for router in build_content_routers(content):
        app.include_router(router)
    for router in build_review_routers(review):
        app.include_router(router)
    app.include_router(build_reading_router(reading))
    app.include_router(build_library_router(library), prefix="/api/v1")
    app.include_router(build_wallet_router(commerce), prefix="/api/v1")
    app.include_router(build_refund_router(refunds), prefix="/api/v1")
    app.include_router(build_community_router(community))
    app.include_router(build_notification_router(notifications))
    app.include_router(build_support_router(support))
    app.include_router(build_risk_router(risk))
    app.include_router(build_approval_router(approvals))
    for router in build_author_finance_router(author_finance):
        app.include_router(router)
    for router in build_author_center_router(author_center):
        app.include_router(router)
    app.include_router(build_admin_center_router(admin_center))
    app.include_router(build_operation_router(operation))
    app.include_router(build_copyright_router(copyright_service))
    app.include_router(build_legal_router(legal))
    app.include_router(build_reader_experience_router(content, reader_experience))
    app.include_router(build_governance_router(governance))
    return app


app = create_app()

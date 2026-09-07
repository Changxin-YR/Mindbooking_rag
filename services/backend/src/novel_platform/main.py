import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from novel_platform.core.auth import SessionSigner
from novel_platform.core.database import get_engine
from novel_platform.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from novel_platform.core.middleware import PrivateApiMiddleware, RequestContextMiddleware
from novel_platform.core.settings import Settings
from novel_platform.interfaces.http.health import build_health_router
from novel_platform.modules.admin_center.api import build_admin_center_router
from novel_platform.modules.admin_center.application import AdminCenterService
from novel_platform.modules.admin_center.sql_service import SqlAdminCenterService
from novel_platform.modules.agent import (
    AgentGateway,
    InMemoryAgentAuditLog,
    SqlPendingActionStore,
    ToolResource,
    build_agent_action_router,
    build_agent_admin_router,
    build_agent_gateway_router,
    build_agent_runtime_router,
)
from novel_platform.modules.agent.runtime import HarnessSessionManager
from novel_platform.modules.agent.sql_audit import SqlAgentAuditSink
from novel_platform.modules.approval.api import build_approval_router
from novel_platform.modules.approval.application import ApprovalService
from novel_platform.modules.approval.sql_service import SqlApprovalService
from novel_platform.modules.author.application import AuthorApplication
from novel_platform.modules.author.http import build_author_router
from novel_platform.modules.author.repository import InMemoryAuthorRepository, SqlAuthorRepository
from novel_platform.modules.author_center.api import build_author_center_router
from novel_platform.modules.author_center.application import AuthorCenterService
from novel_platform.modules.author_center.sql_service import SqlAuthorCenterService
from novel_platform.modules.author_finance.api import (
    build_author_finance_router,
    build_payout_callback_router,
)
from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.sql_service import SqlAuthorFinanceService
from novel_platform.modules.commerce.api import build_refund_router
from novel_platform.modules.commerce.application import CommerceService
from novel_platform.modules.commerce.refund import RefundService
from novel_platform.modules.commerce.sql_refund import SqlRefundService
from novel_platform.modules.commerce.sql_service import SqlCommerceService
from novel_platform.modules.community.api import build_community_router
from novel_platform.modules.community.application import CommunityService
from novel_platform.modules.community.sql_service import SqlCommunityService
from novel_platform.modules.content.api import build_content_routers
from novel_platform.modules.content.application import ContentService
from novel_platform.modules.content.domain import CommercialPolicy
from novel_platform.modules.content.sql_service import SqlContentService
from novel_platform.modules.copyright.api import build_copyright_router
from novel_platform.modules.copyright.application import CopyrightService
from novel_platform.modules.copyright.sql_service import SqlCopyrightService
from novel_platform.modules.governance.api import build_governance_router
from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import OutboxEvent
from novel_platform.modules.governance.sql_service import SqlGovernanceService
from novel_platform.modules.governance.worker import OutboxWorker, SearchProjectionHandler
from novel_platform.modules.iam.application import IdentityApplication
from novel_platform.modules.iam.http import build_iam_router
from novel_platform.modules.iam.repository import InMemoryIdentityRepository, SqlIdentityRepository
from novel_platform.modules.integrations.provider import build_sandbox_provider_registry
from novel_platform.modules.legal.api import build_legal_router
from novel_platform.modules.legal.application import LegalService
from novel_platform.modules.legal.sql_service import SqlLegalService
from novel_platform.modules.library.api import build_library_router
from novel_platform.modules.library.application import LibraryService
from novel_platform.modules.library.sql_service import SqlLibraryService
from novel_platform.modules.membership.api import build_membership_router
from novel_platform.modules.membership.domain import ChapterPolicy, MembershipService
from novel_platform.modules.membership.sql_service import SqlMembershipService
from novel_platform.modules.notification.api import build_notification_router
from novel_platform.modules.notification.application import NotificationService
from novel_platform.modules.notification.sql_service import SqlNotificationService
from novel_platform.modules.operation.api import (
    build_operation_router,
    build_reader_operation_router,
)
from novel_platform.modules.operation.application import OperationService
from novel_platform.modules.operation.sql_service import SqlOperationService
from novel_platform.modules.payment import build_payment_provider, build_payout_provider
from novel_platform.modules.platform.application import PlatformApplication
from novel_platform.modules.platform.http import build_platform_router
from novel_platform.modules.platform.repository import (
    InMemoryPlatformRepository,
    SqlPlatformRepository,
)
from novel_platform.modules.platform.staff_auth import (
    StaffAuthService,
    build_staff_auth_router,
)
from novel_platform.modules.reader_experience.api import build_reader_experience_router
from novel_platform.modules.reader_experience.application import ReaderExperienceService
from novel_platform.modules.reader_experience.sql_service import SqlReaderExperienceService
from novel_platform.modules.reading.api import build_reading_router
from novel_platform.modules.reading.application import ReadingService
from novel_platform.modules.reading.sql_service import SqlReadingService
from novel_platform.modules.review.api import build_review_routers
from novel_platform.modules.review.application import ReviewService
from novel_platform.modules.review.domain import ReviewDecision
from novel_platform.modules.review.sql_service import SqlReviewService
from novel_platform.modules.risk.api import build_risk_router
from novel_platform.modules.risk.application import RiskService
from novel_platform.modules.risk.sql_service import SqlRiskService
from novel_platform.modules.search import (
    BookSearchFact,
    InMemorySearchProjectionStore,
    OpenSearchSearchAdapter,
    RefreshingSearchAdapter,
    SearchService,
)
from novel_platform.modules.search.api import build_search_router
from novel_platform.modules.support.api import build_support_router
from novel_platform.modules.support.application import SupportService
from novel_platform.modules.support.sql_service import SqlSupportService
from novel_platform.modules.wallet.api import build_reader_router as build_wallet_router
from novel_platform.modules.wallet.application import WalletService
from novel_platform.modules.wallet.domain import WalletPort
from novel_platform.modules.wallet.sql_service import SqlWalletService

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    settings.validate_runtime()
    settings.validate_integration_runtime()
    if settings.app_env in {"production", "prod"} and (
        settings.payment_provider != "SANDBOX" or settings.payout_provider != "SANDBOX_PAYOUT"
    ):
        raise ValueError("PRODUCTION_PROVIDER_ADAPTER_NOT_IMPLEMENTED")
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    integration_registry = build_sandbox_provider_registry(
        sms_provider=settings.sms_provider,
        oauth_wechat_provider=settings.oauth_wechat_provider,
        oauth_qq_provider=settings.oauth_qq_provider,
        realname_provider=settings.realname_provider,
        moderation_provider=settings.moderation_provider,
        storage_provider=settings.storage_provider,
        notification_provider=settings.notification_provider,
    )
    app.state.integration_registry = integration_registry
    app.state.sandbox_provider_registry = integration_registry
    app.state.sandbox_integrations = integration_registry
    app.state.integration_health = {
        **integration_registry.health(),
        "status": "ok",
        "sandbox": True,
    }
    app.state.sandbox_provider_health = app.state.integration_health
    app.state.integration_provider_health = app.state.integration_health
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(PrivateApiMiddleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(build_health_router("root"))
    app.include_router(build_health_router("reader"), prefix="/api/v1")
    app.include_router(build_health_router("writer"), prefix="/writer/api/v1")
    app.include_router(build_health_router("admin"), prefix="/admin/api/v1")

    engine = get_engine(settings.database_url) if settings.persistence_mode == "sql" else None
    identity = IdentityApplication(
        SqlIdentityRepository(
            engine,
            settings.real_name_encryption_key or settings.session_secret,
        )
        if engine is not None
        else InMemoryIdentityRepository(),
        SessionSigner(
            settings.session_secret or "development-only-session-secret",
            settings.session_ttl_seconds,
        ),
    )
    app.state.session_signer = identity.signer
    author = AuthorApplication(
        SqlAuthorRepository(engine) if engine is not None else InMemoryAuthorRepository()
    )
    app.state.author_service = author
    platform = PlatformApplication(
        SqlPlatformRepository(engine) if engine is not None else InMemoryPlatformRepository()
    )
    app.state.platform = platform
    staff_auth = StaffAuthService(
        platform,
        identity.signer,
        engine=engine,
        mfa_encryption_key=settings.real_name_encryption_key or settings.session_secret,
    )
    app.state.staff_auth = staff_auth
    if settings.staff_bootstrap_employee_code and settings.staff_bootstrap_password:
        bootstrap = platform.repository.staff_for_employee_code(
            settings.staff_bootstrap_employee_code
        )
        if bootstrap is None:
            bootstrap_id = platform.create_staff(
                settings.staff_bootstrap_employee_code, "platform"
            ).id
        else:
            bootstrap_id = bootstrap.id
        staff_auth.set_password(bootstrap_id, settings.staff_bootstrap_password)
        for permission in (
            "admin.access",
            "review.read",
            "review.decide",
            "approval.write",
            "finance.read",
            "finance.write",
            "commerce.write",
            "risk.read",
            "risk.write",
            "operation.read",
            "operation.write",
            "legal.write",
            "support.read",
            "support.write",
            "platform.manage",
            "governance.read",
            "governance.write",
            "agent.audit.read",
            "agent.audit.sensitive",
            "agent.execute",
            "content.read",
        ):
            platform.grant_permission(bootstrap_id, permission)
        platform.grant_data_scope(bootstrap_id, "ALL", "*")
    content = SqlContentService(engine) if engine is not None else ContentService()
    app.state.content_service = content

    def search_facts() -> tuple[BookSearchFact, ...]:
        return tuple(
            BookSearchFact(
                book_id=book.id,
                title=metadata.title,
                synopsis=metadata.synopsis,
                category=metadata.category,
                channel=metadata.channel,
                status=book.lifecycle.value,
                tags=metadata.tags,
            )
            for book, metadata in content.list_public_books()
        )

    fallback_search = RefreshingSearchAdapter(search_facts)
    search_projection = InMemorySearchProjectionStore(search_facts())
    app.state.search_projection = search_projection
    search = SearchService(
        OpenSearchSearchAdapter(search_facts, settings.opensearch_url)
        if settings.opensearch_url
        else fallback_search,
        fallback=fallback_search if settings.opensearch_url else None,
    )
    agent_audit_sink = SqlAgentAuditSink(engine) if engine is not None else InMemoryAgentAuditLog()
    app.state.agent_audit_sink = agent_audit_sink
    pending_store = (
        SqlPendingActionStore(engine) if engine is not None and hasattr(engine, "connect") else None
    )
    agent_gateway = AgentGateway(
        platform,
        audit_sink=agent_audit_sink,
        pending_store=pending_store,
    )

    def agent_book_in_scope(arguments: dict[str, Any], context: Any) -> bool:
        """Resolve a book resource through the Staff DataScope, never by prompt claims."""
        book_id = arguments.get("book_id")
        if not isinstance(book_id, str) or not book_id.strip() or context is None:
            return False
        if platform.can_access(context.actor_id, "content.read", "BOOK", book_id):
            return True
        if any(
            scope_type.upper() == "CUSTOM" and scope_value in {book_id, f"BOOK:{book_id}"}
            for scope_type, scope_value in context.data_scopes
        ):
            return True
        review_service = getattr(app.state, "review_service", None)
        if review_service is None:
            return False
        return any(
            submission.book_id == book_id
            for scope_type, scope_value in context.data_scopes
            for submission in review_service.list_submissions_for_scope(scope_type, scope_value)
        )

    agent_gateway.register(
        ToolResource(
            name="content.get_book",
            description="Read public book metadata through ContentService",
            permission="content.read",
            input_schema={
                "type": "object",
                "properties": {"book_id": {"type": "string", "minLength": 1}},
                "required": ["book_id"],
                "additionalProperties": False,
            },
            scope_resolver=agent_book_in_scope,
        ),
        lambda arguments: asdict(
            content.get_book_metadata(str(arguments["book_id"]), public_only=True)
        ),
    )
    app.state.agent_gateway = agent_gateway
    app.state.agent_runner = HarnessSessionManager(
        backend_url=settings.agent_backend_url,
        dsh_home=settings.agent_dsh_home,
        project_root=str(Path(__file__).resolve().parents[4]),
        provider=settings.agent_harness_provider,
        model=settings.agent_harness_model,
        api_key=settings.agent_harness_api_key or None,
        base_url=settings.agent_harness_base_url or None,
        profile=settings.agent_harness_profile,
        request_timeout_seconds=settings.agent_harness_timeout_seconds,
        runtime_mode=settings.agent_harness_runtime_mode,
        web_command=settings.agent_harness_web_command or None,
        dsh_bin=settings.agent_harness_dsh_bin or None,
        harness_repo=settings.agent_harness_repo or None,
        web_start_timeout_seconds=settings.agent_harness_web_start_timeout_seconds,
        web_bridge_url=settings.agent_harness_web_bridge_url,
        web_bridge_secret=settings.agent_harness_web_bridge_secret,
    )
    review = SqlReviewService(engine, content) if engine is not None else ReviewService(content)
    app.state.review_service = review
    reading = SqlReadingService(engine) if engine is not None else ReadingService()
    app.state.reading_service = reading
    library = SqlLibraryService(engine) if engine is not None else LibraryService()
    app.state.library_service = library
    membership = (
        SqlMembershipService(engine, identity.is_real_named)
        if engine is not None
        else MembershipService()
    )
    app.state.membership_service = membership
    if settings.persistence_mode == "sql" and engine is not None:
        wallet: WalletPort = SqlWalletService(engine)
    else:
        wallet = WalletService()
    app.state.wallet_service = wallet

    def spend_gift_in_transaction(
        connection: Any, account_id: str, amount: int, spend_mode: str
    ) -> None:
        spend = getattr(wallet, "spend_in_transaction", None)
        if not callable(spend):
            raise TypeError("GIFT_TRANSACTION_CONFIGURATION_ERROR")
        spend(connection, account_id, amount, reason="GIFT", spend_mode=spend_mode)

    gift_asset_spend: Callable[[Any, str, int, str], None] | None = (
        spend_gift_in_transaction if engine is not None else None
    )
    commerce = (
        SqlCommerceService(engine, wallet, identity.is_real_named)
        if engine is not None
        else CommerceService(wallet, identity.is_real_named)
    )
    payment_provider = build_payment_provider(
        settings.payment_provider, settings.payment_callback_secret
    )
    commerce.payment_provider = payment_provider
    commerce.payment_provider_secret = settings.payment_callback_secret
    if isinstance(membership, SqlMembershipService):
        membership.payment_provider = payment_provider
        membership.payment_provider_secret = settings.payment_callback_secret
    app.state.commerce_service = commerce
    refunds: RefundService
    if engine is not None:
        recover_assets_in_connection = None
        recover_source_assets = getattr(wallet, "recover_source_assets_in_transaction", None)
        account_id_for_refund = commerce.refund_account
        if callable(recover_source_assets):
            recover_assets_in_connection = lambda connection, calculation: recover_source_assets(
                connection,
                account_id_for_refund(calculation.payment_no, calculation.recharge_no),
                calculation.recharge_no,
            )
        refunds = SqlRefundService(
            engine,
            commerce.refund_source,
            commerce.recover_refund_assets,
            commerce.refund_account,
            recover_assets_in_connection,
            getattr(commerce, "refund_source_in_transaction", None),
        )
    else:
        refunds = RefundService(
            commerce.refund_source, commerce.recover_refund_assets, commerce.refund_account
        )
    app.state.refund_service = refunds
    community = SqlCommunityService(engine) if engine is not None else CommunityService()
    app.state.community_service = community
    notifications = SqlNotificationService(engine) if engine is not None else NotificationService()
    app.state.notification_service = notifications
    support = SqlSupportService(engine) if engine is not None else SupportService()
    app.state.support_service = support
    risk = SqlRiskService(engine) if engine is not None else RiskService()
    app.state.risk_service = risk
    approvals = SqlApprovalService(engine) if engine is not None else ApprovalService()
    app.state.approval_service = approvals
    author_finance = (
        SqlAuthorFinanceService(engine) if engine is not None else AuthorFinanceService()
    )
    payout_provider = build_payout_provider(
        settings.payout_provider, settings.payment_callback_secret
    )
    author_finance.payout_provider = payout_provider
    author_finance.payout_provider_secret = settings.payment_callback_secret
    app.state.author_finance_service = author_finance

    configure_chapter_commercial_policy: Callable[[str, ChapterPolicy], object] | None = None
    if engine is not None:

        def configure_chapter_commercial_policy(chapter_id: str, policy: ChapterPolicy) -> None:
            content.set_chapter_commercial_policy(chapter_id, CommercialPolicy.VIP)
            commerce.register_chapter_policy(chapter_id, policy)

        def record_chapter_revenue_from_content(
            connection: Any,
            chapter_id: str,
            purchase_no: str,
            gross_cents: int,
        ) -> object:
            sql_content = cast(SqlContentService, content)
            _, _volume, book = sql_content.get_chapter_context_for_connection(
                connection, chapter_id
            )
            sql_author_finance = cast(SqlAuthorFinanceService, author_finance)
            return sql_author_finance.record_revenue_in_transaction(
                connection,
                book.author_id,
                book.id,
                "CHAPTER_PURCHASE",
                purchase_no,
                gross_cents,
            )

        commerce.record_revenue_in_transaction = record_chapter_revenue_from_content
    operation = SqlOperationService(engine) if engine is not None else OperationService()
    app.state.operation_service = operation
    author_center = (
        SqlAuthorCenterService(engine, operation)
        if engine is not None
        else AuthorCenterService(operation)
    )
    app.state.author_center_service = author_center
    admin_center = SqlAdminCenterService(engine) if engine is not None else AdminCenterService()
    app.state.admin_center_service = admin_center
    agent_gateway.register(
        ToolResource(
            name="content.list_books",
            description="List books visible to the current staff data scope",
            permission="content.read",
            input_schema={"type": "object", "additionalProperties": False},
            scope_resolver=lambda _arguments, context: (
                context is not None
                and any(
                    platform.can_access(context.actor_id, "content.read", scope_type, scope_value)
                    for scope_type, scope_value in context.data_scopes
                )
            ),
        ),
        lambda _arguments, context: [
            {
                "id": book.id,
                "author_id": book.author_id,
                "title": metadata.title,
                "lifecycle": book.lifecycle.value,
                "visibility": book.visibility.value,
            }
            for book, metadata in content.list_all_books()
            if agent_book_in_scope({"book_id": book.id}, context)
        ],
    )
    agent_gateway.register(
        ToolResource(
            name="review.list_pending",
            description="List pending review submissions in the current staff assignment scope",
            permission="review.read",
            input_schema={"type": "object", "additionalProperties": False},
        ),
        lambda _arguments, context: [
            asdict(item)
            for scope_type, scope_value in context.data_scopes
            for item in review.list_submissions_for_scope(scope_type, scope_value)
            if item.status.value == "PENDING"
        ],
    )

    def decide_review_from_agent(arguments: dict[str, Any], context: Any) -> dict[str, object]:
        if context is None or not platform.has_permission(context.actor_id, "review.decide"):
            from novel_platform.modules.agent.application import PermissionDenied

            raise PermissionDenied("agent actor lacks review decision permission")
        if set(arguments) != {"submission_id", "decision"}:
            raise ValueError("review decision arguments must contain submission_id and decision")
        submission_id = arguments["submission_id"]
        decision_value = arguments["decision"]
        if not isinstance(submission_id, str) or not submission_id.strip():
            raise ValueError("submission_id is required")
        if not isinstance(decision_value, str):
            raise TypeError("decision must be a string")
        try:
            decision = ReviewDecision(decision_value)
        except ValueError as exc:
            raise ValueError("unsupported review decision") from exc
        if decision not in {
            ReviewDecision.APPROVE,
            ReviewDecision.REJECT,
            ReviewDecision.RETURN_FOR_CHANGES,
        }:
            raise ValueError("unsupported review decision")
        visible_ids = {
            item.id
            for scope_type, scope_value in context.data_scopes
            for item in review.list_submissions_for_scope(scope_type, scope_value)
        }
        if submission_id not in visible_ids:
            from novel_platform.modules.agent.application import PermissionDenied

            raise PermissionDenied("review submission is outside the staff data scope")
        record = review.decide(submission_id, context.actor_id, decision, actor_type="human")
        verified = review.get_submission(submission_id)
        return {
            "id": record.id,
            "submission_id": record.submission_id,
            "decision": record.decision.value,
            "status": verified.status.value,
            "execution_channel": "AGENT",
        }

    def review_submission_in_scope(arguments: dict[str, Any], context: Any) -> bool:
        submission_id = arguments.get("submission_id")
        if not isinstance(submission_id, str) or context is None:
            return False
        return any(
            item.id == submission_id
            for scope_type, scope_value in context.data_scopes
            for item in review.list_submissions_for_scope(scope_type, scope_value)
        )

    agent_gateway.register(
        ToolResource(
            name="review.decide",
            description="Record an assigned review decision through ReviewService",
            permission="review.decide",
            read_only=False,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["submission_id", "decision"],
                "properties": {
                    "submission_id": {"type": "string", "minLength": 1},
                    "decision": {
                        "type": "string",
                        "enum": ["APPROVE", "REJECT", "RETURN_FOR_CHANGES"],
                    },
                },
            },
            scope_resolver=review_submission_in_scope,
            result_validator=lambda data, _arguments, _context: (
                isinstance(data, dict)
                and data.get("submission_id") == _arguments.get("submission_id")
                and data.get("status") in {"APPROVED", "REJECTED", "RETURNED"}
            ),
        ),
        decide_review_from_agent,
    )
    agent_gateway.register(
        ToolResource(
            name="support.dashboard",
            description="Read support dashboard metrics in the current staff scope",
            permission="support.read",
            input_schema={"type": "object", "additionalProperties": False},
        ),
        lambda _arguments: admin_center.support_dashboard(),
    )
    copyright_service = SqlCopyrightService(engine) if engine is not None else CopyrightService()
    app.state.copyright_service = copyright_service
    legal = SqlLegalService(engine) if engine is not None else LegalService()
    app.state.legal_service = legal
    reader_experience = (
        SqlReaderExperienceService(engine) if engine is not None else ReaderExperienceService()
    )
    app.state.reader_experience_service = reader_experience
    governance = SqlGovernanceService(engine) if engine is not None else GovernanceService()
    app.state.governance_service = governance
    commerce.record_payment_credit_failure = governance.record_payment_credit_failure
    governance.repair_payment_credit = commerce.repair_payment_credit

    delivery_table = None
    if engine is not None and getattr(engine, "dialect", None) is not None:
        delivery_table = sa.Table("outbox_event_deliveries", sa.MetaData(), autoload_with=engine)
    delivered_events: set[tuple[str, str]] = set()

    def deliver_outbox_event(event: OutboxEvent) -> None:
        consumer = "backend-runtime"
        if delivery_table is None:
            delivered_events.add((event.id, consumer))
            return
        assert engine is not None
        try:
            with engine.begin() as connection:
                connection.execute(
                    delivery_table.insert().values(event_id=event.id, consumer=consumer)
                )
        except sa.exc.IntegrityError:
            return

    outbox_event_types = (
        "BOOK_INDEX",
        "BOOK_TAKEN_DOWN",
        "ChapterPurchased",
        "ContractCreated",
        "ContractActivated",
        "RechargeOrderCreated",
        "RechargeCredited",
        "EntitlementCreated",
        "PaymentSucceeded",
        "PaymentStatusChanged",
        "RevenueCreated",
        "SettlementCreated",
        "WithdrawalRequested",
        "PayoutOrderCreated",
        "PayoutSucceeded",
        "PayoutStatusChanged",
    )
    search_projection_handler = SearchProjectionHandler(search_projection)

    def deliver_search_event(event: OutboxEvent) -> None:
        search_projection_handler(event)
        deliver_outbox_event(event)

    outbox_worker = OutboxWorker(
        governance,
        {
            **{event_type: deliver_outbox_event for event_type in outbox_event_types},
            "BOOK_INDEX": deliver_search_event,
            "BOOK_TAKEN_DOWN": deliver_search_event,
        },
        worker_id=settings.outbox_worker_id,
    )
    app.state.outbox_worker = outbox_worker
    app.state.outbox_deliveries = delivered_events

    async def outbox_pump() -> None:
        while True:
            try:
                await asyncio.to_thread(governance.auto_repair_payment_credits, limit=50)
                await asyncio.to_thread(outbox_worker.run_once, limit=50)
            except Exception:
                logger.exception("outbox worker iteration failed")
            await asyncio.sleep(settings.outbox_poll_interval_seconds)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app.state.outbox_worker_task = asyncio.create_task(outbox_pump())
        try:
            yield
        finally:
            task = getattr(app.state, "outbox_worker_task", None)
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            app.state.agent_runner.close_all()

    app.router.lifespan_context = lifespan

    app.include_router(build_iam_router(identity, auth_required=True), prefix="/api/v1")
    app.include_router(build_author_router(author, auth_required=True), prefix="/writer/api/v1")
    app.include_router(
        build_platform_router(
            platform,
            on_staff_inactive=staff_auth.revoke_all_for_staff,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        ),
        prefix="/admin/api/v1",
    )
    app.include_router(build_staff_auth_router(staff_auth))
    app.include_router(
        build_agent_admin_router(
            agent_audit_sink,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_agent_gateway_router(
            agent_gateway,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_agent_action_router(
            agent_gateway,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_agent_runtime_router(
            agent_gateway,
            app.state.agent_runner,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    for router in build_content_routers(
        content,
        auth_required=True,
        account_for_author=author.account_id_for_profile,
        configure_commercial_policy=configure_chapter_commercial_policy,
        authorize_staff=staff_auth.authorize,
    ):
        app.include_router(router)
    for router in build_review_routers(
        review,
        auth_required=True,
        account_for_author=author.account_id_for_profile,
        staff_scopes=platform.repository.scopes_for,
        authorize_staff=staff_auth.authorize,
    ):
        app.include_router(router)
    app.include_router(build_reading_router(reading, auth_required=True, content=content))
    app.include_router(
        build_library_router(library, auth_required=True, content=content), prefix="/api/v1"
    )
    app.include_router(build_search_router(search))
    app.include_router(
        build_wallet_router(
            commerce,
            auth_required=True,
            callback_secret=settings.payment_callback_secret,
            callback_max_skew_seconds=settings.payment_callback_max_skew_seconds,
        ),
        prefix="/api/v1",
    )
    app.include_router(build_refund_router(refunds, auth_required=True), prefix="/api/v1")
    app.include_router(
        build_membership_router(
            membership,
            auth_required=True,
            callback_secret=settings.payment_callback_secret,
            callback_max_skew_seconds=settings.payment_callback_max_skew_seconds,
            asset_spend=gift_asset_spend,
        )
    )
    app.include_router(build_community_router(community, auth_required=True))
    app.include_router(build_notification_router(notifications, auth_required=True))
    app.include_router(
        build_support_router(support, auth_required=True, authorize_staff=staff_auth.authorize)
    )
    app.include_router(
        build_risk_router(risk, auth_required=True, authorize_staff=staff_auth.authorize)
    )
    app.include_router(
        build_approval_router(
            approvals,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    for router in build_author_finance_router(
        author_finance,
        auth_required=True,
        account_for_author=author.account_id_for_profile,
        author_for_book=lambda book_id: content.get_book(book_id).author_id,
        is_real_named=identity.is_real_named,
        authorize_staff=staff_auth.authorize,
    ):
        app.include_router(router)
    app.include_router(
        build_payout_callback_router(
            author_finance,
            auth_required=True,
            callback_max_skew_seconds=settings.payment_callback_max_skew_seconds,
            authorize_staff=staff_auth.authorize,
        )
    )
    for router in build_author_center_router(
        author_center,
        auth_required=True,
        account_for_author=author.account_id_for_profile,
        author_for_book=lambda book_id: content.get_book(book_id).author_id,
        chapter_for_book=content.get_chapter_for_book,
        authorize_staff=staff_auth.authorize,
    ):
        app.include_router(router)
    app.include_router(
        build_admin_center_router(
            admin_center,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_operation_router(
            operation,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(build_reader_operation_router(operation))
    app.include_router(
        build_copyright_router(
            copyright_service,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_legal_router(
            legal,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    app.include_router(
        build_reader_experience_router(content, reader_experience, auth_required=True)
    )
    app.include_router(
        build_governance_router(
            governance,
            auth_required=True,
            authorize_staff=staff_auth.authorize,
        )
    )
    return app


app = create_app()

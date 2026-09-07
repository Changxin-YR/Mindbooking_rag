"""SQLAlchemy persistence for membership, tickets, gifts, fans, and growth."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from novel_platform.modules.membership.domain import (
    AccessMode,
    BookTicketVote,
    ChapterPolicy,
    FanProfile,
    GiftDefinition,
    GiftOrder,
    MembershipOrder,
    MembershipPlan,
    TicketBalance,
    TicketRiskStatus,
    TicketType,
    UserGrowthProfile,
)
from novel_platform.modules.payment import PaymentProvider, ProviderEvent, ProviderStatus


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlMembershipService:
    """Persistent membership service; asset debits are supplied by an application port."""

    def __init__(
        self,
        engine: Engine,
        is_real_named: Callable[[str], bool] | None = None,
        payment_provider: PaymentProvider | None = None,
        payment_provider_secret: str = "",
    ) -> None:
        self.engine = engine
        self._is_real_named = is_real_named
        self.payment_provider = payment_provider
        self.payment_provider_secret = payment_provider_secret
        self._metadata = sa.MetaData()
        self._tables: dict[str, Any] = {}

    def _table(self, name: str) -> Any:
        if name not in self._tables:
            self._tables[name] = sa.Table(name, self._metadata, autoload_with=self.engine)
        return self._tables[name]

    def create_plan(
        self,
        plan_code: str,
        name: str,
        duration_days: int,
        *,
        price_cents: int,
        daily_recommend_tickets: int,
        monthly_chapter_tickets: int,
        version: int = 1,
    ) -> MembershipPlan:
        if not plan_code.strip() or not name.strip() or duration_days <= 0 or price_cents <= 0:
            raise ValueError("MEMBERSHIP_PLAN_INVALID")
        if daily_recommend_tickets < 0 or monthly_chapter_tickets < 0 or version <= 0:
            raise ValueError("MEMBERSHIP_PLAN_INVALID")
        plan = MembershipPlan(
            plan_code,
            name.strip(),
            version,
            duration_days,
            price_cents,
            daily_recommend_tickets,
            monthly_chapter_tickets,
        )
        table = self._table("membership_plan_versions")
        with self.engine.begin() as connection:
            try:
                connection.execute(
                    table.insert().values(
                        plan_code=plan.plan_code,
                        name=plan.name,
                        version=plan.version,
                        duration_days=plan.duration_days,
                        price_cents=plan.price_cents,
                        daily_recommend_ticket_count=plan.daily_recommend_tickets,
                        monthly_chapter_ticket_count=plan.monthly_chapter_tickets,
                        status=plan.status,
                        created_at=datetime.now(UTC),
                    )
                )
            except IntegrityError as exc:
                raise ValueError("MEMBERSHIP_PLAN_VERSION_EXISTS") from exc
        return plan

    def create_order(
        self, account_id: str, plan_code: str, channel: str, idempotency_key: str
    ) -> MembershipOrder:
        if (
            not account_id.strip()
            or not plan_code.strip()
            or not channel.strip()
            or not idempotency_key.strip()
        ):
            raise ValueError("MEMBERSHIP_ORDER_INVALID")
        if self._is_real_named is not None and not self._is_real_named(account_id):
            raise ValueError("REAL_NAME_REQUIRED")
        orders = self._table("membership_orders")
        payments = self._table("payment_orders")
        plans = self._table("membership_plan_versions")
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(orders).where(orders.c.idempotency_key == idempotency_key)
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    existing["account_id"] != account_id
                    or existing["plan_code"] != plan_code
                    or existing["channel"] != channel
                ):
                    raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
                return self._with_provider_checkout(self._membership_order_from_row(existing))
            plan = (
                connection.execute(
                    sa.select(plans)
                    .where(plans.c.plan_code == plan_code, plans.c.status == "ACTIVE")
                    .order_by(plans.c.version.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if plan is None:
                raise ValueError("MEMBERSHIP_PLAN_NOT_FOUND")
            payment_no = f"MPAY_{uuid4().hex}"
            payment_result = connection.execute(
                payments.insert().values(
                    payment_no=payment_no,
                    account_id=account_id,
                    channel=channel,
                    paid_cents=int(plan["price_cents"]),
                    status="PENDING",
                    created_at=datetime.now(UTC),
                )
            )
            payment_id = connection.execute(
                sa.select(payments.c.id).where(payments.c.payment_no == payment_no)
            ).scalar_one()
            del payment_result
            order = MembershipOrder(
                _id("MORD"),
                payment_no,
                account_id,
                plan_code,
                int(plan["version"]),
                channel,
                int(plan["price_cents"]),
                "PENDING_PAYMENT",
            )
            connection.execute(
                orders.insert().values(
                    id=order.id,
                    payment_order_id=payment_id,
                    payment_no=order.payment_no,
                    account_id=order.account_id,
                    plan_code=order.plan_code,
                    plan_version=order.plan_version,
                    channel=order.channel,
                    price_cents=order.price_cents,
                    status=order.status,
                    idempotency_key=idempotency_key,
                    created_at=datetime.now(UTC),
                )
            )
            return self._with_provider_checkout(order)

    def payment_details(self, payment_no: str) -> tuple[str, int]:
        payments = self._table("payment_orders")
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(payments.c.account_id, payments.c.paid_cents).where(
                        payments.c.payment_no == payment_no
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("PAYMENT_NOT_FOUND")
        return str(row["account_id"]), int(row["paid_cents"])

    def _with_provider_checkout(self, order: MembershipOrder) -> MembershipOrder:
        provider = self.payment_provider
        if provider is None:
            return order
        checkout = provider.create_checkout(order.payment_no, order.price_cents, currency="CNY")
        return MembershipOrder(
            order.id,
            order.payment_no,
            order.account_id,
            order.plan_code,
            order.plan_version,
            order.channel,
            order.price_cents,
            order.status,
            provider=checkout.provider,
            checkout_url=checkout.checkout_url,
        )

    def handle_payment_callback(self, provider: str, event_id: str, payment_no: str) -> str:
        if not provider.strip() or not event_id.strip() or not payment_no.strip():
            raise ValueError("MEMBERSHIP_PAYMENT_CALLBACK_INVALID")
        orders = self._table("membership_orders")
        payments = self._table("payment_orders")
        events = self._table("payment_channel_events")
        for table_name in (
            "membership_plan_versions",
            "membership_accounts",
            "ticket_lots",
            "ticket_transactions",
            "ticket_accounts",
        ):
            self._table(table_name)
        with self.engine.begin() as connection:
            existing_event = (
                connection.execute(
                    sa.select(events).where(
                        events.c.provider == provider, events.c.provider_event_id == event_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing_event is not None:
                if existing_event["payment_no"] != payment_no:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return str(
                    connection.execute(
                        sa.select(orders.c.id).where(orders.c.payment_no == payment_no)
                    ).scalar_one()
                )
            payment = (
                connection.execute(
                    sa.select(payments).where(payments.c.payment_no == payment_no).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if payment is None:
                raise ValueError("PAYMENT_NOT_FOUND")
            order = (
                connection.execute(
                    sa.select(orders).where(orders.c.payment_no == payment_no).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if order is None:
                raise ValueError("MEMBERSHIP_ORDER_NOT_FOUND")
            if payment["status"] == "PAID" and order["status"] == "PAID":
                self._record_payment_event(events, connection, provider, event_id, payment_no)
                return str(order["id"])
            if payment["status"] != "PENDING" or order["status"] != "PENDING_PAYMENT":
                raise ValueError("PAYMENT_STATE_CONFLICT")
            self._record_payment_event(events, connection, provider, event_id, payment_no)
            plans = self._table("membership_plan_versions")
            plan = (
                connection.execute(
                    sa.select(plans).where(
                        plans.c.plan_code == order["plan_code"],
                        plans.c.version == order["plan_version"],
                    )
                )
                .mappings()
                .one_or_none()
            )
            if plan is None:
                raise ValueError("MEMBERSHIP_PLAN_NOT_FOUND")
            self._activate_order(connection, order, plan)
            connection.execute(
                payments.update().where(payments.c.id == payment["id"]).values(status="PAID")
            )
            connection.execute(
                orders.update().where(orders.c.id == order["id"]).values(status="PAID")
            )
            return str(order["id"])

    def handle_payment_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> str:
        """Verify a sandbox/real provider event before changing membership facts."""
        provider = self.payment_provider
        secret = self.payment_provider_secret
        if provider is None or not secret:
            raise ValueError("MEMBERSHIP_PAYMENT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYMENT":
            raise ValueError("MEMBERSHIP_PAYMENT_EVENT_TYPE_INVALID")
        if event.provider != getattr(provider, "provider_name", event.provider):
            raise ValueError("MEMBERSHIP_PAYMENT_PROVIDER_MISMATCH")
        if not event.verify_signature(secret):
            raise ValueError("MEMBERSHIP_PAYMENT_SIGNATURE_INVALID")
        if _utc(event.available_at) > _utc(now or datetime.now(UTC)):
            raise ValueError("MEMBERSHIP_PAYMENT_EVENT_NOT_AVAILABLE")
        orders = self._table("membership_orders")
        payments = self._table("payment_orders")
        events = self._table("payment_channel_events")
        # Reflect every table before opening the SQLite transaction.  SQLite's
        # in-memory pool can otherwise use a second connection during lazy
        # reflection, hiding the membership row from the committing connection.
        for table_name in (
            "membership_plan_versions",
            "membership_accounts",
            "ticket_lots",
            "ticket_transactions",
            "ticket_accounts",
        ):
            self._table(table_name)
        with self.engine.begin() as connection:
            existing_event = (
                connection.execute(
                    sa.select(events).where(
                        events.c.provider == event.provider,
                        events.c.provider_event_id == event.event_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            order = (
                connection.execute(
                    sa.select(orders)
                    .where(orders.c.payment_no == event.reference_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            payment = (
                connection.execute(
                    sa.select(payments)
                    .where(payments.c.payment_no == event.reference_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if order is None or payment is None:
                raise ValueError("MEMBERSHIP_ORDER_NOT_FOUND")
            if int(payment["paid_cents"]) != event.amount_cents or event.currency != "CNY":
                raise ValueError("MEMBERSHIP_PAYMENT_AMOUNT_MISMATCH")
            if existing_event is not None:
                if existing_event["payment_no"] != event.reference_id:
                    raise ValueError("PAYMENT_EVENT_CONFLICT")
                return str(order["id"])
            existing_transaction = (
                connection.execute(
                    sa.select(events.c.payment_no).where(
                        events.c.provider == event.provider,
                        events.c.channel_transaction_id == event.provider_transaction_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                existing_transaction is not None
                and existing_transaction["payment_no"] != event.reference_id
            ):
                raise ValueError("PAYMENT_TRANSACTION_CONFLICT")
            self._record_payment_event(
                events,
                connection,
                event.provider,
                event.event_id,
                event.reference_id,
                event.provider_transaction_id,
            )
            if event.status is ProviderStatus.SUCCESS:
                if payment["status"] == "PAID" and order["status"] == "PAID":
                    return str(order["id"])
                if payment["status"] not in ("PENDING", "PROCESSING") or order["status"] not in (
                    "PENDING_PAYMENT",
                    "PROCESSING",
                ):
                    raise ValueError("PAYMENT_STATE_CONFLICT")
                plan = (
                    connection.execute(
                        sa.select(self._table("membership_plan_versions")).where(
                            self._table("membership_plan_versions").c.plan_code
                            == order["plan_code"],
                            self._table("membership_plan_versions").c.version
                            == order["plan_version"],
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if plan is None:
                    raise ValueError("MEMBERSHIP_PLAN_NOT_FOUND")
                self._activate_order(connection, order, plan)
                connection.execute(
                    payments.update().where(payments.c.id == payment["id"]).values(status="PAID")
                )
                connection.execute(
                    orders.update().where(orders.c.id == order["id"]).values(status="PAID")
                )
                return str(order["id"])
            status = event.status.value
            if payment["status"] not in ("PENDING", "PROCESSING"):
                if payment["status"] == status:
                    return str(order["id"])
                raise ValueError("PAYMENT_STATE_CONFLICT")
            connection.execute(
                payments.update().where(payments.c.id == payment["id"]).values(status=status)
            )
            connection.execute(
                orders.update().where(orders.c.id == order["id"]).values(status=status)
            )
            return str(order["id"])

    def _record_payment_event(
        self,
        events: Any,
        connection: Connection,
        provider: str,
        event_id: str,
        payment_no: str,
        provider_transaction_id: str | None = None,
    ) -> None:
        if provider_transaction_id:
            existing_transaction = (
                connection.execute(
                    sa.select(events.c.payment_no).where(
                        events.c.provider == provider,
                        events.c.channel_transaction_id == provider_transaction_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing_transaction is not None:
                return
        connection.execute(
            events.insert().values(
                provider=provider,
                provider_event_id=event_id,
                payment_no=payment_no,
                channel_transaction_id=provider_transaction_id,
                created_at=datetime.now(UTC),
            )
        )

    def _activate_order(self, connection: Connection, order: Any, plan: Any) -> None:
        now = datetime.now(UTC)
        accounts = self._table("membership_accounts")
        current = (
            connection.execute(
                sa.select(accounts)
                .where(accounts.c.account_id == order["account_id"])
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        base = now
        if current is not None and current["status"] == "ACTIVE":
            current_expiry = _utc(current["expires_at"])
            base = max(base, current_expiry)
        expires_at = base + timedelta(days=int(plan["duration_days"]))
        if current is None:
            connection.execute(
                accounts.insert().values(
                    id=self._next_numeric_id(connection, accounts),
                    account_id=order["account_id"],
                    plan_code=order["plan_code"],
                    expires_at=expires_at,
                    status="ACTIVE",
                    created_at=now,
                )
            )
        else:
            connection.execute(
                accounts.update()
                .where(accounts.c.account_id == order["account_id"])
                .values(plan_code=order["plan_code"], expires_at=expires_at, status="ACTIVE")
            )
        source = f"membership:{order['id']}"
        self._grant_tickets_in_transaction(
            connection,
            order["account_id"],
            TicketType.RECOMMEND,
            int(plan["daily_recommend_ticket_count"]),
            source,
        )
        self._grant_tickets_in_transaction(
            connection,
            order["account_id"],
            TicketType.MONTHLY,
            int(plan["monthly_chapter_ticket_count"]),
            source,
        )

    def _grant_tickets_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        ticket_type: TicketType,
        quantity: int,
        source: str,
    ) -> None:
        if quantity <= 0:
            return
        lots = self._table("ticket_lots")
        transactions = self._table("ticket_transactions")
        accounts = self._table("ticket_accounts")
        lot_id = _id("TLOT")
        connection.execute(
            lots.insert().values(
                id=lot_id,
                account_id=account_id,
                ticket_type=ticket_type.value,
                issued_quantity=quantity,
                available_quantity=quantity,
                expires_at=None,
                risk_status=TicketRiskStatus.NORMAL.value,
                source_ref=source,
                created_at=datetime.now(UTC),
            )
        )
        connection.execute(
            transactions.insert().values(
                id=_id("TTX"),
                account_id=account_id,
                ticket_type=ticket_type.value,
                kind="GRANT",
                quantity=quantity,
                lot_id=lot_id,
                source_ref=source,
                idempotency_key=f"{source}:{ticket_type.value}",
                created_at=datetime.now(UTC),
            )
        )
        self._adjust_ticket_projection(connection, accounts, account_id, ticket_type, quantity)

    @staticmethod
    def _membership_order_from_row(row: Any) -> MembershipOrder:
        return MembershipOrder(
            str(row["id"]),
            str(row["payment_no"]),
            str(row["account_id"]),
            str(row["plan_code"]),
            int(row["plan_version"]),
            str(row["channel"]),
            int(row["price_cents"]),
            str(row["status"]),
        )

    def activate(
        self,
        account_id: str,
        plan_code: str,
        expires_at: datetime,
    ) -> None:
        if not account_id.strip() or not plan_code.strip() or expires_at <= datetime.now(UTC):
            raise ValueError("MEMBERSHIP_ACTIVATION_INVALID")
        accounts = self._table("membership_accounts")
        plans = self._table("membership_plan_versions")
        with self.engine.begin() as connection:
            plan = connection.execute(
                sa.select(plans.c.plan_code)
                .where(plans.c.plan_code == plan_code, plans.c.status == "ACTIVE")
                .order_by(plans.c.version.desc())
                .limit(1)
            ).first()
            if plan is None:
                raise ValueError("MEMBERSHIP_PLAN_NOT_FOUND")
            current = (
                connection.execute(
                    sa.select(accounts).where(accounts.c.account_id == account_id).with_for_update()
                )
                .mappings()
                .first()
            )
            now = datetime.now(UTC)
            if current is None:
                connection.execute(
                    accounts.insert().values(
                        id=self._next_numeric_id(connection, accounts),
                        account_id=account_id,
                        plan_code=plan_code,
                        expires_at=expires_at,
                        status="ACTIVE",
                        created_at=now,
                    )
                )
            else:
                current_expiry = _utc(current["expires_at"])
                connection.execute(
                    accounts.update()
                    .where(accounts.c.account_id == account_id)
                    .values(
                        plan_code=plan_code,
                        expires_at=max(current_expiry, expires_at),
                        status="ACTIVE",
                    )
                )

    def add_library_book(self, plan_code: str, book_id: str) -> None:
        if not plan_code.strip() or not book_id.strip():
            raise ValueError("MEMBERSHIP_LIBRARY_ENTRY_INVALID")
        table = self._table("membership_library_entries")
        with self.engine.begin() as connection:
            try:
                connection.execute(
                    table.insert().values(
                        id=self._next_numeric_id(connection, table),
                        plan_code=plan_code,
                        book_id=book_id,
                        active_from=datetime.now(UTC),
                        active_until=None,
                        status="ACTIVE",
                    )
                )
            except IntegrityError as exc:
                raise ValueError("MEMBERSHIP_LIBRARY_ENTRY_EXISTS") from exc

    def is_active(self, account_id: str, now: datetime | None = None) -> bool:
        accounts = self._table("membership_accounts")
        at = _utc(now or datetime.now(UTC))
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(accounts.c.expires_at, accounts.c.status).where(
                    accounts.c.account_id == account_id
                )
            ).first()
        return row is not None and row.status == "ACTIVE" and _utc(row.expires_at) > at

    def access(
        self,
        account_id: str,
        chapter_id: str,
        policy: ChapterPolicy,
        purchased: bool,
        now: datetime | None = None,
        book_id: str | None = None,
    ) -> AccessMode:
        del chapter_id
        if purchased:
            return AccessMode.PURCHASED
        if policy.access_mode in (AccessMode.FREE, AccessMode.LIMITED_FREE):
            return policy.access_mode
        if not book_id:
            return AccessMode.VIP_REQUIRED
        accounts = self._table("membership_accounts")
        library = self._table("membership_library_entries")
        at = _utc(now or datetime.now(UTC))
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(accounts.c.expires_at)
                .join(library, library.c.plan_code == accounts.c.plan_code)
                .where(
                    accounts.c.account_id == account_id,
                    accounts.c.status == "ACTIVE",
                    accounts.c.expires_at > at,
                    library.c.book_id == book_id,
                    library.c.status == "ACTIVE",
                    library.c.active_from <= at,
                    sa.or_(library.c.active_until.is_(None), library.c.active_until > at),
                )
            ).first()
        return AccessMode.MEMBER_FREE if row is not None else AccessMode.VIP_REQUIRED

    def grant_tickets(
        self,
        account_id: str,
        ticket_type: TicketType,
        quantity: int,
        *,
        source_ref: str,
        expires_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> TicketBalance:
        if quantity <= 0 or not source_ref.strip():
            raise ValueError("TICKET_GRANT_INVALID")
        transactions = self._table("ticket_transactions")
        lots = self._table("ticket_lots")
        accounts = self._table("ticket_accounts")
        with self.engine.begin() as connection:
            if idempotency_key:
                duplicate = (
                    connection.execute(
                        sa.select(transactions).where(
                            transactions.c.idempotency_key == idempotency_key
                        )
                    )
                    .mappings()
                    .first()
                )
                if duplicate is not None:
                    if (
                        duplicate["account_id"] != account_id
                        or duplicate["ticket_type"] != ticket_type.value
                        or int(duplicate["quantity"]) != quantity
                        or duplicate["source_ref"] != source_ref
                    ):
                        raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
                    return self.ticket_balance(account_id, connection=connection)
            lot_id = _id("TLOT")
            connection.execute(
                lots.insert().values(
                    id=lot_id,
                    account_id=account_id,
                    ticket_type=ticket_type.value,
                    issued_quantity=quantity,
                    available_quantity=quantity,
                    expires_at=expires_at,
                    risk_status=TicketRiskStatus.NORMAL.value,
                    source_ref=source_ref,
                    created_at=datetime.now(UTC),
                )
            )
            connection.execute(
                transactions.insert().values(
                    id=_id("TTX"),
                    account_id=account_id,
                    ticket_type=ticket_type.value,
                    kind="GRANT",
                    quantity=quantity,
                    lot_id=lot_id,
                    source_ref=source_ref,
                    idempotency_key=idempotency_key,
                    created_at=datetime.now(UTC),
                )
            )
            self._adjust_ticket_projection(connection, accounts, account_id, ticket_type, quantity)
            return self.ticket_balance(account_id, connection=connection)

    def ticket_balance(
        self, account_id: str, *, now: datetime | None = None, connection: Connection | None = None
    ) -> TicketBalance:
        owns_connection = connection is None
        active_connection = connection or self.engine.connect()
        try:
            lots = self._table("ticket_lots")
            at = now or datetime.now(UTC)
            rows = active_connection.execute(
                sa.select(
                    lots.c.ticket_type, sa.func.sum(lots.c.available_quantity).label("amount")
                )
                .where(
                    lots.c.account_id == account_id,
                    lots.c.risk_status == TicketRiskStatus.NORMAL.value,
                    sa.or_(lots.c.expires_at.is_(None), lots.c.expires_at > at),
                )
                .group_by(lots.c.ticket_type)
            ).all()
            amounts = {str(row.ticket_type): int(row.amount or 0) for row in rows}
            return TicketBalance(
                account_id,
                amounts.get(TicketType.RECOMMEND.value, 0),
                amounts.get(TicketType.MONTHLY.value, 0),
            )
        finally:
            if owns_connection:
                active_connection.close()

    def vote(
        self,
        account_id: str,
        book_id: str,
        ticket_type: TicketType,
        *,
        quantity: int = 1,
        idempotency_key: str,
    ) -> BookTicketVote:
        if (
            not account_id.strip()
            or not book_id.strip()
            or quantity <= 0
            or not idempotency_key.strip()
        ):
            raise ValueError("TICKET_VOTE_INVALID")
        votes = self._table("book_ticket_votes")
        transactions = self._table("ticket_transactions")
        lots = self._table("ticket_lots")
        accounts = self._table("ticket_accounts")
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(votes).where(votes.c.idempotency_key == idempotency_key)
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return self._vote_from_row(existing)
            at = datetime.now(UTC)
            candidates = (
                connection.execute(
                    sa.select(lots)
                    .where(
                        lots.c.account_id == account_id,
                        lots.c.ticket_type == ticket_type.value,
                        lots.c.available_quantity > 0,
                        lots.c.risk_status == TicketRiskStatus.NORMAL.value,
                        sa.or_(lots.c.expires_at.is_(None), lots.c.expires_at > at),
                    )
                    .order_by(
                        lots.c.expires_at.asc().nulls_last(),
                        lots.c.created_at.asc(),
                        lots.c.id.asc(),
                    )
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            remaining = quantity
            for lot in candidates:
                if remaining == 0:
                    break
                taken = min(remaining, int(lot["available_quantity"]))
                connection.execute(
                    lots.update()
                    .where(lots.c.id == lot["id"])
                    .values(available_quantity=lots.c.available_quantity - taken)
                )
                connection.execute(
                    transactions.insert().values(
                        id=_id("TTX"),
                        account_id=account_id,
                        ticket_type=ticket_type.value,
                        kind="CONSUME",
                        quantity=taken,
                        lot_id=lot["id"],
                        source_ref=book_id,
                        idempotency_key=idempotency_key if remaining == quantity else None,
                        created_at=at,
                    )
                )
                remaining -= taken
            if remaining:
                raise ValueError("TICKET_INSUFFICIENT")
            self._adjust_ticket_projection(connection, accounts, account_id, ticket_type, -quantity)
            vote = BookTicketVote(
                _id("VOTE"),
                account_id,
                book_id,
                ticket_type,
                quantity,
                TicketRiskStatus.NORMAL,
                idempotency_key,
                at,
            )
            connection.execute(
                votes.insert().values(
                    id=vote.id,
                    account_id=vote.account_id,
                    book_id=vote.book_id,
                    ticket_type=vote.ticket_type.value,
                    quantity=vote.quantity,
                    risk_status=vote.risk_status.value,
                    idempotency_key=vote.idempotency_key,
                    created_at=vote.created_at,
                )
            )
            return vote

    @staticmethod
    def _next_numeric_id(connection: Connection, table: Any) -> int:
        """Provide SQLite parity for the legacy BIGINT autoincrement columns."""
        return int(connection.execute(sa.select(sa.func.max(table.c.id))).scalar_one() or 0) + 1

    @staticmethod
    def _adjust_ticket_projection(
        connection: Connection, table: Any, account_id: str, ticket_type: TicketType, amount: int
    ) -> None:
        column = (
            table.c.recommend_balance
            if ticket_type is TicketType.RECOMMEND
            else table.c.monthly_balance
        )
        row = connection.execute(
            sa.select(table.c.account_id).where(table.c.account_id == account_id).with_for_update()
        ).first()
        if row is None:
            connection.execute(
                table.insert().values(
                    account_id=account_id,
                    recommend_balance=amount if ticket_type is TicketType.RECOMMEND else 0,
                    monthly_balance=amount if ticket_type is TicketType.MONTHLY else 0,
                    created_at=datetime.now(UTC),
                )
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.account_id == account_id)
                .values({column: column + amount})
            )

    def register_gift(
        self,
        gift_code: str,
        name: str,
        price_coin: int,
        fan_value: int,
        *,
        spend_mode: str = "GIFT_AND_RECHARGE",
    ) -> GiftDefinition:
        if not gift_code.strip() or not name.strip() or price_coin <= 0 or fan_value <= 0:
            raise ValueError("GIFT_DEFINITION_INVALID")
        if spend_mode not in ("GIFT_AND_RECHARGE", "RECHARGE_ONLY"):
            raise ValueError("GIFT_SPEND_MODE_INVALID")
        gift = GiftDefinition(gift_code, name.strip(), price_coin, fan_value, spend_mode)
        table = self._table("gift_definitions")
        with self.engine.begin() as connection:
            try:
                connection.execute(
                    table.insert().values(
                        gift_code=gift.gift_code,
                        name=gift.name,
                        price_coin=gift.price_coin,
                        fan_value=gift.fan_value,
                        spend_mode=gift.spend_mode,
                        status="ACTIVE",
                        created_at=datetime.now(UTC),
                    )
                )
            except IntegrityError as exc:
                raise ValueError("GIFT_DEFINITION_EXISTS") from exc
        return gift

    def send_gift(
        self,
        account_id: str,
        book_id: str,
        author_id: str,
        gift_code: str,
        *,
        quantity: int = 1,
        idempotency_key: str,
        asset_spend: Callable[[Connection, str, int, str], None],
    ) -> GiftOrder:
        if quantity <= 0 or not idempotency_key.strip():
            raise ValueError("GIFT_ORDER_INVALID")
        gifts = self._table("gift_definitions")
        orders = self._table("gift_orders")
        self._table("fan_value_events")
        self._table("book_fan_profiles")
        self._table("fan_level_rules")
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(orders).where(orders.c.idempotency_key == idempotency_key)
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if (
                    existing["account_id"] != account_id
                    or existing["book_id"] != book_id
                    or existing["author_id"] != author_id
                    or existing["gift_code"] != gift_code
                    or int(existing["quantity"]) != quantity
                ):
                    raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
                return self._gift_from_row(existing)
            definition = (
                connection.execute(
                    sa.select(gifts).where(
                        gifts.c.gift_code == gift_code, gifts.c.status == "ACTIVE"
                    )
                )
                .mappings()
                .first()
            )
            if definition is None:
                raise ValueError("GIFT_NOT_FOUND")
            total = int(definition["price_coin"]) * quantity
            order = GiftOrder(
                _id("GIFT"),
                account_id,
                book_id,
                author_id,
                gift_code,
                quantity,
                total,
                total,
                int(definition["fan_value"]) * quantity,
                "COMPLETED",
                idempotency_key,
                datetime.now(UTC),
            )
            asset_spend(connection, account_id, total, definition["spend_mode"])
            connection.execute(
                orders.insert().values(
                    id=order.id,
                    account_id=order.account_id,
                    book_id=order.book_id,
                    author_id=order.author_id,
                    gift_code=order.gift_code,
                    quantity=order.quantity,
                    total_coin=order.total_coin,
                    income_base_coin=order.income_base_coin,
                    fan_value=order.fan_value,
                    status=order.status,
                    idempotency_key=order.idempotency_key,
                    created_at=order.created_at,
                )
            )
            self._add_fan_value_in_transaction(
                connection, account_id, book_id, "GIFT", order.fan_value, order.id
            )
            return order

    def record_fan_value(
        self, account_id: str, book_id: str, source: str, value: int, *, source_ref: str
    ) -> FanProfile:
        if value <= 0 or not source.strip() or not source_ref.strip():
            raise ValueError("FAN_VALUE_INVALID")
        self._table("fan_value_events")
        self._table("book_fan_profiles")
        self._table("fan_level_rules")
        with self.engine.begin() as connection:
            self._add_fan_value_in_transaction(
                connection, account_id, book_id, source, value, source_ref
            )
            return self._fan_profile(connection, account_id, book_id)

    def fan_profile(self, account_id: str, book_id: str) -> FanProfile:
        with self.engine.connect() as connection:
            return self._fan_profile(connection, account_id, book_id)

    def _add_fan_value_in_transaction(
        self,
        connection: Connection,
        account_id: str,
        book_id: str,
        source: str,
        value: int,
        source_ref: str,
    ) -> None:
        events = self._table("fan_value_events")
        profiles = self._table("book_fan_profiles")
        duplicate = connection.execute(
            sa.select(events.c.id).where(
                events.c.account_id == account_id,
                events.c.book_id == book_id,
                events.c.source == source,
                events.c.source_ref == source_ref,
            )
        ).first()
        if duplicate is not None:
            return
        connection.execute(
            events.insert().values(
                id=_id("FAN"),
                account_id=account_id,
                book_id=book_id,
                source=source,
                value=value,
                source_ref=source_ref,
                created_at=datetime.now(UTC),
            )
        )
        row = (
            connection.execute(
                sa.select(profiles)
                .where(profiles.c.account_id == account_id, profiles.c.book_id == book_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        total = (int(row["value"]) if row else 0) + value
        level = self._fan_level(connection, total)
        if row is None:
            connection.execute(
                profiles.insert().values(
                    account_id=account_id,
                    book_id=book_id,
                    value=total,
                    level=level,
                    created_at=datetime.now(UTC),
                )
            )
        else:
            connection.execute(
                profiles.update()
                .where(profiles.c.account_id == account_id, profiles.c.book_id == book_id)
                .values(value=total, level=level)
            )

    def _fan_profile(self, connection: Connection, account_id: str, book_id: str) -> FanProfile:
        profiles = self._table("book_fan_profiles")
        row = (
            connection.execute(
                sa.select(profiles).where(
                    profiles.c.account_id == account_id, profiles.c.book_id == book_id
                )
            )
            .mappings()
            .first()
        )
        return FanProfile(
            account_id, book_id, int(row["value"]) if row else 0, int(row["level"]) if row else 1
        )

    def set_fan_level(self, level: int, threshold: int, *, version: int = 1) -> None:
        if level <= 0 or threshold < 0 or version <= 0:
            raise ValueError("FAN_LEVEL_RULE_INVALID")
        table = self._table("fan_level_rules")
        with self.engine.begin() as connection:
            connection.execute(
                table.insert().values(version=version, level=level, threshold=threshold)
            )

    def _fan_level(self, connection: Connection, value: int) -> int:
        rules = self._table("fan_level_rules")
        latest = connection.execute(sa.select(sa.func.max(rules.c.version))).scalar_one()
        if latest is None:
            return 1
        count = connection.execute(
            sa.select(sa.func.count()).where(rules.c.version == latest, rules.c.threshold <= value)
        ).scalar_one()
        return max(1, int(count))

    def add_user_growth(
        self, account_id: str, source: str, points: int, *, source_ref: str
    ) -> UserGrowthProfile:
        if points <= 0 or not source.strip() or not source_ref.strip():
            raise ValueError("GROWTH_POINTS_INVALID")
        events = self._table("membership_user_growth_events")
        profiles = self._table("membership_user_growth_profiles")
        self._table("membership_user_growth_rules")
        with self.engine.begin() as connection:
            duplicate = connection.execute(
                sa.select(events.c.id).where(
                    events.c.account_id == account_id, events.c.source_ref == source_ref
                )
            ).first()
            if duplicate is None:
                connection.execute(
                    events.insert().values(
                        id=_id("GROW"),
                        account_id=account_id,
                        source=source,
                        points=points,
                        source_ref=source_ref,
                        created_at=datetime.now(UTC),
                    )
                )
                row = (
                    connection.execute(
                        sa.select(profiles)
                        .where(profiles.c.account_id == account_id)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                total = (int(row["points"]) if row else 0) + points
                level = self._growth_level(connection, total)
                if row is None:
                    connection.execute(
                        profiles.insert().values(
                            account_id=account_id,
                            points=total,
                            level=level,
                            rule_version=1,
                            created_at=datetime.now(UTC),
                        )
                    )
                else:
                    connection.execute(
                        profiles.update()
                        .where(profiles.c.account_id == account_id)
                        .values(points=total, level=level)
                    )
            return self._growth_profile(connection, account_id)

    def user_growth(self, account_id: str) -> UserGrowthProfile:
        with self.engine.connect() as connection:
            return self._growth_profile(connection, account_id)

    def _growth_profile(self, connection: Connection, account_id: str) -> UserGrowthProfile:
        profiles = self._table("membership_user_growth_profiles")
        row = (
            connection.execute(sa.select(profiles).where(profiles.c.account_id == account_id))
            .mappings()
            .first()
        )
        return UserGrowthProfile(
            account_id, int(row["points"]) if row else 0, int(row["level"]) if row else 1
        )

    def set_growth_level(self, level: int, threshold: int, *, version: int = 1) -> None:
        if level <= 0 or threshold < 0 or version <= 0:
            raise ValueError("GROWTH_LEVEL_RULE_INVALID")
        table = self._table("membership_user_growth_rules")
        with self.engine.begin() as connection:
            connection.execute(
                table.insert().values(version=version, level=level, threshold=threshold)
            )

    def _growth_level(self, connection: Connection, points: int) -> int:
        rules = self._table("membership_user_growth_rules")
        latest = connection.execute(sa.select(sa.func.max(rules.c.version))).scalar_one()
        if latest is None:
            return 1
        count = connection.execute(
            sa.select(sa.func.count()).where(rules.c.version == latest, rules.c.threshold <= points)
        ).scalar_one()
        return max(1, int(count))

    @staticmethod
    def _vote_from_row(row: Any) -> BookTicketVote:
        return BookTicketVote(
            str(row["id"]),
            str(row["account_id"]),
            str(row["book_id"]),
            TicketType(str(row["ticket_type"])),
            int(row["quantity"]),
            TicketRiskStatus(str(row["risk_status"])),
            str(row["idempotency_key"]),
            _utc(row["created_at"]),
        )

    @staticmethod
    def _gift_from_row(row: Any) -> GiftOrder:
        return GiftOrder(
            str(row["id"]),
            str(row["account_id"]),
            str(row["book_id"]),
            str(row["author_id"]),
            str(row["gift_code"]),
            int(row["quantity"]),
            int(row["total_coin"]),
            int(row["income_base_coin"]),
            int(row["fan_value"]),
            str(row["status"]),
            str(row["idempotency_key"]),
            _utc(row["created_at"]),
        )


__all__ = ["SqlMembershipService"]

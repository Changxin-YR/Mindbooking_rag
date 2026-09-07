"""SQLAlchemy adapter for the current author-finance contract."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from novel_platform.modules.author_finance.application import AuthorFinanceService
from novel_platform.modules.author_finance.domain import (
    DEFAULT_AUTHOR_SHARE_BPS,
    DEFAULT_POLICY_VERSION,
    DEFAULT_TAX_FREE_THRESHOLD_CENTS,
    DEFAULT_TAX_WITHHOLDING_BPS,
    Chargeback,
    Contract,
    ContractStatus,
    ContractVersion,
    PayoutOrder,
    PayoutStatus,
    RevenueEntry,
    RevenueStatus,
    Settlement,
    SettlementStatus,
    Withdrawal,
    WithdrawalStatus,
    period_bounds,
    render_virtual_contract,
)
from novel_platform.modules.payment import PayoutProvider, ProviderEvent


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _present(table: Any, values: Mapping[str, object]) -> dict[str, object]:
    return {name: value for name, value in values.items() if name in table.c}


class SqlAuthorFinanceService(AuthorFinanceService):
    def __init__(
        self,
        engine: Engine,
        payout_provider: PayoutProvider | None = None,
        payout_provider_secret: str = "",
    ) -> None:
        super().__init__(payout_provider, payout_provider_secret)
        self.engine = engine
        metadata = sa.MetaData()
        self._contracts: Any = sa.Table("contracts", metadata, autoload_with=engine)
        self._contract_versions: Any = sa.Table("contract_versions", metadata, autoload_with=engine)
        self._revenue: Any = sa.Table("author_revenue_entries", metadata, autoload_with=engine)
        self._settlements: Any = sa.Table("author_settlements", metadata, autoload_with=engine)
        self._withdrawals: Any = sa.Table("withdrawal_requests", metadata, autoload_with=engine)
        self._chargebacks: Any = sa.Table("chargebacks", metadata, autoload_with=engine)
        self._claims: Any = sa.Table("financial_recovery_claims", metadata, autoload_with=engine)
        try:
            self._payout_orders: Any = sa.Table("payout_orders", metadata, autoload_with=engine)
        except sa.exc.NoSuchTableError:
            self._payout_orders = None
        try:
            self._outbox: Any = sa.Table("outbox_events", metadata, autoload_with=engine)
        except sa.exc.NoSuchTableError:
            self._outbox = None

    def create_contract(
        self, author_id: str, book_id: str, share_bps: int | None = None
    ) -> Contract:
        effective_share = DEFAULT_AUTHOR_SHARE_BPS if share_bps is None else share_bps
        if not 0 < effective_share <= 10000:
            raise ValueError("INVALID_REVENUE_SHARE_BPS")
        contract = Contract(_id("CTR"), author_id, book_id, policy_version=DEFAULT_POLICY_VERSION)
        version = ContractVersion(
            _id("CTV"),
            contract.id,
            1,
            effective_share,
            DEFAULT_POLICY_VERSION,
            DEFAULT_TAX_WITHHOLDING_BPS,
            DEFAULT_TAX_FREE_THRESHOLD_CENTS,
        )
        document_text, document_hash = render_virtual_contract(
            contract_id=contract.id,
            author_id=author_id,
            book_id=book_id,
            version=version.version,
            revenue_share_bps=version.revenue_share_bps,
            policy_version=version.policy_version,
            tax_withholding_bps=version.tax_withholding_bps,
            tax_free_threshold_cents=version.tax_free_threshold_cents,
        )
        version = ContractVersion(
            version.id,
            version.contract_id,
            version.version,
            version.revenue_share_bps,
            version.policy_version,
            version.tax_withholding_bps,
            version.tax_free_threshold_cents,
            document_text,
            document_hash,
        )
        contract.document_text = document_text
        contract.document_hash = document_hash
        contract.version_ids.append(version.id)
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                self._contracts.insert().values(
                    id=contract.id,
                    author_id=contract.author_id,
                    book_id=contract.book_id,
                    status=contract.status.value,
                    created_at=now,
                )
            )
            connection.execute(
                self._contract_versions.insert().values(
                    **_present(
                        self._contract_versions,
                        {
                            "id": version.id,
                            "contract_id": version.contract_id,
                            "version": version.version,
                            "revenue_share_bps": version.revenue_share_bps,
                            "policy_version": version.policy_version,
                            "tax_withholding_bps": version.tax_withholding_bps,
                            "tax_free_threshold_cents": version.tax_free_threshold_cents,
                            "document_text": version.document_text,
                            "document_hash": version.document_hash,
                            "created_at": now,
                        },
                    )
                )
            )
            self._append_outbox(
                connection,
                "ContractCreated",
                contract.id,
                {"author_id": author_id, "book_id": book_id, "version_id": version.id},
            )
        return contract

    def get_contract(self, contract_id: str) -> Contract:
        with self.engine.begin() as connection:
            return self._contract_from_connection(connection, contract_id)

    def list_contracts(
        self,
        *,
        author_id: str | None = None,
        status: str | None = None,
    ) -> list[Contract]:
        normalized_author = author_id.strip() if author_id is not None else None
        normalized_status = status.strip().upper() if status is not None else None
        allowed_statuses = {item.value for item in ContractStatus}
        if normalized_author == "":
            raise ValueError("AUTHOR_ID_REQUIRED")
        if normalized_status not in {None, *allowed_statuses}:
            raise ValueError("CONTRACT_STATUS_INVALID")
        query = sa.select(self._contracts).order_by(
            self._contracts.c.created_at.desc(), self._contracts.c.id.desc()
        )
        if normalized_author is not None:
            query = query.where(self._contracts.c.author_id == normalized_author)
        if normalized_status is not None:
            query = query.where(self._contracts.c.status == normalized_status)
        with self.engine.begin() as connection:
            return [
                self._contract_from_connection(connection, str(row["id"]))
                for row in connection.execute(query).mappings()
            ]

    def approve_contract(self, contract_id: str, approver_id: str) -> Contract:
        with self.engine.begin() as connection:
            contract = self._contract_from_connection(connection, contract_id, lock=True)
            if contract.author_id == approver_id:
                raise ValueError("MAKER_CHECKER_REQUIRED")
            if contract.status is not ContractStatus.DRAFT:
                raise ValueError("CONTRACT_NOT_DRAFT")
            connection.execute(
                self._contracts.update()
                .where(self._contracts.c.id == contract_id)
                .values(status=ContractStatus.APPROVED.value)
            )
            contract.status = ContractStatus.APPROVED
            return contract

    def activate_contract(self, contract_id: str) -> Contract:
        with self.engine.begin() as connection:
            contract = self._contract_from_connection(connection, contract_id, lock=True)
            if contract.status is not ContractStatus.APPROVED:
                raise ValueError("CONTRACT_NOT_APPROVED")
            if contract.signature_hash is None:
                raise ValueError("CONTRACT_SIGNATURE_REQUIRED")
            connection.execute(
                self._contracts.update()
                .where(self._contracts.c.id == contract_id)
                .values(status=ContractStatus.ACTIVE.value)
            )
            self._append_outbox(
                connection,
                "ContractActivated",
                contract_id,
                {"author_id": contract.author_id, "book_id": contract.book_id},
            )
            contract.status = ContractStatus.ACTIVE
            return contract

    def sign_contract(self, contract_id: str, signer_id: str) -> Contract:
        signer_id = signer_id.strip()
        if not signer_id:
            raise ValueError("SIGNER_ID_REQUIRED")
        with self.engine.begin() as connection:
            contract = self._contract_from_connection(connection, contract_id, lock=True)
            if contract.status is not ContractStatus.APPROVED:
                raise ValueError("CONTRACT_NOT_APPROVED")
            if contract.signed_by is not None:
                if contract.signed_by != signer_id:
                    raise ValueError("CONTRACT_SIGNATURE_CONFLICT")
                return contract
            if "signature_hash" not in self._contracts.c:
                raise ValueError("CONTRACT_SIGNATURE_STORAGE_REQUIRED")
            signed_at = datetime.now(UTC)
            signature_hash = sha256(
                f"{contract.id}:{contract.document_hash}:{signer_id}:{signed_at.isoformat()}".encode()
            ).hexdigest()
            connection.execute(
                self._contracts.update()
                .where(self._contracts.c.id == contract_id)
                .values(
                    signed_by=signer_id,
                    signed_at=signed_at,
                    signature_hash=signature_hash,
                )
            )
            contract.signed_by = signer_id
            contract.signed_at = signed_at
            contract.signature_hash = signature_hash
            self._append_outbox(
                connection,
                "ContractSigned",
                contract.id,
                {
                    "author_id": contract.author_id,
                    "book_id": contract.book_id,
                    "signer_id": signer_id,
                },
            )
            return contract

    def _active_policy(
        self, connection: Connection, author_id: str, book_id: str | None = None
    ) -> tuple[int, str, int, int] | None:
        query = sa.select(self._contracts.c.id).where(
            self._contracts.c.author_id == author_id,
            self._contracts.c.status == ContractStatus.ACTIVE.value,
        )
        if book_id is not None:
            query = query.where(self._contracts.c.book_id == book_id)
        contract_ids = list(connection.execute(query).scalars())
        if book_id is None and len(contract_ids) > 1:
            raise ValueError("BOOK_ID_REQUIRED_FOR_CONTRACT_POLICY")
        contract_id = contract_ids[0] if contract_ids else None
        if contract_id is None:
            return None
        columns = [self._contract_versions.c.revenue_share_bps]
        for name in ("policy_version", "tax_withholding_bps", "tax_free_threshold_cents"):
            column = getattr(self._contract_versions.c, name, None)
            if column is not None:
                columns.append(column)
        row = (
            connection.execute(
                sa.select(*columns)
                .where(self._contract_versions.c.contract_id == contract_id)
                .order_by(self._contract_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return (
            int(row["revenue_share_bps"]),
            str(row.get("policy_version") or DEFAULT_POLICY_VERSION),
            int(row.get("tax_withholding_bps") or DEFAULT_TAX_WITHHOLDING_BPS),
            int(row.get("tax_free_threshold_cents") or DEFAULT_TAX_FREE_THRESHOLD_CENTS),
        )

    def record_revenue(
        self,
        author_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
        share_bps: int | None = None,
        book_id: str | None = None,
    ) -> RevenueEntry:
        if gross_cents <= 0 or (share_bps is not None and not 0 <= share_bps <= 10000):
            raise ValueError("INVALID_REVENUE_AMOUNT")
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(self._revenue)
                    .where(self._revenue.c.source_ref == source_ref)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if (
                    existing["author_id"] != author_id
                    or int(existing["gross_cents"]) != gross_cents
                    or (
                        share_bps is not None
                        and int(existing["author_cents"]) != gross_cents * share_bps // 10000
                    )
                ):
                    raise ValueError("REVENUE_SOURCE_CONFLICT")
                return self._revenue_from_row(existing)
            policy_version: str | None = None
            withholding_bps = 0
            threshold_cents = 0
            effective_share = share_bps
            if effective_share is None:
                policy = self._active_policy(connection, author_id, book_id)
                if policy is not None:
                    effective_share, policy_version, withholding_bps, threshold_cents = policy
                else:
                    effective_share = DEFAULT_AUTHOR_SHARE_BPS
            author_cents = gross_cents * effective_share // 10000
            tax_cents = max(0, author_cents - threshold_cents) * withholding_bps // 10000
            entry = RevenueEntry(
                _id("REV"),
                author_id,
                source,
                source_ref,
                gross_cents,
                author_cents,
                tax_cents=tax_cents,
                net_author_cents=author_cents - tax_cents,
                policy_version=policy_version,
            )
            connection.execute(
                self._revenue.insert().values(
                    **_present(
                        self._revenue,
                        {
                            "id": entry.id,
                            "author_id": entry.author_id,
                            "source": entry.source,
                            "source_ref": entry.source_ref,
                            "gross_cents": entry.gross_cents,
                            "author_cents": entry.author_cents,
                            "status": entry.status.value,
                            "settlement_id": entry.settlement_id,
                            "tax_cents": entry.tax_cents,
                            "net_author_cents": entry.net_author_cents,
                            "policy_version": entry.policy_version,
                            "created_at": entry.created_at,
                        },
                    )
                )
            )
            self._append_outbox(
                connection,
                "RevenueCreated",
                entry.id,
                {"author_id": author_id, "source": source, "source_ref": source_ref},
            )
            return entry

    def record_revenue_in_transaction(
        self,
        connection: Connection,
        author_id: str,
        book_id: str,
        source: str,
        source_ref: str,
        gross_cents: int,
    ) -> RevenueEntry:
        """Record chapter revenue on the caller's transaction connection."""
        if (
            gross_cents <= 0
            or not author_id.strip()
            or not book_id.strip()
            or not source_ref.strip()
        ):
            raise ValueError("INVALID_REVENUE_AMOUNT")
        existing = (
            connection.execute(
                sa.select(self._revenue)
                .where(self._revenue.c.source_ref == source_ref)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["author_id"] != author_id or int(existing["gross_cents"]) != gross_cents:
                raise ValueError("REVENUE_SOURCE_CONFLICT")
            return self._revenue_from_row(existing)
        contract_row = connection.execute(
            sa.select(self._contracts.c.id)
            .where(
                self._contracts.c.author_id == author_id,
                self._contracts.c.book_id == book_id,
                self._contracts.c.status == ContractStatus.ACTIVE.value,
            )
            .limit(1)
        ).scalar_one_or_none()
        if contract_row is None:
            raise ValueError("CONTRACT_NOT_ACTIVE")
        columns = [self._contract_versions.c.revenue_share_bps]
        for name in ("policy_version", "tax_withholding_bps", "tax_free_threshold_cents"):
            column = getattr(self._contract_versions.c, name, None)
            if column is not None:
                columns.append(column)
        policy_row = (
            connection.execute(
                sa.select(*columns)
                .where(self._contract_versions.c.contract_id == contract_row)
                .order_by(self._contract_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        share_bps = int(policy_row["revenue_share_bps"])
        policy_version = str(policy_row.get("policy_version") or DEFAULT_POLICY_VERSION)
        withholding_bps = int(policy_row.get("tax_withholding_bps") or DEFAULT_TAX_WITHHOLDING_BPS)
        threshold_cents = int(
            policy_row.get("tax_free_threshold_cents") or DEFAULT_TAX_FREE_THRESHOLD_CENTS
        )
        author_cents = gross_cents * share_bps // 10000
        tax_cents = max(0, author_cents - threshold_cents) * withholding_bps // 10000
        entry = RevenueEntry(
            _id("REV"),
            author_id,
            source,
            source_ref,
            gross_cents,
            author_cents,
            tax_cents=tax_cents,
            net_author_cents=author_cents - tax_cents,
            policy_version=policy_version,
        )
        connection.execute(
            self._revenue.insert().values(
                **_present(
                    self._revenue,
                    {
                        "id": entry.id,
                        "author_id": entry.author_id,
                        "source": entry.source,
                        "source_ref": entry.source_ref,
                        "gross_cents": entry.gross_cents,
                        "author_cents": entry.author_cents,
                        "status": entry.status.value,
                        "settlement_id": None,
                        "tax_cents": entry.tax_cents,
                        "net_author_cents": entry.net_author_cents,
                        "policy_version": entry.policy_version,
                        "created_at": datetime.now(UTC),
                    },
                )
            )
        )
        self._append_outbox(
            connection,
            "RevenueCreated",
            entry.id,
            {"author_id": author_id, "source": source, "source_ref": source_ref},
        )
        return entry

    def confirm_revenue(self, revenue_id: str) -> RevenueEntry:
        with self.engine.begin() as connection:
            row = self._revenue_row(connection, revenue_id, lock=True)
            entry = self._revenue_from_row(row)
            if entry.status is not RevenueStatus.RISK_PENDING:
                raise ValueError("REVENUE_NOT_PENDING")
            connection.execute(
                self._revenue.update()
                .where(self._revenue.c.id == revenue_id)
                .values(status=RevenueStatus.CONFIRMED.value)
            )
            entry.status = RevenueStatus.CONFIRMED
            return entry

    def settle(self, author_id: str, period: str) -> Settlement:
        start, end = period_bounds(period)
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    sa.select(self._settlements)
                    .where(
                        self._settlements.c.author_id == author_id,
                        self._settlements.c.period == period,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._settlement_from_row(existing)
            eligible = [
                row
                for row in connection.execute(
                    sa.select(self._revenue)
                    .where(
                        self._revenue.c.author_id == author_id,
                        self._revenue.c.status == RevenueStatus.CONFIRMED.value,
                    )
                    .with_for_update()
                ).mappings()
                if start <= _utc(row["created_at"]) < end
            ]
            gross_cents = sum(int(row["gross_cents"]) for row in eligible)
            tax_cents = sum(int(row.get("tax_cents") or 0) for row in eligible)
            settlement = Settlement(
                _id("SET"),
                author_id,
                period,
                sum(int(row.get("net_author_cents") or row["author_cents"]) for row in eligible),
                status=SettlementStatus.WITHDRAWABLE,
                gross_cents=gross_cents,
                tax_cents=tax_cents,
            )
            connection.execute(
                self._settlements.insert().values(
                    **_present(
                        self._settlements,
                        {
                            "id": settlement.id,
                            "author_id": settlement.author_id,
                            "period": settlement.period,
                            "amount_cents": settlement.amount_cents,
                            "withdrawn_cents": settlement.withdrawn_cents,
                            "status": settlement.status.value,
                            "gross_cents": settlement.gross_cents,
                            "tax_cents": settlement.tax_cents,
                            "created_at": datetime.now(UTC),
                        },
                    )
                )
            )
            for row in eligible:
                connection.execute(
                    self._revenue.update()
                    .where(self._revenue.c.id == row["id"])
                    .values(status=RevenueStatus.SETTLED.value, settlement_id=settlement.id)
                )
            self._append_outbox(
                connection,
                "SettlementCreated",
                settlement.id,
                {"author_id": author_id, "period": period, "amount_cents": settlement.amount_cents},
            )
            return settlement

    def list_settlements(self, author_id: str) -> list[Settlement]:
        if not author_id.strip():
            raise ValueError("AUTHOR_ID_REQUIRED")
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(self._settlements)
                .where(self._settlements.c.author_id == author_id)
                .order_by(self._settlements.c.period.desc(), self._settlements.c.id.desc())
            ).mappings()
            return [self._settlement_from_row(row) for row in rows]

    def withdraw(
        self,
        settlement_id: str,
        author_id: str,
        amount_cents: int,
        payout_method: str,
        holder_matches_real_name: bool,
    ) -> Withdrawal:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._settlements)
                    .where(self._settlements.c.id == settlement_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(settlement_id)
            settlement = self._settlement_from_row(row)
            if (
                settlement.author_id != author_id
                or settlement.status is not SettlementStatus.WITHDRAWABLE
            ):
                raise ValueError("SETTLEMENT_NOT_WITHDRAWABLE")
            if (
                amount_cents < 1000
                or amount_cents > settlement.amount_cents - settlement.withdrawn_cents
            ):
                raise ValueError("INVALID_WITHDRAWAL_AMOUNT")
            if not holder_matches_real_name:
                raise ValueError("PAYOUT_HOLDER_MISMATCH")
            withdrawal = Withdrawal(
                _id("WD"), settlement_id, author_id, amount_cents, payout_method
            )
            connection.execute(
                self._withdrawals.insert().values(
                    id=withdrawal.id,
                    settlement_id=withdrawal.settlement_id,
                    author_id=withdrawal.author_id,
                    amount_cents=withdrawal.amount_cents,
                    payout_method=withdrawal.payout_method,
                    status=withdrawal.status.value,
                    created_at=datetime.now(UTC),
                    **self._withdrawal_review_values(
                        risk_status="PENDING",
                        finance_status="PENDING",
                        second_factor_verified=holder_matches_real_name,
                        payout_destination=payout_method,
                    ),
                )
            )
            connection.execute(
                self._settlements.update()
                .where(self._settlements.c.id == settlement_id)
                .values(withdrawn_cents=settlement.withdrawn_cents + amount_cents)
            )
            self._append_outbox(
                connection,
                "WithdrawalRequested",
                withdrawal.id,
                {"author_id": author_id, "amount_cents": amount_cents},
            )
            return withdrawal

    def approve_withdrawal_risk(self, withdrawal_id: str, reviewer_id: str) -> Withdrawal:
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValueError("REVIEWER_ID_REQUIRED")
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            if "risk_status" not in self._withdrawals.c:
                raise ValueError("PAYOUT_REVIEW_NOT_CONFIGURED")
            if row["status"] != WithdrawalStatus.PENDING.value:
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            if row["risk_status"] not in ("PENDING", "APPROVED"):
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            if row["risk_status"] == "APPROVED":
                return self._withdrawal_from_row(cast(Mapping[str, Any], row))
            if row.get("finance_reviewer_id") == reviewer_id:
                raise ValueError("MAKER_CHECKER_REQUIRED")
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == withdrawal_id)
                .values(
                    **_present(
                        self._withdrawals,
                        {"risk_status": "APPROVED", "risk_reviewer_id": reviewer_id},
                    )
                )
            )
            return self._withdrawal_from_row(
                {**dict(row), "risk_status": "APPROVED", "risk_reviewer_id": reviewer_id}
            )

    def approve_withdrawal_finance(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValueError("REVIEWER_ID_REQUIRED")
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            existing = self._payout_row_for_withdrawal(connection, withdrawal_id, lock=True)
            if existing is not None:
                return self._payout_from_row(existing)
            if "risk_status" not in self._withdrawals.c:
                raise ValueError("PAYOUT_REVIEW_NOT_CONFIGURED")
            if row["risk_status"] != "APPROVED":
                raise ValueError("PAYOUT_REVIEW_REQUIRED")
            if row.get("risk_reviewer_id") == reviewer_id:
                raise ValueError("MAKER_CHECKER_REQUIRED")
            if row["status"] != WithdrawalStatus.PENDING.value:
                raise ValueError("WITHDRAWAL_NOT_REVIEWABLE")
            if self.payout_provider is None or not self.payout_provider_secret:
                raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == withdrawal_id)
                .values(
                    **_present(
                        self._withdrawals,
                        {"finance_status": "APPROVED", "finance_reviewer_id": reviewer_id},
                    )
                )
            )
            return self._create_payout_order_in_connection(connection, row)

    def create_payout_order(self, withdrawal_id: str, reviewer_id: str) -> PayoutOrder:
        """Create a provider order only after both review facts are present."""
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValueError("REVIEWER_ID_REQUIRED")
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        with self.engine.begin() as connection:
            row = self._withdrawal_row(connection, withdrawal_id, lock=True)
            existing = self._payout_row_for_withdrawal(connection, withdrawal_id, lock=True)
            if existing is not None:
                return self._payout_from_row(existing)
            if (
                "risk_status" not in self._withdrawals.c
                or row["risk_status"] != "APPROVED"
                or row["finance_status"] != "APPROVED"
            ):
                raise ValueError("PAYOUT_REVIEW_REQUIRED")
            if row.get("risk_reviewer_id") == reviewer_id:
                raise ValueError("MAKER_CHECKER_REQUIRED")
            if self.payout_provider is None or not self.payout_provider_secret:
                raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
            return self._create_payout_order_in_connection(connection, row)

    def handle_payout_provider_event(
        self, event: ProviderEvent, *, now: datetime | None = None
    ) -> PayoutOrder:
        if self._payout_orders is None:
            raise ValueError("PAYOUT_NOT_CONFIGURED")
        if self.payout_provider is None or not self.payout_provider_secret:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        if event.event_type != "PAYOUT":
            raise ValueError("PAYOUT_EVENT_TYPE_INVALID")
        if (
            not isinstance(event.provider_transaction_id, str)
            or not event.provider_transaction_id.strip()
        ):
            raise ValueError("PAYOUT_PROVIDER_TRANSACTION_ID_REQUIRED")
        provider_name = getattr(self.payout_provider, "provider_name", event.provider)
        if event.provider != provider_name:
            raise ValueError("PAYOUT_PROVIDER_MISMATCH")
        if not event.verify_signature(self.payout_provider_secret):
            raise ValueError("PAYOUT_SIGNATURE_INVALID")
        current = _utc(now or datetime.now(UTC))
        if _utc(event.available_at) > current:
            raise ValueError("PAYOUT_EVENT_NOT_AVAILABLE")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._payout_orders)
                    .where(self._payout_orders.c.payout_no == event.reference_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueError("PAYOUT_NOT_FOUND")
            payout = self._payout_from_row(row)
            if payout.amount_cents != event.amount_cents or payout.currency != event.currency:
                raise ValueError("PAYOUT_AMOUNT_MISMATCH")
            if payout.provider_event_id == event.event_id:
                return payout
            if payout.status is not PayoutStatus.PROCESSING:
                raise ValueError("PAYOUT_STATE_CONFLICT")
            if (
                payout.provider_transaction_id is not None
                and payout.provider_transaction_id != event.provider_transaction_id
            ):
                raise ValueError("PAYOUT_PROVIDER_TRANSACTION_CONFLICT")
            provider_transaction_column = getattr(
                self._payout_orders.c, "provider_transaction_id", None
            )
            if provider_transaction_column is not None:
                transaction_conflict = connection.execute(
                    sa.select(self._payout_orders.c.id)
                    .where(
                        self._payout_orders.c.provider == event.provider,
                        provider_transaction_column == event.provider_transaction_id,
                        self._payout_orders.c.id != payout.id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if transaction_conflict is not None:
                    raise ValueError("PAYOUT_PROVIDER_TRANSACTION_CONFLICT")
            event_conflict = connection.execute(
                sa.select(self._payout_orders.c.id)
                .where(
                    self._payout_orders.c.provider == event.provider,
                    self._payout_orders.c.provider_event_id == event.event_id,
                    self._payout_orders.c.id != payout.id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if event_conflict is not None:
                raise ValueError("PAYOUT_PROVIDER_EVENT_CONFLICT")
            updated_status = PayoutStatus(event.status.value)
            updated_at = datetime.now(UTC)
            try:
                connection.execute(
                    self._payout_orders.update()
                    .where(self._payout_orders.c.id == payout.id)
                    .values(
                        **_present(
                            self._payout_orders,
                            {
                                "status": updated_status.value,
                                "provider_event_id": event.event_id,
                                "provider_transaction_id": event.provider_transaction_id,
                                "updated_at": updated_at,
                            },
                        )
                    )
                )
            except sa.exc.IntegrityError as exc:
                raise ValueError("PAYOUT_PROVIDER_TRANSACTION_CONFLICT") from exc
            if updated_status is PayoutStatus.SUCCESS:
                withdrawal_status = WithdrawalStatus.PAID.value
            elif updated_status in (
                PayoutStatus.FAILED,
                PayoutStatus.REJECTED,
                PayoutStatus.TIMEOUT,
            ):
                withdrawal_status = WithdrawalStatus.FAILED.value
            else:
                withdrawal_status = WithdrawalStatus.PENDING.value
            connection.execute(
                self._withdrawals.update()
                .where(self._withdrawals.c.id == payout.withdrawal_id)
                .values(status=withdrawal_status)
            )
            self._append_outbox(
                connection,
                "PayoutSucceeded"
                if updated_status is PayoutStatus.SUCCESS
                else "PayoutStatusChanged",
                payout.payout_no,
                {"withdrawal_id": payout.withdrawal_id, "status": updated_status.value},
            )
            return PayoutOrder(
                payout.id,
                payout.withdrawal_id,
                payout.payout_no,
                payout.provider,
                payout.amount_cents,
                payout.currency,
                payout.destination,
                updated_status,
                event.event_id,
                event.provider_transaction_id,
            )

    def _create_payout_order_in_connection(
        self, connection: Connection, withdrawal_row: sa.RowMapping
    ) -> PayoutOrder:
        if self._payout_orders is None or self.payout_provider is None:
            raise ValueError("PAYOUT_PROVIDER_NOT_CONFIGURED")
        destination = str(
            withdrawal_row.get("payout_destination") or withdrawal_row["payout_method"]
        )
        payout_no = f"PO-{uuid4().hex}"
        payout = self.payout_provider.create_payout(
            payout_no,
            int(withdrawal_row["amount_cents"]),
            "CNY",
            destination,
        )
        now = datetime.now(UTC)
        result = PayoutOrder(
            id=_id("PAYOUT"),
            withdrawal_id=str(withdrawal_row["id"]),
            payout_no=payout.payout_no,
            provider=payout.provider,
            amount_cents=payout.amount_cents,
            currency=payout.currency,
            destination=payout.destination,
        )
        connection.execute(
            self._payout_orders.insert().values(
                id=result.id,
                withdrawal_id=result.withdrawal_id,
                payout_no=result.payout_no,
                provider=result.provider,
                amount_cents=result.amount_cents,
                currency=result.currency,
                destination=result.destination,
                status=result.status.value,
                provider_event_id=None,
                provider_transaction_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        self._append_outbox(
            connection,
            "PayoutOrderCreated",
            result.payout_no,
            {"withdrawal_id": result.withdrawal_id, "amount_cents": result.amount_cents},
        )
        return result

    def payout_details(self, payout_no: str) -> tuple[int, str, str]:
        if self._payout_orders is None or not payout_no.strip():
            raise ValueError("PAYOUT_NOT_FOUND")
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(
                        self._payout_orders.c.amount_cents,
                        self._payout_orders.c.currency,
                        self._payout_orders.c.destination,
                    ).where(self._payout_orders.c.payout_no == payout_no)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("PAYOUT_NOT_FOUND")
        return int(row["amount_cents"]), str(row["currency"]), str(row["destination"])

    def _withdrawal_row(
        self, connection: Connection, withdrawal_id: str, *, lock: bool = False
    ) -> sa.RowMapping:
        query = sa.select(self._withdrawals).where(self._withdrawals.c.id == withdrawal_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(withdrawal_id)
        return row

    def _payout_row_for_withdrawal(
        self, connection: Connection, withdrawal_id: str, *, lock: bool = False
    ) -> sa.RowMapping | None:
        if self._payout_orders is None:
            return None
        query = sa.select(self._payout_orders).where(
            self._payout_orders.c.withdrawal_id == withdrawal_id
        )
        if lock:
            query = query.with_for_update()
        return connection.execute(query).mappings().one_or_none()

    @staticmethod
    def _payout_from_row(row: sa.RowMapping) -> PayoutOrder:
        return PayoutOrder(
            id=str(row["id"]),
            withdrawal_id=str(row["withdrawal_id"]),
            payout_no=str(row["payout_no"]),
            provider=str(row["provider"]),
            amount_cents=int(row["amount_cents"]),
            currency=str(row["currency"]),
            destination=str(row["destination"]),
            status=PayoutStatus(str(row["status"])),
            provider_event_id=(
                str(row["provider_event_id"]) if row["provider_event_id"] is not None else None
            ),
            provider_transaction_id=(
                str(row["provider_transaction_id"])
                if row.get("provider_transaction_id") is not None
                else None
            ),
        )

    @staticmethod
    def _withdrawal_from_row(row: Mapping[str, Any]) -> Withdrawal:
        return Withdrawal(
            id=str(row["id"]),
            settlement_id=str(row["settlement_id"]),
            author_id=str(row["author_id"]),
            amount_cents=int(row["amount_cents"]),
            payout_method=str(row["payout_method"]),
            status=WithdrawalStatus(str(row["status"])),
        )

    def _withdrawal_review_values(self, **values: object) -> dict[str, object]:
        return {name: value for name, value in values.items() if name in self._withdrawals.c}

    def _append_outbox(
        self,
        connection: Connection,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        if self._outbox is None:
            return
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "id": f"OUTBOX_{uuid4().hex}",
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "attempts": 0,
            "created_at": now,
        }
        optional = {
            "status": "NEW",
            "available_at": None,
            "locked_by": None,
            "locked_at": None,
            "last_error": None,
            "processed_at": None,
        }
        values.update({name: value for name, value in optional.items() if name in self._outbox.c})
        connection.execute(self._outbox.insert().values(**values))

    def chargeback(self, source_ref: str, amount_cents: int) -> Chargeback:
        if amount_cents <= 0:
            raise ValueError("INVALID_CHARGEBACK_AMOUNT")
        with self.engine.begin() as connection:
            revenue_row = (
                connection.execute(
                    sa.select(self._revenue)
                    .where(self._revenue.c.source_ref == source_ref)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if revenue_row is None:
                raise KeyError(source_ref)
            already_recovered = connection.execute(
                sa.select(
                    sa.func.coalesce(sa.func.sum(self._chargebacks.c.recovered_cents), 0)
                ).where(self._chargebacks.c.source_ref == source_ref)
            ).scalar_one()
            recovered = min(
                max(0, int(revenue_row["author_cents"]) - int(already_recovered)), amount_cents
            )
            chargeback = Chargeback(_id("CB"), source_ref, amount_cents, recovered)
            connection.execute(
                self._chargebacks.insert().values(
                    id=chargeback.id,
                    source_ref=chargeback.source_ref,
                    amount_cents=chargeback.amount_cents,
                    recovered_cents=chargeback.recovered_cents,
                    created_at=datetime.now(UTC),
                )
            )
            if recovered < amount_cents:
                connection.execute(
                    self._claims.insert().values(
                        id=_id("CLM"),
                        author_id=str(revenue_row["author_id"]),
                        chargeback_id=chargeback.id,
                        amount_cents=amount_cents - recovered,
                        status="OPEN",
                        created_at=datetime.now(UTC),
                    )
                )
            return chargeback

    def _contract_from_connection(
        self, connection: Connection, contract_id: str, *, lock: bool = False
    ) -> Contract:
        query = sa.select(self._contracts).where(self._contracts.c.id == contract_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(contract_id)
        versions = connection.execute(
            sa.select(self._contract_versions.c.id)
            .where(self._contract_versions.c.contract_id == contract_id)
            .order_by(self._contract_versions.c.version)
        ).scalars()
        # Select the reflected row so old test/legacy schemas that predate the
        # optional policy/document columns still produce valid SQL.  Selecting
        # an empty dynamic column list would compile to ``SELECT FROM ...``.
        latest = (
            connection.execute(
                sa.select(self._contract_versions)
                .where(self._contract_versions.c.contract_id == contract_id)
                .order_by(self._contract_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return Contract(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            book_id=str(row["book_id"]),
            status=ContractStatus(str(row["status"])),
            version_ids=[str(version_id) for version_id in versions],
            policy_version=str(latest.get("policy_version") if latest is not None else None)
            or DEFAULT_POLICY_VERSION,
            document_text=str(latest.get("document_text") or "") if latest else "",
            document_hash=str(latest.get("document_hash") or "") if latest else "",
            signed_by=str(row.get("signed_by")) if row.get("signed_by") else None,
            signed_at=(_utc(row["signed_at"]) if row.get("signed_at") else None),
            signature_hash=(str(row["signature_hash"]) if row.get("signature_hash") else None),
        )

    def _contract_policy_version(self, connection: Connection, contract_id: str) -> str:
        column = getattr(self._contract_versions.c, "policy_version", None)
        if column is None:
            return DEFAULT_POLICY_VERSION
        value = connection.execute(
            sa.select(column)
            .where(self._contract_versions.c.contract_id == contract_id)
            .order_by(self._contract_versions.c.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return str(value or DEFAULT_POLICY_VERSION)

    def _revenue_row(
        self, connection: Connection, revenue_id: str, *, lock: bool = False
    ) -> sa.RowMapping:
        query = sa.select(self._revenue).where(self._revenue.c.id == revenue_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().one_or_none()
        if row is None:
            raise KeyError(revenue_id)
        return row

    @staticmethod
    def _revenue_from_row(row: sa.RowMapping) -> RevenueEntry:
        return RevenueEntry(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            source=str(row["source"]),
            source_ref=str(row["source_ref"]),
            gross_cents=int(row["gross_cents"]),
            author_cents=int(row["author_cents"]),
            status=RevenueStatus(str(row["status"])),
            settlement_id=str(row["settlement_id"]) if row["settlement_id"] else None,
            tax_cents=int(row.get("tax_cents") or 0),
            net_author_cents=(
                int(row["net_author_cents"])
                if row.get("net_author_cents") is not None
                else int(row["author_cents"])
            ),
            policy_version=(str(row["policy_version"]) if row.get("policy_version") else None),
            created_at=_utc(row["created_at"]),
        )

    @staticmethod
    def _settlement_from_row(row: sa.RowMapping) -> Settlement:
        return Settlement(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            period=str(row["period"]),
            amount_cents=int(row["amount_cents"]),
            status=SettlementStatus(str(row["status"])),
            withdrawn_cents=int(row["withdrawn_cents"]),
            gross_cents=int(row.get("gross_cents") or row["amount_cents"]),
            tax_cents=int(row.get("tax_cents") or 0),
        )

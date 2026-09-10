"""SQLAlchemy adapter for privacy, governance, reconciliation, and outbox facts."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from novel_platform.modules.governance.application import GovernanceService
from novel_platform.modules.governance.domain import (
    AgreementAcceptance,
    Emergency,
    Invoice,
    OutboxEvent,
    OutboxStatus,
    ParameterStatus,
    ParameterVersion,
    PaymentCreditPending,
    PrivacyRequest,
    ReconciliationBatch,
    ReconciliationDifference,
    ReconciliationItem,
    ReconciliationStatus,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class SqlGovernanceService(GovernanceService):
    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        metadata = sa.MetaData()
        self._privacy_table: Any = sa.Table("privacy_requests", metadata, autoload_with=engine)
        self._agreements_table: Any = sa.Table(
            "agreement_acceptances", metadata, autoload_with=engine
        )
        self._parameters_table: Any = sa.Table("parameter_versions", metadata, autoload_with=engine)
        self._pending_table: Any = sa.Table(
            "payment_credit_pending", metadata, autoload_with=engine
        )
        self._batches_table: Any = sa.Table(
            "reconciliation_batches", metadata, autoload_with=engine
        )
        self._items_table: Any = sa.Table("reconciliation_items", metadata, autoload_with=engine)
        self._emergencies_table: Any = sa.Table(
            "platform_emergencies", metadata, autoload_with=engine
        )
        self._outbox_table: Any = sa.Table("outbox_events", metadata, autoload_with=engine)
        self._outbox_lifecycle = all(
            name in self._outbox_table.c
            for name in (
                "status",
                "available_at",
                "locked_by",
                "locked_at",
                "last_error",
                "processed_at",
            )
        )
        self._invoices_table: Any = sa.Table("invoice_requests", metadata, autoload_with=engine)
        self._reload()

    def _reload(self) -> None:
        with self.engine.begin() as connection:
            self._privacy = {
                (str(row["account_id"]), str(row["kind"])): PrivacyRequest(
                    str(row["id"]), str(row["account_id"]), str(row["kind"]), str(row["status"])
                )
                for row in connection.execute(sa.select(self._privacy_table)).mappings()
            }
            self._agreements = {
                (
                    str(row["account_id"]),
                    str(row["agreement_code"]),
                    str(row["version"]),
                ): AgreementAcceptance(
                    str(row["account_id"]),
                    str(row["agreement_code"]),
                    str(row["version"]),
                )
                for row in connection.execute(sa.select(self._agreements_table)).mappings()
            }
            self._parameters = {
                str(row["id"]): ParameterVersion(
                    str(row["id"]),
                    str(row["parameter_key"]),
                    str(row["value_text"]),
                    str(row["maker_id"]),
                    ParameterStatus(str(row["status"])),
                    str(row["checker_id"]) if row["checker_id"] is not None else None,
                    row["effective_at"].isoformat() if row["effective_at"] is not None else None,
                )
                for row in connection.execute(sa.select(self._parameters_table)).mappings()
            }
            self._pending = {
                str(row["payment_id"]): self._pending_from_row(row)
                for row in connection.execute(sa.select(self._pending_table)).mappings()
            }
            self._batches = {
                str(row["id"]): ReconciliationBatch(
                    str(row["id"]),
                    str(row["business_date"]),
                    ReconciliationStatus(str(row["status"])),
                )
                for row in connection.execute(sa.select(self._batches_table)).mappings()
            }
            for row in connection.execute(sa.select(self._items_table)).mappings():
                batch = self._batches.get(str(row["batch_id"]))
                if batch is not None:
                    batch.items.append(
                        ReconciliationItem(
                            str(row["id"]),
                            str(row["batch_id"]),
                            str(row["reference"]),
                            ReconciliationDifference(str(row["difference"])),
                            int(row["amount_cents"]),
                        )
                    )
            self._emergencies = {
                str(row["id"]): Emergency(
                    str(row["id"]),
                    str(row["reason"]),
                    set(json.loads(str(row["features_json"]))),
                    str(row["operator_id"]),
                    str(row["status"]),
                )
                for row in connection.execute(sa.select(self._emergencies_table)).mappings()
            }
            self._outbox = {}
            for row in connection.execute(sa.select(self._outbox_table)).mappings():
                self._outbox[str(row["id"])] = self._event_from_row(row)
            self._invoices = {
                str(row["id"]): Invoice(
                    str(row["id"]),
                    str(row["account_id"]),
                    int(row["amount_cents"]),
                    str(row["title"]),
                    str(row["tax_id"]),
                    str(row["status"]),
                    str(row["document_id"]) if row["document_id"] is not None else None,
                    str(row["reversal_document_id"])
                    if row["reversal_document_id"] is not None
                    else None,
                )
                for row in connection.execute(sa.select(self._invoices_table)).mappings()
            }

    def open_privacy_request(self, account_id: str, kind: str) -> PrivacyRequest:
        if not account_id.strip() or not kind.strip():
            raise ValueError("PRIVACY_REQUEST_INVALID")
        key = (account_id, kind.upper())
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._privacy_table).where(
                        self._privacy_table.c.account_id == key[0],
                        self._privacy_table.c.kind == key[1],
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                return PrivacyRequest(str(row["id"]), key[0], key[1], str(row["status"]))
            request = PrivacyRequest(_id("PRV"), account_id, key[1])
            connection.execute(
                self._privacy_table.insert().values(
                    id=request.id,
                    account_id=request.account_id,
                    kind=request.kind,
                    status=request.status,
                    created_at=datetime.now(UTC),
                )
            )
            return request

    def accept_agreement(
        self, account_id: str, agreement_code: str, version: str
    ) -> AgreementAcceptance:
        if not account_id.strip() or not agreement_code.strip() or not version.strip():
            raise ValueError("AGREEMENT_VERSION_REQUIRED")
        acceptance = AgreementAcceptance(account_id, agreement_code, version)
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._agreements_table.c.account_id).where(
                    self._agreements_table.c.account_id == account_id,
                    self._agreements_table.c.agreement_code == agreement_code,
                    self._agreements_table.c.version == version,
                )
            ).scalar_one_or_none()
            if exists is None:
                agreement_id = connection.execute(
                    sa.select(sa.func.coalesce(sa.func.max(self._agreements_table.c.id), 0) + 1)
                ).scalar_one()
                connection.execute(
                    self._agreements_table.insert().values(
                        id=agreement_id,
                        account_id=account_id,
                        agreement_code=agreement_code,
                        version=version,
                        created_at=datetime.now(UTC),
                    )
                )
        return acceptance

    def draft_parameter(self, key: str, value: str, maker_id: str) -> ParameterVersion:
        if not key.strip() or not value.strip() or not maker_id.strip():
            raise ValueError("PARAMETER_DRAFT_INVALID")
        parameter = ParameterVersion(_id("PARAM"), key, value, maker_id)
        with self.engine.begin() as connection:
            connection.execute(
                self._parameters_table.insert().values(
                    id=parameter.id,
                    parameter_key=parameter.key,
                    value_text=parameter.value,
                    maker_id=parameter.maker_id,
                    checker_id=None,
                    status=parameter.status.value,
                    effective_at=None,
                    created_at=datetime.now(UTC),
                )
            )
        self._parameters[parameter.id] = parameter
        return parameter

    def approve_parameter(self, parameter_id: str, checker_id: str) -> ParameterVersion:
        parameter = self._parameters[parameter_id]
        if parameter.maker_id == checker_id:
            raise ValueError("PARAMETER_MAKER_CHECKER_SEPARATION")
        with self.engine.begin() as connection:
            connection.execute(
                self._parameters_table.update()
                .where(self._parameters_table.c.id == parameter_id)
                .values(status=ParameterStatus.APPROVED.value, checker_id=checker_id)
            )
        parameter.status = ParameterStatus.APPROVED
        parameter.checker_id = checker_id
        return parameter

    def activate_parameter(self, parameter_id: str, effective_at: str) -> ParameterVersion:
        parameter = self._parameters[parameter_id]
        if parameter.status is not ParameterStatus.APPROVED or not parameter.checker_id:
            raise ValueError("PARAMETER_CHECKER_REQUIRED")
        if not effective_at.strip():
            raise ValueError("PARAMETER_EFFECTIVE_AT_REQUIRED")
        effective = _datetime(effective_at)
        with self.engine.begin() as connection:
            connection.execute(
                self._parameters_table.update()
                .where(self._parameters_table.c.id == parameter_id)
                .values(status=ParameterStatus.ACTIVE.value, effective_at=effective)
            )
        parameter.status = ParameterStatus.ACTIVE
        parameter.effective_at = effective_at
        return parameter

    def record_payment_credit_failure(
        self, payment_id: str, account_id: str, amount_cents: int
    ) -> PaymentCreditPending:
        if not payment_id.strip() or not account_id.strip() or amount_cents <= 0:
            raise ValueError("PAYMENT_AMOUNT_INVALID")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._pending_table).where(
                        self._pending_table.c.payment_id == payment_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                existing = self._pending_from_row(row)
                if existing.account_id != account_id or existing.amount_cents != amount_cents:
                    raise ValueError("PAYMENT_CREDIT_CONFLICT")
                self._pending[payment_id] = existing
                return existing
            pending = PaymentCreditPending(_id("CREDIT"), payment_id, account_id, amount_cents)
            values: dict[str, object] = {
                "id": pending.id,
                "payment_id": pending.payment_id,
                "account_id": pending.account_id,
                "amount_cents": pending.amount_cents,
                "status": pending.status,
                "created_at": datetime.now(UTC),
            }
            self._set_pending_optional_values(values, attempts=0)
            connection.execute(self._pending_table.insert().values(**values))
            self._pending[payment_id] = pending
            return pending

    def list_payment_credit_pending(
        self, status: str | None = None
    ) -> tuple[PaymentCreditPending, ...]:
        normalized = status.strip().upper() if status else None
        if normalized not in {
            None,
            "CREDIT_PENDING",
            "REPAIRING",
            "REPAIR_REQUIRED",
            "RESOLVED",
        }:
            raise ValueError("PAYMENT_CREDIT_STATUS_INVALID")
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._pending_table).order_by(self._pending_table.c.id)
            ).mappings()
            result = tuple(
                pending
                for row in rows
                for pending in (self._pending_from_row(row),)
                if (
                    normalized is None
                    and pending.status in {"CREDIT_PENDING", "REPAIRING", "REPAIR_REQUIRED"}
                    or normalized is not None
                    and pending.status == normalized
                )
            )
        self._pending.update({item.payment_id: item for item in result})
        return result

    def retry_payment_credit(self, payment_id: str, actor_id: str) -> PaymentCreditPending:
        if not actor_id.strip():
            raise ValueError("PAYMENT_CREDIT_ACTOR_REQUIRED")
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._pending_table)
                    .where(self._pending_table.c.payment_id == payment_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(payment_id)
            pending = self._pending_from_row(row)
            if pending.status == "RESOLVED":
                return pending
            if pending.status == "REPAIRING":
                stale = pending.last_attempted_at is None or pending.last_attempted_at <= (
                    now - timedelta(minutes=5)
                )
                if not stale:
                    raise ValueError("PAYMENT_CREDIT_REPAIR_IN_PROGRESS")
            values: dict[str, object] = {"status": "REPAIRING"}
            self._set_pending_optional_values(
                values,
                attempts=pending.attempts + 1,
                last_attempted_at=now,
                repair_actor_id=actor_id.strip(),
                last_error=None,
            )
            connection.execute(
                self._pending_table.update()
                .where(self._pending_table.c.payment_id == payment_id)
                .values(**values)
            )
            pending = PaymentCreditPending(
                pending.id,
                pending.payment_id,
                pending.account_id,
                pending.amount_cents,
                "REPAIRING",
                pending.attempts + 1,
                None,
                now,
                pending.resolved_at,
                actor_id.strip(),
            )
        repair = self.repair_payment_credit
        error: str | None = None
        try:
            if not callable(repair):
                raise ValueError("CREDIT_REPAIR_PORT_UNAVAILABLE")  # noqa: TRY004
            if repair(payment_id) is False:
                raise RuntimeError("CREDIT_REPAIR_REJECTED")
        except Exception as exc:  # noqa: BLE001 - preserve repair state for every failure
            error = str(exc) or type(exc).__name__
        status = "REPAIR_REQUIRED" if error is not None else "RESOLVED"
        resolved_at = now if error is None else None
        with self.engine.begin() as connection:
            final_values: dict[str, object] = {"status": status}
            self._set_pending_optional_values(
                final_values, last_error=error, resolved_at=resolved_at
            )
            connection.execute(
                self._pending_table.update()
                .where(
                    self._pending_table.c.payment_id == payment_id,
                    self._pending_table.c.status == "REPAIRING",
                )
                .values(**final_values)
            )
        pending = PaymentCreditPending(
            pending.id,
            pending.payment_id,
            pending.account_id,
            pending.amount_cents,
            status,
            pending.attempts,
            error,
            pending.last_attempted_at,
            resolved_at,
            pending.repair_actor_id,
        )
        self._pending[payment_id] = pending
        return pending

    def auto_repair_payment_credits(self, *, limit: int = 10) -> tuple[PaymentCreditPending, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("PAYMENT_CREDIT_REPAIR_LIMIT_INVALID")
        pending = self.list_payment_credit_pending("CREDIT_PENDING")[:limit]
        return tuple(
            self.retry_payment_credit(item.payment_id, "system-credit-repair") for item in pending
        )

    def _set_pending_optional_values(self, values: dict[str, object], **kwargs: object) -> None:
        for name, value in kwargs.items():
            if name in self._pending_table.c:
                values[name] = value

    @staticmethod
    def _pending_from_row(row: sa.RowMapping) -> PaymentCreditPending:
        def timestamp(name: str) -> datetime | None:
            value = cast(datetime | None, row.get(name))
            if value is None:
                return None
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

        return PaymentCreditPending(
            str(row["id"]),
            str(row["payment_id"]),
            str(row["account_id"]),
            int(row["amount_cents"]),
            str(row["status"]),
            int(row.get("attempts") or 0),
            str(row["last_error"]) if row.get("last_error") is not None else None,
            timestamp("last_attempted_at"),
            timestamp("resolved_at"),
            str(row["repair_actor_id"]) if row.get("repair_actor_id") is not None else None,
        )

    def open_reconciliation(self, business_date: str) -> ReconciliationBatch:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._batches_table).where(
                        self._batches_table.c.business_date == date.fromisoformat(business_date)
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                batch = ReconciliationBatch(
                    str(row["id"]), business_date, ReconciliationStatus(str(row["status"]))
                )
                batch.items.extend(
                    ReconciliationItem(
                        str(item["id"]),
                        str(item["batch_id"]),
                        str(item["reference"]),
                        ReconciliationDifference(str(item["difference"])),
                        int(item["amount_cents"]),
                    )
                    for item in connection.execute(
                        sa.select(self._items_table).where(
                            self._items_table.c.batch_id == row["id"]
                        )
                    ).mappings()
                )
                return batch
            batch = ReconciliationBatch(_id("RECON"), business_date)
            connection.execute(
                self._batches_table.insert().values(
                    id=batch.id,
                    business_date=date.fromisoformat(business_date),
                    status=batch.status.value,
                    created_at=datetime.now(UTC),
                )
            )
            self._batches[batch.id] = batch
            return batch

    def add_reconciliation_item(
        self,
        batch_id: str,
        reference: str,
        difference: ReconciliationDifference,
        amount_cents: int,
    ) -> ReconciliationItem:
        if amount_cents < 0:
            raise ValueError("RECONCILIATION_AMOUNT_INVALID")
        item = ReconciliationItem(_id("RECON_ITEM"), batch_id, reference, difference, amount_cents)
        with self.engine.begin() as connection:
            exists = connection.execute(
                sa.select(self._batches_table.c.id).where(self._batches_table.c.id == batch_id)
            ).scalar_one_or_none()
            if exists is None:
                raise KeyError(batch_id)
            connection.execute(
                self._items_table.insert().values(
                    id=item.id,
                    batch_id=item.batch_id,
                    reference=item.reference,
                    difference=item.difference.value,
                    amount_cents=item.amount_cents,
                    created_at=datetime.now(UTC),
                )
            )
        self._batches[batch_id].items.append(item)
        return item

    def reconciliation_batch(self, batch_id: str) -> ReconciliationBatch:
        return self._batches[batch_id]

    def list_reconciliation_batches(
        self, status: str | None = None
    ) -> tuple[ReconciliationBatch, ...]:
        normalized = status.strip().upper() if status else None
        allowed = {item.value for item in ReconciliationStatus}
        if normalized not in {None, *allowed}:
            raise ValueError("RECONCILIATION_STATUS_INVALID")
        with self.engine.begin() as connection:
            batches = {
                str(row["id"]): ReconciliationBatch(
                    str(row["id"]),
                    str(row["business_date"]),
                    ReconciliationStatus(str(row["status"])),
                )
                for row in connection.execute(
                    sa.select(self._batches_table).order_by(
                        self._batches_table.c.business_date.desc(),
                        self._batches_table.c.id.desc(),
                    )
                ).mappings()
                if normalized is None or str(row["status"]) == normalized
            }
            if batches:
                rows = connection.execute(
                    sa.select(self._items_table).where(
                        self._items_table.c.batch_id.in_(tuple(batches))
                    )
                ).mappings()
                for row in rows:
                    batches[str(row["batch_id"])].items.append(
                        ReconciliationItem(
                            str(row["id"]),
                            str(row["batch_id"]),
                            str(row["reference"]),
                            ReconciliationDifference(str(row["difference"])),
                            int(row["amount_cents"]),
                        )
                    )
        self._batches.update(batches)
        return tuple(batches.values())

    def mark_reconciliation_repaired(self, batch_id: str, operator_id: str) -> ReconciliationBatch:
        if not operator_id.strip():
            raise ValueError("RECONCILIATION_OPERATOR_REQUIRED")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._batches_table)
                    .where(self._batches_table.c.id == batch_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(batch_id)
            current = ReconciliationStatus(str(row["status"]))
            if current is ReconciliationStatus.OPEN:
                connection.execute(
                    self._batches_table.update()
                    .where(self._batches_table.c.id == batch_id)
                    .values(status=ReconciliationStatus.REPAIRED.value)
                )
                current = ReconciliationStatus.REPAIRED
        batch = self._batches.get(batch_id) or ReconciliationBatch(
            batch_id, str(row["business_date"]), current
        )
        batch.status = current
        self._batches[batch_id] = batch
        return batch

    def close_reconciliation(self, batch_id: str, operator_id: str) -> ReconciliationBatch:
        if not operator_id.strip():
            raise ValueError("RECONCILIATION_OPERATOR_REQUIRED")
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._batches_table)
                    .where(self._batches_table.c.id == batch_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(batch_id)
            current = ReconciliationStatus(str(row["status"]))
            if current is ReconciliationStatus.OPEN:
                raise ValueError("RECONCILIATION_REPAIR_REQUIRED")
            if current is ReconciliationStatus.REPAIRED:
                connection.execute(
                    self._batches_table.update()
                    .where(self._batches_table.c.id == batch_id)
                    .values(status=ReconciliationStatus.CLOSED.value)
                )
                current = ReconciliationStatus.CLOSED
        batch = self._batches.get(batch_id) or ReconciliationBatch(
            batch_id, str(row["business_date"]), current
        )
        batch.status = current
        self._batches[batch_id] = batch
        return batch

    def pause_features(self, reason: str, features: set[str], operator_id: str) -> Emergency:
        if not reason.strip() or not features or not operator_id.strip():
            raise ValueError("EMERGENCY_INVALID")
        emergency = Emergency(_id("EMG"), reason.strip(), set(features), operator_id)
        with self.engine.begin() as connection:
            connection.execute(
                self._emergencies_table.insert().values(
                    id=emergency.id,
                    reason=emergency.reason,
                    features_json=json.dumps(sorted(emergency.features)),
                    operator_id=emergency.operator_id,
                    status=emergency.status,
                    created_at=datetime.now(UTC),
                )
            )
        self._emergencies[emergency.id] = emergency
        return emergency

    def resolve_emergency(self, emergency_id: str, operator_id: str) -> Emergency:
        emergency = self._emergencies[emergency_id]
        if not operator_id.strip():
            raise ValueError("EMERGENCY_OPERATOR_REQUIRED")
        with self.engine.begin() as connection:
            connection.execute(
                self._emergencies_table.update()
                .where(self._emergencies_table.c.id == emergency_id)
                .values(status="RESOLVED")
            )
        emergency.status = "RESOLVED"
        return emergency

    def is_feature_paused(self, feature: str) -> bool:
        with self.engine.begin() as connection:
            rows = connection.execute(
                sa.select(self._emergencies_table.c.features_json).where(
                    self._emergencies_table.c.status == "ACTIVE"
                )
            )
            return any(feature in json.loads(str(row[0])) for row in rows)

    def enqueue_outbox(
        self, event_type: str, aggregate_id: str, payload: dict[str, object]
    ) -> OutboxEvent:
        event = OutboxEvent(_id("OUTBOX"), event_type, aggregate_id, dict(payload))
        values: dict[str, object] = {
            "id": event.id,
            "event_type": event.event_type,
            "aggregate_id": event.aggregate_id,
            "payload_json": json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
            "attempts": event.attempts,
            "created_at": datetime.now(UTC),
        }
        if self._outbox_lifecycle:
            values.update(status=event.status.value, available_at=None, locked_by=None)
            values.update(locked_at=None, last_error=None, processed_at=None)
        with self.engine.begin() as connection:
            connection.execute(self._outbox_table.insert().values(**values))
        self._outbox[event.id] = event
        return event

    def outbox_event(self, event_id: str) -> OutboxEvent:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(self._outbox_table).where(self._outbox_table.c.id == event_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(event_id)
        return self._event_from_row(row)

    def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int = 10,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> tuple[OutboxEvent, ...]:
        self._require_outbox_lifecycle()
        if not worker_id.strip() or not 1 <= limit <= 100 or lease_seconds <= 0:
            raise ValueError("OUTBOX_CLAIM_INVALID")
        now = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            query = (
                sa.select(self._outbox_table)
                .where(
                    self._outbox_table.c.status.in_(
                        (
                            OutboxStatus.NEW.value,
                            OutboxStatus.PROCESSING.value,
                            OutboxStatus.PENDING.value,
                            OutboxStatus.FAILED.value,
                            OutboxStatus.CLAIMED.value,
                        )
                    ),
                    sa.or_(
                        self._outbox_table.c.available_at.is_(None),
                        self._outbox_table.c.available_at <= now,
                    ),
                    sa.or_(
                        self._outbox_table.c.locked_at.is_(None),
                        self._outbox_table.c.locked_at <= now,
                    ),
                )
                .order_by(self._outbox_table.c.created_at, self._outbox_table.c.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = list(connection.execute(query).mappings())
            claimed: list[OutboxEvent] = []
            locked_until = now + timedelta(seconds=lease_seconds)
            for row in rows:
                connection.execute(
                    self._outbox_table.update()
                    .where(
                        self._outbox_table.c.id == row["id"],
                        self._outbox_table.c.status.in_(
                            (
                                OutboxStatus.NEW.value,
                                OutboxStatus.PROCESSING.value,
                                OutboxStatus.PENDING.value,
                                OutboxStatus.FAILED.value,
                                OutboxStatus.CLAIMED.value,
                            )
                        ),
                    )
                    .values(
                        status=(
                            OutboxStatus.PROCESSING.value
                            if row["status"]
                            in (OutboxStatus.NEW.value, OutboxStatus.PROCESSING.value)
                            else OutboxStatus.CLAIMED.value
                        ),
                        locked_by=worker_id.strip(),
                        locked_at=now,
                        available_at=locked_until,
                    )
                )
                claimed.append(
                    OutboxEvent(
                        str(row["id"]),
                        str(row["event_type"]),
                        str(row["aggregate_id"]),
                        dict(json.loads(str(row["payload_json"]))),
                        int(row["attempts"]),
                        (
                            OutboxStatus.PROCESSING
                            if row["status"]
                            in (OutboxStatus.NEW.value, OutboxStatus.PROCESSING.value)
                            else OutboxStatus.CLAIMED
                        ),
                        locked_until,
                        worker_id.strip(),
                        now,
                        str(row["last_error"]) if row["last_error"] is not None else None,
                        None,
                    )
                )
            for event in claimed:
                self._outbox[event.id] = event
            return tuple(claimed)

    def ack_outbox(
        self, event_id: str, worker_id: str, *, now: datetime | None = None
    ) -> OutboxEvent:
        self._require_outbox_lifecycle()
        if not worker_id.strip():
            raise ValueError("OUTBOX_WORKER_REQUIRED")
        now = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._outbox_table)
                    .where(self._outbox_table.c.id == event_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(event_id)
            current = self._event_from_row(row)
            result = connection.execute(
                self._outbox_table.update()
                .where(
                    self._outbox_table.c.id == event_id,
                    self._outbox_table.c.status.in_(
                        (OutboxStatus.CLAIMED.value, OutboxStatus.PROCESSING.value)
                    ),
                    self._outbox_table.c.locked_by == worker_id.strip(),
                    self._outbox_table.c.available_at > now,
                )
                .values(
                    status=(
                        OutboxStatus.PROCESSED.value
                        if current.status is OutboxStatus.PROCESSING
                        else OutboxStatus.PUBLISHED.value
                    ),
                    available_at=None,
                    locked_by=None,
                    locked_at=None,
                    processed_at=now,
                )
            )
            if result.rowcount != 1:
                raise ValueError("OUTBOX_CLAIM_REQUIRED")
        event = current
        updated = OutboxEvent(
            event.id,
            event.event_type,
            event.aggregate_id,
            event.payload,
            event.attempts,
            (
                OutboxStatus.PROCESSED
                if event.status is OutboxStatus.PROCESSING
                else OutboxStatus.PUBLISHED
            ),
            None,
            None,
            None,
            event.last_error,
            now,
        )
        self._outbox[event_id] = updated
        return updated

    def fail_outbox(
        self,
        event_id: str,
        worker_id: str,
        error: str,
        *,
        retry_after_seconds: int = 30,
        now: datetime | None = None,
    ) -> OutboxEvent:
        self._require_outbox_lifecycle()
        if not worker_id.strip() or not error.strip() or retry_after_seconds <= 0:
            raise ValueError("OUTBOX_FAILURE_INVALID")
        now = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    sa.select(self._outbox_table)
                    .where(self._outbox_table.c.id == event_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(event_id)
            event = self._event_from_row(row)
            result = connection.execute(
                self._outbox_table.update()
                .where(
                    self._outbox_table.c.id == event_id,
                    self._outbox_table.c.status.in_(
                        (OutboxStatus.CLAIMED.value, OutboxStatus.PROCESSING.value)
                    ),
                    self._outbox_table.c.locked_by == worker_id.strip(),
                    self._outbox_table.c.available_at > now,
                )
                .values(
                    attempts=event.attempts + 1,
                    status=OutboxStatus.FAILED.value,
                    available_at=now + timedelta(seconds=retry_after_seconds),
                    locked_by=None,
                    locked_at=None,
                    last_error=error.strip(),
                )
            )
            if result.rowcount != 1:
                raise ValueError("OUTBOX_CLAIM_REQUIRED")
        updated = OutboxEvent(
            event.id,
            event.event_type,
            event.aggregate_id,
            event.payload,
            event.attempts + 1,
            OutboxStatus.FAILED,
            now + timedelta(seconds=retry_after_seconds),
            None,
            None,
            error.strip(),
            None,
        )
        self._outbox[event_id] = updated
        return updated

    def _require_outbox_lifecycle(self) -> None:
        if not self._outbox_lifecycle:
            raise RuntimeError("OUTBOX_LIFECYCLE_MIGRATION_REQUIRED")

    @staticmethod
    def _event_from_row(row: sa.RowMapping) -> OutboxEvent:
        def timestamp(name: str) -> datetime | None:
            value = cast(datetime | None, row.get(name))
            if value is None:
                return None
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

        raw_status = row.get("status")
        return OutboxEvent(
            str(row["id"]),
            str(row["event_type"]),
            str(row["aggregate_id"]),
            dict(json.loads(str(row["payload_json"]))),
            int(row["attempts"]),
            OutboxStatus(str(raw_status)) if raw_status is not None else OutboxStatus.PENDING,
            timestamp("available_at"),
            str(row["locked_by"]) if row.get("locked_by") is not None else None,
            timestamp("locked_at"),
            str(row["last_error"]) if row.get("last_error") is not None else None,
            timestamp("processed_at"),
        )

    def request_invoice(
        self, account_id: str, amount_cents: int, title: str, tax_id: str
    ) -> Invoice:
        if amount_cents <= 0 or not account_id.strip() or not title.strip() or not tax_id.strip():
            raise ValueError("INVOICE_INVALID")
        invoice = Invoice(_id("INV"), account_id, amount_cents, title.strip(), tax_id.strip())
        with self.engine.begin() as connection:
            connection.execute(
                self._invoices_table.insert().values(
                    id=invoice.id,
                    account_id=invoice.account_id,
                    amount_cents=invoice.amount_cents,
                    title=invoice.title,
                    tax_id=invoice.tax_id,
                    status=invoice.status,
                    document_id=None,
                    reversal_document_id=None,
                    created_at=datetime.now(UTC),
                )
            )
        self._invoices[invoice.id] = invoice
        return invoice

    def issue_invoice(self, invoice_id: str, document_id: str) -> Invoice:
        invoice = self._invoices[invoice_id]
        if invoice.status != "APPLIED":
            raise ValueError("INVOICE_STATUS_INVALID")
        if not document_id.strip():
            raise ValueError("INVOICE_DOCUMENT_REQUIRED")
        with self.engine.begin() as connection:
            connection.execute(
                self._invoices_table.update()
                .where(self._invoices_table.c.id == invoice_id)
                .values(status="ISSUED", document_id=document_id)
            )
        invoice.status = "ISSUED"
        invoice.document_id = document_id
        return invoice

    def reverse_invoice(self, invoice_id: str, document_id: str) -> Invoice:
        invoice = self._invoices[invoice_id]
        if invoice.status != "ISSUED":
            raise ValueError("INVOICE_STATUS_INVALID")
        if not document_id.strip():
            raise ValueError("INVOICE_DOCUMENT_REQUIRED")
        with self.engine.begin() as connection:
            connection.execute(
                self._invoices_table.update()
                .where(self._invoices_table.c.id == invoice_id)
                .values(status="REVERSED", reversal_document_id=document_id)
            )
        invoice.status = "REVERSED"
        invoice.reversal_document_id = document_id
        return invoice


__all__ = ["SqlGovernanceService"]

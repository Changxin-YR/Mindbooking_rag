CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_foundation

INSERT INTO alembic_version (version_num) VALUES ('0001_foundation');

-- Running upgrade 0001_foundation -> 0002_identity_author_staff

CREATE TABLE login_identities (
    id VARCHAR(36) NOT NULL, 
    identity_type VARCHAR(32) NOT NULL, 
    normalized_value VARCHAR(255) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_login_identity_value UNIQUE (identity_type, normalized_value)
);

CREATE TABLE platform_accounts (
    id VARCHAR(36) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE login_identity_accounts (
    identity_id VARCHAR(36) NOT NULL, 
    account_id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (identity_id, account_id), 
    FOREIGN KEY(identity_id) REFERENCES login_identities (id), 
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id)
);

CREATE TABLE login_identity_routing (
    identity_id VARCHAR(36) NOT NULL, 
    account_id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (identity_id), 
    FOREIGN KEY(identity_id) REFERENCES login_identities (id), 
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id)
);

CREATE TABLE real_name_subjects (
    id VARCHAR(36) NOT NULL, 
    id_fingerprint VARCHAR(64) NOT NULL, 
    encrypted_name TEXT NOT NULL, 
    encrypted_id_number TEXT NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_real_name_subject_fingerprint UNIQUE (id_fingerprint)
);

CREATE TABLE account_real_name_links (
    account_id VARCHAR(36) NOT NULL, 
    real_name_subject_id VARCHAR(36) NOT NULL, 
    slot_status VARCHAR(32) NOT NULL, 
    PRIMARY KEY (account_id), 
    CONSTRAINT ck_real_name_slot_status CHECK (slot_status IN ('ACTIVE', 'PENDING_RELEASE', 'RELEASED', 'BLOCKED_BY_VIOLATION')), 
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id), 
    FOREIGN KEY(real_name_subject_id) REFERENCES real_name_subjects (id)
);

CREATE TABLE author_profiles (
    id VARCHAR(36) NOT NULL, 
    account_id VARCHAR(36) NOT NULL, 
    pen_name VARCHAR(255) NOT NULL, 
    normalized_pen_name VARCHAR(255) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_author_profile_account UNIQUE (account_id)
);

CREATE TABLE author_pen_name_registry (
    normalized_pen_name VARCHAR(255) NOT NULL, 
    author_profile_id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (normalized_pen_name), 
    FOREIGN KEY(author_profile_id) REFERENCES author_profiles (id)
);

CREATE TABLE pen_name_history (
    id VARCHAR(36) NOT NULL, 
    author_profile_id VARCHAR(36) NOT NULL, 
    pen_name VARCHAR(255) NOT NULL, 
    normalized_pen_name VARCHAR(255) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(author_profile_id) REFERENCES author_profiles (id), 
    CONSTRAINT uq_pen_name_history_normalized UNIQUE (normalized_pen_name)
);

CREATE TABLE staff_accounts (
    id VARCHAR(36) NOT NULL, 
    employee_code VARCHAR(128) NOT NULL, 
    department VARCHAR(128) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_staff_employee_code UNIQUE (employee_code), 
    CONSTRAINT ck_staff_status CHECK (status IN ('PENDING_ACTIVATION', 'ACTIVE', 'LOCKED', 'DISABLED', 'OFFBOARDED'))
);

CREATE TABLE staff_permissions (
    staff_id VARCHAR(36) NOT NULL, 
    permission VARCHAR(255) NOT NULL, 
    PRIMARY KEY (staff_id, permission), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE staff_data_scopes (
    staff_id VARCHAR(36) NOT NULL, 
    scope_type VARCHAR(64) NOT NULL, 
    scope_value VARCHAR(255) NOT NULL, 
    PRIMARY KEY (staff_id, scope_type, scope_value), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id)
);

UPDATE alembic_version SET version_num='0002_identity_author_staff' WHERE alembic_version.version_num = '0001_foundation';

-- Running upgrade 0002_identity_author_staff -> 0003_content_review_reading

CREATE TABLE books (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    lifecycle VARCHAR(32) NOT NULL, 
    visibility VARCHAR(32) NOT NULL, 
    public_metadata_version_id VARCHAR(64), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE book_metadata_versions (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    synopsis TEXT NOT NULL, 
    is_public BOOL NOT NULL DEFAULT false, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_book_metadata_version UNIQUE (book_id, version), 
    FOREIGN KEY(book_id) REFERENCES books (id)
);

CREATE TABLE volumes (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    number INTEGER NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_volume_book_number UNIQUE (book_id, number), 
    FOREIGN KEY(book_id) REFERENCES books (id)
);

CREATE TABLE chapters (
    id VARCHAR(64) NOT NULL, 
    volume_id VARCHAR(64) NOT NULL, 
    number INTEGER NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    commercial_policy VARCHAR(16) NOT NULL, 
    publish_state VARCHAR(16) NOT NULL, 
    visibility_state VARCHAR(32) NOT NULL, 
    published_version_id VARCHAR(64), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_chapter_volume_number UNIQUE (volume_id, number), 
    FOREIGN KEY(volume_id) REFERENCES volumes (id)
);

CREATE TABLE chapter_draft_heads (
    chapter_id VARCHAR(64) NOT NULL, 
    current_revision INTEGER NOT NULL DEFAULT '0', 
    current_snapshot_id VARCHAR(64), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (chapter_id), 
    FOREIGN KEY(chapter_id) REFERENCES chapters (id)
);

CREATE TABLE chapter_draft_snapshots (
    id VARCHAR(64) NOT NULL, 
    chapter_id VARCHAR(64) NOT NULL, 
    revision INTEGER NOT NULL, 
    content TEXT NOT NULL, 
    save_mode VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_draft_snapshot_revision UNIQUE (chapter_id, revision), 
    FOREIGN KEY(chapter_id) REFERENCES chapters (id)
);

CREATE TABLE chapter_versions (
    id VARCHAR(64) NOT NULL, 
    chapter_id VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    content TEXT NOT NULL, 
    word_count INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_chapter_version UNIQUE (chapter_id, version), 
    FOREIGN KEY(chapter_id) REFERENCES chapters (id), 
    FOREIGN KEY(snapshot_id) REFERENCES chapter_draft_snapshots (id)
);

CREATE TABLE review_submissions (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    submission_type VARCHAR(32) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(book_id) REFERENCES books (id)
);

CREATE TABLE review_submission_versions (
    submission_id VARCHAR(64) NOT NULL, 
    chapter_version_id VARCHAR(64) NOT NULL, 
    position INTEGER NOT NULL, 
    PRIMARY KEY (submission_id, chapter_version_id), 
    CONSTRAINT uq_submission_version_position UNIQUE (submission_id, position), 
    FOREIGN KEY(submission_id) REFERENCES review_submissions (id), 
    FOREIGN KEY(chapter_version_id) REFERENCES chapter_versions (id)
);

CREATE TABLE review_tasks (
    id VARCHAR(64) NOT NULL, 
    submission_id VARCHAR(64) NOT NULL, 
    task_type VARCHAR(32) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(submission_id) REFERENCES review_submissions (id)
);

CREATE TABLE review_decisions (
    id VARCHAR(64) NOT NULL, 
    submission_id VARCHAR(64) NOT NULL, 
    reviewer_id VARCHAR(64) NOT NULL, 
    decision VARCHAR(32) NOT NULL, 
    actor_type VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(submission_id) REFERENCES review_submissions (id)
);

CREATE TABLE book_reading_progress (
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    last_chapter_id VARCHAR(64), 
    last_chapter_number INTEGER NOT NULL, 
    last_position INTEGER NOT NULL, 
    furthest_chapter_id VARCHAR(64), 
    furthest_chapter_number INTEGER NOT NULL, 
    furthest_position INTEGER NOT NULL, 
    revision INTEGER NOT NULL, 
    current_session_id VARCHAR(128), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id, book_id)
);

CREATE TABLE bookshelf_entries (
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    group_name VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id, book_id)
);

UPDATE alembic_version SET version_num='0003_content_review_reading' WHERE alembic_version.version_num = '0002_identity_author_staff';

-- Running upgrade 0003_content_review_reading -> 0005_wallet_commerce

CREATE TABLE wallet_accounts (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    recharge_coin BIGINT NOT NULL DEFAULT 0, 
    gift_coin BIGINT NOT NULL DEFAULT 0, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_wallet_accounts_account_id UNIQUE (account_id)
);

CREATE TABLE wallet_journals (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    journal_type VARCHAR(32) NOT NULL, 
    idempotency_key VARCHAR(128), 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_wallet_journals_idempotency UNIQUE (account_id, idempotency_key)
);

CREATE TABLE wallet_entries (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    journal_id BIGINT NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    asset_type VARCHAR(24) NOT NULL, 
    amount BIGINT NOT NULL, 
    reason VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(journal_id) REFERENCES wallet_journals (id), 
    CONSTRAINT ck_wallet_entries_nonzero CHECK (amount <> 0)
);

CREATE TABLE wallet_asset_lots (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    lot_id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    asset_type VARCHAR(24) NOT NULL, 
    origin VARCHAR(64) NOT NULL, 
    available_amount BIGINT NOT NULL, 
    issued_at DATETIME NOT NULL, 
    expires_at DATETIME, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_wallet_asset_lots_lot_id UNIQUE (lot_id)
);

CREATE INDEX ix_wallet_asset_lots_spend ON wallet_asset_lots (account_id, asset_type, available_amount, expires_at, issued_at);

CREATE TABLE wallet_lot_allocations (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    lot_id VARCHAR(64) NOT NULL, 
    journal_id BIGINT NOT NULL, 
    allocation_type VARCHAR(32) NOT NULL, 
    amount BIGINT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(journal_id) REFERENCES wallet_journals (id), 
    CONSTRAINT ck_wallet_lot_allocations_positive CHECK (amount > 0)
);

CREATE TABLE payment_orders (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    payment_no VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    channel VARCHAR(32) NOT NULL, 
    paid_cents BIGINT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_payment_orders_payment_no UNIQUE (payment_no)
);

CREATE TABLE payment_attempts (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    payment_order_id BIGINT NOT NULL, 
    attempt_no INTEGER NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(payment_order_id) REFERENCES payment_orders (id), 
    CONSTRAINT uq_payment_attempts_number UNIQUE (payment_order_id, attempt_no)
);

CREATE TABLE payment_channel_events (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    provider VARCHAR(32) NOT NULL, 
    provider_event_id VARCHAR(128) NOT NULL, 
    payment_no VARCHAR(64) NOT NULL, 
    channel_transaction_id VARCHAR(128), 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_payment_events_provider_event UNIQUE (provider, provider_event_id), 
    CONSTRAINT uq_payment_events_provider_tx UNIQUE (provider, channel_transaction_id)
);

CREATE TABLE recharge_orders (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    recharge_no VARCHAR(64) NOT NULL, 
    payment_order_id BIGINT NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    paid_cents BIGINT NOT NULL, 
    recharge_coin BIGINT NOT NULL, 
    gift_coin BIGINT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(payment_order_id) REFERENCES payment_orders (id), 
    CONSTRAINT uq_recharge_orders_recharge_no UNIQUE (recharge_no), 
    CONSTRAINT uq_recharge_orders_payment UNIQUE (payment_order_id)
);

CREATE TABLE chapter_purchase_orders (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    purchase_no VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    total_coin BIGINT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_chapter_purchase_orders_purchase_no UNIQUE (purchase_no)
);

CREATE TABLE chapter_purchase_items (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    purchase_order_id BIGINT NOT NULL, 
    chapter_id VARCHAR(64) NOT NULL, 
    price_coin BIGINT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(purchase_order_id) REFERENCES chapter_purchase_orders (id), 
    CONSTRAINT ck_chapter_purchase_items_positive CHECK (price_coin > 0)
);

CREATE TABLE chapter_entitlements (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    chapter_id VARCHAR(64) NOT NULL, 
    source_purchase_no VARCHAR(64) NOT NULL, 
    granted_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_chapter_entitlements_account_chapter UNIQUE (account_id, chapter_id)
);

CREATE TABLE membership_accounts (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    expires_at DATETIME NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_membership_accounts_account_id UNIQUE (account_id)
);

CREATE TABLE membership_library_entries (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    book_id VARCHAR(64) NOT NULL, 
    active_from DATETIME NOT NULL, 
    active_until DATETIME, 
    status VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_membership_library_entries_book_id UNIQUE (book_id)
);

UPDATE alembic_version SET version_num='0005_wallet_commerce' WHERE alembic_version.version_num = '0003_content_review_reading';

-- Running upgrade 0005_wallet_commerce -> 0006_refund

CREATE TABLE refund_calculation_snapshots (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    refund_reference VARCHAR(128) NOT NULL, 
    payment_no VARCHAR(64) NOT NULL, 
    recharge_no VARCHAR(64) NOT NULL, 
    original_paid_cents BIGINT NOT NULL, 
    consumed_recharge_coin BIGINT NOT NULL, 
    consumed_promo_gift_coin BIGINT NOT NULL, 
    naturally_expired_promo_gift_coin BIGINT NOT NULL, 
    prior_refunded_cents BIGINT NOT NULL, 
    refundable_cents BIGINT NOT NULL, 
    recoverable_recharge_coin BIGINT NOT NULL, 
    recoverable_promo_gift_coin BIGINT NOT NULL, 
    executed BOOL NOT NULL DEFAULT false, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_refund_snapshot_reference UNIQUE (refund_reference), 
    CONSTRAINT ck_refund_snapshot_nonnegative CHECK (refundable_cents >= 0)
);

CREATE TABLE refund_requests (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    refund_no VARCHAR(64) NOT NULL, 
    refund_reference VARCHAR(128) NOT NULL, 
    payment_no VARCHAR(64) NOT NULL, 
    recharge_no VARCHAR(64) NOT NULL, 
    snapshot_id BIGINT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_refund_request_no UNIQUE (refund_no), 
    CONSTRAINT uq_refund_request_reference UNIQUE (refund_reference), 
    FOREIGN KEY(snapshot_id) REFERENCES refund_calculation_snapshots (id)
);

CREATE TABLE refund_source_locks (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    payment_no VARCHAR(64) NOT NULL, 
    recharge_no VARCHAR(64) NOT NULL, 
    refund_reference VARCHAR(128) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_refund_source_lock UNIQUE (payment_no, recharge_no)
);

UPDATE alembic_version SET version_num='0006_refund' WHERE alembic_version.version_num = '0005_wallet_commerce';

-- Running upgrade 0006_refund -> 0007_governance

CREATE TABLE community_report_cases (
    id VARCHAR(64) NOT NULL, 
    content_type VARCHAR(32) NOT NULL, 
    content_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_report_case_content UNIQUE (content_type, content_id), 
    CONSTRAINT ck_report_case_status CHECK (status IN ('OPEN', 'PROCESSING', 'RESOLVED'))
);

CREATE TABLE community_report_submissions (
    id VARCHAR(64) NOT NULL, 
    case_id VARCHAR(64) NOT NULL, 
    reporter_id VARCHAR(64) NOT NULL, 
    reason VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES community_report_cases (id), 
    CONSTRAINT uq_report_submission_reporter UNIQUE (case_id, reporter_id)
);

CREATE TABLE notifications (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    category VARCHAR(32) NOT NULL, 
    priority VARCHAR(8) NOT NULL, 
    channels VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_notification_priority CHECK (priority IN ('NORMAL', 'P0')), 
    CONSTRAINT ck_notification_category CHECK (category IN ('SYSTEM', 'SECURITY', 'MARKETING')), 
    CONSTRAINT ck_notification_p0_channels CHECK (NOT (category = 'SECURITY' AND priority = 'P0') OR channels = 'IN_APP,SMS')
);

CREATE TABLE notification_preferences (
    account_id VARCHAR(64) NOT NULL, 
    marketing_enabled BOOL NOT NULL DEFAULT true, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id), 
    CONSTRAINT ck_marketing_cannot_be_disabled CHECK (marketing_enabled = 1)
);

CREATE TABLE support_tickets (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    category VARCHAR(32) NOT NULL, 
    priority VARCHAR(8) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_support_ticket_status CHECK (status IN ('NEW', 'IN_PROGRESS', 'WAITING_USER', 'WAITING_INTERNAL', 'RESOLVED', 'CLOSED', 'CANCELLED')), 
    CONSTRAINT ck_support_ticket_priority CHECK (priority IN ('P0', 'P1', 'P2', 'P3'))
);

CREATE TABLE support_messages (
    id VARCHAR(64) NOT NULL, 
    ticket_id VARCHAR(64) NOT NULL, 
    author_type VARCHAR(16) NOT NULL, 
    body TEXT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(ticket_id) REFERENCES support_tickets (id), 
    CONSTRAINT ck_support_message_author CHECK (author_type IN ('USER', 'STAFF'))
);

CREATE TABLE risk_order_facts (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    amount_coin BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_risk_order_amount_nonnegative CHECK (amount_coin >= 0)
);

CREATE TABLE risk_signals (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    signal_type VARCHAR(64) NOT NULL, 
    order_id VARCHAR(64) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(order_id) REFERENCES risk_order_facts (id), 
    CONSTRAINT ck_risk_signal_status CHECK (status IN ('OBSERVE', 'FROZEN'))
);

CREATE TABLE approval_requests (
    id VARCHAR(64) NOT NULL, 
    action VARCHAR(64) NOT NULL, 
    requester_id VARCHAR(64) NOT NULL, 
    critical BOOL NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_approval_request_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE TABLE approval_decisions (
    id VARCHAR(64) NOT NULL, 
    request_id VARCHAR(64) NOT NULL, 
    approver_id VARCHAR(64) NOT NULL, 
    decision VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(request_id) REFERENCES approval_requests (id), 
    CONSTRAINT uq_approval_decision_approver UNIQUE (request_id, approver_id), 
    CONSTRAINT ck_approval_decision CHECK (decision IN ('APPROVE', 'REJECT'))
);

UPDATE alembic_version SET version_num='0007_governance' WHERE alembic_version.version_num = '0006_refund';

-- Running upgrade 0007_governance -> 0008_author_finance

CREATE TABLE contracts (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_contract_status CHECK (status IN ('DRAFT', 'APPROVED', 'ACTIVE', 'TERMINATED'))
);

CREATE TABLE contract_versions (
    id VARCHAR(64) NOT NULL, 
    contract_id VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    revenue_share_bps INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(contract_id) REFERENCES contracts (id), 
    CONSTRAINT uq_contract_version UNIQUE (contract_id, version), 
    CONSTRAINT ck_contract_share_bps CHECK (revenue_share_bps BETWEEN 1 AND 10000)
);

CREATE TABLE author_revenue_entries (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    source_ref VARCHAR(128) NOT NULL, 
    gross_cents BIGINT NOT NULL, 
    author_cents BIGINT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    settlement_id VARCHAR(64), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_author_revenue_source_ref UNIQUE (source_ref), 
    CONSTRAINT ck_author_revenue_amount CHECK (gross_cents > 0 AND author_cents >= 0)
);

CREATE TABLE author_settlements (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    period VARCHAR(32) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    withdrawn_cents BIGINT NOT NULL DEFAULT 0, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_author_settlement_period UNIQUE (author_id, period), 
    CONSTRAINT ck_settlement_amount CHECK (amount_cents >= 0 AND withdrawn_cents >= 0)
);

CREATE TABLE withdrawal_requests (
    id VARCHAR(64) NOT NULL, 
    settlement_id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    payout_method VARCHAR(24) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(settlement_id) REFERENCES author_settlements (id), 
    CONSTRAINT ck_withdrawal_minimum CHECK (amount_cents >= 1000)
);

CREATE TABLE chargebacks (
    id VARCHAR(64) NOT NULL, 
    source_ref VARCHAR(128) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    recovered_cents BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_chargeback_amount CHECK (amount_cents > 0 AND recovered_cents >= 0)
);

CREATE TABLE financial_recovery_claims (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    chargeback_id VARCHAR(64) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(chargeback_id) REFERENCES chargebacks (id), 
    CONSTRAINT ck_recovery_claim_amount CHECK (amount_cents > 0)
);

UPDATE alembic_version SET version_num='0008_author_finance' WHERE alembic_version.version_num = '0007_governance';

-- Running upgrade 0008_author_finance -> 0009_operation_legal

CREATE TABLE ranking_items (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    score BIGINT NOT NULL, 
    `rank` INTEGER NOT NULL, 
    snapshot_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ranking_kind CHECK (kind IN ('ALGORITHM', 'RECOMMENDATION_SCORE', 'EDITORIAL', 'CAMPAIGN'))
);

CREATE TABLE recommendations (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    score BIGINT NOT NULL, 
    personalized BOOL NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE operation_jobs (
    id VARCHAR(64) NOT NULL, 
    job_type VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE export_jobs (
    id VARCHAR(64) NOT NULL, 
    requester_id VARCHAR(64) NOT NULL, 
    resource_type VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE retention_policies (
    resource_type VARCHAR(64) NOT NULL, 
    action VARCHAR(32) NOT NULL, 
    days INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (resource_type), 
    CONSTRAINT ck_retention_action CHECK (action IN ('DELETE', 'ANONYMIZE', 'ARCHIVE', 'KEEP', 'DOMAIN_CONTROLLED')), 
    CONSTRAINT ck_retention_days CHECK (days >= 0)
);

CREATE TABLE copyright_dossiers (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE copyright_right_items (
    id VARCHAR(64) NOT NULL, 
    dossier_id VARCHAR(64) NOT NULL, 
    region VARCHAR(64) NOT NULL, 
    language VARCHAR(32) NOT NULL, 
    media VARCHAR(32) NOT NULL, 
    exclusive BOOL NOT NULL, 
    start_year INTEGER NOT NULL, 
    end_year INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(dossier_id) REFERENCES copyright_dossiers (id), 
    CONSTRAINT ck_right_year_range CHECK (end_year > start_year)
);

CREATE TABLE copyright_complaints (
    id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    claimant_id VARCHAR(64) NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    counter_notice TEXT, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE legal_cases (
    id VARCHAR(64) NOT NULL, 
    subject VARCHAR(255) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE legal_holds (
    id VARCHAR(64) NOT NULL, 
    case_id VARCHAR(64) NOT NULL, 
    resource_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES legal_cases (id), 
    CONSTRAINT ck_legal_hold_status CHECK (status IN ('ACTIVE', 'RELEASED'))
);

UPDATE alembic_version SET version_num='0009_operation_legal' WHERE alembic_version.version_num = '0008_author_finance';

-- Running upgrade 0009_operation_legal -> 0010_reader_experience

ALTER TABLE book_metadata_versions ADD COLUMN channel VARCHAR(16) NOT NULL DEFAULT 'UNSPECIFIED';

ALTER TABLE book_metadata_versions ADD COLUMN category VARCHAR(64) NOT NULL DEFAULT '';

ALTER TABLE book_metadata_versions ADD COLUMN tags_json TEXT;

UPDATE book_metadata_versions SET tags_json = '[]' WHERE tags_json IS NULL;

ALTER TABLE book_metadata_versions MODIFY tags_json TEXT NOT NULL;

CREATE TABLE book_user_ratings (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    overall_score SMALLINT NOT NULL, 
    plot_score SMALLINT NOT NULL, 
    character_score SMALLINT NOT NULL, 
    writing_score SMALLINT NOT NULL, 
    update_score SMALLINT NOT NULL, 
    eligibility_metric_version VARCHAR(64) NOT NULL, 
    eligible_words BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_book_user_rating UNIQUE (account_id, book_id), 
    CONSTRAINT ck_rating_overall CHECK (overall_score BETWEEN 1 AND 5)
);

CREATE TABLE book_user_rating_versions (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    rating_id VARCHAR(64) NOT NULL, 
    overall_score SMALLINT NOT NULL, 
    plot_score SMALLINT NOT NULL, 
    character_score SMALLINT NOT NULL, 
    writing_score SMALLINT NOT NULL, 
    update_score SMALLINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(rating_id) REFERENCES book_user_ratings (id)
);

CREATE TABLE follow_relations (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    target_type VARCHAR(16) NOT NULL, 
    target_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_follow_relation UNIQUE (account_id, target_type, target_id), 
    CONSTRAINT ck_follow_target_type CHECK (target_type IN ('AUTHOR', 'ACCOUNT'))
);

CREATE TABLE user_growth_profiles (
    account_id VARCHAR(64) NOT NULL, 
    points BIGINT NOT NULL DEFAULT 0, 
    level INTEGER NOT NULL DEFAULT 1, 
    membership_level INTEGER NOT NULL DEFAULT 0, 
    fan_level INTEGER NOT NULL DEFAULT 0, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id)
);

CREATE TABLE user_growth_events (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    source VARCHAR(64) NOT NULL, 
    points BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_growth_points_positive CHECK (points > 0)
);

CREATE TABLE content_correction_reports (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    chapter_id VARCHAR(64) NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    position BIGINT NOT NULL, 
    description TEXT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_correction_position CHECK (position >= 0)
);

CREATE TABLE minor_protection_profiles (
    account_id VARCHAR(64) NOT NULL, 
    is_minor BOOL NOT NULL, 
    policy_version VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id)
);

UPDATE alembic_version SET version_num='0010_reader_experience' WHERE alembic_version.version_num = '0009_operation_legal';

-- Running upgrade 0010_reader_experience -> 0011_governance

CREATE TABLE privacy_requests (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_privacy_request_kind UNIQUE (account_id, kind)
);

CREATE TABLE agreement_acceptances (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    account_id VARCHAR(64) NOT NULL, 
    agreement_code VARCHAR(64) NOT NULL, 
    version VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_agreement_acceptance UNIQUE (account_id, agreement_code, version)
);

CREATE TABLE parameter_versions (
    id VARCHAR(64) NOT NULL, 
    parameter_key VARCHAR(128) NOT NULL, 
    value_text TEXT NOT NULL, 
    maker_id VARCHAR(64) NOT NULL, 
    checker_id VARCHAR(64), 
    status VARCHAR(24) NOT NULL, 
    effective_at DATETIME, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE payment_credit_pending (
    id VARCHAR(64) NOT NULL, 
    payment_id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_payment_credit_pending UNIQUE (payment_id)
);

CREATE TABLE reconciliation_batches (
    id VARCHAR(64) NOT NULL, 
    business_date DATE NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_reconciliation_business_date UNIQUE (business_date)
);

CREATE TABLE reconciliation_items (
    id VARCHAR(64) NOT NULL, 
    batch_id VARCHAR(64) NOT NULL, 
    reference VARCHAR(128) NOT NULL, 
    difference VARCHAR(32) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(batch_id) REFERENCES reconciliation_batches (id)
);

CREATE TABLE platform_emergencies (
    id VARCHAR(64) NOT NULL, 
    reason TEXT NOT NULL, 
    features_json TEXT NOT NULL, 
    operator_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE outbox_events (
    id VARCHAR(64) NOT NULL, 
    event_type VARCHAR(128) NOT NULL, 
    aggregate_id VARCHAR(64) NOT NULL, 
    payload_json TEXT NOT NULL, 
    attempts INTEGER NOT NULL DEFAULT 0, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='0011_governance' WHERE alembic_version.version_num = '0010_reader_experience';

-- Running upgrade 0011_governance -> 0012_author_center

CREATE TABLE author_daily_writing_stats (
    author_id VARCHAR(64) NOT NULL, 
    business_date DATE NOT NULL, 
    words BIGINT NOT NULL, 
    goal BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (author_id, business_date)
);

CREATE TABLE author_task_definitions (
    id VARCHAR(64) NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    title VARCHAR(128) NOT NULL, 
    target BIGINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_author_task_code UNIQUE (code)
);

CREATE TABLE author_task_progress (
    author_id VARCHAR(64) NOT NULL, 
    task_id VARCHAR(64) NOT NULL, 
    progress BIGINT NOT NULL, 
    claimed BOOL NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (author_id, task_id)
);

CREATE TABLE writer_learning_contents (
    id VARCHAR(64) NOT NULL, 
    category VARCHAR(64) NOT NULL, 
    title VARCHAR(256) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE writer_learning_progress (
    author_id VARCHAR(64) NOT NULL, 
    content_id VARCHAR(64) NOT NULL, 
    percent SMALLINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (author_id, content_id)
);

CREATE TABLE chapter_funnel_metrics (
    chapter_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    entrants BIGINT NOT NULL, 
    completion_bps INTEGER NOT NULL, 
    next_chapter_bps INTEGER NOT NULL, 
    subscription_bps INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (chapter_id)
);

CREATE TABLE author_appeals (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    subject_type VARCHAR(32) NOT NULL, 
    subject_id VARCHAR(64) NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE invoice_requests (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    title VARCHAR(256) NOT NULL, 
    tax_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    document_id VARCHAR(128), 
    reversal_document_id VARCHAR(128), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='0012_author_center' WHERE alembic_version.version_num = '0011_governance';

-- Running upgrade 0012_author_center -> 0013_admin_center

CREATE TABLE review_rules (
    code VARCHAR(64) NOT NULL, 
    version VARCHAR(64) NOT NULL, 
    severity VARCHAR(24) NOT NULL, 
    recommended_action VARCHAR(64) NOT NULL, 
    auto_block_policy BOOL NOT NULL, 
    subject_types_json TEXT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (code, version)
);

CREATE TABLE reviewer_quality_metrics (
    reviewer_id VARCHAR(64) NOT NULL, 
    accuracy_bps INTEGER NOT NULL, 
    false_positive_bps INTEGER NOT NULL, 
    miss_bps INTEGER NOT NULL, 
    overturn_bps INTEGER NOT NULL, 
    avg_handle_seconds INTEGER NOT NULL, 
    complaint_bps INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (reviewer_id)
);

CREATE TABLE author_alerts (
    id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    alert_type VARCHAR(64) NOT NULL, 
    summary TEXT NOT NULL, 
    risk_level VARCHAR(24) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE support_csat_records (
    ticket_id VARCHAR(64) NOT NULL, 
    score SMALLINT NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (ticket_id)
);

UPDATE alembic_version SET version_num='0013_admin_center' WHERE alembic_version.version_num = '0012_author_center';

-- Running upgrade 0013_admin_center -> 0014_risk_center

CREATE TABLE login_risk_signals (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    device_id VARCHAR(128) NOT NULL, 
    browser VARCHAR(64) NOT NULL, 
    operating_system VARCHAR(64) NOT NULL, 
    ip VARCHAR(64) NOT NULL, 
    region VARCHAR(64) NOT NULL, 
    user_agent TEXT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE risk_watchlist_entries (
    id VARCHAR(64) NOT NULL, 
    target_type VARCHAR(32) NOT NULL, 
    target_value VARCHAR(256) NOT NULL, 
    reason TEXT NOT NULL, 
    case_id VARCHAR(64) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    release_reason TEXT, 
    evidence_id VARCHAR(64), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='0014_risk_center' WHERE alembic_version.version_num = '0013_admin_center';

-- Running upgrade 0014_risk_center -> 0015_auth_credentials

CREATE TABLE account_password_credentials (
    account_id VARCHAR(36) NOT NULL, 
    password_hash VARCHAR(512) NOT NULL, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (account_id), 
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id)
);

CREATE TABLE auth_sessions (
    id VARCHAR(36) NOT NULL, 
    account_id VARCHAR(36) NOT NULL, 
    token_fingerprint VARCHAR(64) NOT NULL, 
    expires_at DATETIME NOT NULL, 
    revoked_at DATETIME, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id), 
    CONSTRAINT uq_auth_sessions_token_fingerprint UNIQUE (token_fingerprint)
);

CREATE INDEX ix_auth_sessions_account_expires ON auth_sessions (account_id, expires_at);

UPDATE alembic_version SET version_num='0015_auth_credentials' WHERE alembic_version.version_num = '0014_risk_center';

-- Running upgrade 0015_auth_credentials -> 0016_wallet_lot_sources

ALTER TABLE wallet_asset_lots ADD COLUMN source_ref VARCHAR(128);

ALTER TABLE wallet_asset_lots ADD COLUMN issued_amount BIGINT;

UPDATE wallet_asset_lots SET issued_amount = available_amount WHERE issued_amount IS NULL;

CREATE INDEX ix_wallet_asset_lots_source_ref ON wallet_asset_lots (account_id, source_ref);

UPDATE alembic_version SET version_num='0016_wallet_lot_sources' WHERE alembic_version.version_num = '0015_auth_credentials';

-- Running upgrade 0016_wallet_lot_sources -> 0017_staff_auth_rbac

CREATE TABLE staff_credentials (
    staff_id VARCHAR(36) NOT NULL, 
    password_hash VARCHAR(512) NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (staff_id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE staff_sessions (
    id VARCHAR(36) NOT NULL, 
    staff_id VARCHAR(36) NOT NULL, 
    token_fingerprint VARCHAR(64) NOT NULL, 
    expires_at DATETIME NOT NULL, 
    revoked_at DATETIME, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id), 
    CONSTRAINT uq_staff_sessions_token_fingerprint UNIQUE (token_fingerprint)
);

CREATE INDEX ix_staff_sessions_staff_expires ON staff_sessions (staff_id, expires_at);

CREATE TABLE staff_devices (
    id VARCHAR(36) NOT NULL, 
    staff_id VARCHAR(36) NOT NULL, 
    device_fingerprint VARCHAR(128) NOT NULL, 
    last_seen_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id), 
    CONSTRAINT uq_staff_device_fingerprint UNIQUE (staff_id, device_fingerprint)
);

CREATE TABLE staff_mfa_factors (
    id VARCHAR(36) NOT NULL, 
    staff_id VARCHAR(36) NOT NULL, 
    factor_type VARCHAR(32) NOT NULL, 
    secret_ciphertext TEXT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id)
);

CREATE TABLE staff_roles (
    id VARCHAR(36) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_staff_role_name UNIQUE (name)
);

CREATE TABLE staff_role_bindings (
    staff_id VARCHAR(36) NOT NULL, 
    role_id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (staff_id, role_id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id), 
    FOREIGN KEY(role_id) REFERENCES staff_roles (id)
);

CREATE TABLE staff_role_permissions (
    role_id VARCHAR(36) NOT NULL, 
    permission VARCHAR(255) NOT NULL, 
    PRIMARY KEY (role_id, permission), 
    FOREIGN KEY(role_id) REFERENCES staff_roles (id)
);

UPDATE alembic_version SET version_num='0017_staff_auth_rbac' WHERE alembic_version.version_num = '0016_wallet_lot_sources';

-- Running upgrade 0017_staff_auth_rbac -> 0018_chapter_commerce_policies

CREATE TABLE chapter_commerce_policies (
    chapter_id VARCHAR(64) NOT NULL, 
    price_coin BIGINT NOT NULL, 
    access_mode VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (chapter_id), 
    FOREIGN KEY(chapter_id) REFERENCES chapters (id), 
    CONSTRAINT ck_chapter_commerce_policies_price_positive CHECK (price_coin > 0)
);

UPDATE alembic_version SET version_num='0018_chapter_commerce_policies' WHERE alembic_version.version_num = '0017_staff_auth_rbac';

-- Running upgrade 0018_chapter_commerce_policies -> 0019_operation_facts

CREATE TABLE operation_legal_holds (
    resource_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (resource_id)
);

CREATE TABLE operation_campaigns (
    id VARCHAR(64) NOT NULL, 
    title VARCHAR(256) NOT NULL, 
    start_date VARCHAR(32) NOT NULL, 
    end_date VARCHAR(32) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id)
);

CREATE TABLE operation_campaign_enrollments (
    account_id VARCHAR(64) NOT NULL, 
    campaign_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (account_id, campaign_id)
);

CREATE TABLE operation_reward_grants (
    id VARCHAR(64) NOT NULL, 
    subject_id VARCHAR(64) NOT NULL, 
    reward_type VARCHAR(64) NOT NULL, 
    amount BIGINT NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_operation_reward_idempotency UNIQUE (idempotency_key), 
    CONSTRAINT ck_operation_reward_amount CHECK (amount > 0)
);

UPDATE alembic_version SET version_num='0019_operation_facts' WHERE alembic_version.version_num = '0018_chapter_commerce_policies';

-- Running upgrade 0019_operation_facts -> 0020_copyright_evidence

CREATE TABLE copyright_complaint_evidence (
    complaint_id VARCHAR(64) NOT NULL, 
    evidence_id VARCHAR(64) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (complaint_id, evidence_id), 
    FOREIGN KEY(complaint_id) REFERENCES copyright_complaints (id)
);

UPDATE alembic_version SET version_num='0020_copyright_evidence' WHERE alembic_version.version_num = '0019_operation_facts';

-- Running upgrade 0020_copyright_evidence -> 0021_agent_audit

CREATE TABLE agent_audit_events (
    id VARCHAR(64) NOT NULL, 
    agent_id VARCHAR(64) NOT NULL, 
    actor_id VARCHAR(64) NOT NULL, 
    tool_name VARCHAR(128) NOT NULL, 
    permission VARCHAR(128) NOT NULL, 
    outcome VARCHAR(24) NOT NULL, 
    reason VARCHAR(255), 
    occurred_at DATETIME NOT NULL, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='0021_agent_audit' WHERE alembic_version.version_num = '0020_copyright_evidence';

-- Running upgrade 0021_agent_audit -> 0022_outbox_lifecycle

ALTER TABLE outbox_events ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'PENDING';

ALTER TABLE outbox_events ADD COLUMN available_at DATETIME;

ALTER TABLE outbox_events ADD COLUMN locked_by VARCHAR(128);

ALTER TABLE outbox_events ADD COLUMN locked_at DATETIME;

ALTER TABLE outbox_events ADD COLUMN last_error TEXT;

ALTER TABLE outbox_events ADD COLUMN processed_at DATETIME;

CREATE INDEX ix_outbox_events_delivery ON outbox_events (status, available_at, locked_at, created_at);

UPDATE alembic_version SET version_num='0022_outbox_lifecycle' WHERE alembic_version.version_num = '0021_agent_audit';

-- Running upgrade 0022_outbox_lifecycle -> 0023_agent_audit_context

ALTER TABLE agent_audit_events ADD COLUMN session_id VARCHAR(64);

ALTER TABLE agent_audit_events ADD COLUMN arguments_json TEXT;

ALTER TABLE agent_audit_events ADD COLUMN result_summary VARCHAR(255);

ALTER TABLE agent_audit_events ADD COLUMN ip VARCHAR(64);

ALTER TABLE agent_audit_events ADD COLUMN device_id VARCHAR(128);

ALTER TABLE agent_audit_events ADD COLUMN confirmed BOOL NOT NULL DEFAULT false;

ALTER TABLE agent_audit_events ADD COLUMN risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW';

CREATE INDEX ix_agent_audit_events_actor_time ON agent_audit_events (actor_id, occurred_at);

UPDATE alembic_version SET version_num='0023_agent_audit_context' WHERE alembic_version.version_num = '0022_outbox_lifecycle';

-- Running upgrade 0023_agent_audit_context -> 0024_membership_commercial

ALTER TABLE membership_accounts ADD COLUMN plan_code VARCHAR(64);

ALTER TABLE membership_library_entries ADD COLUMN plan_code VARCHAR(64);

ALTER TABLE membership_library_entries DROP INDEX uq_membership_library_entries_book_id;

ALTER TABLE membership_library_entries ADD CONSTRAINT uq_membership_library_entries_plan_book UNIQUE (plan_code, book_id);

CREATE INDEX ix_membership_accounts_plan ON membership_accounts (plan_code);

CREATE TABLE membership_plan_versions (
    plan_code VARCHAR(64) NOT NULL, 
    version INTEGER NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    duration_days INTEGER NOT NULL, 
    daily_recommend_ticket_count INTEGER NOT NULL, 
    monthly_chapter_ticket_count INTEGER NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (plan_code, version), 
    CONSTRAINT ck_membership_plan_duration_positive CHECK (duration_days > 0), 
    CONSTRAINT ck_membership_plan_daily_nonnegative CHECK (daily_recommend_ticket_count >= 0), 
    CONSTRAINT ck_membership_plan_monthly_nonnegative CHECK (monthly_chapter_ticket_count >= 0)
);

CREATE TABLE ticket_accounts (
    account_id VARCHAR(64) NOT NULL, 
    recommend_balance BIGINT NOT NULL DEFAULT 0, 
    monthly_balance BIGINT NOT NULL DEFAULT 0, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (account_id), 
    CONSTRAINT ck_ticket_recommend_nonnegative CHECK (recommend_balance >= 0), 
    CONSTRAINT ck_ticket_monthly_nonnegative CHECK (monthly_balance >= 0)
);

CREATE TABLE ticket_lots (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    ticket_type VARCHAR(16) NOT NULL, 
    issued_quantity BIGINT NOT NULL, 
    available_quantity BIGINT NOT NULL, 
    expires_at DATETIME, 
    risk_status VARCHAR(16) NOT NULL, 
    source_ref VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ticket_lot_issued_positive CHECK (issued_quantity > 0), 
    CONSTRAINT ck_ticket_lot_available_nonnegative CHECK (available_quantity >= 0)
);

CREATE INDEX ix_ticket_lots_account_spend ON ticket_lots (account_id, ticket_type, expires_at, created_at);

CREATE TABLE ticket_transactions (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    ticket_type VARCHAR(16) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    quantity BIGINT NOT NULL, 
    lot_id VARCHAR(64), 
    source_ref VARCHAR(128), 
    idempotency_key VARCHAR(128), 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_transactions_idempotency UNIQUE (idempotency_key), 
    CONSTRAINT ck_ticket_transaction_quantity_positive CHECK (quantity > 0)
);

CREATE TABLE book_ticket_votes (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    ticket_type VARCHAR(16) NOT NULL, 
    quantity BIGINT NOT NULL, 
    risk_status VARCHAR(16) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_book_ticket_votes_idempotency UNIQUE (idempotency_key)
);

CREATE TABLE gift_definitions (
    gift_code VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    price_coin BIGINT NOT NULL, 
    fan_value BIGINT NOT NULL, 
    spend_mode VARCHAR(32) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (gift_code), 
    CONSTRAINT ck_gift_price_positive CHECK (price_coin > 0), 
    CONSTRAINT ck_gift_fan_value_positive CHECK (fan_value > 0)
);

CREATE TABLE gift_orders (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    author_id VARCHAR(64) NOT NULL, 
    gift_code VARCHAR(64) NOT NULL, 
    quantity BIGINT NOT NULL, 
    total_coin BIGINT NOT NULL, 
    income_base_coin BIGINT NOT NULL, 
    fan_value BIGINT NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_gift_orders_idempotency UNIQUE (idempotency_key)
);

CREATE TABLE book_fan_profiles (
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    value BIGINT NOT NULL, 
    level INTEGER NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (account_id, book_id)
);

CREATE TABLE fan_value_events (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    book_id VARCHAR(64) NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    value BIGINT NOT NULL, 
    source_ref VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_fan_value_event_source UNIQUE (account_id, book_id, source, source_ref)
);

CREATE TABLE fan_level_rules (
    version INTEGER NOT NULL, 
    level INTEGER NOT NULL, 
    threshold BIGINT NOT NULL, 
    PRIMARY KEY (version, level)
);

CREATE TABLE membership_user_growth_profiles (
    account_id VARCHAR(64) NOT NULL, 
    points BIGINT NOT NULL, 
    level INTEGER NOT NULL, 
    rule_version INTEGER NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (account_id)
);

CREATE TABLE membership_user_growth_events (
    id VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    points BIGINT NOT NULL, 
    source_ref VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_membership_growth_event_source UNIQUE (account_id, source_ref)
);

CREATE TABLE membership_user_growth_rules (
    version INTEGER NOT NULL, 
    level INTEGER NOT NULL, 
    threshold BIGINT NOT NULL, 
    PRIMARY KEY (version, level)
);

UPDATE alembic_version SET version_num='0024_membership_commercial' WHERE alembic_version.version_num = '0023_agent_audit_context';

-- Running upgrade 0024_membership_commercial -> 0025_membership_orders

ALTER TABLE membership_plan_versions ADD COLUMN price_cents BIGINT NOT NULL DEFAULT 0;

ALTER TABLE membership_plan_versions ALTER COLUMN price_cents DROP DEFAULT;

ALTER TABLE membership_plan_versions ADD CONSTRAINT ck_membership_plan_price_nonnegative CHECK (price_cents >= 0);

CREATE TABLE membership_orders (
    id VARCHAR(64) NOT NULL, 
    payment_order_id BIGINT NOT NULL, 
    payment_no VARCHAR(64) NOT NULL, 
    account_id VARCHAR(64) NOT NULL, 
    plan_code VARCHAR(64) NOT NULL, 
    plan_version INTEGER NOT NULL, 
    channel VARCHAR(32) NOT NULL, 
    price_cents BIGINT NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(payment_order_id) REFERENCES payment_orders (id), 
    CONSTRAINT uq_membership_orders_payment UNIQUE (payment_order_id), 
    CONSTRAINT uq_membership_orders_payment_no UNIQUE (payment_no), 
    CONSTRAINT uq_membership_orders_idempotency UNIQUE (idempotency_key), 
    CONSTRAINT ck_membership_order_price_positive CHECK (price_cents > 0)
);

CREATE INDEX ix_membership_orders_account_created ON membership_orders (account_id, created_at);

UPDATE alembic_version SET version_num='0025_membership_orders' WHERE alembic_version.version_num = '0024_membership_commercial';

-- Running upgrade 0025_membership_orders -> 0026_payout_orders

ALTER TABLE withdrawal_requests ADD COLUMN risk_status VARCHAR(24) NOT NULL DEFAULT 'PENDING';

ALTER TABLE withdrawal_requests ADD COLUMN finance_status VARCHAR(24) NOT NULL DEFAULT 'PENDING';

ALTER TABLE withdrawal_requests ADD COLUMN second_factor_verified BOOL NOT NULL DEFAULT 0;

ALTER TABLE withdrawal_requests ADD COLUMN payout_destination VARCHAR(128) NOT NULL DEFAULT '';

CREATE TABLE payout_orders (
    id VARCHAR(64) NOT NULL, 
    withdrawal_id VARCHAR(64) NOT NULL, 
    payout_no VARCHAR(64) NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    currency VARCHAR(8) NOT NULL, 
    destination VARCHAR(128) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    provider_event_id VARCHAR(128), 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(withdrawal_id) REFERENCES withdrawal_requests (id), 
    CONSTRAINT uq_payout_orders_withdrawal UNIQUE (withdrawal_id), 
    CONSTRAINT uq_payout_orders_payout_no UNIQUE (payout_no), 
    CONSTRAINT uq_payout_provider_event UNIQUE (provider, provider_event_id), 
    CONSTRAINT ck_payout_order_status CHECK (status IN ('PROCESSING', 'SUCCESS', 'FAILED', 'REJECTED', 'TIMEOUT')), 
    CONSTRAINT ck_payout_order_amount CHECK (amount_cents > 0)
);

UPDATE alembic_version SET version_num='0026_payout_orders' WHERE alembic_version.version_num = '0025_membership_orders';

-- Running upgrade 0026_payout_orders -> 0027_mfa_review_scope

ALTER TABLE staff_mfa_factors ADD COLUMN recovery_codes_hash TEXT;

CREATE TABLE staff_mfa_audits (
    id VARCHAR(64) NOT NULL, 
    staff_id VARCHAR(36) NOT NULL, 
    action VARCHAR(32) NOT NULL, 
    actor_staff_id VARCHAR(36) NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (id), 
    FOREIGN KEY(staff_id) REFERENCES staff_accounts (id), 
    FOREIGN KEY(actor_staff_id) REFERENCES staff_accounts (id), 
    CONSTRAINT ck_staff_mfa_audit_action CHECK (action IN ('ENABLED', 'DISABLED'))
);

CREATE INDEX ix_staff_mfa_audits_staff_created ON staff_mfa_audits (staff_id, created_at);

ALTER TABLE review_tasks ADD COLUMN assigned_staff_id VARCHAR(36);

ALTER TABLE review_tasks ADD CONSTRAINT fk_review_tasks_assigned_staff FOREIGN KEY(assigned_staff_id) REFERENCES staff_accounts (id);

CREATE INDEX ix_review_tasks_assigned_staff_status ON review_tasks (assigned_staff_id, status);

CREATE TABLE outbox_event_deliveries (
    event_id VARCHAR(64) NOT NULL, 
    consumer VARCHAR(128) NOT NULL, 
    delivered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    PRIMARY KEY (event_id, consumer), 
    FOREIGN KEY(event_id) REFERENCES outbox_events (id)
);

UPDATE alembic_version SET version_num='0027_mfa_review_scope' WHERE alembic_version.version_num = '0026_payout_orders';

-- Running upgrade 0027_mfa_review_scope -> 0028_author_center_idempotency

ALTER TABLE author_task_progress ADD COLUMN idempotency_key VARCHAR(128);

CREATE UNIQUE INDEX uq_author_task_progress_idempotency ON author_task_progress (idempotency_key);

UPDATE alembic_version SET version_num='0028_author_center_idempotency' WHERE alembic_version.version_num = '0027_mfa_review_scope';

-- Running upgrade 0028_author_center_idempotency -> 0029_sandbox_finance_policy

ALTER TABLE contract_versions ADD COLUMN policy_version VARCHAR(64) NOT NULL DEFAULT 'SANDBOX_CN_2026_V1';

ALTER TABLE contract_versions ADD COLUMN tax_withholding_bps INTEGER NOT NULL DEFAULT 1000;

ALTER TABLE contract_versions ADD COLUMN tax_free_threshold_cents BIGINT NOT NULL DEFAULT 100000;

ALTER TABLE contract_versions ADD CONSTRAINT ck_contract_tax_withholding_bps CHECK (tax_withholding_bps BETWEEN 0 AND 10000);

ALTER TABLE contract_versions ADD CONSTRAINT ck_contract_tax_free_threshold CHECK (tax_free_threshold_cents >= 0);

ALTER TABLE author_revenue_entries ADD COLUMN tax_cents BIGINT;

ALTER TABLE author_revenue_entries ADD COLUMN net_author_cents BIGINT;

ALTER TABLE author_revenue_entries ADD COLUMN policy_version VARCHAR(64);

UPDATE author_revenue_entries SET tax_cents = 0 WHERE tax_cents IS NULL;

UPDATE author_revenue_entries SET net_author_cents = author_cents WHERE net_author_cents IS NULL;

ALTER TABLE author_settlements ADD COLUMN gross_cents BIGINT;

ALTER TABLE author_settlements ADD COLUMN tax_cents BIGINT;

UPDATE author_settlements SET gross_cents = amount_cents WHERE gross_cents IS NULL;

UPDATE author_settlements SET tax_cents = 0 WHERE tax_cents IS NULL;

UPDATE alembic_version SET version_num='0029_sandbox_finance_policy' WHERE alembic_version.version_num = '0028_author_center_idempotency';

-- Running upgrade 0029_sandbox_finance_policy -> 0030_finance_constraints

ALTER TABLE author_revenue_entries ADD CONSTRAINT ck_author_revenue_tax_cents CHECK (tax_cents >= 0);

ALTER TABLE author_revenue_entries ADD CONSTRAINT ck_author_revenue_net_cents CHECK (net_author_cents >= 0 AND net_author_cents <= author_cents);

ALTER TABLE author_settlements ADD CONSTRAINT ck_author_settlement_gross_cents CHECK (gross_cents >= 0);

ALTER TABLE author_settlements ADD CONSTRAINT ck_author_settlement_tax_cents CHECK (tax_cents >= 0 AND tax_cents <= gross_cents);

UPDATE alembic_version SET version_num='0030_finance_constraints' WHERE alembic_version.version_num = '0029_sandbox_finance_policy';

-- Running upgrade 0030_finance_constraints -> 0031_finance_maker_checker

ALTER TABLE withdrawal_requests ADD COLUMN risk_reviewer_id VARCHAR(64);

ALTER TABLE withdrawal_requests ADD COLUMN finance_reviewer_id VARCHAR(64);

CREATE INDEX ix_withdrawal_requests_risk_reviewer ON withdrawal_requests (risk_reviewer_id);

CREATE INDEX ix_withdrawal_requests_finance_reviewer ON withdrawal_requests (finance_reviewer_id);

UPDATE alembic_version SET version_num='0031_finance_maker_checker' WHERE alembic_version.version_num = '0030_finance_constraints';

-- Running upgrade 0031_finance_maker_checker -> 0032_credit_pending_lifecycle

ALTER TABLE payment_credit_pending ADD COLUMN attempts INTEGER NOT NULL DEFAULT '0';

ALTER TABLE payment_credit_pending ADD COLUMN last_error TEXT;

ALTER TABLE payment_credit_pending ADD COLUMN last_attempted_at DATETIME;

ALTER TABLE payment_credit_pending ADD COLUMN resolved_at DATETIME;

ALTER TABLE payment_credit_pending ADD COLUMN repair_actor_id VARCHAR(64);

CREATE INDEX ix_payment_credit_pending_status ON payment_credit_pending (status, created_at);

UPDATE alembic_version SET version_num='0032_credit_pending_lifecycle' WHERE alembic_version.version_num = '0031_finance_maker_checker';

-- Running upgrade 0032_credit_pending_lifecycle -> 0033_payout_provider_transaction

ALTER TABLE payout_orders ADD COLUMN provider_transaction_id VARCHAR(128);

ALTER TABLE payout_orders ADD CONSTRAINT uq_payout_provider_transaction UNIQUE (provider, provider_transaction_id);

UPDATE alembic_version SET version_num='0033_payout_provider_transaction' WHERE alembic_version.version_num = '0032_credit_pending_lifecycle';

-- Running upgrade 0033_payout_provider_transaction -> 0034_notification_read_state

ALTER TABLE notifications ADD COLUMN read_at DATETIME;

CREATE INDEX ix_notifications_account_read ON notifications (account_id, read_at);

UPDATE alembic_version SET version_num='0034_notification_read_state' WHERE alembic_version.version_num = '0033_payout_provider_transaction';

-- Running upgrade 0034_notification_read_state -> 0035_virtual_contract_document

ALTER TABLE contract_versions ADD COLUMN document_text TEXT;

ALTER TABLE contract_versions ADD COLUMN document_hash VARCHAR(64);

UPDATE alembic_version SET version_num='0035_virtual_contract_document' WHERE alembic_version.version_num = '0034_notification_read_state';

-- Running upgrade 0035_virtual_contract_document -> 0036_contract_author_signature

ALTER TABLE contracts ADD COLUMN signed_by VARCHAR(64);

ALTER TABLE contracts ADD COLUMN signed_at DATETIME;

ALTER TABLE contracts ADD COLUMN signature_hash VARCHAR(64);

UPDATE alembic_version SET version_num='0036_contract_author_signature' WHERE alembic_version.version_num = '0035_virtual_contract_document';

-- Running upgrade 0036_contract_author_signature -> 0037_agent_request_id

ALTER TABLE agent_audit_events ADD COLUMN request_id VARCHAR(128);

UPDATE alembic_version SET version_num='0037_agent_request_id' WHERE alembic_version.version_num = '0036_contract_author_signature';

-- Running upgrade 0037_agent_request_id -> 0038_account_profile

ALTER TABLE platform_accounts ADD COLUMN account_no VARCHAR(32);

ALTER TABLE platform_accounts ADD COLUMN nickname VARCHAR(64);

ALTER TABLE platform_accounts ADD COLUMN login_name VARCHAR(32);

CREATE UNIQUE INDEX uq_platform_accounts_account_no ON platform_accounts (account_no);

CREATE UNIQUE INDEX uq_platform_accounts_login_name ON platform_accounts (login_name);

UPDATE alembic_version SET version_num='0038_account_profile' WHERE alembic_version.version_num = '0037_agent_request_id';

-- Running upgrade 0038_account_profile -> 0039_reader_preferences

CREATE TABLE reading_preferences (
    account_id VARCHAR(36) NOT NULL,
    preferences_json TEXT NOT NULL,
    PRIMARY KEY (account_id),
    FOREIGN KEY(account_id) REFERENCES platform_accounts (id)
);

UPDATE alembic_version SET version_num='0039_reader_preferences' WHERE alembic_version.version_num = '0038_account_profile';


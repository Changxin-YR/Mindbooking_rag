"""Add public account number and editable account profile fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_account_profile"
down_revision: str | None = "0037_agent_request_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable keeps this migration deployable against existing accounts. The
    # application deterministically backfills account_no on first read.
    op.add_column("platform_accounts", sa.Column("account_no", sa.String(32), nullable=True))
    op.add_column("platform_accounts", sa.Column("nickname", sa.String(64), nullable=True))
    op.add_column("platform_accounts", sa.Column("login_name", sa.String(32), nullable=True))
    op.create_index(
        "uq_platform_accounts_account_no", "platform_accounts", ["account_no"], unique=True
    )
    op.create_index(
        "uq_platform_accounts_login_name", "platform_accounts", ["login_name"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_platform_accounts_login_name", table_name="platform_accounts")
    op.drop_index("uq_platform_accounts_account_no", table_name="platform_accounts")
    op.drop_column("platform_accounts", "login_name")
    op.drop_column("platform_accounts", "nickname")
    op.drop_column("platform_accounts", "account_no")

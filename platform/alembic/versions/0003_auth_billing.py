"""Auth + billing: magic_link_tokens and billing_accounts tables.

magic_link_tokens — single-use passwordless sign-in tokens (SHA-256 hash only).
billing_accounts  — org ↔ Stripe customer/subscription linkage; the entitlement
itself lives on orgs.plan.

Follows the house pattern: every DDL is inspector-guarded so the migration is
safe both on incremental upgrades and on fresh DBs where the 0001 baseline may
already have created these tables from current model metadata. billing_accounts
is tenant-scoped (org_id) so it gets RLS on Postgres; magic_link_tokens is
keyed by user (pre-auth) and carries no org_id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_auth_billing"
down_revision = "0002_probe"
branch_labels = None
depends_on = None


def _insp(bind):
    return sa.inspect(bind)


def _has_table(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _indexes(insp, table: str) -> set[str]:
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = _insp(bind)

    if not _has_table(insp, "magic_link_tokens"):
        op.create_table(
            "magic_link_tokens",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    insp = _insp(bind)
    if "ix_magiclink_hash" not in _indexes(insp, "magic_link_tokens"):
        op.create_index("ix_magiclink_hash", "magic_link_tokens", ["token_hash"])

    insp = _insp(bind)
    if not _has_table(insp, "billing_accounts"):
        op.create_table(
            "billing_accounts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("org_id", sa.String(length=36), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
            sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("org_id", name="uq_billing_org"),
        )
    insp = _insp(bind)
    if "ix_billing_subscription" not in _indexes(insp, "billing_accounts"):
        op.create_index("ix_billing_subscription", "billing_accounts", ["stripe_subscription_id"])

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE billing_accounts ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DROP POLICY IF EXISTS billing_org_isolation ON billing_accounts; "
            "CREATE POLICY billing_org_isolation ON billing_accounts "
            "USING (org_id = current_setting('app.current_org', true))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = _insp(bind)

    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS billing_org_isolation ON billing_accounts")

    if _has_table(insp, "billing_accounts"):
        if "ix_billing_subscription" in _indexes(insp, "billing_accounts"):
            op.drop_index("ix_billing_subscription", table_name="billing_accounts")
        op.drop_table("billing_accounts")

    insp = _insp(bind)
    if _has_table(insp, "magic_link_tokens"):
        if "ix_magiclink_hash" in _indexes(insp, "magic_link_tokens"):
            op.drop_index("ix_magiclink_hash", table_name="magic_link_tokens")
        op.drop_table("magic_link_tokens")

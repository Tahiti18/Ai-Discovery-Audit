"""Cache LLM-generated buyer questions per business.

Adds two nullable columns to business_entity:
- custom_prompts (JSON): list of {text, category} dicts — the tailored buyer
  questions the classifier generated for this specific business.
- custom_prompts_version (str): the generator version that produced them, so we
  can trigger regeneration when we improve the generator.

Idempotent (inspector-guarded), matching the house pattern.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_entity_custom_prompts"
down_revision = "0003_auth_billing"
branch_labels = None
depends_on = None


def _insp(bind):
    return sa.inspect(bind)


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = _insp(bind)

    existing = _columns(insp, "business_entity")
    to_add = []
    if "custom_prompts" not in existing:
        to_add.append(sa.Column("custom_prompts", sa.JSON(), nullable=True))
    if "custom_prompts_version" not in existing:
        to_add.append(sa.Column("custom_prompts_version", sa.String(length=32), nullable=True))
    if to_add:
        with op.batch_alter_table("business_entity") as batch:
            for col in to_add:
                batch.add_column(col)


def downgrade() -> None:
    bind = op.get_bind()
    insp = _insp(bind)
    existing = _columns(insp, "business_entity")
    to_drop = [n for n in ("custom_prompts_version", "custom_prompts") if n in existing]
    if to_drop:
        with op.batch_alter_table("business_entity") as batch:
            for name in to_drop:
                batch.drop_column(name)

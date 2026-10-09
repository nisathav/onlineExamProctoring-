"""exam pause workflow

Adds the "paused" and "terminated" attempt states and the columns used when an exam is
auto-paused after repeated looking-away detections: when and why it paused, the
student's request for help, and the staff decision (continue or end).

Revision ID: c3a1f2d4e5b6
Revises: bb458f8f0230
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a1f2d4e5b6"
down_revision: Union[str, None] = "bb458f8f0230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = [
    sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("pause_reason", sa.String(length=255), nullable=False, server_default=""),
    sa.Column("last_resumed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("help_requested_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("help_message", sa.Text(), nullable=False, server_default=""),
    sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
    sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # ALTER TYPE ... ADD VALUE must run outside the migration transaction.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE attempt_status ADD VALUE IF NOT EXISTS 'paused'")
            op.execute("ALTER TYPE attempt_status ADD VALUE IF NOT EXISTS 'terminated'")
    for column in NEW_COLUMNS:
        op.add_column("exam_attempts", column)


def downgrade() -> None:
    # Postgres cannot drop enum values; map the new states back to existing ones instead.
    op.execute("UPDATE exam_attempts SET status = 'in_progress' WHERE status = 'paused'")
    op.execute("UPDATE exam_attempts SET status = 'submitted' WHERE status = 'terminated'")
    for column in reversed(NEW_COLUMNS):
        op.drop_column("exam_attempts", column.name)

"""make audit_logs append-only

Revision ID: b7c1e9d4a2f0
Revises: ac015fd27f69
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7c1e9d4a2f0"
down_revision: Union[str, Sequence[str], None] = "ac015fd27f69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enforce immutability of the audit log at the database level."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only and cannot be modified';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_modification();
        """
    )


def downgrade() -> None:
    """Remove the append-only guard."""
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_modification();")

"""add user authentication fields

Revision ID: c1a2b3d4e5f6
Revises: b7c1e9d4a2f0
Create Date: 2026-09-13 00:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b7c1e9d4a2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

userrole = postgresql.ENUM(
    "applicant", "reviewer", "admin", name="userrole"
)


def upgrade() -> None:
    """Add RBAC role and password hash to the users table."""
    userrole.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("role", userrole, nullable=True, server_default="applicant"),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    userrole.drop(op.get_bind(), checkfirst=True)

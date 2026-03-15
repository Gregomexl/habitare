"""add unique constraint users tenant_id email

Revision ID: 7da6e1ed7cf9
Revises: 90a37ffef55e
Create Date: 2026-03-15 10:44:23.546488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7da6e1ed7cf9'
down_revision: Union[str, Sequence[str], None] = '90a37ffef55e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_users_tenant_email",
        "users",
        ["tenant_id", "email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_tenant_email", table_name="users")

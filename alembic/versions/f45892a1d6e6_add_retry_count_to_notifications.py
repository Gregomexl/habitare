"""add retry_count to notifications

Revision ID: f45892a1d6e6
Revises: 7da6e1ed7cf9
Create Date: 2026-03-15 11:42:12.324135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f45892a1d6e6'
down_revision: Union[str, Sequence[str], None] = '7da6e1ed7cf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('notifications', sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'retry_count')

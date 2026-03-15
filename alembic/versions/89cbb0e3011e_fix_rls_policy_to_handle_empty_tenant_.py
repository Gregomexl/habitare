"""fix rls policy to handle empty tenant context

Revision ID: 89cbb0e3011e
Revises: d999c9183826
Create Date: 2026-01-11 12:20:52.664620

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89cbb0e3011e'
down_revision: Union[str, Sequence[str], None] = 'd999c9183826'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix RLS policy to handle empty tenant context.

    When current_setting returns an empty string (no tenant context set),
    we need to convert it to NULL using NULLIF before casting to UUID.
    This prevents "invalid input syntax for type uuid" errors.
    """
    # Drop existing policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users")

    # Recreate with NULLIF to handle empty strings
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON users
        USING (
            tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID
        )
    """)


def downgrade() -> None:
    """Revert to original RLS policy without NULLIF."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users")

    op.execute("""
        CREATE POLICY tenant_isolation_policy ON users
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)

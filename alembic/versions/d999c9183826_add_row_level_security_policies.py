"""add row level security policies

Revision ID: d999c9183826
Revises: 1c75a4f9f403
Create Date: 2026-01-11 12:06:55.695817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd999c9183826'
down_revision: Union[str, None] = '1c75a4f9f403'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Enable Row-Level Security (RLS) on users table for tenant isolation.

    RLS ensures that queries automatically filter by tenant_id using
    the app.current_tenant_id session variable set by the application.

    IMPORTANT: RLS does NOT apply to database superusers. In production,
    the application MUST use a non-superuser database role. For development,
    you can test RLS by connecting as a non-superuser (e.g., habitare_app).
    """
    # Enable Row-Level Security on users table
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")

    # Force RLS even for table owner (important for security)
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")

    # Create RLS policy: users can only see/modify their own tenant's data
    # The policy uses current_setting to get tenant_id from session variable
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON users
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID)
    """)


def downgrade() -> None:
    """Remove Row-Level Security policies."""
    # Drop the policy first
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users")

    # Disable RLS
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")

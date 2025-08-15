"""Install pg_trgm and fuzzystrmatch extensions.

Revision ID: 1a7a08e7bcd0
Revises:
Create Date: 2024-12-17 14:54:53.377859

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1a7a08e7bcd0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Install pg_trgm and fuzzystrmatch extensions."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;")


def downgrade():
    """Drop the extensions."""
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    op.execute("DROP EXTENSION IF EXISTS fuzzystrmatch;")

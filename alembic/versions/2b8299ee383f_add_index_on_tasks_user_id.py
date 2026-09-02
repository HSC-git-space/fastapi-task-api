"""Add index on tasks.user_id

Revision ID: 2b8299ee383f
Revises: 0d87386a32d3
Create Date: 2026-09-02 15:55:32.688993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b8299ee383f'
down_revision: Union[str, Sequence[str], None] = '0d87386a32d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_tasks_user_id', 'tasks', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tasks_user_id', table_name='tasks')